# ADR register

Architecture decision records for `3rdparty-as`. The design they record is
[`../新系统整体架构.md`](../新系统整体架构.md); the table below maps each confirmed
decision in that document's §0 ledger to the ADR that carries its context,
consequences and accepted gaps.

**Status legend** — `skeleton`: the decision is confirmed but the ADR is not
written yet; `draft`: written, not reviewed; `accepted`: reviewed and binding.

An ADR is written **with** the change it authorises, not after it, and not in a
batch at the end. A decision without an ADR is a decision that will be re-litigated.

## The register

| ADR | Decision | §0 | Status |
|---|---|---|---|
| [0000](0000-adr-template.md) | the template every ADR below uses | — | accepted |
| 0001 | Single monorepo + uv workspace; POC and `as_platform` merged in | 3 | skeleton |
| 0002 | Runtime model: one process per use case, state externalised to Redis | 2 | skeleton |
| 0003 | Single ISC access semantic — S-SBC is a transparent bridge, not a second business semantic | 10 | skeleton |
| 0004 | No media; a media seam is reserved with an explicit trigger condition | 11 | skeleton |
| 0005 | OTel three signals, backend-neutral, export must never block the call path; call trace keeps an independent query channel | 12 | skeleton |
| 0006 | Configuration governance: PostgreSQL version repository + change-order state machine, not GitOps | 13 | skeleton |
| 0007 | Data plane split: Redis for run state, PostgreSQL for governance state | 14 | skeleton |
| 0008 | Redundancy: in-site N+1 with no single point; cross-site 1+1 warm standby, not active-active | 7 | skeleton |
| 0009 | ISSU is draining, not in-flight state migration | §6.2 | skeleton |
| 0010 | Scaling: custom-metric HPA plus a scale-down protection controller | 15 | skeleton |
| 0011 | SIP stack: dual-stack, `sippy` holds production, `go-b2bua` on probation | 8 | skeleton |
| 0012 | Language-agnostic contracts and cross-implementation comparison as the promotion gate | 9 | skeleton |
| 0013 | Helm is the only production form; compose is a developer environment | 6 | skeleton |
| 0014 | Three-layer testbed; real-socket load; not a v1 deliverable | 16 | skeleton |
| 0015 | Development model: layered TDD, institutionalised ADRs, four CI gates | 17 | skeleton |
| 0016 | Security inside the boundary: peer allowlist, end-to-end TLS, console authz, full audit. No LI, no charging | 18 | skeleton |
| 0017 | No CDR: no collection, no delivery channel, no archive — call trace replaces it | 4 | skeleton |
| 0018 | One product release version, independent component interface versions | §11.3 | skeleton |

## Rules

- **Numbering is append-only.** A superseded ADR keeps its number and is marked
  superseded by the newer one; numbers are never reused or renumbered.
- **One decision per ADR.** "Architecture" is not a decision.
- **An ADR states what it accepts.** The gaps it knowingly accepts are part of the
  record; an ADR with no consequences section is propaganda.
- **Code points at its ADR.** A non-obvious line carries `# See ADR-00NN` so a
  reviewer moves from code to rationale in one step.
- **Reversing a decision** means writing a new ADR and updating
  [`../新系统整体架构.md`](../新系统整体架构.md) in the same change.

## Relationship to the POC ADRs

The POC carried ADR-0001 … ADR-0016 in `3rtparty_AS_POC/docs/architecture/adr/`.
They are **not** imported. They record decisions about a proof of concept — a
different system with different non-goals. Where a POC decision survives into the
product it is re-argued here against product constraints and the POC original is
cited as context. Where it does not survive, it is simply absent, and the
migration triage ([`../../migration/triage.md`](../../migration/triage.md)) records
why.
