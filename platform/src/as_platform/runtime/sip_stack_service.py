"""Product SIP stack service: runtime listener, checkpoints, and recovery restore."""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from as_platform.decision import RuleSet
from as_platform.runtime.active_calls import ActiveCallSource
from as_platform.runtime.ruleset_loader import load_ruleset_from_env
from as_platform.runtime.transport_env import (
    SipListenConfig,
    load_sip_listen_config_from_env,
    load_transport_seam_from_env,
)
from as_platform.sip.call_controller import CallController
from as_platform.sip.ingress import TransportIngressGate
from as_platform.sip.recovery import CallStateRecovery, ProcessStartRestoreResult
from as_platform.sip.recovery_coordinator import RecoveryCoordinator
from as_platform.sip.resip_runtime import ResipRuntimeListener, load_resip_runtime_extension
from as_platform.state.call_checkpoint import (
    CallCheckpointCommit,
    CallStateCheckpoint,
    CallStateCheckpointRepository,
    DialogLegCheckpoint,
)
from as_platform.state.in_memory import InMemoryStateStore
from as_platform.state.redis_store import load_redis_store_from_env
from as_platform.state.store import StateStore

_DEFAULT_RECOVERY_CASE = "translation"
_DEFAULT_CHECKPOINT_TTL_SECONDS = 3600


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _recovery_call_keys() -> tuple[str, ...]:
    raw = os.environ.get("AS_RECOVERY_CALL_KEYS", "").strip()
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _checkpoint_repository(store: StateStore) -> CallStateCheckpointRepository:
    ttl_raw = os.environ.get("AS_RECOVERY_CHECKPOINT_TTL_SECONDS", "").strip()
    ttl_seconds = int(ttl_raw) if ttl_raw else _DEFAULT_CHECKPOINT_TTL_SECONDS
    return CallStateCheckpointRepository(
        store=store,
        ttl_seconds=ttl_seconds,
        allowed_header_namespaces={},
    )


def _leg_from_established_fields(fields: dict[str, object]) -> DialogLegCheckpoint:
    route_set_raw = fields.get("route_set", ())
    route_set = (
        tuple(str(item) for item in route_set_raw) if isinstance(route_set_raw, tuple) else ()
    )
    return DialogLegCheckpoint(
        call_id=str(fields["call_id"]),
        local_tag=str(fields["local_tag"]),
        remote_tag=str(fields["remote_tag"]),
        local_uri=str(fields["local_uri"]),
        remote_uri=str(fields["remote_uri"]),
        remote_target=str(fields["remote_target"]),
        route_set=route_set,
        local_cseq=int(cast(str | int, fields["local_cseq"])),
        remote_cseq=int(cast(str | int, fields["remote_cseq"])),
    )


@dataclass(frozen=True, slots=True)
class SipStackServiceConfig:
    """Configuration for :class:`SipStackService`."""

    recovery_case: str
    accept_all_invites: bool
    recovery_call_keys: tuple[str, ...]
    enable_native_restore_on_start: bool
    listen: SipListenConfig


