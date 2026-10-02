"""Read-only internal API coverage. REQ-F-12 and REQ-F-14."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from as_config_service.api import ApiIdentity, ManagedRuleChangeResponse, create_app
from as_config_service.auth import ConsoleUser, IssuedSession, RevokedSession
from as_config_service.change_order import (
    AuditEntry,
    ChangeOrder,
    ChangeState,
    ManagedRuleChange,
    ManagedRuleChangeAction,
)
from as_config_service.change_order_store import (
    ChangeOrderNotFoundError,
    DuplicateChangeOrderError,
    InvalidChangeOrderTransitionError,
    StaleChangeOrderRevisionError,
    StoredChangeOrder,
    deserialize_order,
    serialize_order,
)
from as_config_service.managed_rule import ManagedRule, MatchField, MatchMode, TargetService
from as_config_service.managed_rule_store import (
    StoredManagedRule,
    serialize_managed_rule,
)
from as_console.access import AuditOutcome, AuditRecord, Principal, Role
from as_platform.api.contract import ConfigBundle, RuleDTO, ToggleDTO

pytestmark = pytest.mark.unit

_NOW = 1_700_000_000.0
_AUDIT_RESOURCE_HMAC_KEY = b"t" * 32
_PATHS = (
    "/internal/v1/managed-rules",
    "/internal/v1/managed-rules/rule@region-1",
    "/internal/v1/change-orders",
    "/internal/v1/change-orders/change@region-1",
    "/internal/v1/change-orders/change@region-1/distribution",
)


@dataclass(frozen=True)
class Identity:
    user_id: str


class FakeManagedRuleStore:
    def __init__(self, records: tuple[StoredManagedRule, ...]) -> None:
        self.records = {record.rule_id: record for record in records}
        self.mutation_calls = 0

    def create(
        self, rule: ManagedRule, change_id: str, actor: str, created_at: float
    ) -> StoredManagedRule:
        self.mutation_calls += 1
        raise AssertionError("read-only API must not create rules")

    def get(self, rule_id: str) -> StoredManagedRule | None:
        return self.records.get(rule_id)

    def list_latest(self) -> tuple[StoredManagedRule, ...]:
        return tuple(self.records[key] for key in sorted(self.records))

    def history(self, rule_id: str) -> tuple[StoredManagedRule, ...]:
        raise AssertionError("read-only API does not request history")

    def append(
        self,
        rule_id: str,
        rule: ManagedRule | None,
        change_id: str,
        actor: str,
        created_at: float,
        expected_revision: int,
    ) -> StoredManagedRule:
        self.mutation_calls += 1
        raise AssertionError("read-only API must not append rules")


class FakeChangeOrderStore:
    def __init__(self, records: tuple[StoredChangeOrder, ...] = ()) -> None:
        self.records = {record.order.change_id: record for record in records}
        self.create_calls = 0
        self.append_calls = 0
        self.stale_on_append = False
        self.invalid_transition_on_append = False

    def create(self, order: ChangeOrder, *, commit: bool = True) -> StoredChangeOrder:
        self.create_calls += 1
        if order.change_id in self.records:
            raise DuplicateChangeOrderError("duplicate")
        stored = StoredChangeOrder(order=order, revision=1)
        self.records[order.change_id] = stored
        return stored

    def get(self, change_id: str) -> StoredChangeOrder | None:
        return self.records.get(change_id)

    def list_latest(self) -> tuple[StoredChangeOrder, ...]:
        return tuple(self.records[key] for key in sorted(self.records))

    def history(self, change_id: str) -> tuple[StoredChangeOrder, ...]:
        raise AssertionError("read-only API does not request history")

    def append_transition(
        self, order: ChangeOrder, expected_revision: int, *, commit: bool = True
    ) -> StoredChangeOrder:
        self.append_calls += 1
        current = self.records.get(order.change_id)
        if current is None:
            raise ChangeOrderNotFoundError("missing")
        if self.stale_on_append or current.revision != expected_revision:
            raise StaleChangeOrderRevisionError(
                order.change_id, expected_revision, current.revision + 1
            )
        if self.invalid_transition_on_append:
            raise InvalidChangeOrderTransitionError("invalid snapshot")
        allowed = {
            (ChangeState.DRAFT, ChangeState.SUBMITTED),
            (ChangeState.SUBMITTED, ChangeState.APPROVED),
            (ChangeState.SUBMITTED, ChangeState.REJECTED),
        }
        if (
            (current.order.state, order.state) not in allowed
            or order.audit[:-1] != current.order.audit
            or len(order.audit) != len(current.order.audit) + 1
        ):
            raise InvalidChangeOrderTransitionError("invalid snapshot")
        stored = StoredChangeOrder(order=order, revision=current.revision + 1)
        self.records[order.change_id] = stored
        return stored


class FakeAuthStore:
    def __init__(self, roles: frozenset[Role] = frozenset({Role.ADMIN})) -> None:
        self.users = {
            "admin-1": ConsoleUser("admin-1", roles, True, _NOW, _NOW),
        }
        self.sessions: dict[str, tuple[str, str, float, float, bool]] = {}
        self.login_calls = 0
        self._session_number = 0

    def authenticate(self, user_id: str, password: str) -> Principal | None:
        self.login_calls += 1
        user = self.users.get(user_id)
        if user is None or not user.enabled or password != "admin-password-long":
            return None
        return Principal(user_id, user.roles)

    def create_session(self, user_id: str, now: float, *, commit: bool = True) -> IssuedSession:
        self._session_number += 1
        token = f"{self._session_number:043d}"
        csrf = f"{self._session_number + 100:043d}"
        self.sessions[token] = (csrf, user_id, now, now + 28_800, False)
        return IssuedSession(token, csrf, now, now + 28_800)

    def resolve_session(self, token: str, now: float) -> Principal | None:
        session = self.sessions.get(token)
        if session is None or session[4] or session[3] <= now:
            return None
        user = self.users.get(session[1])
        if user is None or not user.enabled:
            return None
        return Principal(user.user_id, user.roles)

    def verify_csrf(self, token: str, cookie: str, header: str, now: float) -> bool:
        session = self.sessions.get(token)
        return (
            self.resolve_session(token, now) is not None
            and session is not None
            and cookie == header == session[0]
        )

    def revoke_session(
        self, token: str, now: float, *, commit: bool = True
    ) -> RevokedSession | None:
        session = self.sessions.get(token)
        if session is None or session[4]:
            return None
        self.sessions[token] = (session[0], session[1], session[2], session[3], True)
        return RevokedSession(session[1], session[2], session[3], now)

    def list_users(self) -> tuple[ConsoleUser, ...]:
        return tuple(self.users[key] for key in sorted(self.users))


class FakeAuditStore:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []
        self.fail_append = False

    def append(self, record: AuditRecord, *, commit: bool = True) -> AuditRecord:
        if self.fail_append:
            raise RuntimeError("audit append failed")
        self.records.append(record)
        return record


def _rule(rule_id: str = "rule@region-1") -> ManagedRule:
    return ManagedRule(
        rule_id=rule_id,
        name="International callers",
        match_field=MatchField.CALLING,
        match_mode=MatchMode.PREFIX,
        match_value="+8613",
        target_service=TargetService.TRANSLATION,
        enabled=True,
        target_detail="primary route",
    )


def _stored_rule(rule_id: str, rule: ManagedRule | None, revision: int) -> StoredManagedRule:
    return StoredManagedRule(
        rule_id=rule_id,
        revision=revision,
        rule=rule,
        change_id="change-1",
        actor="ops-alice",
        created_at=_NOW,
    )


def _stored_order() -> StoredChangeOrder:
    order = ChangeOrder(
        change_id="change@region-1",
        state=ChangeState.SUBMITTED,
        bundle=ConfigBundle(
            version="v1",
            rules=(RuleDTO("rule-1", "+8613", "translate", "return-uas"),),
            toggles=(ToggleDTO("translation.v2", True, "remove after M6", ""),),
        ),
        created_by="ops-alice",
        created_at=_NOW,
        audit=(AuditEntry("ops-alice", "submit", _NOW + 1),),
        managed_rule_change=ManagedRuleChange(
            ManagedRuleChangeAction.UPDATE,
            "rule@region-1",
            _rule(),
            2,
        ),
    )
    return StoredChangeOrder(order=order, revision=3)


def _stored_draft_order() -> StoredChangeOrder:
    return StoredChangeOrder(
        order=ChangeOrder(
            change_id="change@region-1",
            state=ChangeState.DRAFT,
            bundle=ConfigBundle(version="v1", rules=(), toggles=()),
            created_by="ops-alice",
            created_at=_NOW,
        ),
        revision=3,
    )


def _legacy_stored_order() -> StoredChangeOrder:
    encoded = (
        '{"order":{"approved_at":null,"approver":null,"audit":[],"bundle":'
        '{"rules":[],"toggles":[],"version":"legacy-v1"},"change_id":"legacy-co",'
        '"created_at":1700000000.0,"created_by":"ops-alice","state":"draft"},'
        '"schema_version":1}'
    )
    return StoredChangeOrder(order=deserialize_order(encoded), revision=1)


def _client(
    *,
    identity: Identity | None = None,
    allowed: bool = True,
    submit_allowed: bool | None = None,
    approve_allowed: bool | None = None,
    now: Callable[[], float] | None = None,
    change_id: Callable[[], str] | None = None,
    change_order_store: FakeChangeOrderStore | None = None,
    managed_rule_store: FakeManagedRuleStore | None = None,
    auth_store: FakeAuthStore | None = None,
    audit_store: FakeAuditStore | None = None,
    base_url: str = "http://testserver",
    audit_resource_hmac_key: bytes | None = _AUDIT_RESOURCE_HMAC_KEY,
) -> TestClient:
    live_rule = _stored_rule("rule@region-1", _rule(), 2)
    tombstone = _stored_rule("rule-deleted", None, 4)

    def resolve_identity(request: Request) -> ApiIdentity | None:
        return identity

    def can_read_config(candidate: ApiIdentity) -> bool:
        return allowed and candidate.user_id == "ops-alice"

    rules = managed_rule_store or FakeManagedRuleStore((live_rule, tombstone))
    orders = change_order_store or FakeChangeOrderStore((_stored_order(), _legacy_stored_order()))

    def can_submit_change(candidate: ApiIdentity) -> bool:
        return submit_allowed is True

    def can_approve_change(candidate: ApiIdentity) -> bool:
        return approve_allowed is True

    app = create_app(
        managed_rule_store=rules,
        change_order_store=orders,
        resolve_identity=resolve_identity,
        can_read_config=can_read_config,
        can_submit_change=can_submit_change if submit_allowed is not None else None,
        can_approve_change=can_approve_change if approve_allowed is not None else None,
        now=now or (lambda: _NOW),
        new_change_id=change_id or (lambda: "new-change@region-1"),
        auth_store=auth_store,
        audit_store=(audit_store or (FakeAuditStore() if auth_store is not None else None)),
        allow_unaudited_callback_mode=auth_store is None,
        audit_resource_hmac_key=audit_resource_hmac_key,
    )
    return TestClient(app, base_url=base_url)


def test_console_assets_are_served_from_app_root() -> None:
    client = _client()

    html = client.get("/")
    javascript = client.get("/console.js")
    stylesheet = client.get("/console.css")

    assert html.status_code == 200
    assert "<title>Rule registry | AS Operations</title>" in html.text
    assert javascript.status_code == 200
    assert javascript.text
    assert stylesheet.status_code == 200
    assert stylesheet.text


def _proposed_rule_response(rule_id: str = "rule-1") -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "name": "International callers",
        "match_field": "calling",
        "match_mode": "prefix",
        "match_value": "+8613",
        "target_service": "translation",
        "enabled": True,
        "target_detail": "primary route",
    }


def _draft_payload() -> dict[str, object]:
    return {
        "bundle": {
            "version": "v2",
            "rules": [
                {"rule_id": "route-1", "prefix": "+8613", "action": "translate", "target": None}
            ],
            "toggles": [],
        },
        "managed_rule_change": {
            "action": "update",
            "rule_id": "rule@region-1",
            "proposed_rule": _proposed_rule_response("rule@region-1"),
            "expected_revision": 2,
        },
    }


def test_managed_rule_change_response_accepts_valid_action_variants() -> None:
    adapter = TypeAdapter(ManagedRuleChangeResponse)
    proposed_rule = _proposed_rule_response()

    create = adapter.validate_python(
        {"action": "create", "rule_id": "rule-1", "proposed_rule": proposed_rule}
    )
    update = adapter.validate_python(
        {
            "action": "update",
            "rule_id": "rule-1",
            "proposed_rule": proposed_rule,
            "expected_revision": 2,
        }
    )
    delete = adapter.validate_python(
        {"action": "delete", "rule_id": "rule-1", "expected_revision": 2}
    )

    assert create.action == "create"
    assert create.expected_revision is None
    assert update.action == "update"
    assert update.expected_revision == 2
    assert delete.action == "delete"
    assert delete.proposed_rule is None


@pytest.mark.parametrize(
    "change",
    [
        {"action": "create", "rule_id": "rule-1", "proposed_rule": None},
        {
            "action": "create",
            "rule_id": "rule-1",
            "proposed_rule": _proposed_rule_response(),
            "expected_revision": 1,
        },
        {
            "action": "update",
            "rule_id": "rule-1",
            "proposed_rule": None,
            "expected_revision": 1,
        },
        {
            "action": "update",
            "rule_id": "rule-1",
            "proposed_rule": _proposed_rule_response(),
        },
        {
            "action": "delete",
            "rule_id": "rule-1",
            "proposed_rule": _proposed_rule_response(),
            "expected_revision": 1,
        },
        {"action": "delete", "rule_id": "rule-1", "expected_revision": True},
        {
            "action": "update",
            "rule_id": "rule-1",
            "proposed_rule": _proposed_rule_response("rule-2"),
            "expected_revision": 1,
        },
    ],
)
def test_managed_rule_change_response_rejects_invalid_action_variants(
    change: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(ManagedRuleChangeResponse).validate_python(change)


@pytest.mark.parametrize("path", _PATHS)
def test_every_data_route_requires_identity(path: str) -> None:
    response = _client().get(path)

    assert response.status_code == 401, response.text


@pytest.mark.parametrize("path", _PATHS)
def test_every_data_route_checks_config_read_permission(path: str) -> None:
    response = _client(identity=Identity("ops-alice"), allowed=False).get(path)

    assert response.status_code == 403


def test_session_mode_never_falls_back_to_callback_identity() -> None:
    callback_calls = 0

    def resolve_identity(request: Request) -> ApiIdentity | None:
        nonlocal callback_calls
        callback_calls += 1
        return Identity("admin-1")

    app = create_app(
        managed_rule_store=FakeManagedRuleStore(()),
        change_order_store=FakeChangeOrderStore(),
        resolve_identity=resolve_identity,
        can_read_config=lambda _: True,
        auth_store=FakeAuthStore(),
        audit_store=FakeAuditStore(),
        audit_resource_hmac_key=_AUDIT_RESOURCE_HMAC_KEY,
    )
    client = TestClient(app)

    missing = client.get("/internal/v1/managed-rules")
    invalid = client.get(
        "/internal/v1/managed-rules",
        cookies={"__Host-as_console_session": "not-a-session"},
    )
    unmatched = client.get("/internal/v1/unknown/resource")

    assert missing.status_code == invalid.status_code == unmatched.status_code == 401
    assert callback_calls == 0


def test_unknown_internal_path_audit_resource_hashes_catchall_path_parameter() -> None:
    token_like_id = "A" * 43
    unmatched_path = f"config/export/{token_like_id}/unknown"
    path = f"/internal/v1/{unmatched_path}"
    audit_store = FakeAuditStore()
    client = _client(identity=Identity("ops-alice"), audit_store=audit_store)

    response = client.get(path)

    assert response.status_code == 404
    assert len(audit_store.records) == 1
    record = audit_store.records[0]
    expected_digest = hmac.new(
        _AUDIT_RESOURCE_HMAC_KEY, unmatched_path.encode(), hashlib.sha256
    ).hexdigest()
    assert record.outcome is AuditOutcome.DENIED
    assert record.action == "GET /internal/v1/{unmatched_path:path}"
    assert record.resource == (
        f"/internal/v1/{{unmatched_path:path}} unmatched_path#{expected_digest}"
    )
    assert token_like_id not in record.resource
    assert path not in record.resource


@pytest.mark.parametrize("method", ("OPTIONS", "TRACE", "CONNECT"))
def test_unknown_internal_standard_probe_methods_are_audited(method: str) -> None:
    token_like_id = "B" * 43
    unmatched_path = f"config/export/{token_like_id}/unknown"
    path = f"/internal/v1/{unmatched_path}"
    audit_store = FakeAuditStore()
    client = _client(identity=Identity("ops-alice"), audit_store=audit_store)

    response = client.request(method, path)

    assert response.status_code == 404
    assert len(audit_store.records) == 1
    record = audit_store.records[0]
    expected_digest = hmac.new(
        _AUDIT_RESOURCE_HMAC_KEY, unmatched_path.encode(), hashlib.sha256
    ).hexdigest()
    assert record.outcome is AuditOutcome.DENIED
    assert record.action == f"{method} /internal/v1/{{unmatched_path:path}}"
    assert record.resource == (
        f"/internal/v1/{{unmatched_path:path}} unmatched_path#{expected_digest}"
    )
    assert token_like_id not in record.resource
    assert path not in record.resource


def test_password_login_requires_https_and_sets_host_only_cookies() -> None:
    auth_store = FakeAuthStore()
    payload = {"user_id": "admin-1", "password": "admin-password-long"}

    insecure = _client(auth_store=auth_store).post("/internal/v1/auth/login", json=payload)
    secure_client = _client(auth_store=auth_store, base_url="https://testserver")
    secure = secure_client.post("/internal/v1/auth/login", json=payload)

    assert insecure.status_code == 400
    assert auth_store.login_calls == 1
    assert secure.status_code == 200
    assert secure.json() == {"authenticated": True}
    assert "admin-password-long" not in secure.text
    cookie_headers = secure.headers.get_list("set-cookie")
    assert len(cookie_headers) == 2
    session_cookie = next(
        value for value in cookie_headers if "__Host-as_console_session=" in value
    )
    csrf_cookie = next(value for value in cookie_headers if "__Host-as_console_csrf=" in value)
    assert "HttpOnly" in session_cookie
    assert (
        "Secure" in session_cookie
        and "SameSite=strict" in session_cookie
        and "Path=/" in session_cookie
    )
    assert "Secure" in csrf_cookie and "SameSite=strict" in csrf_cookie and "Path=/" in csrf_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "Domain=" not in session_cookie + csrf_cookie


def test_successful_session_lifecycle_audits_safe_snapshots() -> None:
    auth_store = FakeAuthStore()
    audit_store = FakeAuditStore()
    client = _client(
        auth_store=auth_store,
        audit_store=audit_store,
        base_url="https://testserver",
    )

    login = client.post(
        "/internal/v1/auth/login",
        json={"user_id": "admin-1", "password": "admin-password-long"},
    )
    session_token = client.cookies.get("__Host-as_console_session")
    csrf_token = client.cookies.get("__Host-as_console_csrf")
    assert login.status_code == 200
    assert session_token is not None and csrf_token is not None
    assert audit_store.records[0].actor == "admin-1"
    assert audit_store.records[0].before_value is None
    assert audit_store.records[0].after_value == {
        "user_id": "admin-1",
        "created_at": _NOW,
        "expires_at": _NOW + 28_800,
    }

    logout = client.post(
        "/internal/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout.status_code == 204
    assert audit_store.records[1].actor == "admin-1"
    assert audit_store.records[1].before_value == {
        "user_id": "admin-1",
        "created_at": _NOW,
        "expires_at": _NOW + 28_800,
        "revoked_at": None,
    }
    assert audit_store.records[1].after_value == {
        "user_id": "admin-1",
        "created_at": _NOW,
        "expires_at": _NOW + 28_800,
        "revoked_at": _NOW,
    }

    client.cookies.set("__Host-as_console_session", session_token)
    client.cookies.set("__Host-as_console_csrf", csrf_token)
    replayed_logout = client.post(
        "/internal/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert replayed_logout.status_code == 401
    assert audit_store.records[2].outcome is AuditOutcome.DENIED
    assert audit_store.records[2].before_value is audit_store.records[2].after_value is None

    serialized_records = json.dumps(
        [
            (record.actor, record.action, record.resource, record.before_value, record.after_value)
            for record in audit_store.records
        ]
    )
    assert session_token not in serialized_records
    assert csrf_token not in serialized_records


def test_invalid_login_is_generic_and_does_not_create_a_session() -> None:
    auth_store = FakeAuthStore()
    audit_store = FakeAuditStore()
    response = _client(
        auth_store=auth_store,
        audit_store=audit_store,
        base_url="https://testserver",
    ).post(
        "/internal/v1/auth/login",
        json={"user_id": "admin-1", "password": "incorrect-password"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}
    assert "incorrect-password" not in response.text
    assert auth_store.sessions == {}
    assert len(audit_store.records) == 1
    assert audit_store.records[0].actor == "anonymous"
    assert audit_store.records[0].outcome is AuditOutcome.DENIED
    assert audit_store.records[0].before_value is audit_store.records[0].after_value is None
    assert "incorrect-password" not in json.dumps(
        (
            audit_store.records[0].actor,
            audit_store.records[0].action,
            audit_store.records[0].resource,
        )
    )


def test_app_requires_an_identity_source_and_missing_auth_store_is_unavailable() -> None:
    with pytest.raises(ValueError, match="resolve_identity is required"):
        create_app(
            managed_rule_store=FakeManagedRuleStore(()),
            change_order_store=FakeChangeOrderStore(),
            resolve_identity=None,
            can_read_config=lambda _: True,
        )

    app = create_app(
        managed_rule_store=FakeManagedRuleStore(()),
        change_order_store=FakeChangeOrderStore(),
        resolve_identity=lambda _: Identity("admin-1"),
        can_read_config=lambda _: True,
        can_manage_users=lambda _: True,
        allow_unaudited_callback_mode=True,
    )
    response = TestClient(app).get("/internal/v1/auth/users")

    assert response.status_code == 503


def test_session_authentication_requires_audit_store_at_construction() -> None:
    with pytest.raises(ValueError, match="audit_store is required"):
        create_app(
            managed_rule_store=FakeManagedRuleStore(()),
            change_order_store=FakeChangeOrderStore(),
            resolve_identity=None,
            can_read_config=lambda _: True,
            auth_store=FakeAuthStore(),
        )


def test_callback_authentication_requires_explicit_unaudited_test_mode() -> None:
    arguments = {
        "managed_rule_store": FakeManagedRuleStore(()),
        "change_order_store": FakeChangeOrderStore(),
        "resolve_identity": lambda _: Identity("admin-1"),
        "can_read_config": lambda _: True,
    }
    with pytest.raises(ValueError, match="audit_store is required"):
        create_app(**arguments)

    app = create_app(**arguments, allow_unaudited_callback_mode=True)
    assert app is not None


@pytest.mark.parametrize("key", [None, b"short-key"])
def test_audited_app_requires_a_32_byte_resource_hmac_key(key: bytes | None) -> None:
    arguments = {
        "managed_rule_store": FakeManagedRuleStore(()),
        "change_order_store": FakeChangeOrderStore(),
        "resolve_identity": lambda _: Identity("admin-1"),
        "can_read_config": lambda _: True,
        "audit_store": FakeAuditStore(),
    }
    if key is not None:
        arguments["audit_resource_hmac_key"] = key

    with pytest.raises(ValueError, match="audit_resource_hmac_key must be exactly 32 bytes"):
        create_app(**arguments)


def test_path_parameter_audit_resource_uses_full_keyed_hmac() -> None:
    token_like_id = "A" * 43
    path = f"/internal/v1/change-orders/{token_like_id}"
    first_key = b"a" * 32
    second_key = b"b" * 32
    first_audit_store = FakeAuditStore()
    second_audit_store = FakeAuditStore()
    first_client = _client(
        identity=Identity("ops-alice"),
        audit_store=first_audit_store,
        audit_resource_hmac_key=first_key,
    )
    second_client = _client(
        identity=Identity("ops-alice"),
        audit_store=second_audit_store,
        audit_resource_hmac_key=second_key,
    )

    assert first_client.get(path).status_code == 404
    assert first_client.get(path).status_code == 404
    assert second_client.get(path).status_code == 404

    expected_digest = hmac.new(first_key, token_like_id.encode(), hashlib.sha256).hexdigest()
    expected_resource = f"/internal/v1/change-orders/{{change_id}} change_id#{expected_digest}"
    first_resources = [record.resource for record in first_audit_store.records]
    second_resource = second_audit_store.records[0].resource
    assert first_resources == [expected_resource, expected_resource]
    assert token_like_id not in expected_resource
    assert second_resource != expected_resource


def test_unaudited_callback_mode_cannot_be_combined_with_session_authentication() -> None:
    with pytest.raises(ValueError, match="requires callback authentication"):
        create_app(
            managed_rule_store=FakeManagedRuleStore(()),
            change_order_store=FakeChangeOrderStore(),
            resolve_identity=None,
            can_read_config=lambda _: True,
            auth_store=FakeAuthStore(),
            audit_store=FakeAuditStore(),
            audit_resource_hmac_key=_AUDIT_RESOURCE_HMAC_KEY,
            allow_unaudited_callback_mode=True,
        )


def test_callback_audit_records_allowed_reads_and_change_order_writes() -> None:
    audit_store = FakeAuditStore()
    journal = FakeChangeOrderStore()
    client = _client(
        identity=Identity("ops-alice"),
        submit_allowed=True,
        change_order_store=journal,
        audit_store=audit_store,
    )

    read = client.get("/internal/v1/managed-rules?ignored=not-a-resource")
    created = client.post("/internal/v1/change-orders", json=_draft_payload())

    assert read.status_code == 200
    assert created.status_code == 201
    assert [record.outcome for record in audit_store.records] == [
        AuditOutcome.ALLOWED,
        AuditOutcome.ALLOWED,
    ]
    assert audit_store.records[0].actor == "ops-alice"
    assert audit_store.records[0].action == "GET /internal/v1/managed-rules"
    assert audit_store.records[0].resource == "/internal/v1/managed-rules"
    assert audit_store.records[0].before_value is audit_store.records[0].after_value is None
    assert audit_store.records[1].before_value is None
    assert audit_store.records[1].after_value == {
        "revision": 1,
        "record": json.loads(serialize_order(journal.records["new-change@region-1"].order)),
    }
    assert "password" not in json.dumps(
        [(record.before_value, record.after_value) for record in audit_store.records]
    )


def test_audited_request_validation_failure_is_denied_with_null_snapshots() -> None:
    audit_store = FakeAuditStore()
    response = _client(
        identity=Identity("ops-alice"),
        audit_store=audit_store,
    ).post("/internal/v1/change-orders", json={"bundle": {}})

    assert response.status_code == 422
    assert len(audit_store.records) == 1
    assert audit_store.records[0].outcome is AuditOutcome.DENIED
    assert audit_store.records[0].before_value is audit_store.records[0].after_value is None


def test_audited_session_denials_and_reads_use_authenticated_actor_only() -> None:
    audit_store = FakeAuditStore()
    auth_store = FakeAuthStore(frozenset({Role.VIEWER}))
    issued = auth_store.create_session("admin-1", _NOW)
    client = _client(auth_store=auth_store, audit_store=audit_store)

    invalid = client.get(
        "/internal/v1/managed-rules",
        cookies={"__Host-as_console_session": "invalid-token-value"},
    )
    allowed = client.get(
        "/internal/v1/managed-rules",
        cookies={"__Host-as_console_session": issued.token},
    )
    denied = client.post(
        "/internal/v1/change-orders",
        json=_draft_payload(),
        cookies={
            "__Host-as_console_session": issued.token,
            "__Host-as_console_csrf": issued.csrf_token,
        },
        headers={"X-CSRF-Token": issued.csrf_token},
    )

    assert invalid.status_code == 401
    assert allowed.status_code == 200
    assert denied.status_code == 403
    assert [(event.actor, event.outcome) for event in audit_store.records] == [
        ("anonymous", AuditOutcome.DENIED),
        ("admin-1", AuditOutcome.ALLOWED),
        ("admin-1", AuditOutcome.DENIED),
    ]
    assert all(event.before_value is event.after_value is None for event in audit_store.records)
    assert "invalid-token-value" not in json.dumps(
        [
            (record.actor, record.action, record.resource, record.before_value, record.after_value)
            for record in audit_store.records
        ]
    )


def test_session_writes_require_exact_double_submit_csrf_and_submit_permission() -> None:
    auth_store = FakeAuthStore(frozenset({Role.OPERATOR}))
    issued = auth_store.create_session("admin-1", _NOW)
    client = _client(auth_store=auth_store)
    cookies = {"__Host-as_console_session": issued.token}
    payload = _draft_payload()

    missing = client.post("/internal/v1/change-orders", json=payload, cookies=cookies)
    mismatch = client.post(
        "/internal/v1/change-orders",
        json=payload,
        cookies={**cookies, "__Host-as_console_csrf": "wrong"},
        headers={"X-CSRF-Token": issued.csrf_token},
    )
    accepted = client.post(
        "/internal/v1/change-orders",
        json=payload,
        cookies={**cookies, "__Host-as_console_csrf": issued.csrf_token},
        headers={"X-CSRF-Token": issued.csrf_token},
    )

    assert missing.status_code == mismatch.status_code == 403
    assert accepted.status_code == 201


def test_session_permission_denial_and_admin_only_user_management() -> None:
    viewer_store = FakeAuthStore(frozenset({Role.VIEWER}))
    viewer_session = viewer_store.create_session("admin-1", _NOW)
    viewer_client = _client(auth_store=viewer_store)
    viewer_cookies = {
        "__Host-as_console_session": viewer_session.token,
        "__Host-as_console_csrf": viewer_session.csrf_token,
    }
    denied_write = viewer_client.post(
        "/internal/v1/change-orders",
        json=_draft_payload(),
        cookies=viewer_cookies,
        headers={"X-CSRF-Token": viewer_session.csrf_token},
    )
    denied_users = viewer_client.get(
        "/internal/v1/auth/users",
        cookies={"__Host-as_console_session": viewer_session.token},
    )

    admin_store = FakeAuthStore()
    admin_session = admin_store.create_session("admin-1", _NOW)
    admin = _client(auth_store=admin_store).get(
        "/internal/v1/auth/users",
        cookies={"__Host-as_console_session": admin_session.token},
    )

    assert denied_write.status_code == denied_users.status_code == 403
    assert admin.status_code == 200
    assert admin.json()[0]["user_id"] == "admin-1"
    assert "password" not in admin.json()[0]
    assert "verifier" not in admin.json()[0]


@pytest.mark.parametrize("path", ("/docs", "/redoc", "/openapi.json"))
def test_generated_documentation_routes_are_disabled(path: str) -> None:
    response = _client().get(path)

    assert response.status_code == 404


def test_managed_rule_list_and_detail_preserve_typed_fields_and_tombstone() -> None:
    client = _client(identity=Identity("ops-alice"))

    listed = client.get("/internal/v1/managed-rules")
    detail = client.get("/internal/v1/managed-rules/rule@region-1")

    assert listed.status_code == detail.status_code == 200
    by_id = {
        item["record"]["rule"]["rule_id"]: item for item in listed.json() if item["record"]["rule"]
    }
    assert by_id["rule@region-1"] == {
        "revision": 2,
        "record": json.loads(serialize_managed_rule(_rule())),
    }
    tombstone = next(item for item in listed.json() if item["record"]["rule"] is None)
    assert tombstone == {
        "revision": 4,
        "record": json.loads(serialize_managed_rule(None)),
    }
    assert detail.json() == by_id["rule@region-1"]


def test_managed_rule_tombstone_detail_preserves_revision() -> None:
    response = _client(identity=Identity("ops-alice")).get(
        "/internal/v1/managed-rules/rule-deleted"
    )

    assert response.status_code == 200
    assert response.json() == {
        "revision": 4,
        "record": json.loads(serialize_managed_rule(None)),
    }
    assert response.json()["record"]["rule"] is None


def test_change_order_list_and_detail_preserve_proposal_bundle_and_audit() -> None:
    client = _client(identity=Identity("ops-alice"))
    stored = _stored_order()

    listed = client.get("/internal/v1/change-orders")
    detail = client.get("/internal/v1/change-orders/change@region-1")
    expected = {
        "revision": stored.revision,
        "record": json.loads(serialize_order(stored.order)),
    }

    assert listed.status_code == detail.status_code == 200
    assert listed.json() == [
        expected,
        {
            "revision": 1,
            "record": json.loads(serialize_order(_legacy_stored_order().order)),
        },
    ]
    assert detail.json() == expected
    proposal = detail.json()["record"]["order"]["managed_rule_change"]
    assert proposal["action"] == "update"
    assert proposal["rule_id"] == "rule@region-1"
    assert proposal["proposed_rule"]["rule_id"] == "rule@region-1"
    assert proposal["expected_revision"] == 2


def test_change_order_list_and_legacy_detail_expose_null_proposal() -> None:
    client = _client(identity=Identity("ops-alice"))

    listed = client.get("/internal/v1/change-orders")
    detail = client.get("/internal/v1/change-orders/legacy-co")

    assert listed.status_code == detail.status_code == 200
    assert listed.json()[1]["record"]["order"]["managed_rule_change"] is None
    assert detail.json() == listed.json()[1]


@pytest.mark.parametrize(
    "path",
    (
        "/internal/v1/managed-rules/missing",
        "/internal/v1/change-orders/missing",
    ),
)
def test_missing_detail_returns_404(path: str) -> None:
    response = _client(identity=Identity("ops-alice")).get(path)

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("resource", "bad_id"),
    [
        ("managed-rules", " "),
        ("managed-rules", "r" * 257),
        ("managed-rules", "rule\x01id"),
        ("managed-rules", "rule\u200bid"),
        ("managed-rules", "rule\u2028id"),
        ("managed-rules", "rule\u2029id"),
        ("change-orders", " "),
        ("change-orders", "c" * 257),
        ("change-orders", "change\x01id"),
        ("change-orders", "change\u200bid"),
        ("change-orders", "change\u2028id"),
        ("change-orders", "change\u2029id"),
    ],
)
def test_detail_rejects_blank_overlong_and_control_ids(resource: str, bad_id: str) -> None:
    response = _client(identity=Identity("ops-alice")).get(
        f"/internal/v1/{resource}/{quote(bad_id, safe='@-')}"
    )

    assert response.status_code == 422


def test_write_routes_fail_closed_when_write_authorizers_are_missing() -> None:
    client = _client(identity=Identity("ops-alice"))

    draft = client.post("/internal/v1/change-orders", json=_draft_payload())
    submission = client.post("/internal/v1/change-orders/change@region-1/submit")
    approval = client.post("/internal/v1/change-orders/change@region-1/approve")

    assert draft.status_code == submission.status_code == approval.status_code == 403


def test_write_routes_deny_when_write_authorizers_reject_identity() -> None:
    client = _client(identity=Identity("ops-alice"), submit_allowed=False, approve_allowed=False)

    draft = client.post("/internal/v1/change-orders", json=_draft_payload())
    approval = client.post("/internal/v1/change-orders/change@region-1/approve")

    assert draft.status_code == approval.status_code == 403


def test_distribution_routes_fail_closed_without_distribution_store() -> None:
    client = _client(identity=Identity("ops-alice"), approve_allowed=True)

    status = client.get("/internal/v1/change-orders/change@region-1/distribution")
    start = client.post(
        "/internal/v1/change-orders/change@region-1/distribution",
        json={
            "version": 4,
            "batches": [["as-1"]],
            "expected_change_order_revision": 3,
        },
    )

    assert status.status_code == start.status_code == 503


def test_distribution_report_body_requires_strict_boolean_reports() -> None:
    response = _client(identity=Identity("ops-alice"), approve_allowed=True).post(
        "/internal/v1/change-orders/change@region-1/distribution/reports",
        json={"expected_distribution_revision": 1, "reports": {"as-1": "true"}},
    )

    assert response.status_code == 422


def test_distribution_mutations_use_the_approval_permission_seam() -> None:
    response = _client(identity=Identity("ops-alice"), approve_allowed=False).post(
        "/internal/v1/change-orders/change@region-1/distribution/reports",
        json={"expected_distribution_revision": 1, "reports": {"as-1": True}},
    )

    assert response.status_code == 403


def test_create_draft_uses_authenticated_actor_injected_id_time_and_typed_proposal() -> None:
    journal = FakeChangeOrderStore()
    managed_rules = FakeManagedRuleStore((_stored_rule("rule@region-1", _rule(), 2),))
    client = _client(
        identity=Identity("ops-alice"),
        submit_allowed=True,
        now=lambda: _NOW + 10,
        change_id=lambda: "new-change@region-1",
        change_order_store=journal,
        managed_rule_store=managed_rules,
    )

    response = client.post("/internal/v1/change-orders", json=_draft_payload())

    assert response.status_code == 201
    snapshot = journal.records["new-change@region-1"]
    assert snapshot.revision == 1
    assert snapshot.order.state is ChangeState.DRAFT
    assert snapshot.order.created_by == "ops-alice"
    assert snapshot.order.created_at == _NOW + 10
    assert snapshot.order.bundle.rules == (RuleDTO("route-1", "+8613", "translate"),)
    assert snapshot.order.managed_rule_change == ManagedRuleChange(
        ManagedRuleChangeAction.UPDATE,
        "rule@region-1",
        _rule(),
        2,
    )
    assert response.json()["record"]["order"]["managed_rule_change"]["action"] == "update"
    assert managed_rules.list_latest() == (_stored_rule("rule@region-1", _rule(), 2),)
    assert managed_rules.mutation_calls == 0


def test_creator_can_submit_with_audit_and_expected_revision() -> None:
    journal = FakeChangeOrderStore((_stored_draft_order(),))
    client = _client(
        identity=Identity("ops-alice"),
        submit_allowed=True,
        now=lambda: _NOW + 20,
        change_order_store=journal,
    )

    response = client.post("/internal/v1/change-orders/change@region-1/submit")

    assert response.status_code == 200
    assert response.json()["revision"] == 4
    order = journal.records["change@region-1"].order
    assert order.state is ChangeState.SUBMITTED
    assert order.audit[-1] == AuditEntry("ops-alice", "submit", _NOW + 20)
    assert journal.append_calls == 1


def test_submit_by_other_user_is_denied() -> None:
    journal = FakeChangeOrderStore((_stored_draft_order(),))
    response = _client(
        identity=Identity("ops-bob"), submit_allowed=True, change_order_store=journal
    ).post("/internal/v1/change-orders/change@region-1/submit")

    assert response.status_code == 403
    assert journal.append_calls == 0


def test_creator_cannot_approve_own_change_order() -> None:
    journal = FakeChangeOrderStore((_stored_order(),))
    response = _client(
        identity=Identity("ops-alice"), approve_allowed=True, change_order_store=journal
    ).post("/internal/v1/change-orders/change@region-1/approve")

    assert response.status_code == 403
    assert journal.append_calls == 0


def test_creator_cannot_reject_own_change_order() -> None:
    journal = FakeChangeOrderStore((_stored_order(),))
    response = _client(
        identity=Identity("ops-alice"), approve_allowed=True, change_order_store=journal
    ).post(
        "/internal/v1/change-orders/change@region-1/reject",
        json={"reason": "not allowed"},
    )

    assert response.status_code == 403
    order = journal.records["change@region-1"].order
    assert order.state is ChangeState.SUBMITTED
    assert journal.append_calls == 0


def test_different_approver_succeeds_with_approver_time_and_audit() -> None:
    journal = FakeChangeOrderStore((_stored_order(),))
    response = _client(
        identity=Identity("ops-bob"),
        approve_allowed=True,
        now=lambda: _NOW + 30,
        change_order_store=journal,
    ).post("/internal/v1/change-orders/change@region-1/approve")

    assert response.status_code == 200
    assert response.json()["revision"] == 4
    order = journal.records["change@region-1"].order
    assert order.state is ChangeState.APPROVED
    assert order.approver == "ops-bob"
    assert order.approved_at == _NOW + 30
    assert order.audit[-1] == AuditEntry("ops-bob", "approve", _NOW + 30)


def test_reject_requires_nonblank_reason_and_records_trimmed_audit() -> None:
    journal = FakeChangeOrderStore((_stored_order(),))
    client = _client(identity=Identity("ops-bob"), approve_allowed=True, change_order_store=journal)

    blank = client.post(
        "/internal/v1/change-orders/change@region-1/reject", json={"reason": "  \t "}
    )
    rejected = client.post(
        "/internal/v1/change-orders/change@region-1/reject",
        json={"reason": "  rule conflict  "},
    )

    assert blank.status_code == 422
    assert rejected.status_code == 200
    order = journal.records["change@region-1"].order
    assert order.state is ChangeState.REJECTED
    assert order.audit[-1] == AuditEntry("ops-bob", "reject: rule conflict", _NOW)


def test_illegal_state_stale_revision_and_invalid_persisted_transition_map_to_conflict() -> None:
    submitted = FakeChangeOrderStore((_stored_order(),))
    client = _client(
        identity=Identity("ops-alice"),
        submit_allowed=True,
        change_order_store=submitted,
    )
    illegal = client.post("/internal/v1/change-orders/change@region-1/submit")

    stale = FakeChangeOrderStore((_stored_draft_order(),))
    stale.stale_on_append = True
    stale_response = _client(
        identity=Identity("ops-alice"),
        submit_allowed=True,
        change_order_store=stale,
    ).post("/internal/v1/change-orders/change@region-1/submit")

    invalid = FakeChangeOrderStore((_stored_draft_order(),))
    invalid.invalid_transition_on_append = True
    invalid_response = _client(
        identity=Identity("ops-alice"),
        submit_allowed=True,
        change_order_store=invalid,
    ).post("/internal/v1/change-orders/change@region-1/submit")

    assert illegal.status_code == stale_response.status_code == invalid_response.status_code == 409


def test_duplicate_draft_id_maps_to_conflict() -> None:
    journal = FakeChangeOrderStore((_stored_order(),))
    response = _client(
        identity=Identity("ops-alice"),
        submit_allowed=True,
        change_id=lambda: "change@region-1",
        change_order_store=journal,
    ).post("/internal/v1/change-orders", json=_draft_payload())

    assert response.status_code == 409


def test_write_transition_missing_order_maps_to_not_found() -> None:
    response = _client(identity=Identity("ops-alice"), submit_allowed=True).post(
        "/internal/v1/change-orders/missing/submit"
    )

    assert response.status_code == 404
