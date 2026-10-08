# Pre-M8 demo scripts

Customer-facing plan: [`docs/handoff/pre-m8-demo-review-plan.md`](../../docs/handoff/pre-m8-demo-review-plan.md).

Artifacts: `artifacts/demo-review/<date>/story-{a,b,c,d,e}/`

## One-click

| Story | Command | Typical duration |
|-------|---------|------------------|
| A 开通翻译号段 | `make demo-story-a` or `bash scripts/demo-review/story-a.sh` | control plane as before; signaling needs kind `as-m71` |
| B 拦截诈骗号段 | `make demo-story-b` | kind `as-m71` test page, UDP/TCP/TLS, then local 487/608 checks |
| C 平台运维 | `make demo-story-c` | 1–10 min (kind optional) |
| D 恢复/checkpoint | `AS_REDIS_URL=redis://127.0.0.1:6379/0 make demo-story-d` | 2–5 min |
| E 容量研究 | `make demo-story-e` | ~1 min (+ `--full-o1` for long batch) |
| All (CI smoke) | `AS_REDIS_URL=redis://127.0.0.1:6379/0 make demo-review-all` | ~5–15 min |

### Story A flags

- `--with-compose` — run `deploy/compose/scripts/smoke-https.sh` when `.env` + certs exist
- `--skip-pg` — skip PostgreSQL pipeline integration (browser-only control plane)

### Story C flags

- `--require-kind` — fail if `kind-as-m5` kubectl context missing

### Story D / E

- Redis: `docker run -d --rm -p 6379:6379 --name as-d10-redis redis:7`
- Story E: `--full-o1` runs `m6-o1-formal-report.sh` (several minutes)

## Prerequisites

```bash
cd /path/to/3rdparty-as && uv sync
make m2-platform-resip-build   # stories B (487), D, E
bash testbed/sim-platform/kind-up.sh   # stories A step 5 and B step 2; context kind-as-m71
```

Stories A and B tell the room that rules still come from lab `AS_RULESET_JSON`. That is not console distribution. The test page is not the product console.

Compose (story A live UI): [`deploy/compose/README.md`](../../deploy/compose/README.md).

Kind (story C cluster): [`docs/acceptance/m5-evidence-summary.md`](../../docs/acceptance/m5-evidence-summary.md).
