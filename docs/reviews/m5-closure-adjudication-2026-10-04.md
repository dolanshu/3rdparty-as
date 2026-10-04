# M5 closure adjudication (2026-10-04)

> **Subject:** M5 engineering tasks vs `plan.md` §4.4–§4.6 / §217  
> **Process:** Per-task reviews in [`m5-task-register-2026-10-04.md`](m5-task-register-2026-10-04.md) (subagent + maintainer synthesis)  
> **Status:** Engineering adjudication + **maintainer sign-off recorded 2026-10-04** (chat authorization).

Does **not** claim REQ / `test-plan` acceptance or production cluster sign-off.

## Adjudication key

| Verdict | Meaning |
|---------|---------|
| **Accept** | Task meets plan for M5 engineering closure (kind/lab where specified). |
| **Fix** | Gap remedied in repo **or** tracked fix applied (see column). |
| **Deny** | Must not be treated as M5-done (deferred milestone or out of scope). |

## §4.4.2 — Pre-delivered

| Task | Review | Plan match | Adjudication | Notes |
|------|--------|------------|--------------|-------|
| M5-a | [m5-a-helm-chart-review-2026-10-04.md](m5-a-helm-chart-review-2026-10-04.md) | Yes | **Accept** | See also [m5-helm-alerts-review.md](m5-helm-alerts-review.md) H1–H9 |
| M5-b | [m5-b-alerts-review-2026-10-04.md](m5-b-alerts-review-2026-10-04.md) | Yes | **Accept** | H12 **Deny** in M5 (→ M6) |
| M5-c | [m5-c-downscale-guard-review-2026-10-04.md](m5-c-downscale-guard-review-2026-10-04.md) | Yes | **Accept** | |
| M5-d | [m5-d-metrics-contract-review-2026-10-04.md](m5-d-metrics-contract-review-2026-10-04.md) | Yes | **Accept** | Control-plane alert metrics partly forward-looking → **Fix** README note |
| M5-e | [m5-e-version-store-review-2026-10-04.md](m5-e-version-store-review-2026-10-04.md) | Yes | **Accept** | |
| M5-f | [m5-f-container-draining-review-2026-10-04.md](m5-f-container-draining-review-2026-10-04.md) | Yes | **Accept** | Docker smoke historical; cluster ISSU → M5-217 |

## §4.4.4 — Stage 0

| Task | Review | Plan match | Adjudication | Notes |
|------|--------|------------|--------------|-------|
| M5-0a | [m5-0a-gate-review-2026-10-04.md](m5-0a-gate-review-2026-10-04.md) | Yes | **Accept** | |
| M5-0b | [m5-0b-integration-compose-review-2026-10-04.md](m5-0b-integration-compose-review-2026-10-04.md) | Partial | **Accept** + **Fix** | CI layer ② ≠ `make test-integration-compose`; document maintainer gate |
| M5-0c | [m5-0c-chart-check-review-2026-10-04.md](m5-0c-chart-check-review-2026-10-04.md) | Yes | **Accept** | |

## §4.4.4 — Stage 1 + §217③

| Task | Review | Plan match | Adjudication | Notes |
|------|--------|------------|--------------|-------|
| M5-1a | [m5-1a-images-review-2026-10-04.md](m5-1a-images-review-2026-10-04.md) | Yes | **Accept** | Digests in [`m5-evidence-summary.md`](../acceptance/m5-evidence-summary.md) |
| M5-1b | [m5-1b-kind-helm-review-2026-10-04.md](m5-1b-kind-helm-review-2026-10-04.md) | Yes | **Accept** | Bundled state default documented |
| M5-1c | [m5-1c-ingress-template-review-2026-10-04.md](m5-1c-ingress-template-review-2026-10-04.md) | Yes | **Accept** | Template/slice; 4–5 → M5-7.2d |
| M5-1d | [m5-1d-config-pg-review-2026-10-04.md](m5-1d-config-pg-review-2026-10-04.md) | Yes | **Accept** | **Fix** plan/README compose vs bundled wording |
| M5-7.2d | [m5-7.2d-ingress-closure-review-2026-10-04.md](m5-7.2d-ingress-closure-review-2026-10-04.md) | Yes (kind) | **Accept** | §217③ kind evidence; item 6 nginx controller doc **Fix** optional |

## §4.4.4 — Stage 2

