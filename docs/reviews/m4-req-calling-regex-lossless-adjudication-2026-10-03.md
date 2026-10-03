# M4 REQ: Rule match axis & console scope (Maintainer adjudication)

> **Date:** 2026-10-03  
> **Status:** **Accepted** (maintainer confirmed in chat; agent recorded)  
> **Does not** close M4/M4b/REQ acceptance by itself.

## Decisions

| # | Topic | Decision |
|---|--------|----------|
| 1 | **Match axis** | Align with **REQ-F-6 / REQ-F-7** and kernel: routing, block, and translate rules match the **called** number (Request-URI target). PRD user-story wording that implied **calling-party** match is corrected (US-2). |
| 2 | **M4 console scope** | **Called party + prefix** only. **Calling-party** and **regex** match modes are **v1.1** (out of M4 acceptance); live console hides/disables those choices. |
| 3 | **“Lossless”** | **Not a separate M4 maintainer gate.** For M4: activated `ConfigBundle` must match what the operator entered for **called + prefix** fields (no silent rewrite). Compiler rejections for unsupported shapes remain an implementation guard ([ADR-0025](../architecture/adr/0025-managed-rule-runtime-bundle.md)); disabling a rule and redistributing is normal **refresh**, not a “lossless” test case. |

## M4b-8 step matrix (after this adjudication)

| Step | Status |
|------|--------|
| 1 Rule CRUD (F-12) | **Runnable** for **called + prefix** on dev HTTPS; not blocked by calling/regex |
| 2 Approval (F-14) | Runnable |
| 3 Trace (F-13) | **BLOCKED** (7.4 deferred) |
| 4 Distribution (F-15) | **PARTIAL** (API + fleet UI; full browser distribution / AS load 补测) |
| 5 Audit (S-4) | Runnable in scope of 1–2 |
| 7.2d production preflight | **BLOCKED** (M5) |

## References

- PRD: `docs/requirements/prd.md` (US-2, REQ-F-12 M4 note, §2.6 gap row)
- Test plan: `docs/acceptance/test-plan.md` §1.4 intro + REQ-F-12
- Runbook: `docs/acceptance/m4b-8-runbook.md`

## Maintainer signoff

| Field | Value |
|-------|--------|
| Adjudication | Accepted 2026-10-03 |
| Maintainer | Approved; recorded by AI agent per maintainer authorization in chat (2026-10-03). REQ scope: called+prefix M4; no separate “lossless” gate. |
