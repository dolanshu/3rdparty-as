# Migration triage — how POC code enters this repository

**Nothing is copied in wholesale.** The POC (`3rtparty_AS_POC`, ~24 kLOC
including tests and tools) and the extracted library (`as_platform`, ~4.2 kLOC)
were built to prove a concept, under non-goals that the product explicitly does
not share: no HA, no persistence, no capacity target, no managed configuration.
Adopting a file because it exists is exactly how the product inherits those
non-goals with the code.

Every file that crosses over is triaged first. The output of triage is a
verdict per file, with evidence.

## 1. Sequence — snapshot before you touch anything

1. **Freeze the POC.** Record the commit of `3rtparty_AS_POC` and `as_platform`
   that this triage was made against. The POC does not change while the product
   is being built; if it must, the triage is re-run for the affected files.
2. **Capture the behaviour baseline.** Before any file is rewritten, capture what
   the POC actually does: real message samples, end-to-end call traces, and the
   observed sippy behaviour the code depends on. A rewrite is only allowed to
   claim "equivalent" against this baseline, never against memory.
3. **Inventory and classify** every file, using §3.
4. **Only then write code** into `platform/`, `apps/`, `services/`, `testbed/`.

Steps 1 and 2 are not optional. Without a baseline, "the rewrite behaves the
same" is an assertion no one can check.

## 2. The four verdicts

| Verdict | Meaning | Burden of proof |
|---|---|---|
| **A — adopt** | The file matches the target architecture and its behaviour is already verified by tests | Existing tests must pass here unchanged, or be re-written to prove the same behaviour |
| **B — rewrite, concept kept** | The idea survives; the implementation violates a product constraint (statefulness, blocking, no versioning, no audit) | Name the constraint and the ADR that imposes it |
| **C — baseline reference only** | The code is not adopted. It is read to recover behaviour that must be reproduced | The recovered behaviour must become a contract case or a test |
| **D — discard** | Nothing to carry over | One line stating why |

A file with no verdict does not move. A verdict with no evidence is not a verdict.

## 3. Inventory and opening classification

Sizes are as measured at triage time. **The classification column is an opening
proposal, derived from the POC's `AGENT.md`, its ADRs and
[`../architecture/新系统整体架构.md`](../architecture/新系统整体架构.md) — it is not
a file-by-file review.** Each row is confirmed or overturned during M1, which is
why M1 does not write product code.

### `as_platform/` → `platform/` (~4.2 kLOC)

| File | LOC | Verdict | Why |
|---|---|---|---|
| `call_controller.py` | 1030 | C | The B2BUA state machine is the deepest coupling to sippy and to in-process state. §6.2 states outright that sippy's transaction state cannot be serialised or migrated, so the product's draining model has to be built around it, not on top of it. Recover behaviour, then rewrite. |
| `internal_api.py` | 497 | B | The surface becomes the language-agnostic contract (`/healthz`, `/metrics`, `/traces`) in ADR-0012. Shape survives, payloads do not. |
| `observability/tracing.py` | 347 | B | Call trace becomes a product capability queried by Call-ID, with retention (ADR-0005); the in-memory ring does not survive. |
| `state_store.py` | 334 | B | The `StateStore` seam is the right idea and stays. `InMemoryStateStore` does not: §7 requires Redis with Sentinel, and ADR-0002 forbids per-process session state. |
| `main.py` | 357 | B | Process shell survives; it gains draining, version reporting and non-blocking export (ADR-0009, ADR-0005). |
| `transport.py` | 239 | B | UDP plus a `TlsTransport` that only reached the listening side. ADR-0016 requires end-to-end TLS with rotation that does not restart the process. |
| `observability/logging.py` | 193 | B | Structured fields survive; the emitter becomes OTel logs. |
| `observability/metrics.py` | 179 | B | `MetricsRegistry` is an in-process view, useless behind N replicas. Gains `active_calls` and `cps`, which HPA also needs (ADR-0010). |
| `capacity_harness.py` | 195 | C | Drives callbacks, not sockets. ADR-0014: a harness that bypasses the socket and the event loop measures business logic, not capacity. |
| `errors.py` | 163 | A | The memberless `ErrorCode` mechanism over per-family subclasses is already the model the product wants. |
| `sip_adapter.py` | 244 | B | Keeps sippy confined to one module, which is exactly right. Re-argued against the dual-stack decision (ADR-0011). |
| `bootstrap.py` | 111 | B | Startup self-check survives and is extended (state store reachability, rule version). |
| `version.py` | 102 | D | Per-component version files are the drift ADR-0018 removes. |
| `route_header.py` | 84 | A | Small, RFC-derived, testable. Verify against observed behaviour. |
| `hop.py` | 53 | A | `NextHop` value object, no product constraint touches it. |
| `observability/__init__.py` | 21 | A | — |
| `__init__.py` | 59 | B | Re-exports only; rebuilt for the new package surface. |

### `src/as_app/` → `apps/translation/` (~2.3 kLOC)

