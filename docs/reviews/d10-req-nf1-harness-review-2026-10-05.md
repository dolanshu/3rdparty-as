# D10 REQ-NF-1 engineering harness review (2026-10-05)

> **Scope:** `test_d10_req_nf1_harness_integration.py`, `scripts/d10-req-nf1-harness.sh`  
> **Not:** Maintainer REQ-NF-1 sign-off or full `test-plan.md` D10 baseline

## Commands

```bash
make m2-platform-resip-build m7-platform-recovery-build
uv run pytest platform/tests/test_d10_req_nf1_harness_integration.py -m integration -q
bash scripts/d10-req-nf1-harness.sh
```

## Result

Pass (local 2026-10-05): establish via `SipStackService` → committed checkpoint → coordinator restore → fresh `RecoveryStackSession` → upstream BYE → downstream 200.

## Gaps vs test-plan D10

- In-memory store (not production Redis) in default harness path
- Synthetic UAC leg + harness tag rewrite (not full product B2BUA establish)
- No maintainer kill/restart AS orchestration

## Recommendation

**Accept** as engineering harness evidence. **Deny** REQ-NF-1 / D10 milestone closure.
