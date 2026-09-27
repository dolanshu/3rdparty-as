# AGENT.md — 3rdparty-as

> Rules of engagement for humans and AI agents.
> Read this file **before** writing any code. If a rule here conflicts with a request,
> follow this file and raise the conflict with the maintainer.

## 1. What this repository is

A **productised third-party IMS Application Server**: single-tenant, on-premises,
deployed **outside** the operator's IMS network and triggered by the S-CSCF
through the operator's S-SBC, which bridges transparently.

It is **not** the POC. The POC (`../3rtparty_AS_POC`) existed to prove a concept
under non-goals this product does not share. This repository is the product.

**We implement the external AS only.** The S-CSCF, the S-SBC and the HSS are the
operator's; they appear here only as simulators under `testbed/`.

```text
  operator IMS core                    SIP trunk (UDP / TLS)        us
+---------------------------+                              +--------------------+
| S-CSCF --ISC--> S-SBC     | ============================ | 3rd-party AS       |
+---------------------------+                              +--------------------+
   (testbed/simulators)                                        (this repository)
```

### Position: one access semantic only

Because the S-SBC bridges transparently, the AS is triggered by the S-CSCF
(3GPP TS 24.229 iFC / ISC) and **nothing else**. There is no "in-network /
out-of-network dual-mode adapter": the trunk is a bearer, not a second business
semantic. Anything that suggests otherwise is a design error (ADR-0003).

### Scope

| Layer | Directory | Statefulness |
|---|---|---|
| ① signalling plane | `apps/<use case>/` | **stateless** — state lives in Redis |
| ② kernel | `platform/` | stateless |
| ③ control plane | `services/` | stateless — state lives in PostgreSQL |
| ④ data plane | Redis + PostgreSQL | **stateful**, redundant |
| ⑤ cross-cutting | observability, security, operations | stateless except backends |
| ⑥ test platform | `testbed/` | research asset |

## 2. Non-goals

Explicitly out of scope. Each one is a decision, not an oversight:

- **No media.** No RTP, no transcoding, no DTMF, no MRF, no media anchoring. A
  seam is reserved with an explicit trigger condition (ADR-0004).
- **No CDR.** No collection, no delivery channel, no archive, no rating. Call
  trace by Call-ID replaces it for complaint tracing and fraud evidence (ADR-0017).
- **No lawful interception.** IRI belongs to in-network elements; involving a
  third-party AS adds cross-jurisdiction exposure (ADR-0016).
- **No Diameter Sh.** Data comes from our own data plane.
- **No multi-tenancy.** Single tenant, on-premises.
- **No GitOps for configuration.** Operators must not need Git to edit a number
  range; versions are rows in PostgreSQL behind a change-order state machine
  (ADR-0006).
- **No Operator (CRD).** Helm plus plain Deployment/ConfigMap/Secret (ADR-0013).
- **No capacity figures before M6.** No published CPS or concurrency number
  until the real-socket harness has measured it.

## 3. Layering

```text
apps/  ──uses──▶  platform/          one use case per process
services/ ─────────────────────────▶  PostgreSQL, AS internal API
testbed/ ──may use──▶ platform/       research asset, never a runtime dependency
```

**The kernel must never import an application, a service or the testbed.**
Repository boundaries do not enforce this — inside a monorepo every import
resolves. `platform/tests/test_library_independence.py` enforces it, and
`tests/test_workspace_layout.py` enforces the structure itself.

An app must never import another app. A use case is a process, a fault domain
and a rollout unit.

## 4. Coding conventions

- **Language of artefacts: English.** Identifiers, comments, log messages, error
  strings, commit messages, code-adjacent docs. Human-facing docs in this
  repository are written in Chinese; that is the only exception.
- **Type hints on all public functions; `mypy` strict, clean.**
- **Decision modules are pure.** No sockets, no clock, no global state in the
  module that produces the verdict. That is what makes TDD cheap there.
- **sippy interaction stays confined** to the SIP adapter and the call
  controller. The glue stays thin.
- **`ED2.loop()` blocks.** Never call a blocking operation from inside a sippy
  callback — including a telemetry export. Export runs on its own thread
  (ADR-0005).
- **Every non-obvious line points at its ADR**: `# See ADR-00NN`. A reviewer must
  move from code to rationale in one step.
- **No `util`, `helper`, `misc`, `common`, `tools`-style module names** in `src/`.
- **sippy behaviour is observed, not assumed.** When in doubt, write a probe
  under `testbed/` and run it. Never invent a header, status code or API.

## 5. Testing

