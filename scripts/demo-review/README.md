# Pre-M8 demo scripts

Customer-facing plan: [`docs/handoff/pre-m8-demo-review-plan.md`](../../docs/handoff/pre-m8-demo-review-plan.md).

Artifacts: `artifacts/demo-review/<date>/story-{a,b,c,d,e}/`

## One-click

| Story | Command | Typical duration |
|-------|---------|------------------|
| A 开通翻译号段 | `make demo-story-a` or `bash scripts/demo-review/story-a.sh` | control plane as before; signaling needs kind `as-m71` |
| B 拦截诈骗号段 | `make demo-story-b` | kind `as-m71` test page, UDP/TCP/TLS, then local 487/608 checks |
| C 平台运维 | `make demo-story-c` | cluster shot is kind `as-m71`; 7.2d stays on `kind-as-m5` |
| D 恢复/checkpoint | `AS_REDIS_URL=redis://127.0.0.1:6379/0 make demo-story-d` | harness unchanged; speech says `as-sut` Redis is not customer-K8s REQ-NF-1 |
| E 容量研究 | `make demo-story-e` | research method, not an SLA; `as-m71` page counts stay out of the O1 report |
| All (CI smoke) | `AS_REDIS_URL=redis://127.0.0.1:6379/0 make demo-review-all` | ~5–15 min |

### Story A flags

- `--with-compose` — run `deploy/compose/scripts/smoke-https.sh` when `.env` + certs exist
- `--skip-pg` — skip PostgreSQL pipeline integration (browser-only control plane)

### Story C flags

- `--require-kind` — fail if `kind-as-m71` kubectl context missing. Story C's cluster shot is that cluster. 7.2d Ingress login stays on `kind-as-m5` and is skipped unless `M5_7_2D_E2E_PASSWORD` is set.

### Story D / E

- Redis: `docker run -d --rm -p 6379:6379 --name as-d10-redis redis:7`
- Story E: `--full-o1` runs `m6-o1-formal-report.sh` (several minutes)

## Prerequisites

`kind` / `kubectl` / `helm` may live on your system `PATH`, or in the repo vendored dir **`.tools/m71-bin`** (see `pre-m8-demo-review-plan.md`). `make chart-check`, `kind-up.sh`, and demo scripts resolve that directory automatically when present.

```bash
cd /path/to/3rdparty-as && uv sync
make m2-platform-resip-build   # stories B (487), D, E
bash testbed/sim-platform/kind-up.sh   # stories A step 5 and B step 2; context kind-as-m71
```

Stories A and B use the compiled config-service bundle (`AS_CONFIG_BUNDLE_PATH`) for the kernel decision. The +86 rewrite stays in `AS_TRANSLATION_RULES_JSON`. The test page is not the product console, and this cluster does not serve the console login. `bash scripts/demo-review/publish-m71-bundle.sh` compiles and mounts the bundle. `kind-up.sh` keeps that mount when ConfigMap `as-sut-runtime-bundle` already exists.

Compose (story A live UI): [`deploy/compose/README.md`](../../deploy/compose/README.md).

Kind cluster shot: [`docs/acceptance/m71-sim-platform-evidence.md`](../../docs/acceptance/m71-sim-platform-evidence.md). Manual pass criteria: [`docs/handoff/pre-m8-demo-review-plan.md`](../../docs/handoff/pre-m8-demo-review-plan.md) section 4. 7.2d stays on [`docs/acceptance/m5-7.2d-ingress-runbook.md`](../../docs/acceptance/m5-7.2d-ingress-runbook.md).
