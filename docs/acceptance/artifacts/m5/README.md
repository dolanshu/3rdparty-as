# M5 committable evidence (redacted)

Sanitized M5.1 transcripts. Raw kind runs may still land under gitignored `artifacts/m5/<date>/`.

| Path | Meaning |
|---|---|
| `2026-10-05/gate-full.txt` | full `make gate` (must end in pytest passed) |
| `2026-10-05/gate-sample.txt` | last lines of that run |
| `2026-10-05/chart-check-full.txt` | `make chart-check` |
| `2026-10-05/alert-check-full.txt` | `promtool check rules` |
| `2026-10-05/m5-strict-context.txt` | `M5_STRICT=1` with no `kind-as-m5` (non-zero) |
| `README.md` | this index |

Do not store passwords, tokens, DSNs, or cookies.