| File | LOC | Verdict | Why |
|---|---|---|---|
| `call_controller.py` | 527 | C | Thin glue over the kernel state machine; rewritten with it. |
| `internal_api.py` | 388 | B | See kernel `internal_api.py`. |
| `main.py` | 331 | B | Process shell for one use case. |
| `routing/rules.py` | 371 | B | Loading and hot reload are right; the source of truth moves to config-service with versions and a compatibility matrix (ADR-0006, R4). |
| `routing/engine.py` | 220 | **A** | Pure functions, no sockets, no clock — exactly the shape TDD is mandated for. Adopt with its tests. |
| `bootstrap.py` | 164 | B | See kernel `bootstrap.py`. |
| `observability/*` | ~147 | D | Re-export facades that existed only to bridge two repositories. The monorepo makes them meaningless. |
| `errors.py` | 63 | A | The `AS-RULE-*` / `AS-ROUTE-*` family. |
| `route_header.py` | 61 | D | Duplicates the kernel's; one copy only. |
| `sip_adapter.py` | 47 | D | Re-export facade, same reason as `observability/*`. |
| `__init__.py` | 84 | B | — |

### `src/anti_fraud_as/` → `apps/anti-fraud/` (~2.6 kLOC)

| File | LOC | Verdict | Why |
|---|---|---|---|
| `call_controller.py` | 601 | C | The verdict seam is the right concept; the leg handling is rewritten with the kernel. |
| `internal_api.py` | 394 | B | See above. |
| `main.py` | 357 | B | — |
| `screening_data.py` | 405 | B | The declarative model survives; the schema must be versioned with a compatibility matrix (R4). |
| `caller_state.py` | 352 | B | Rate windows and reputation decay move out of process memory into Redis (ADR-0002, R5). |
| `screening.py` | 180 | **A** | The pure verdict function. Adopt with its tests; it is the highest-value TDD target in the tree. |
| `bootstrap.py` | 157 | B | — |
| `errors.py` | 60 | A | The `AS-FRAUD-*` family. |
| `route_header.py` | 61 | D | Duplicate. |
| `__init__.py` | 33 | B | — |

### `src/console/` → `services/console/` (~1 kLOC)

| File | LOC | Verdict | Why |
|---|---|---|---|
| `main.py` | 990 | C | Read-only, no authentication, inline HTML/CSS/JS with a vendored Chart.js. The product console is read-write behind SSO with full audit (ADR-0016). Recover the operator-facing behaviours as acceptance items; the page is rebuilt. |

### `src/s_sbc_mock/`, `src/ims_mock/` → `testbed/simulators/` (~2.2 kLOC)

| File | LOC | Verdict | Why |
|---|---|---|---|
| `s_sbc_mock/uac.py` | 488 | B | Promoted to a simulated S-SBC; must model transparent bridging, which the AS relies on (ADR-0003). |
| `s_sbc_mock/main.py` + `uas.py` | 612 | B | Same, return side. |
| `ims_mock/chained_stack.py` | 427 | B | The iFC chain simulator. A first-class asset: without it integration tests have nowhere to run (ADR-0014). |
| remaining `ims_mock/*` | ~523 | B | Orchestrator, P-CSCF relay, terminating UAS — promoted with the chain. |

### `tools/` (~4.8 kLOC) and `tests/` (~11.1 kLOC)

| Group | Verdict | Why |
|---|---|---|
| `tools/capacity_probe.py`, `tools/call_load_generator.py` | C | The measurement method has to change (real sockets). Keep to recover what was learned; do not carry the harness forward as-is. |
| `tools/capture_call.py`, `tools/sippy_probe.py` | A | Probe and capture utilities: observation tools, not product shape. |
| `tools/demo_*.py`, `tools/anti_fraud_probe.py`, `tools/chained_*` | D | Demo scripts for a POC narration. |
| `tools/path_dependency_probe.py` | D | Existed only to diagnose the two-repository `path` dependency, which the monorepo removes. |
| `tests/**` | C | 11 kLOC of tests are the cheapest record of what the POC actually did — treat them as the behaviour baseline, then re-derive the ones that still apply. Never copied in bulk. |

## 4. Rules that bind the triage

1. **Verdict before code.** A pull request that adds product code must be able to
   point at the triage row it implements.
2. **Adopted code arrives with its tests.** Verdict A without tests is verdict C.
3. **sippy behaviour is observed, never assumed.** Where the POC encodes a sippy
   behaviour, the product proves it again with a probe under `testbed/`.
4. **No file is adopted "for now".** A temporary adoption with a TODO is a
   permanent adoption with a stale TODO.
5. **Every discard is recorded.** A file that simply never appears in the new
   repository is indistinguishable from one someone forgot.
6. **The POC is not a dependency.** This repository must build, test and run with
   no reference to `../3rtparty_AS_POC` or `../as_platform`. The two-repository
   `path` dependency was one of the three defects the monorepo exists to remove.
