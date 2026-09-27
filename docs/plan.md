# Plan — `3rdparty-as`

Productised third-party IMS Application Server. Single-tenant, on-premises
delivery, deployed outside the operator's network and triggered by the S-CSCF
through the operator's S-SBC.

The design baseline is [`architecture/新系统整体架构.md`](architecture/新系统整体架构.md).
This document is the plan built on it.

---

## 0. Status of this plan

| | |
|---|---|
| Step now in progress | **M0 — repository skeleton** |
| Design baseline | confirmed (`architecture/新系统整体架构.md`, decisions 1–18) |
| Open items that gate later milestones | §5 |
| Migration of POC code | **deliberately deferred** to M1–M3, and gated by [`migration/triage.md`](migration/triage.md) |

---

## 1. Decisions taken for this step

Confirmed with the maintainer before anything was created:

| # | Decision |
|---|---|
| 1 | New repository `3rdparty-as`, created on the maintainer's machine. Fresh git history — the POC's history is **not** imported. |
| 2 | POC code is **not bulk-imported**. The stack changes and the architecture is reorganised, so every file is triaged first ([`migration/triage.md`](migration/triage.md)) to avoid inheriting POC-era compromises with the code. |
| 3 | M0 delivers the skeleton only: directory structure, `pyproject.toml` + uv workspace, CI, `AGENT.md`, the ADR register, and the structural guards. Structure is reviewed **before** code moves. |
| 4 | **O1 (capacity targets) gets its own research phase.** It is not assumed here and does not gate the skeleton. The Go migration and the HPA thresholds are decided after that research, not before. |

---

## 2. What the skeleton delivers

### 2.1 Structure

```
3rdparty-as/
├── AGENT.md  README.md  CHANGELOG.md  VERSION  CONTRIBUTING.md
├── CODE_OF_CONDUCT.md  SECURITY.md  NOTICE  LICENSE  Makefile
├── pyproject.toml            workspace root — virtual manifest, one tool config
├── platform/                 ② kernel: shell, state machine, decide() seam, seams
├── apps/                     ① signalling plane: translation/, anti-fraud/
├── services/                 ③ control plane: config-service/, console/
├── testbed/                  ⑥ contracts/ (data) · simulators/ · load/
├── deploy/                   helm/ (production) · compose/ (dev only)
├── docs/                     architecture/ · adr/ · migration/ · plan.md
└── tests/                    cross-cutting structural guards
```

### 2.2 The three POC defects this structure removes, and how

| POC defect | Mechanism here |
|---|---|
| CI had to `git clone ../as_platform` in every job | one repository, one `uv sync`, no sibling checkout |
| `deploy/Dockerfile.as` failed: build context outside the repo | everything is under one root |
| `VERSION` 0.2.0 vs `pyproject` 0.1.0 | `tests/test_version_consistency.py` — one home per number, asserted |

### 2.3 Guards that ship with the skeleton

The layering is not protected by the directory layout — inside a monorepo every
import resolves. It is protected by tests:

| Guard | Asserts |
|---|---|
| `platform/tests/test_library_independence.py` | the kernel imports no app, service or testbed package; the forbidden list covers every other workspace member |
| `tests/test_workspace_layout.py` | declared members exist, one package each under `src/`, unique distribution names, ruff `src` is complete, no member declares its own tool config, no member owns a `VERSION` file |
| `tests/test_version_consistency.py` | `VERSION` is a SemVer, the newest CHANGELOG heading equals it, every component version is a SemVer |

### 2.4 Four-layer CI gate (ADR-0015)

| Layer | Marker | Runs on |
|---|---|---|
| ① fast | `unit or contract` | every push and PR |
| ② integration | `integration` | after ① |
| ③ e2e | `e2e` | after ② |
| ④ performance | `performance` | nightly, tags, manual |

**Known skeleton exception:** layers ② ③ ④ carry `continue-on-error` because no
tests of those kinds exist yet. They must be made blocking in the milestone that
first adds a test of that kind. Tracked as an exit criterion of M2/M3/M6.

---

## 3. Exit criteria for M0

- [x] Directory structure created and each directory carries a README stating what belongs there
- [x] `pyproject.toml` workspace with seven members; `uv sync` resolves
- [x] `make gate` green: `ruff format --check`, `ruff check`, `mypy`, pytest
- [x] Three structural guards written and passing
- [x] `AGENT.md` — rules of engagement for the product, not the POC
- [x] ADR register: 18 decisions mapped to ADR numbers, template in place
- [x] `docs/migration/triage.md` — inventory and opening classification
- [x] Four-layer CI workflow
- [ ] **Structure reviewed and signed off by the maintainer**
- [ ] Initial commit (branch named by the maintainer)

---

## 4. Milestones

Milestones are sequential. Each ends with its own definition of done; none is
started before the previous one is signed off.

