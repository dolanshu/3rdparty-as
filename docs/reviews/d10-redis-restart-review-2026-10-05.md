# D10 Redis + process restart review (2026-10-05)

> **Scope:** `test_d10_req_nf1_redis_integration.py`, `test_d10_process_restart_integration.py`, `runtime/_d10_child.py`  
> **Not:** Maintainer REQ-NF-1 sign-off or full `test-plan.md` D10 baseline

## Commands

```bash
make m2-platform-resip-build m7-platform-recovery-build
# optional: docker run -p 6379:6379 redis:7
export AS_REDIS_URL=redis://127.0.0.1:6379/15
uv run pytest platform/tests/test_d10_req_nf1_redis_integration.py \
  platform/tests/test_d10_process_restart_integration.py -m integration -q
```

## Result

Pass (local 2026-10-05, Redis 7 via `docker run -p 6379:6379 redis:7`, native extensions built).

| Test | Flow |
|------|------|
| Redis integration | `SipStackService` establish → `RedisStateStore` + repository save → `CallStateRecovery` restore → `RecoveryStackSession` BYE → peer 200 |
| Process restart | `_d10_child` subprocess establish → Redis checkpoint fix-up → SIGKILL → child with `AS_RECOVERY_CALL_KEYS` → BYE on RecoveryTU port → upstream 200 |

## Gaps vs test-plan D10

- Harness tag rewrite and synthetic UAC leg target (same seam as in-memory harness)
- Subprocess child is not `python -m as_platform` full process shell (drain/metrics/health omitted)
- No maintainer kill/restart orchestration or unified single-listener product model
- Fresh-DUM 481 research baseline for non-RecoveryTU paths unchanged

## Recommendation

**Accept** as engineering evidence toward REQ-NF-1. **Deny** REQ-NF-1 / D10 milestone closure.
