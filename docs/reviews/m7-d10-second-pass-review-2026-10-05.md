# M7.1–M7.6 D10 product slices — second-pass review (2026-10-05)

> **Subject:** Independent second-pass review of M7 D10 **engineering slices** (RecoveryTU, coordinator, CallController restore, checkpoint v2, lifecycle, product integration)  
> **Authority:** [`plan.md`](../plan.md) §5 D10 M7 TODO (checkboxes M7.1–M7.6); honesty baseline [`m7-d10-status-2026-10-05.md`](m7-d10-status-2026-10-05.md)

## Verification (this pass)

| Command | Result |
|---------|--------|
| `make gate` | **Pass** (941 unit/contract; 2 unrelated skips) |
| `make m7-platform-recovery-build` | **Pass** after `addTransport` / `Transport::port()` fix |
| `uv run pytest platform/tests/test_d10_product_recovery_integration.py platform/tests/test_call_controller_recovery.py -q` | **Pass** (3 tests; integration after Via-echo fix) |

## Fixes applied (major)

| Issue | Fix |
|-------|-----|
| `platform/native/resip_recovery/recovery_module.cxx` did not compile (`addTransport` returns `Transport*`, not `int`) | Match `resip_runtime` pattern: null-check transport, bind port via `udpTransport->port()` |
| M7.6 integration peer 200 OK used a hardcoded `Via` branch | Echo all `Via` headers from the received downstream BYE (same shape as testbed `makePeerResponse`) |
| `NATIVE_ON_PROCESS_START_RESTORE_IMPLEMENTED` was set to `_native_recovery_built()` | Reset to **`False`**: `RecoveryStackSession` restores RecoveryTU from a checkpoint file, but `CallStateRecovery.on_process_start_restore` is still Redis load only and is **not** wired to native restart |

---

## Standards

Judgement against [`CONTRIBUTING.md`](../../CONTRIBUTING.md) / [`AGENT.md`](../../AGENT.md) (gate, typing, workspace layout) and Fowler smell baseline where repo docs are silent.

| # | Finding | Severity | Notes |
|---|---------|----------|-------|
| S1 | Native recovery build was broken on current reSIProcate `SipStack::addTransport` signature | **Major** (fixed) | Would skip M7.1/M7.6 evidence in CI/job that builds recovery |
| S2 | `CallCheckpointLifecycle` reads `repository._store` / `_ttl_seconds` (private repository fields) | Minor | Works; prefer a small repository accessor if lifecycle grows |
| S3 | `ScheduledRestoreHandle.done` is always `False` | Minor | Name suggests completion tracking; harmless for current tests |
| S4 | `recovery_coordinator` invokes `on_restored` on the worker thread (not main/SIP thread) | Info | Documented; callers must not recurse into blocking SIP from callback |
| S5 | Slice code matches existing platform patterns: dataclasses, typed checkpoints, ADR-0023 comments, `pytest.mark` unit/contract/integration | Info | **Pass** |
| S6 | `make gate` green; no secrets in recovery adapter temp files (under `tempfile.mkdtemp`, unlinked on `stop`) | Info | **Pass** |

**Standards summary:** One **major** build/integration honesty gap found and fixed. Remaining items are minor API/documentation smells; no additional code changes required for this pass.

---

## Spec (vs [`plan.md`](../plan.md) §5 M7.1–M7.6)

Plan checkboxes (all marked `[x]` as **engineering slices**; D10 maintainer acceptance **still pending** per plan and [`m7-d10-status-2026-10-05.md`](m7-d10-status-2026-10-05.md)).

### M7.1 — 产品恢复接入

| Plan bullet | Implementation | Verdict |
|-------------|----------------|---------|
| `platform/native/resip_recovery/` + `RecoveryStackSession` | Native `RecoveryTu` TransactionUser loads `d10-native-checkpoint-v1` fields; Python wrapper starts stack, pumps `process`, exposes BYE path flags | **Met** (engineering) |
| Full DUM dialog rehydrate / product `_resip_runtime` on restart | Not wired; RecoveryTU matches testbed narrow BYE-forwarding seam | **Partial** (expected for slice) |

### M7.2 — 非阻塞恢复读取

| Plan bullet | Implementation | Verdict |
|-------------|----------------|---------|
| `recovery_coordinator.py` + unit tests | `ThreadPoolExecutor` posts `CallStateRecovery.on_process_start_restore`; slow-load test proves callback not on caller thread | **Met** |
| Redis in SIP callback | Avoided on scheduled path | **Met** |

### M7.3 — CallController context restoration

| Plan bullet | Implementation | Verdict |
|-------------|----------------|---------|
| `restore_from_checkpoint` / `route_in_dialog_bye` | Rebuilds FORWARD correlation and `route_target` from `uac_leg.remote_target`; unit tests | **Met** |
| Wired into live runtime on process start | Not present | **Out of slice** |

### M7.4 — owner 与提交安全

| Plan bullet | Implementation | Verdict |
|-------------|----------------|---------|
| Schema v2 + `CallCheckpointCommit` / `save_if_generation` | `owner_generation` / `committed` on encode-decode; v1 round-trip defaults; CAS on generation | **Met** |
| Enforced on native BYE path | Helpers only; RecoveryTU does not call `require_committed_before_side_effect` | **Partial** (seam) |

### M7.5 — checkpoint 生命周期

| Plan bullet | Implementation | Verdict |
|-------------|----------------|---------|
| `CallCheckpointLifecycle` renew / terminal delete | `renew` via `StateStore.expire`; `mark_terminal_and_delete`; contract tests | **Met** |

### M7.6 — D10 产品集成测试

| Plan bullet | Implementation | Verdict |
|-------------|----------------|---------|
| `test_d10_product_recovery_integration.py` | Loopback upstream BYE → RecoveryTU → peer BYE → 200 → upstream 200; `-m integration`; skips without native build | **Met** after this pass |
| REQ-NF-1 / full test-plan D10 (kill/restart AS, real Redis, maintainer sign-off) | Explicitly **not** claimed; M7.6 does not exercise coordinator, CallController, or Redis restart orchestration | **Not met** (milestone; by design) |

**Spec summary:** All six **engineering slice** checkboxes are substantiated in-repo. **D10 / REQ-NF-1 remain open** — slices are intentionally disjoint until product adapter wires coordinator → controller → native/runtime on restart.

---

## Recommendation

**Accept** M7.1–M7.6 as **engineering slices** with the fixes above recorded. **Do not** treat this second pass as D10 closure, REQ-NF-1 satisfaction, or M7 milestone exit.

## Sign-off

- Second-pass review recorded: 2026-10-05  
- Maintainer D10 / M7 sign-off: **not requested** (unchanged)