| Task | Review | Plan match | Adjudication |
|------|--------|------------|--------------|
| M5-2a | [m5-2a-metrics-runtime-review-2026-10-04.md](m5-2a-metrics-runtime-review-2026-10-04.md) | Yes | **Accept** |
| M5-2b | [m5-2b-readiness-review-2026-10-04.md](m5-2b-readiness-review-2026-10-04.md) | Yes | **Accept** |
| M5-2c | [m5-2c-downscale-config-review-2026-10-04.md](m5-2c-downscale-config-review-2026-10-04.md) | Yes | **Accept** |
| M5-2d | [m5-2d-downscale-runbook-review-2026-10-04.md](m5-2d-downscale-runbook-review-2026-10-04.md) | Yes | **Accept** |

## §4.4.4 — Stage 3 + §217①②

| Task | Review | Plan match | Adjudication | Notes |
|------|--------|------------|--------------|-------|
| M5-3a | [m5-3a-rollout-review-2026-10-04.md](m5-3a-rollout-review-2026-10-04.md) | Yes | **Accept** | **Fix** `m5-rollout-scale.sh` → anti-fraud deploy |
| M5-3b | [m5-3b-scale-guard-review-2026-10-04.md](m5-3b-scale-guard-review-2026-10-04.md) | Yes | **Accept** | Logic in `m5-issu-scale-evidence.sh` |
| M5-217 | [m5-217-issu-scale-review-2026-10-04.md](m5-217-issu-scale-review-2026-10-04.md) | Yes (simulated) | **Accept** | **Deny** as M7 real-SIP proof |
| M5-H10 | [m5-h10-ops-wiring-review-2026-10-04.md](m5-h10-ops-wiring-review-2026-10-04.md) | Yes | **Accept** | |
| M5-3c | [m5-3c-closure-docs-review-2026-10-04.md](m5-3c-closure-docs-review-2026-10-04.md) | Yes | **Accept** | **Fix** evidence summary committed |

## §4.6 — D12

| Task | Review | Plan match | Adjudication | Notes |
|------|--------|------------|--------------|-------|
| M5-D12-adr | [m5-d12-adr-0026-review-2026-10-04.md](m5-d12-adr-0026-review-2026-10-04.md) | Yes | **Accept** | |
| M5-D12-helm | [m5-d12-helm-state-review-2026-10-04.md](m5-d12-helm-state-review-2026-10-04.md) | Yes | **Accept** | |
| M5-D12-kind | [m5-d12-kind-bundled-review-2026-10-04.md](m5-d12-kind-bundled-review-2026-10-04.md) | Yes | **Accept** | |
| M5-D12-prod | [m5-d12-production-profile-review-2026-10-04.md](m5-d12-production-profile-review-2026-10-04.md) | Yes | **Accept** | Customer HA / D3 **Deny** as M5 sign-off blockers |

## Explicitly **Deny** for M5 maintainer sign-off scope

| Item | Reason |
|------|--------|
| HPA `minReplicas` / custom thresholds | §4.4.3 → **M6** |
| H12 capacity alerts (CPS/concurrency) | §4.4.3 → **M6** |
| D3 Redis Sentinel | **M2/O5** |
| Real SIP “不掉呼叫” under load | **M7** |
| REQ / `test-plan` full green | **§5.4** / M8 |
| Production cluster (non-kind) mandatory re-run | Not in plan as hard gate; kind satisfies §217 for engineering |

## Fixes applied in this adjudication pass

| Fix | Location |
|-----|----------|
| Anti-fraud pinned rollout | `deploy/kind/m5-rollout-scale.sh` |
| Committed evidence index | `docs/acceptance/m5-evidence-summary.md` |
| Plan / README drift | `plan.md` §4.4.4, §4.5; `deploy/kind/README.md` |
| Review process | `docs/reviews/m5-task-register-2026-10-04.md` + per-task `m5-*-review-2026-10-04.md` |
| Helm review signing row | `m5-helm-alerts-review.md` |

## Maintainer sign-off

| Field | Value |
|-------|--------|
| Engineering adjudication | Recorded 2026-10-04 (AI agent + subtask reviews) |
| Maintainer sign-off | **Approved** — maintainer authorized AI agent in chat (2026-10-04). Scope: M5 engineering closure per §4.4–§4.6 / §217 on **kind** evidence; **not** REQ / `test-plan` acceptance, **not** M6 HPA/O1, **not** M7 product SIP. |
| Evidence basis | [`m5-evidence-summary.md`](../acceptance/m5-evidence-summary.md); scripts `m5-issu-scale-evidence`, `m5-7.2d-evidence`, `m5-kind-verify` |