| Layer | Marker | Method |
|---|---|---|
| Decision logic | `unit` | **mandatory TDD**, red-green-refactor. This is where TDD pays. |
| Contracts | `contract` | declarative cases in `testbed/contracts/`, replayed against **every** implementation |
| Protocol / access | `integration` | contract tests and simulated peers; not strict TDD — cost is high, return is low |
| Complete flows | `e2e` | full call plus error branches, console included |
| Capacity | `performance` | real sockets only. Never by calling callbacks — that measures business logic, not the system (ADR-0014) |

Test ports must be configurable so parallel runs never collide.

## 6. ADRs

Every architectural decision gets a record in `docs/architecture/adr/`. The
register maps the 18 confirmed decisions to ADR numbers.

- An ADR is written **with** the change it authorises.
- An ADR states the gaps it accepts. Empty consequences = unfinished analysis.
- Reversing a decision means a new ADR **and** an update to
  `docs/architecture/新系统整体架构.md` in the same change.
- The POC's ADR-0001…0016 are **not** imported. They describe a different system.
  Cite them as context; do not treat them as binding.

## 7. Versions and dependencies

- **`./VERSION`** is the single product release version. One number per delivery,
  because the operator receives one system.
- **`<member>/pyproject.toml`** carries that component's own interface version.
- **No member may own a `VERSION` file.** Two homes for one number is the drift
  this repository was created to kill (ADR-0018). Guarded by
  `tests/test_version_consistency.py`.
- **`sippy==2.4.2` is pinned and workspace-wide.** One SIP stack version in one
  interpreter. Widening the pin requires an ADR.
- **`go-b2bua` has no release.** It is **commit-pinned and vendored**, and its
  upstream regression suite runs here.
- Every dependency goes through `uv`, with `uv.lock` committed and verified in CI.

## 8. Gates

`make gate` = `ruff format --check` → `ruff check` → `mypy` → pytest. CI runs the
same four layers:

① fast (`unit or contract`) → ② integration → ③ e2e → ④ performance (nightly/tags).

Nothing is committed unless the local gate is green first. **The local gate is
not CI**: never present a local re-run as a CI result.

## 9. AI assistance

1. AI-generated code passes the **identical** gate. It is never held to a lower
   standard because it was generated.
2. A PR containing AI-generated work is **marked as such**, so review can weight
   it accordingly.
3. The Go mirror translation is the highest-value AI task in this project —
   isomorphic translation with a comparison harness. Use the leverage; keep the
   standard.

## 10. Git rules

- **Never push without the maintainer's explicit approval given in that
  conversation.** Not a push, not a force-push, not a tag.
- **Agents do not create branches.** Work happens on the branch the maintainer
  names. Every branch needs a stated purpose and an end condition.
- **Nothing enters `main` without explicit, per-change approval.**
- **Conventional Commits**, English, one logical change per commit:
  `feat` · `fix` · `docs` · `refactor` · `test` · `chore` · `build`.
- **No hook skipping.** `--no-verify` and equivalents are forbidden. If a hook
  blocks a commit, fix the cause.
- **No secrets, certificates or real traffic captures** are ever committed.
- A behaviour change walks the whole documentation chain: requirement → design →
  interface contract → acceptance item → CHANGELOG.

## 11. Adopting code from the POC

**Nothing is copied in wholesale.** See `docs/migration/triage.md`.

- Every POC file gets a verdict — adopt / rewrite / baseline-reference / discard —
  with evidence, before product code is written.
- Adopted code arrives **with its tests**.
- The POC behaviour baseline is captured **before** any rewrite, so "equivalent"
  is a checkable claim.
- This repository must build, test and run with **no reference** to
  `../3rtparty_AS_POC` or `../as_platform`.

## 12. Security

- Nothing sensitive is committed: no keys, certificates, tokens or real addresses.
- The trunk is untrusted. Verify the peer against the allowlist, and terminate
  TLS end to end with the S-SBC — anyone who can impersonate the S-SBC can
  inject calls (ADR-0016).
- Certificate rotation is a configuration hot update. It must not restart a
  process or drop an in-flight call.
- Payload logging is explicit and switchable; off by default in logs.
- Every console operation is authenticated and audited.

## 13. Definition of done

- [ ] Works end to end against a simulated peer
- [ ] Tests added at the layer the change belongs to; `make gate` green
- [ ] `ruff format`, `ruff check`, `mypy` clean
- [ ] ADR written with the change, and `docs/architecture/新系统整体架构.md`
      updated if a decision moved
- [ ] README and affected docs updated (new env var, port, command, directory)
- [ ] CHANGELOG entry; product version bumped if the delivery changed
- [ ] If POC code was adopted: the triage row is cited
- [ ] No secrets committed

## 14. Open items

`docs/plan.md` §5 owns the open list (O1–O5 from the architecture document,
D1–D6 added since). **Do not silently resolve an open item.** If a decision is
forced by a piece of work, write the ADR and move the row.

The largest of them, **O1 (capacity targets)**, has its own research milestone
(M6). No capacity number is assumed before it runs.