| # | Milestone | Output | Gate |
|---|---|---|---|
| **M0** | Repository skeleton | this structure, guards, ADR register, CI | §3, plus maintainer sign-off |
| **M1** | Triage and behaviour baseline | freeze the POC commit; capture message samples and traces; confirm or overturn every verdict in `migration/triage.md`. **No product code.** | every file has a verdict with evidence; baseline captured and reproducible |
| **M2** | Kernel | `platform/`: process shell, `decide()` seam, `RedisStateStore` behind the seam, TLS transport, OTel three signals with non-blocking export, internal API contract | kernel guards green; a use case can be built on it without touching sippy |
| **M3** | Applications | `apps/translation` and `apps/anti-fraud`; decision modules TDD'd first | contract case set replayed green against both |
| **M4** | Control plane | `services/config-service` (PG version repository, change-order state machine, staged distribution, rollback) and `services/console` (read-write, authentication, audit) | a rule change completes the full loop: edit → approve → distribute → report version → roll back |
| **M5** | Operations | Helm chart, custom-metric HPA, scale-down protection controller, draining/ISSU, alert rule set | rolling upgrade with no dropped call; scale-down with no dropped call |
| **M6** | **Capacity research** | real-socket load harness; measured CPS, concurrent sessions, setup latency — per stack | produces the answer to O1; no target is assumed before this runs |
| **M7** | Go migration | `go-b2bua` mirror of one use case, commit-pinned and vendored; cross-implementation comparison | **gated on M6.** Promotion only on output-for-output agreement with the Python implementation (ADR-0012) |
| **M8** | Release candidate | acceptance run with evidence, documentation chain complete, unified product version | acceptance report per item |

M6 is a research milestone with a decision at the end of it, not a
commitment to a number. M7 does not start until M6 has reported.

---

## 5. Open items

### 5.1 Carried from the architecture document (§12.1)

| # | Item | Blocks | Needed to resolve |
|---|---|---|---|
| O1 | Capacity targets: CPS, concurrent sessions, setup-latency budget | M7 (Go), HPA thresholds (M5) | the M6 measurement, run after the harness is real-socket |
| O2 | C/C++ stack selection | nothing today | O1 first; only if Go is proven insufficient |
| O3 | `go-b2bua` vs `sippy 2.4.2` behaviour comparison | M7 | manual comparison; upstream only names commit `61f1da28` |
| O4 | Call-trace retention period | M4 | customer compliance requirement |
| O5 | Disaster-recovery level: N+1 (node) or N+M (rack/AZ) | M5 Redis topology | customer SLA |

### 5.2 Added while building the skeleton

| # | Item | Blocks | Note |
|---|---|---|---|
| D1 | **Python 3.10 reaches end of life in October 2026.** The product pins 3.10 because that is the version sippy has been verified against. | any delivery after that date | Verify sippy behaviour on 3.11/3.12 early; either move or register the EOL runtime as an accepted risk in an ADR. Not decided here. |
| D2 | Where a second (Go) implementation of a use case lives: `apps/<case>/{py,go}` or a separate tree | M7 | Decided by ADR-0012 before the spike, so the structure is not churned mid-migration |
| D3 | Redis client and Sentinel wiring; verdict idempotence through a split-brain window | M2 | Risk R5 |
| D4 | Console front-end shape: keep the vendored single bundle and no build step, or accept a toolchain | M4 | The POC forbade npm and a build step; the product console is larger |
| D5 | Call-trace storage: PostgreSQL, or a separate short-retention store | M4 | Related to O4 |
| D6 | Whether the testbed must support customer acceptance testing in v1 | M8 | The architecture document defers it to v1.1 |

---

## 6. Working rules that shape the plan

- **Triage before adoption** ([`migration/triage.md`](migration/triage.md)) — the POC is a source of behaviour, not of code.
- **ADR with the change**, not after it and not in a batch.
- **TDD is mandatory in the decision layer**, contract-plus-simulation tests in the protocol layer (ADR-0015).
- **The POC is not a dependency.** Nothing here may reference `../3rtparty_AS_POC` or `../as_platform`.
- **AI-generated code passes the identical gate** and is marked as AI-generated in the PR (AGENT.md §AI assistance).
- **No capacity figure is published before M6.**

---

## 7. Risk register

Inherits §12.2 of the architecture document. Two additions from this step:

| # | Risk | Mitigation |
|---|---|---|
| R10 | **Triage is skipped under schedule pressure** and POC code is imported wholesale, importing its non-goals with it | M1 produces a verdict per file before M2 writes code; a PR must cite its triage row |
| R11 | **Behaviour is lost in the rewrite** because the POC's observed behaviour was never captured | M1 captures the baseline before any rewrite; "equivalent" is then checkable |
