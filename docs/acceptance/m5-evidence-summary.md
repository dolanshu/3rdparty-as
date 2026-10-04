# M5 kind evidence summary (committed pointer)

> Runtime logs live under `artifacts/m5/<UTC-date>/` (gitignored). Reproduce on maintainer machine; paste redacted excerpts here after sign-off if required.

## Images (M5-1a)

| Image | Digest (2026-10-04 kind build) |
|-------|--------------------------------|
| `as-platform:m5` | `sha256:be05fffd0705eeba5f5ff47d2c9fa9d3dc45d057743389b2da7d0410612ac317` |
| `as-config-service:m5` | `sha256:dc7b201ded3a494c7e6c33382a87d7f16794f5ce66000fed5054dedaaf9a45be` |

## Scripts (reproduce)

```sh
make gate && make chart-check && make test-integration-compose
make m5-issu-scale-evidence          # §217①② + H10 → issu-scale-evidence.log
export M5_7_2D_E2E_PASSWORD='<12+ chars>'
make m5-7.2d-evidence                # §217③ → 7.2d-evidence.log + browser JSON
make m5-kind-verify
```

## Expected log files (local, not in git)

| Path | Task |
|------|------|
| `artifacts/m5/<date>/issu-scale-evidence.log` | M5-217, M5-H10 |
| `artifacts/m5/<date>/7.2d-evidence.log` | M5-7.2d |
| `artifacts/m5/<date>/7.2d-browser-log.json` | M5-7.2d item 5 |
| `artifacts/m5/<date>/cluster-evidence.log` | `m5-cluster-evidence.sh` |

Reviews: [`reviews/m5-task-register-2026-10-04.md`](../reviews/m5-task-register-2026-10-04.md), [`reviews/m5-closure-adjudication-2026-10-04.md`](../reviews/m5-closure-adjudication-2026-10-04.md).
