# D8 REQ-NF-15 testbed / performance traceability review (2026-10-05)

> **Scope:** Close plan §5.2 **D8** by adding PRD trace for [ADR-0014](../architecture/adr/0014-three-layer-testbed.md)  
> **Not:** M6 milestone maintainer sign-off or public O1 / SLA publication

## Problem (D8)

ADR-0014 header and Evidence historically pointed at **REQ-NF-13** (OTel), which ADR-0005 already owns. PRD had no requirement for three-layer testbed structure or real-socket capacity research harness.

## Delivered

| Artifact | Role |
|----------|------|
| [`req-nf-15-testbed-performance.md`](../requirements/req-nf-15-testbed-performance.md) | Normative REQ-NF-15 text |
| [`prd.md`](../requirements/prd.md) §3 | PRD index entry + link |
| [`test-plan.md`](../acceptance/test-plan.md) §2-REQ-NF-15 | Acceptance checklist (engineering) |
| ADR-0014 `回应 REQ` | Updated to REQ-NF-15 |
| [`adr/README.md`](../architecture/adr/README.md) | Registry note on 0014 → NF-15 |

## Standards check

- **AGENT.md §6:** `performance` layer tied to real socket — REQ-NF-15 restates load-layer obligation without claiming shipped capacity.
- **REQ-G-2:** Requirement → ADR → harness code path is traceable (`testbed/load/`, ADR-0014).
- **Tests:** Existing `as_load` integration tests carry `integration` marker; formal REQ acceptance remains checklist-based for M8, not all green today.

## Gaps (explicit)

- REQ-NF-15 does not assert operator-facing capacity targets (O1 still a plan open item for **targets**, not harness existence).
- Full `performance` CI layer blocking and cluster-scale measurement are out of scope for this D8 close.

## Recommendation

**Accept** D8 closure via REQ-NF-15. **Deny** using this alone as M6 milestone exit or marketing capacity publication.

## Sign-off

- Review recorded: 2026-10-05  
- Maintainer REQ-NF-15 acceptance: **pending** (engineering traceability only)