class SipStackService:
    """Owns the product runtime listener, controller, and post-restart recovery."""

    def __init__(
        self,
        *,
        active_calls: ActiveCallSource,
        repository: CallStateCheckpointRepository,
        config: SipStackServiceConfig,
        gate: TransportIngressGate | None = None,
        rules: RuleSet | None = None,
        call_controller: CallController | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        """Wire runtime listener, checkpoint repository, and recovery coordinator."""
        self._active_calls = active_calls
        self._repository = repository
        self._config = config
        self._gate = gate or TransportIngressGate(load_transport_seam_from_env())
        self._rules = rules if rules is not None else RuleSet(rules=())
        self._call_controller = call_controller or CallController()
        self._now = now or time.time
        self._listener: ResipRuntimeListener | None = None
        self._recovery = CallStateRecovery(repository)
        self._coordinator = RecoveryCoordinator(self._recovery)
        self._restore_lock = threading.Lock()
        self._last_committed_checkpoints: dict[str, CallStateCheckpoint] = {}
        self._last_adapter_paths: dict[str, Path] = {}

    @classmethod
    def from_env(cls, active_calls: ActiveCallSource) -> SipStackService | None:
        """Build a service when ``AS_ENABLE_SIP_RUNTIME=1``; otherwise return ``None``."""
        if not _env_flag("AS_ENABLE_SIP_RUNTIME"):
            return None
        if load_resip_runtime_extension() is None:
            raise RuntimeError(
                "AS_ENABLE_SIP_RUNTIME=1 but _resip_runtime is not built; "
                "run make m2-platform-resip-build"
            )

        redis_store = load_redis_store_from_env(time.time)
        if redis_store is not None:
            store: StateStore = redis_store
        else:
            store = InMemoryStateStore(now=time.time)

        rules = load_ruleset_from_env()
        listen = load_sip_listen_config_from_env()
        gate = TransportIngressGate(load_transport_seam_from_env())
        config = SipStackServiceConfig(
            recovery_case=os.environ.get("AS_RECOVERY_CASE", _DEFAULT_RECOVERY_CASE).strip()
            or _DEFAULT_RECOVERY_CASE,
            accept_all_invites=_env_flag("AS_SIP_ACCEPT_ALL_INVITES"),
            recovery_call_keys=_recovery_call_keys(),
            enable_native_restore_on_start=_env_flag("AS_RECOVERY_NATIVE_ON_START", default=True),
            listen=listen,
        )
        return cls(
            active_calls=active_calls,
            repository=_checkpoint_repository(store),
            config=config,
            gate=gate,
            rules=rules if rules is not None else RuleSet(rules=()),
        )

    @property
    def call_controller(self) -> CallController:
        """The in-process cross-leg controller owned by the runtime listener."""
        if self._listener is None:
            return self._call_controller
        return self._listener.call_controller

    @property
    def listen_port(self) -> int:
        """UDP listen port after :meth:`start`."""
        if self._listener is None:
            raise RuntimeError("SipStackService is not started")
        return self._listener.port

    def committed_checkpoint(self, call_key: str) -> CallStateCheckpoint | None:
        """Return the last committed checkpoint for ``call_key`` (tests / harness)."""
        return self._last_committed_checkpoints.get(call_key)

    def adapter_path_for(self, call_key: str) -> Path | None:
        """Return the on-disk native adapter written at establish time, if any."""
        return self._last_adapter_paths.get(call_key)

    def rewrite_uas_local_tag(self, call_key: str, local_tag: str) -> CallStateCheckpoint:
        """Replace the UAS local tag on a committed checkpoint (harness seam)."""
        existing = self._last_committed_checkpoints.get(call_key)
        if existing is None:
            msg = f"no committed checkpoint for call_key={call_key!r}"
            raise KeyError(msg)
        uas = existing.uas_leg
        updated = CallStateCheckpoint(
            state="established",
            uas_leg=DialogLegCheckpoint(
                call_id=uas.call_id,
                local_tag=local_tag,
                remote_tag=uas.remote_tag,
                local_uri=uas.local_uri,
                remote_uri=uas.remote_uri,
                remote_target=uas.remote_target,
                route_set=uas.route_set,
                local_cseq=uas.local_cseq,
                remote_cseq=uas.remote_cseq,
            ),
            uac_leg=existing.uac_leg,
            extensions=existing.extensions,
            owner_generation=existing.owner_generation,
            committed=existing.committed,
        )
        self._repository.save(
            case=self._config.recovery_case,
            call_key=call_key,
            checkpoint=updated,
        )
        self._last_committed_checkpoints[call_key] = updated
        from as_platform.sip.resip_recovery import write_native_adapter

        adapter_path = self._last_adapter_paths.get(call_key)
        if adapter_path is not None:
            write_native_adapter(adapter_path, updated)
        return updated

    def _on_dialog_established(self, fields: dict[str, object]) -> None:
        uas_leg = _leg_from_established_fields(fields)
        uac_raw = fields.get("uac_leg")
        if isinstance(uac_raw, dict):
            uac_leg = _leg_from_established_fields(uac_raw)
        else:
            peer_contact = str(fields.get("peer_contact", uas_leg.remote_target))
            token = uuid.uuid4().hex[:8]
            host = self._config.listen.advertised_address
            uac_call_id = f"d10-harness-uac-{token}@{host}"
            uac_leg = DialogLegCheckpoint(
                call_id=uac_call_id,
                local_tag="as-uac-local",
                remote_tag="peer-remote",
                local_uri=uas_leg.local_uri,
                remote_uri=peer_contact,
                remote_target=peer_contact,
                route_set=(),
                local_cseq=3,
                remote_cseq=1,
            )
        token = uuid.uuid4().hex[:8]
        pending = CallStateCheckpoint(
            state="established",
            uas_leg=uas_leg,
            uac_leg=uac_leg,
            committed=False,
        )
        committed = CallCheckpointCommit(pending).mark_committed()
        call_key = uas_leg.call_id
        self._repository.save(
            case=self._config.recovery_case,
            call_key=call_key,
            checkpoint=committed,
        )
        self._call_controller.restore_from_checkpoint(committed)
        self._last_committed_checkpoints[call_key] = committed
        from as_platform.sip.resip_recovery import write_native_adapter

        adapter_dir = Path(os.environ.get("TMPDIR", "/tmp")) / f"as-established-{token}"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        adapter_path = adapter_dir / "checkpoint.fields"
        write_native_adapter(adapter_path, committed)
        self._last_adapter_paths[call_key] = adapter_path
        self._active_calls.increment()
        logging.info("checkpoint committed for call_key=%s", call_key)

    def _on_dialog_terminated(self, call_id: str) -> None:
        self._active_calls.decrement()
        logging.info("dialog terminated call_id=%s", call_id)

    def _handle_restore_result(self, result: ProcessStartRestoreResult) -> None:
        with self._restore_lock:
            for item in result.loaded:
                self._call_controller.restore_from_checkpoint(item.checkpoint)
                self._last_committed_checkpoints[item.call_key] = item.checkpoint
            if result.missing_call_keys:
                logging.warning(
                    "recovery missing call keys: %s",
                    ",".join(result.missing_call_keys),
                )

    def start(self) -> None:
        """Start the runtime listener and schedule post-restart checkpoint restore."""
        if self._listener is not None:
            raise RuntimeError("SipStackService is already started")

        self._listener = ResipRuntimeListener(
            self._gate,
            self._rules,
            accept_all_invites=self._config.accept_all_invites,
            call_controller=self._call_controller,
            received_at=self._now,
            bind_address=self._config.listen.bind_address,
            advertised_address=self._config.listen.advertised_address,
            on_dialog_established=self._on_dialog_established,
            on_dialog_terminated=self._on_dialog_terminated
            if self._config.accept_all_invites
            else None,
            on_connection_closed=self._gate.unregister_connection,
        )
        self._listener.start()

        if self._config.recovery_call_keys and self._config.enable_native_restore_on_start:
            keys = self._config.recovery_call_keys
            self._coordinator.schedule_restore(
                self._config.recovery_case,
                keys,
                self._handle_restore_result,
            )

    def stop(self) -> None:
        """Stop listener, recovery sessions, and the coordinator worker pool."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._recovery.stop_native_recovery_sessions()
        self._coordinator.shutdown(wait=True)
