"""Read-only internal management API for REQ-F-12 and REQ-F-14.

Authentication is supplied by the caller; generated public documentation routes
are disabled until the API has a real authentication scheme.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import unicodedata
from collections.abc import Callable, Iterator
from contextlib import suppress
from importlib.resources import files
from pathlib import Path as FilePath
from threading import Lock
from typing import Annotated, Any, Literal, Protocol, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from starlette.staticfiles import StaticFiles

from as_config_service.activation import apply_distributed_change
from as_config_service.audit_store import PostgresAuditStore
from as_config_service.auth import (
    ConsoleBootstrapRequiredError,
    ConsoleUser,
    ConsoleUserNotFoundError,
    DuplicateConsoleUserError,
    LastEnabledConsoleAdminError,
    PostgresConsoleAuthStore,
)
from as_config_service.change_order import (
    ChangeOrder,
    ChangeState,
    IllegalTransitionError,
    ManagedRuleChange,
    ManagedRuleChangeAction,
    approve,
    begin_distribution,
    reject,
    roll_back,
    submit,
)
from as_config_service.change_order_store import (
    ChangeOrderNotFoundError,
    ChangeOrderStore,
    DuplicateChangeOrderError,
    InvalidChangeOrderTransitionError,
    PostgresChangeOrderStore,
    StaleChangeOrderRevisionError,
    StoredChangeOrder,
    serialize_order,
)
from as_config_service.distribution_store import (
    DistributionNotFoundError,
    DuplicateDistributionError,
    InvalidDistributionSnapshotError,
    PostgresDistributionStore,
    StaleDistributionRevisionError,
    StoredDistribution,
    serialize_distribution,
)
from as_config_service.distributor import (
    DistributionPlan,
    DistributionState,
    IllegalDistributionStateError,
)
from as_config_service.managed_rule import ManagedRule, MatchField, MatchMode, TargetService
from as_config_service.managed_rule_store import (
    ManagedRuleStore,
    PostgresManagedRuleStore,
    StaleManagedRuleRevisionError,
    StoredManagedRule,
    serialize_managed_rule,
)
from as_console.access import AuditOutcome, AuditRecord, Permission, Principal, Role, authorize
from as_platform.api.contract import ConfigBundle, RuleDTO, ToggleDTO

_MAX_PATH_ID_LENGTH = 256


class _ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ManagedRuleRecordResponse(_ResponseModel):
    """The serialized managed-rule fields in a versioned snapshot."""

    rule_id: str
    name: str
    match_field: Literal["calling", "called"]
    match_mode: Literal["prefix", "regex"]
    match_value: str
    target_service: Literal["translation", "anti-fraud", "routing", "block", "default"]
    enabled: bool
    target_detail: str | None


class ManagedRuleEnvelopeResponse(_ResponseModel):
    """Versioned managed-rule payload, including deletion tombstones."""

    schema_version: Literal[1]
    rule: ManagedRuleRecordResponse | None


class ManagedRuleResponse(_ResponseModel):
    """Managed-rule snapshot and its positive store revision."""

    revision: int = Field(gt=0)
    record: ManagedRuleEnvelopeResponse


class BundleRuleResponse(_ResponseModel):
    """A serialized rule inside a configuration bundle."""

    rule_id: str
    prefix: str
    action: str
    target: str | None


class ToggleResponse(_ResponseModel):
    """A serialized feature toggle inside a configuration bundle."""

    name: str
    enabled: bool
    removal_condition: str
    scope: str


class ConfigBundleResponse(_ResponseModel):
    """Configuration bundle carried by a change order."""

    version: str
    rules: list[BundleRuleResponse]
    toggles: list[ToggleResponse]


class AuditEntryResponse(_ResponseModel):
    """One serialized change-order audit entry."""

    actor: str
    action: str
    at: float


class _ManagedRuleProposalResponse(_ResponseModel):
    rule_id: str
    proposed_rule: ManagedRuleRecordResponse

    @model_validator(mode="after")
    def proposed_rule_id_matches(self) -> _ManagedRuleProposalResponse:
        if self.proposed_rule.rule_id != self.rule_id:
            raise ValueError("proposed rule id must match rule_id")
        return self


class _CreateManagedRuleChangeResponse(_ManagedRuleProposalResponse):
    action: Literal["create"]
    expected_revision: None = None


class _UpdateManagedRuleChangeResponse(_ManagedRuleProposalResponse):
    action: Literal["update"]
    expected_revision: int = Field(gt=0, strict=True)


class _DeleteManagedRuleChangeResponse(_ResponseModel):
    action: Literal["delete"]
    rule_id: str
    proposed_rule: None = None
    expected_revision: int = Field(gt=0, strict=True)


ManagedRuleChangeResponse = Annotated[
    _CreateManagedRuleChangeResponse
    | _UpdateManagedRuleChangeResponse
    | _DeleteManagedRuleChangeResponse,
    Field(discriminator="action"),
]


class ChangeOrderRecordResponse(_ResponseModel):
    """The serialized order, bundle, and audit trail."""

    change_id: str
    state: Literal[
        "draft",
        "submitted",
        "approved",
        "distributing",
        "applied",
        "rejected",
        "rolled_back",
    ]
    bundle: ConfigBundleResponse
    created_by: str
    created_at: float
    approver: str | None
    approved_at: float | None
    audit: list[AuditEntryResponse]
    managed_rule_change: ManagedRuleChangeResponse | None


class ChangeOrderEnvelopeResponse(_ResponseModel):
    """Versioned change-order payload."""

    schema_version: Literal[2]
    order: ChangeOrderRecordResponse


class ChangeOrderResponse(_ResponseModel):
    """Change-order snapshot and its positive store revision."""

    revision: int = Field(gt=0)
    record: ChangeOrderEnvelopeResponse


class CreateChangeOrderRequest(_ResponseModel):
    """Strict draft payload; identity, id, and creation time are server-owned."""

    bundle: ConfigBundleResponse
    managed_rule_change: ManagedRuleChangeResponse | None = None


class RejectChangeOrderRequest(_ResponseModel):
    """Reason recorded in the rejection audit entry."""

    reason: str


class StartDistributionRequest(_ResponseModel):
    """Strict distribution plan and change-order compare-and-swap revision."""

    version: int = Field(gt=0, strict=True)
    batches: list[list[str]] = Field(min_length=1)
    expected_change_order_revision: int = Field(gt=0, strict=True)


class ReportDistributionBatchRequest(_ResponseModel):
    """Observed health reports for exactly the current batch."""

    expected_distribution_revision: int = Field(gt=0, strict=True)
    reports: dict[str, bool]


class ApplyDistributionRequest(_ResponseModel):
    """Change-order compare-and-swap revision for a completed distribution."""

    expected_change_order_revision: int = Field(gt=0, strict=True)


class RollbackDistributionRequest(_ResponseModel):
    """Operator rollback reason and both journal revisions."""

    expected_distribution_revision: int = Field(gt=0, strict=True)
    expected_change_order_revision: int = Field(gt=0, strict=True)
    reason: str


class LoginRequest(_ResponseModel):
    """Strict login credentials with a redacted password field."""

    user_id: str = Field(min_length=1, max_length=128, strict=True)
    password: SecretStr


_RoleName = Literal["viewer", "operator", "approver", "admin"]


class CreateConsoleUserRequest(_ResponseModel):
    """Account fields accepted when an administrator creates a user."""

    user_id: str = Field(min_length=1, max_length=128, strict=True)
    password: SecretStr
    roles: list[_RoleName]
    enabled: bool = True


class UpdateConsoleUserRequest(_ResponseModel):
    """Optional account fields accepted for an administrator update."""

    roles: list[_RoleName] | None = None
    password: SecretStr | None = None
    enabled: bool | None = None


class ConsoleUserResponse(_ResponseModel):
    """Public account view; password verifier material is never represented."""

    user_id: str
    roles: list[_RoleName]
    enabled: bool
    created_at: float
    updated_at: float


class DistributionPlanResponse(_ResponseModel):
    """Observed distribution plan and its batch boundaries."""

    change_id: str
    version: int
    batches: list[list[str]]


class InstanceReportResponse(_ResponseModel):
    """One API-received instance health report."""

    instance_id: str
    healthy: bool


class DistributionRecordResponse(_ResponseModel):
    """Latest immutable distribution snapshot and its journal metadata."""

    revision: int = Field(gt=0)
    actor: str
    action: Literal["begin", "batch_result", "roll_back"]
    plan: DistributionPlanResponse
    state: Literal["pending", "in_progress", "completed", "rolled_back"]
    completed_batches: int
    reports: list[InstanceReportResponse]
    rolled_back_to: int | None
    rollback_reason: str | None
    updated_at: float | None


class DistributionWorkflowResponse(_ResponseModel):
    """Distribution result and an optional corresponding change-order snapshot."""

    distribution: DistributionRecordResponse
    change_order: ChangeOrderResponse | None = None


class ApiIdentity(Protocol):
    """Minimal identity surface required by the injected authorization seam."""

    @property
    def user_id(self) -> str:
        """Stable identifier for the acting user."""
        ...


IdentityResolver = Callable[[Request], ApiIdentity | None]
ConfigReadAuthorizer = Callable[[ApiIdentity], bool]
ChangeAuthorizer = Callable[[ApiIdentity], bool]
UserManagementAuthorizer = Callable[[ApiIdentity], bool]
Clock = Callable[[], float]
ChangeIdFactory = Callable[[], str]


def _resource_digest(key: bytes, value: object) -> str:
    return hmac.new(key, str(value).encode("utf-8"), hashlib.sha256).hexdigest()


def create_app(
    managed_rule_store: ManagedRuleStore,
    change_order_store: ChangeOrderStore,
    resolve_identity: IdentityResolver | None,
    can_read_config: ConfigReadAuthorizer,
    can_submit_change: ChangeAuthorizer | None = None,
    can_approve_change: ChangeAuthorizer | None = None,
    now: Clock = time.time,
    new_change_id: ChangeIdFactory = lambda: str(uuid4()),
    distribution_store: PostgresDistributionStore | None = None,
    can_manage_users: UserManagementAuthorizer | None = None,
    auth_store: PostgresConsoleAuthStore | None = None,
    audit_store: PostgresAuditStore | None = None,
    *,
    allow_unaudited_callback_mode: bool = False,
    audit_resource_hmac_key: bytes | None = None,
) -> FastAPI:
    """Build the API around injected stores, identity, and authorization callbacks.

    One app serializes access to its injected PostgreSQL connections; those connections
    must be dedicated to this app and not shared externally.
    """
    if auth_store is None and resolve_identity is None:
        raise ValueError("resolve_identity is required when session authentication is disabled")
    if allow_unaudited_callback_mode and auth_store is not None:
        raise ValueError("allow_unaudited_callback_mode requires callback authentication")
    if audit_store is None and not allow_unaudited_callback_mode:
        raise ValueError(
            "audit_store is required unless unaudited callback mode is explicitly enabled"
        )
    if audit_store is not None and (
        not isinstance(audit_resource_hmac_key, bytes) or len(audit_resource_hmac_key) != 32
    ):
        raise ValueError("audit_resource_hmac_key must be exactly 32 bytes when audit_store is set")
    api_request_lock = Lock()
    connections_by_id: dict[int, Any] = {}
    request_stores = (managed_rule_store, change_order_store, distribution_store, auth_store)
    for store in (*request_stores, audit_store):
        connection = getattr(store, "connection", None)
        if connection is not None:
            connections_by_id.setdefault(id(connection), connection)
    api_connections = tuple(connections_by_id.values())
    if audit_store is not None:
        postgres_stores = (
            store
            for store in (*request_stores, audit_store)
            if isinstance(
                store,
                (
                    PostgresChangeOrderStore,
                    PostgresManagedRuleStore,
                    PostgresDistributionStore,
                    PostgresConsoleAuthStore,
                    PostgresAuditStore,
                ),
            )
        )
        postgres_connections = tuple(store.connection for store in postgres_stores)
        if postgres_connections and any(
            connection is not postgres_connections[0] for connection in postgres_connections[1:]
        ):
            raise ValueError("all PostgreSQL API stores must share one connection")
    if isinstance(audit_store, PostgresAuditStore):
        audit_store.validate_runtime_connection()
    audit_connection = None if audit_store is None else getattr(audit_store, "connection", None)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def replace_audit_failure_response(request: Request, call_next: Any) -> Response:
        try:
            response = await call_next(request)
        except BaseException:
            if not getattr(request.state, "audit_response_failure", False):
                raise
            return JSONResponse(status_code=500, content={"detail": "audit service unavailable"})
        if getattr(request.state, "audit_response_failure", False):
            return JSONResponse(status_code=500, content={"detail": "audit service unavailable"})
        return cast(Response, response)

    def rollback_api_connections() -> None:
        for connection in api_connections:
            connection.rollback()

    def append_request_audit(request: Request, outcome: AuditOutcome) -> None:
        assert audit_store is not None
        audit_store.append(
            AuditRecord(
                actor=request.state.audit_actor,
                action=request.state.audit_action,
                resource=request.state.audit_resource,
                outcome=outcome,
                at=now(),
                before_value=request.state.audit_before,
                after_value=request.state.audit_after,
            ),
            commit=False,
        )

    def serialize_api_request(request: Request) -> Iterator[None]:
        from psycopg.pq import TransactionStatus

        api_request_lock.acquire()
        request_started = False
        try:
            if any(
                connection.info.transaction_status is not TransactionStatus.IDLE
                for connection in api_connections
            ):
                raise HTTPException(status_code=409, detail="database connection is not idle")
            request_started = True
            request.state.audit_actor = "anonymous"
            route = request.scope.get("route")
            route_template = getattr(route, "path", "<unmatched>")
            request.state.audit_action = f"{request.method.upper()} {route_template}"
            path_params = request.scope.get("path_params", {})
            if audit_resource_hmac_key is None:
                parameter_digests = ""
            else:
                resource_key = audit_resource_hmac_key
                parameter_digests = " ".join(
                    f"{name}#{_resource_digest(resource_key, path_params[name])}"
                    for name in sorted(path_params)
                )
            request.state.audit_resource = (
                f"{route_template} {parameter_digests}" if parameter_digests else route_template
            )
            request.state.audit_before = None
            request.state.audit_after = None
            request.state.audit_failed = False
            try:
                yield
            except BaseException:
                if audit_store is None:
                    raise
                try:
                    rollback_api_connections()
                    request.state.audit_before = None
                    request.state.audit_after = None
                    if request.state.audit_failed:
                        request.state.audit_response_failure = True
                        return
                    append_request_audit(request, AuditOutcome.DENIED)
                    if audit_connection is not None:
                        audit_connection.commit()
                except BaseException:
                    with suppress(BaseException):
                        rollback_api_connections()
                    request.state.audit_response_failure = True
                    return
                raise
            else:
                if audit_store is not None:
                    try:
                        append_request_audit(request, AuditOutcome.ALLOWED)
                        if audit_connection is not None:
                            audit_connection.commit()
                    except BaseException:
                        with suppress(BaseException):
                            rollback_api_connections()
                        request.state.audit_response_failure = True
        finally:
            try:
                if request_started:
                    for connection in api_connections:
                        if connection.info.transaction_status is not TransactionStatus.IDLE:
                            connection.rollback()
            finally:
                api_request_lock.release()

    def require_identity(request: Request) -> ApiIdentity:
        identity: ApiIdentity | None
        if auth_store is not None:
            token = request.cookies.get("__Host-as_console_session")
            if token is None:
                raise HTTPException(status_code=401, detail="authentication required")
            try:
                identity = auth_store.resolve_session(token, now())
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail="authentication service unavailable"
                ) from exc
        else:
            assert resolve_identity is not None
            identity = resolve_identity(request)
        if identity is None:
            raise HTTPException(status_code=401, detail="authentication required")
        request.state.audit_actor = identity.user_id
        return identity

    def set_audit_context(
        request: Request,
        *,
        action: str | None = None,
        resource: str | None = None,
        before_value: object | None = None,
        after_value: object | None = None,
    ) -> None:
        request.state.audit_action = action or request.state.audit_action
        request.state.audit_resource = resource or request.state.audit_resource
        request.state.audit_before = before_value
        request.state.audit_after = after_value

    identity_dependency: Any = Depends(require_identity)

    def require_config_read(identity: ApiIdentity = identity_dependency) -> None:
        if not permission_allowed(identity, Permission.READ_CONFIG, can_read_config):
            raise HTTPException(status_code=403, detail="config read access denied")

    def permission_allowed(
        identity: ApiIdentity,
        permission: Permission,
        legacy_authorizer: ChangeAuthorizer,
    ) -> bool:
        if auth_store is not None:
            return authorize(cast(Principal, identity), permission)
        return legacy_authorizer(identity)

    def require_csrf(request: Request) -> None:
        if auth_store is None:
            return
        session_token = request.cookies.get("__Host-as_console_session")
        csrf_cookie = request.cookies.get("__Host-as_console_csrf")
        csrf_header = request.headers.get("X-CSRF-Token")
        if session_token is None or csrf_cookie is None or csrf_header is None:
            raise HTTPException(status_code=403, detail="CSRF validation failed")
        try:
            valid = auth_store.verify_csrf(session_token, csrf_cookie, csrf_header, now())
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail="authentication service unavailable"
            ) from exc
        if not valid:
            raise HTTPException(status_code=403, detail="CSRF validation failed")

    csrf_dependency: Any = Depends(require_csrf)

    router = APIRouter(
        prefix="/internal/v1",
        dependencies=[
            Depends(serialize_api_request, scope="function"),
            identity_dependency,
            Depends(require_config_read),
        ],
    )
    write_router = APIRouter(
        prefix="/internal/v1",
        dependencies=[
            Depends(serialize_api_request, scope="function"),
            identity_dependency,
            csrf_dependency,
        ],
    )
    session_router = APIRouter(
        prefix="/internal/v1",
        dependencies=[Depends(serialize_api_request, scope="function"), identity_dependency],
    )
    login_router = APIRouter(
        prefix="/internal/v1",
        dependencies=[Depends(serialize_api_request, scope="function")],
    )
    unmatched_read_router = APIRouter(
        prefix="/internal/v1",
        dependencies=[
            Depends(serialize_api_request, scope="function"),
            identity_dependency,
            Depends(require_config_read),
        ],
    )
    unmatched_write_router = APIRouter(
        prefix="/internal/v1",
        dependencies=[
            Depends(serialize_api_request, scope="function"),
            identity_dependency,
            csrf_dependency,
        ],
    )

    def require_submit_permission(identity: ApiIdentity) -> None:
        if auth_store is not None:
            allowed = permission_allowed(identity, Permission.SUBMIT_CHANGE, lambda _: False)
        else:
            allowed = can_submit_change is not None and can_submit_change(identity)
        if not allowed:
            raise HTTPException(status_code=403, detail="change submission denied")

    def require_approve_permission(identity: ApiIdentity) -> None:
        if auth_store is not None:
            allowed = permission_allowed(identity, Permission.APPROVE_CHANGE, lambda _: False)
        else:
            allowed = can_approve_change is not None and can_approve_change(identity)
        if not allowed:
            raise HTTPException(status_code=403, detail="change approval denied")

    def require_rollback_permission(identity: ApiIdentity) -> None:
        if auth_store is not None:
            allowed = permission_allowed(identity, Permission.ROLLBACK_CHANGE, lambda _: False)
        else:
            allowed = can_approve_change is not None and can_approve_change(identity)
        if not allowed:
            raise HTTPException(status_code=403, detail="change rollback denied")

    def require_manage_users(identity: ApiIdentity) -> None:
        if auth_store is not None:
            allowed = permission_allowed(identity, Permission.MANAGE_USERS, lambda _: False)
        else:
            allowed = can_manage_users is not None and can_manage_users(identity)
        if not allowed:
            raise HTTPException(status_code=403, detail="user management denied")

    def require_auth_store() -> PostgresConsoleAuthStore:
        if auth_store is None:
            raise HTTPException(status_code=503, detail="console account service unavailable")
        return auth_store

    def console_user_response(user: ConsoleUser) -> dict[str, object]:
        return {
            "user_id": user.user_id,
            "roles": sorted(role.value for role in user.roles),
            "enabled": user.enabled,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    def require_distribution_store() -> PostgresDistributionStore:
        if distribution_store is None:
            raise HTTPException(status_code=503, detail="distribution API unavailable")
        if not isinstance(change_order_store, PostgresChangeOrderStore) or not isinstance(
            managed_rule_store, PostgresManagedRuleStore
        ):
            raise HTTPException(status_code=503, detail="distribution API unavailable")
        if (
            distribution_store.connection is not change_order_store.connection
            or distribution_store.connection is not managed_rule_store.connection
        ):
            raise HTTPException(status_code=503, detail="distribution storage unavailable")
        return distribution_store

    def require_activation_stores() -> tuple[PostgresChangeOrderStore, PostgresManagedRuleStore]:
        if not isinstance(change_order_store, PostgresChangeOrderStore) or not isinstance(
            managed_rule_store, PostgresManagedRuleStore
        ):
            raise HTTPException(status_code=503, detail="distribution API unavailable")
        return change_order_store, managed_rule_store

    def require_idle_distribution_connection(store: PostgresDistributionStore) -> None:
        from psycopg.pq import TransactionStatus

        if store.connection.info.transaction_status is not TransactionStatus.IDLE:
            raise HTTPException(status_code=409, detail="distribution connection is not idle")

    def distribution_response(stored: StoredDistribution) -> dict[str, object]:
        distribution = stored.distribution
        return {
            "revision": stored.revision,
            "actor": stored.actor,
            "action": stored.action,
            "plan": {
                "change_id": distribution.plan.change_id,
                "version": distribution.plan.version,
                "batches": [list(batch) for batch in distribution.plan.batches],
            },
            "state": distribution.state.value,
            "completed_batches": distribution.completed_batches,
            "reports": [
                {
                    "instance_id": report.instance_id,
                    "healthy": report.healthy,
                }
                for report in distribution.reports
            ],
            "rolled_back_to": distribution.rolled_back_to,
            "rollback_reason": distribution.rollback_reason,
            "updated_at": distribution.updated_at,
        }

    def get_distribution(store: PostgresDistributionStore, change_id: str) -> StoredDistribution:
        try:
            stored = store.get(change_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="distribution storage error") from exc
        if stored is None:
            raise HTTPException(status_code=404, detail="distribution not found")
        return stored

    def workflow_response(
        distribution: StoredDistribution, order: StoredChangeOrder | None = None
    ) -> dict[str, object]:
        response: dict[str, object] = {"distribution": distribution_response(distribution)}
        if order is not None:
            response["change_order"] = _change_order_response(order)
        return response

    def workflow_snapshot(
        distribution: StoredDistribution | None,
        order: StoredChangeOrder | None = None,
        managed_rule: StoredManagedRule | None = None,
    ) -> dict[str, object]:
        return {
            "distribution": (
                None if distribution is None else json.loads(serialize_distribution(distribution))
            ),
            "change_order": None if order is None else _change_order_response(order),
            "managed_rule": None if managed_rule is None else _managed_rule_response(managed_rule),
        }

    def get_order(change_id: str) -> StoredChangeOrder:
        try:
            stored = change_order_store.get(change_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="change order storage error") from exc
        if stored is None:
            raise HTTPException(status_code=404, detail="change order not found")
        return stored

    def append_order(order: ChangeOrder, expected_revision: int) -> StoredChangeOrder:
        try:
            if audit_store is None:
                return change_order_store.append_transition(order, expected_revision)
            return change_order_store.append_transition(order, expected_revision, commit=False)
        except ChangeOrderNotFoundError as exc:
            raise HTTPException(status_code=404, detail="change order not found") from exc
        except (
            IllegalTransitionError,
            InvalidChangeOrderTransitionError,
            StaleChangeOrderRevisionError,
        ) as exc:
            raise HTTPException(status_code=409, detail="change order transition conflict") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="change order storage error") from exc

    @router.get("/managed-rules", response_model=list[ManagedRuleResponse])
    def list_managed_rules() -> list[dict[str, object]]:
        return [_managed_rule_response(item) for item in managed_rule_store.list_latest()]

    @router.get("/managed-rules/{rule_id}", response_model=ManagedRuleResponse)
    def get_managed_rule(
        rule_id: Annotated[str, Path(min_length=1, max_length=_MAX_PATH_ID_LENGTH)],
    ) -> dict[str, object]:
        validated_id = _validate_path_id(rule_id)
        stored = managed_rule_store.get(validated_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="managed rule not found")
        return _managed_rule_response(stored)

    @router.get("/change-orders", response_model=list[ChangeOrderResponse])
    def list_change_orders() -> list[dict[str, object]]:
        return [_change_order_response(item) for item in change_order_store.list_latest()]

    @router.get("/change-orders/{change_id}", response_model=ChangeOrderResponse)
    def get_change_order(
        change_id: Annotated[str, Path(min_length=1, max_length=_MAX_PATH_ID_LENGTH)],
    ) -> dict[str, object]:
        validated_id = _validate_path_id(change_id)
        stored = change_order_store.get(validated_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="change order not found")
        return _change_order_response(stored)

    @write_router.post(
        "/change-orders",
        response_model=ChangeOrderResponse,
        status_code=201,
    )
    def create_change_order(
        body: CreateChangeOrderRequest,
        request: Request,
        identity: ApiIdentity = identity_dependency,
    ) -> dict[str, object]:
        require_submit_permission(identity)
        change_id = _validate_path_id(new_change_id())
        try:
            order = ChangeOrder(
                change_id=change_id,
                state=ChangeState.DRAFT,
                bundle=_config_bundle(body.bundle),
                created_by=identity.user_id,
                created_at=now(),
                managed_rule_change=_managed_rule_change(body.managed_rule_change),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="invalid change order request") from exc
        try:
            if audit_store is None:
                stored = change_order_store.create(order)
            else:
                stored = change_order_store.create(order, commit=False)
        except DuplicateChangeOrderError as exc:
            raise HTTPException(status_code=409, detail="change order already exists") from exc
        except InvalidChangeOrderTransitionError as exc:
            raise HTTPException(status_code=409, detail="change order transition conflict") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="change order storage error") from exc
        response = _change_order_response(stored)
        set_audit_context(request, after_value=response)
        return response

    @write_router.post(
        "/change-orders/{change_id}/submit",
        response_model=ChangeOrderResponse,
    )
    def submit_change_order(
        change_id: Annotated[str, Path(min_length=1, max_length=_MAX_PATH_ID_LENGTH)],
        request: Request,
        identity: ApiIdentity = identity_dependency,
    ) -> dict[str, object]:
        require_submit_permission(identity)
        stored = get_order(_validate_path_id(change_id))
        if stored.order.created_by != identity.user_id:
            raise HTTPException(status_code=403, detail="only the creator may submit this change")
        try:
            transitioned = submit(stored.order, identity.user_id, now())
        except IllegalTransitionError as exc:
            raise HTTPException(status_code=409, detail="change order transition conflict") from exc
        updated = append_order(transitioned, stored.revision)
        response = _change_order_response(updated)
        set_audit_context(
            request,
            before_value=_change_order_response(stored),
            after_value=response,
        )
        return response

    @write_router.post(
        "/change-orders/{change_id}/distribution",
        response_model=DistributionWorkflowResponse,
        status_code=201,
    )
    def start_distribution(
        change_id: Annotated[str, Path(min_length=1, max_length=_MAX_PATH_ID_LENGTH)],
        body: StartDistributionRequest,
        request: Request,
        identity: ApiIdentity = identity_dependency,
    ) -> dict[str, object]:
        require_approve_permission(identity)
        store = require_distribution_store()
        require_idle_distribution_connection(store)
        validated_id = _validate_path_id(change_id)
        connection = store.connection
        try:
            stored_order = change_order_store.get(validated_id)
            if stored_order is None:
                raise HTTPException(status_code=404, detail="change order not found")
            if stored_order.revision != body.expected_change_order_revision:
                raise HTTPException(status_code=409, detail="change order revision conflict")
            if stored_order.order.state is not ChangeState.APPROVED:
                raise HTTPException(status_code=409, detail="change order is not approved")
            plan = DistributionPlan(
                change_id=validated_id,
                version=body.version,
                batches=tuple(tuple(batch) for batch in body.batches),
            )
            started = store.create(plan, identity.user_id, now(), commit=False)
            distributing = begin_distribution(stored_order.order, identity.user_id, now())
            updated_order = change_order_store.append_transition(
                distributing, stored_order.revision, commit=False
            )
            if audit_store is None:
                connection.commit()
            set_audit_context(
                request,
                before_value=workflow_snapshot(None, stored_order),
                after_value=workflow_snapshot(started, updated_order),
            )
            return workflow_response(started, updated_order)
        except HTTPException:
            connection.rollback()
            raise
        except (
            IllegalTransitionError,
            InvalidChangeOrderTransitionError,
            StaleChangeOrderRevisionError,
            DuplicateDistributionError,
        ) as exc:
            connection.rollback()
            raise HTTPException(status_code=409, detail="distribution transition conflict") from exc
        except (TypeError, ValueError, InvalidDistributionSnapshotError) as exc:
            connection.rollback()
            raise HTTPException(status_code=422, detail="invalid distribution request") from exc
        except Exception as exc:
            connection.rollback()
            raise HTTPException(status_code=500, detail="distribution storage error") from exc

    @router.get(
        "/change-orders/{change_id}/distribution",
        response_model=DistributionRecordResponse,
    )
    def read_distribution(
        change_id: Annotated[str, Path(min_length=1, max_length=_MAX_PATH_ID_LENGTH)],
    ) -> dict[str, object]:
        store = require_distribution_store()
        try:
            stored = get_distribution(store, _validate_path_id(change_id))
        except HTTPException:
            store.connection.rollback()
            raise
        try:
            store.connection.rollback()
        except Exception as exc:
            raise HTTPException(status_code=500, detail="distribution storage error") from exc
        return distribution_response(stored)

    @write_router.post(
        "/change-orders/{change_id}/distribution/reports",
        response_model=DistributionWorkflowResponse,
    )
    def report_distribution_batch(
        change_id: Annotated[str, Path(min_length=1, max_length=_MAX_PATH_ID_LENGTH)],
        body: ReportDistributionBatchRequest,
        request: Request,
        identity: ApiIdentity = identity_dependency,
    ) -> dict[str, object]:
        require_approve_permission(identity)
        store = require_distribution_store()
        activation_orders, activation_rules = require_activation_stores()
        require_idle_distribution_connection(store)
        validated_id = _validate_path_id(change_id)
        connection = store.connection
        try:
            previous_distribution = get_distribution(store, validated_id)
            previous_order = change_order_store.get(validated_id)
            if previous_order is None:
                raise HTTPException(status_code=404, detail="change order not found")
            updated_distribution = store.record_batch(
                validated_id,
                body.reports,
                identity.user_id,
                now(),
                body.expected_distribution_revision,
                commit=False,
            )
            if updated_distribution.distribution.state is DistributionState.ROLLED_BACK:
                stored_order = change_order_store.get(validated_id)
                if stored_order is None:
                    raise HTTPException(status_code=404, detail="change order not found")
                if stored_order.order.state is not ChangeState.DISTRIBUTING:
                    raise HTTPException(status_code=409, detail="change order is not distributing")
                rolled_back = roll_back(
                    stored_order.order,
                    identity.user_id,
                    updated_distribution.distribution.rollback_reason or "health check failed",
                    now(),
                )
                updated_order = change_order_store.append_transition(
                    rolled_back, stored_order.revision, commit=False
                )
                if audit_store is None:
                    connection.commit()
                set_audit_context(
                    request,
                    before_value=workflow_snapshot(previous_distribution, previous_order),
                    after_value=workflow_snapshot(updated_distribution, updated_order),
                )
                return workflow_response(updated_distribution, updated_order)

            if updated_distribution.distribution.state is not DistributionState.COMPLETED:
                if audit_store is None:
                    connection.commit()
                set_audit_context(
                    request,
                    before_value=workflow_snapshot(previous_distribution, previous_order),
                    after_value=workflow_snapshot(updated_distribution),
                )
                return workflow_response(updated_distribution)

            confirmed_distribution = get_distribution(store, validated_id)
            if confirmed_distribution.distribution.state is not DistributionState.COMPLETED:
                raise HTTPException(status_code=409, detail="distribution is not completed")
            stored_order = change_order_store.get(validated_id)
            if stored_order is None:
                raise HTTPException(status_code=404, detail="change order not found")
            if stored_order.order.state is not ChangeState.DISTRIBUTING:
                raise HTTPException(status_code=409, detail="change order is not distributing")
            rule_change = stored_order.order.managed_rule_change
            managed_rule_before = (
                None if rule_change is None else activation_rules.get(rule_change.rule_id)
            )
            if audit_store is not None:
                set_audit_context(
                    request,
                    before_value=workflow_snapshot(
                        previous_distribution, previous_order, managed_rule_before
                    ),
                    after_value=workflow_snapshot(
                        confirmed_distribution, stored_order, managed_rule_before
                    ),
                )
                try:
                    append_request_audit(request, AuditOutcome.ALLOWED)
                    connection.commit()
                except BaseException:
                    request.state.audit_failed = True
                    connection.rollback()
                    raise HTTPException(
                        status_code=500, detail="audit service unavailable"
                    ) from None
                set_audit_context(
                    request,
                    before_value=workflow_snapshot(confirmed_distribution, stored_order),
                )
            else:
                connection.commit()
            connection.rollback()
            set_audit_context(request)
            applied_order = apply_distributed_change(
                activation_orders,
                activation_rules,
                validated_id,
                stored_order.revision,
                identity.user_id,
                now(),
                commit=audit_store is None,
            )
            managed_rule_after = (
                None if rule_change is None else activation_rules.get(rule_change.rule_id)
            )
            set_audit_context(
                request,
                before_value=workflow_snapshot(
                    confirmed_distribution, stored_order, managed_rule_before
                ),
                after_value=workflow_snapshot(
                    confirmed_distribution, applied_order, managed_rule_after
                ),
            )
            return workflow_response(confirmed_distribution, applied_order)
        except HTTPException:
            connection.rollback()
            raise
        except StaleDistributionRevisionError as exc:
            connection.rollback()
            raise HTTPException(status_code=409, detail="distribution revision conflict") from exc
        except DistributionNotFoundError as exc:
            connection.rollback()
            raise HTTPException(status_code=404, detail="distribution not found") from exc
        except (
            IllegalDistributionStateError,
            IllegalTransitionError,
            StaleChangeOrderRevisionError,
        ) as exc:
            connection.rollback()
            raise HTTPException(status_code=409, detail="distribution transition conflict") from exc
        except (InvalidChangeOrderTransitionError, StaleManagedRuleRevisionError) as exc:
            connection.rollback()
            raise HTTPException(status_code=409, detail="activation conflict") from exc
        except InvalidDistributionSnapshotError as exc:
            connection.rollback()
            raise HTTPException(status_code=422, detail="invalid distribution report") from exc
        except Exception as exc:
            connection.rollback()
            raise HTTPException(status_code=500, detail="distribution storage error") from exc

    @write_router.post(
        "/change-orders/{change_id}/distribution/apply",
        response_model=DistributionWorkflowResponse,
    )
    def apply_completed_distribution(
        change_id: Annotated[str, Path(min_length=1, max_length=_MAX_PATH_ID_LENGTH)],
        body: ApplyDistributionRequest,
        request: Request,
        identity: ApiIdentity = identity_dependency,
    ) -> dict[str, object]:
        require_approve_permission(identity)
        store = require_distribution_store()
        activation_orders, activation_rules = require_activation_stores()
        require_idle_distribution_connection(store)
        validated_id = _validate_path_id(change_id)
        try:
            distribution = get_distribution(store, validated_id)
            if distribution.distribution.state is not DistributionState.COMPLETED:
                raise HTTPException(status_code=409, detail="distribution is not completed")
            stored_order = change_order_store.get(validated_id)
            if stored_order is None:
                raise HTTPException(status_code=404, detail="change order not found")
            if stored_order.order.state is ChangeState.APPLIED:
                audit = stored_order.order.audit
                if (
                    stored_order.revision == body.expected_change_order_revision + 1
                    and audit
                    and audit[-1].action == "mark_applied"
                    and audit[-1].actor == identity.user_id
                ):
                    store.connection.rollback()
                    rule_change = stored_order.order.managed_rule_change
                    managed_rule = (
                        None if rule_change is None else activation_rules.get(rule_change.rule_id)
                    )
                    set_audit_context(
                        request,
                        before_value=workflow_snapshot(distribution, stored_order, managed_rule),
                        after_value=workflow_snapshot(distribution, stored_order, managed_rule),
                    )
                    return workflow_response(distribution, stored_order)
                raise HTTPException(status_code=409, detail="change order revision conflict")
            if stored_order.revision != body.expected_change_order_revision:
                raise HTTPException(status_code=409, detail="change order revision conflict")
            if stored_order.order.state is not ChangeState.DISTRIBUTING:
                raise HTTPException(status_code=409, detail="change order is not distributing")
            rule_change = stored_order.order.managed_rule_change
            managed_rule_before = (
                None if rule_change is None else activation_rules.get(rule_change.rule_id)
            )
            store.connection.rollback()
            applied_order = apply_distributed_change(
                activation_orders,
                activation_rules,
                validated_id,
                body.expected_change_order_revision,
                identity.user_id,
                now(),
                commit=audit_store is None,
            )
            managed_rule_after = (
                None if rule_change is None else activation_rules.get(rule_change.rule_id)
            )
            set_audit_context(
                request,
                before_value=workflow_snapshot(distribution, stored_order, managed_rule_before),
                after_value=workflow_snapshot(distribution, applied_order, managed_rule_after),
            )
            return workflow_response(distribution, applied_order)
        except HTTPException:
            store.connection.rollback()
            raise
        except (
            IllegalTransitionError,
            InvalidChangeOrderTransitionError,
            StaleChangeOrderRevisionError,
            StaleManagedRuleRevisionError,
        ) as exc:
            store.connection.rollback()
            raise HTTPException(status_code=409, detail="change order transition conflict") from exc
        except Exception as exc:
            store.connection.rollback()
            raise HTTPException(status_code=500, detail="distribution storage error") from exc

    @write_router.post(
        "/change-orders/{change_id}/distribution/rollback",
        response_model=DistributionWorkflowResponse,
    )
    def rollback_distribution(
        change_id: Annotated[str, Path(min_length=1, max_length=_MAX_PATH_ID_LENGTH)],
        body: RollbackDistributionRequest,
        request: Request,
        identity: ApiIdentity = identity_dependency,
    ) -> dict[str, object]:
        require_rollback_permission(identity)
        store = require_distribution_store()
        require_idle_distribution_connection(store)
        validated_id = _validate_path_id(change_id)
        if not body.reason.strip():
            raise HTTPException(status_code=422, detail="rollback reason must not be blank")
        connection = store.connection
        try:
            previous_distribution = get_distribution(store, validated_id)
            previous_order = change_order_store.get(validated_id)
            if previous_order is None:
                raise HTTPException(status_code=404, detail="change order not found")
            rolled_back_distribution = store.roll_back(
                validated_id,
                body.reason.strip(),
                identity.user_id,
                now(),
                body.expected_distribution_revision,
                commit=False,
            )
            stored_order = change_order_store.get(validated_id)
            if stored_order is None:
                raise HTTPException(status_code=404, detail="change order not found")
            if stored_order.revision != body.expected_change_order_revision:
                raise HTTPException(status_code=409, detail="change order revision conflict")
            if stored_order.order.state is not ChangeState.DISTRIBUTING:
                raise HTTPException(status_code=409, detail="change order is not distributing")
            rolled_back_order = roll_back(
                stored_order.order, identity.user_id, body.reason.strip(), now()
            )
            updated_order = change_order_store.append_transition(
                rolled_back_order, stored_order.revision, commit=False
            )
            if audit_store is None:
                connection.commit()
            set_audit_context(
                request,
                before_value=workflow_snapshot(previous_distribution, previous_order),
                after_value=workflow_snapshot(rolled_back_distribution, updated_order),
            )
            return workflow_response(rolled_back_distribution, updated_order)
        except HTTPException:
            connection.rollback()
            raise
        except StaleDistributionRevisionError as exc:
            connection.rollback()
            raise HTTPException(status_code=409, detail="distribution revision conflict") from exc
        except DistributionNotFoundError as exc:
            connection.rollback()
            raise HTTPException(status_code=404, detail="distribution not found") from exc
        except ChangeOrderNotFoundError as exc:
            connection.rollback()
            raise HTTPException(status_code=404, detail="change order not found") from exc
        except (
            IllegalDistributionStateError,
            IllegalTransitionError,
            InvalidChangeOrderTransitionError,
            StaleChangeOrderRevisionError,
        ) as exc:
            connection.rollback()
            raise HTTPException(status_code=409, detail="distribution transition conflict") from exc
        except InvalidDistributionSnapshotError as exc:
            connection.rollback()
            raise HTTPException(status_code=422, detail="invalid rollback request") from exc
        except Exception as exc:
            connection.rollback()
            raise HTTPException(status_code=500, detail="distribution storage error") from exc

    @write_router.post(
        "/change-orders/{change_id}/approve",
        response_model=ChangeOrderResponse,
    )
    def approve_change_order(
        change_id: Annotated[str, Path(min_length=1, max_length=_MAX_PATH_ID_LENGTH)],
        request: Request,
        identity: ApiIdentity = identity_dependency,
    ) -> dict[str, object]:
        require_approve_permission(identity)
        stored = get_order(_validate_path_id(change_id))
        if stored.order.created_by == identity.user_id:
            raise HTTPException(status_code=403, detail="creator may not approve this change")
        try:
            transitioned = approve(stored.order, identity.user_id, now())
        except IllegalTransitionError as exc:
            raise HTTPException(status_code=409, detail="change order transition conflict") from exc
        updated = append_order(transitioned, stored.revision)
        response = _change_order_response(updated)
        set_audit_context(
            request,
            before_value=_change_order_response(stored),
            after_value=response,
        )
        return response

    @write_router.post(
        "/change-orders/{change_id}/reject",
        response_model=ChangeOrderResponse,
    )
    def reject_change_order(
        change_id: Annotated[str, Path(min_length=1, max_length=_MAX_PATH_ID_LENGTH)],
        body: RejectChangeOrderRequest,
        request: Request,
        identity: ApiIdentity = identity_dependency,
    ) -> dict[str, object]:
        require_approve_permission(identity)
        reason = body.reason.strip()
        if not reason:
            raise HTTPException(status_code=422, detail="rejection reason must not be blank")
        stored = get_order(_validate_path_id(change_id))
        if stored.order.created_by == identity.user_id:
            raise HTTPException(status_code=403, detail="creator may not reject this change")
        try:
            transitioned = reject(stored.order, identity.user_id, reason, now())
        except IllegalTransitionError as exc:
            raise HTTPException(status_code=409, detail="change order transition conflict") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid rejection reason") from exc
        updated = append_order(transitioned, stored.revision)
        response = _change_order_response(updated)
        set_audit_context(
            request,
            before_value=_change_order_response(stored),
            after_value=response,
        )
        return response

    @login_router.post("/auth/login")
    def login(body: LoginRequest, request: Request, response: Response) -> dict[str, bool]:
        store = require_auth_store()
        if request.url.scheme != "https":
            raise HTTPException(status_code=400, detail="HTTPS is required")
        try:
            principal = store.authenticate(body.user_id, body.password.get_secret_value())
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail="authentication service unavailable"
            ) from exc
        if principal is None:
            raise HTTPException(status_code=401, detail="invalid credentials")
        request.state.audit_actor = principal.user_id
        try:
            if audit_store is None:
                session = store.create_session(principal.user_id, now())
            else:
                session = store.create_session(principal.user_id, now(), commit=False)
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail="authentication service unavailable"
            ) from exc
        set_audit_context(
            request,
            after_value={
                "user_id": principal.user_id,
                "created_at": session.created_at,
                "expires_at": session.expires_at,
            },
        )
        response.set_cookie(
            "__Host-as_console_session",
            session.token,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/",
        )
        response.set_cookie(
            "__Host-as_console_csrf",
            session.csrf_token,
            secure=True,
            samesite="strict",
            path="/",
        )
        return {"authenticated": True}

    @session_router.get("/auth/session")
    def get_session(identity: ApiIdentity = identity_dependency) -> dict[str, object]:
        require_auth_store()
        principal = identity
        return {
            "user_id": principal.user_id,
            "roles": sorted(role.value for role in cast(Principal, principal).roles),
        }

    @write_router.post("/auth/logout", status_code=204)
    def logout(request: Request, response: Response) -> Response:
        store = require_auth_store()
        token = request.cookies.get("__Host-as_console_session")
        if token is None:
            raise HTTPException(status_code=401, detail="authentication required")
        try:
            if audit_store is None:
                revoked = store.revoke_session(token, now())
            else:
                revoked = store.revoke_session(token, now(), commit=False)
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail="authentication service unavailable"
            ) from exc
        if revoked is None:
            raise HTTPException(status_code=401, detail="authentication required")
        set_audit_context(
            request,
            before_value={
                "user_id": revoked.user_id,
                "created_at": revoked.created_at,
                "expires_at": revoked.expires_at,
                "revoked_at": None,
            },
            after_value={
                "user_id": revoked.user_id,
                "created_at": revoked.created_at,
                "expires_at": revoked.expires_at,
                "revoked_at": revoked.revoked_at,
            },
        )
        response.delete_cookie(
            "__Host-as_console_session",
            httponly=True,
            secure=True,
            samesite="strict",
            path="/",
        )
        response.delete_cookie(
            "__Host-as_console_csrf",
            secure=True,
            samesite="strict",
            path="/",
        )
        response.status_code = 204
        return response

    @session_router.get("/auth/users", response_model=list[ConsoleUserResponse])
    def list_console_users(identity: ApiIdentity = identity_dependency) -> list[dict[str, object]]:
        store = require_auth_store()
        require_manage_users(identity)
        try:
            return [console_user_response(user) for user in store.list_users()]
        except Exception as exc:
            raise HTTPException(status_code=500, detail="console account storage error") from exc

    @write_router.post(
        "/auth/users",
        response_model=ConsoleUserResponse,
        status_code=201,
    )
    def create_console_user(
        body: CreateConsoleUserRequest,
        request: Request,
        identity: ApiIdentity = identity_dependency,
    ) -> dict[str, object]:
        store = require_auth_store()
        require_manage_users(identity)
        try:
            user_args = (
                body.user_id,
                body.password.get_secret_value(),
                frozenset(Role(role) for role in body.roles),
                now(),
            )
            if audit_store is None:
                user = store.create_user(*user_args, enabled=body.enabled)
            else:
                user = store.create_user(*user_args, enabled=body.enabled, commit=False)
        except DuplicateConsoleUserError as exc:
            raise HTTPException(status_code=409, detail="console user already exists") from exc
        except ConsoleBootstrapRequiredError as exc:
            raise HTTPException(status_code=409, detail="console bootstrap is required") from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="invalid console user request") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="console account storage error") from exc
        response = console_user_response(user)
        set_audit_context(request, after_value=response)
        return response

    @write_router.patch(
        "/auth/users/{user_id}",
        response_model=ConsoleUserResponse,
    )
    def update_console_user(
        body: UpdateConsoleUserRequest,
        user_id: Annotated[str, Path(min_length=1, max_length=128)],
        request: Request,
        identity: ApiIdentity = identity_dependency,
    ) -> dict[str, object]:
        store = require_auth_store()
        require_manage_users(identity)
        if not body.model_fields_set:
            raise HTTPException(status_code=422, detail="at least one user field is required")
        if any(getattr(body, field) is None for field in body.model_fields_set):
            raise HTTPException(status_code=422, detail="user fields must not be null")
        try:
            before_user = store.get_user(user_id)
            updated_roles = (
                frozenset(Role(role) for role in body.roles)
                if "roles" in body.model_fields_set and body.roles is not None
                else None
            )
            updated_password = (
                body.password.get_secret_value() if body.password is not None else None
            )
            if audit_store is None:
                user = store.update_user(
                    user_id,
                    now(),
                    roles=updated_roles,
                    password=updated_password,
                    enabled=body.enabled,
                )
            else:
                user = store.update_user(
                    user_id,
                    now(),
                    roles=updated_roles,
                    password=updated_password,
                    enabled=body.enabled,
                    commit=False,
                )
        except ConsoleUserNotFoundError as exc:
            raise HTTPException(status_code=404, detail="console user not found") from exc
        except LastEnabledConsoleAdminError as exc:
            raise HTTPException(
                status_code=409, detail="last enabled administrator cannot be removed"
            ) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="invalid console user request") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="console account storage error") from exc
        response = console_user_response(user)
        set_audit_context(
            request,
            before_value=(None if before_user is None else console_user_response(before_user)),
            after_value=response,
        )
        return response

    @unmatched_read_router.api_route("/{unmatched_path:path}", methods=["GET", "HEAD"])
    def unmatched_read(unmatched_path: str) -> None:
        raise HTTPException(status_code=404, detail="Not Found")

    @unmatched_write_router.api_route(
        "/{unmatched_path:path}",
        methods=["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"],
    )
    def unmatched_write(unmatched_path: str) -> None:
        raise HTTPException(status_code=404, detail="Not Found")

    app.include_router(router)
    app.include_router(write_router)
    app.include_router(session_router)
    app.include_router(login_router)
    app.include_router(unmatched_read_router)
    app.include_router(unmatched_write_router)
    console_assets = files("as_console").joinpath("web")
    if not console_assets.is_dir():
        console_assets = FilePath(__file__).resolve().parents[3] / "console" / "web"
    app.mount("/", StaticFiles(directory=str(console_assets), html=True), name="console")
    return app


def _config_bundle(value: ConfigBundleResponse) -> ConfigBundle:
    return ConfigBundle(
        version=value.version,
        rules=tuple(RuleDTO(**rule.model_dump()) for rule in value.rules),
        toggles=tuple(ToggleDTO(**toggle.model_dump()) for toggle in value.toggles),
    )


def _managed_rule_change(
    value: ManagedRuleChangeResponse | None,
) -> ManagedRuleChange | None:
    if value is None:
        return None
    if isinstance(value, _DeleteManagedRuleChangeResponse):
        return ManagedRuleChange(
            action=ManagedRuleChangeAction(value.action),
            rule_id=value.rule_id,
            proposed_rule=None,
            expected_revision=value.expected_revision,
        )
    rule = value.proposed_rule
    return ManagedRuleChange(
        action=ManagedRuleChangeAction(value.action),
        rule_id=value.rule_id,
        proposed_rule=ManagedRule(
            rule_id=rule.rule_id,
            name=rule.name,
            match_field=MatchField(rule.match_field),
            match_mode=MatchMode(rule.match_mode),
            match_value=rule.match_value,
            target_service=TargetService(rule.target_service),
            enabled=rule.enabled,
            target_detail=rule.target_detail,
        ),
        expected_revision=value.expected_revision,
    )


def _validate_path_id(value: str) -> str:
    rejected_categories = {"Cc", "Cf", "Cs", "Zl", "Zp"}
    if not value.strip() or any(
        unicodedata.category(character) in rejected_categories for character in value
    ):
        raise HTTPException(
            status_code=422,
            detail="path id must be nonblank and contain no prohibited Unicode characters",
        )
    return value


def _managed_rule_response(stored: StoredManagedRule) -> dict[str, object]:
    return {
        "revision": stored.revision,
        "record": json.loads(serialize_managed_rule(stored.rule)),
    }


def _change_order_response(stored: StoredChangeOrder) -> dict[str, object]:
    return {
        "revision": stored.revision,
        "record": json.loads(serialize_order(stored.order)),
    }
