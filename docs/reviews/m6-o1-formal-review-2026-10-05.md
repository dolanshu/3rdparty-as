# M6 O1 formal measurement review (2026-10-05)

> **Scope:** `m6-o1-formal-report.sh` batch + [`m6-o1-measurement-report-2026-10-05.md`](../acceptance/m6-o1-measurement-report-2026-10-05.md)  
> **Not:** Maintainer M6 milestone sign-off, O1 target publication, or REQ-NF-15 full test-plan green

## Commands

```bash
make m2-platform-resip-build
bash testbed/load/scripts/m6-o1-formal-report.sh
```

## Result (local 2026-10-05)

Pass: four scenarios (30s/60s × cps 10/20) on product `ResipRuntimeListener` UAS; evidence under `/tmp/as-m6-o1-formal-20261005-092643/` with `formal_manifest.json`.

## Checks

| Check | Status |
|-------|--------|
| Real UDP socket path (`as_load` → UAS) | Pass |
| `summary.json` + `resources.json` per scenario | Pass |
| C6 1s sliding peaks present | Pass |
| C6 100s sliding peak (full window) | N/A at ≤60s duration (expected `unavailable`) |
| Saturation / multi-replica | Not exercised |
| D8 REQ-NF-15 trace | Closed separately |

## Gaps vs M6 milestone exit

- No cluster-scale or TLS/S-SBC-shaped load
- No O1 numeric **targets** or HPA values
- `performance` CI layer still non-blocking
- Maintainer milestone sign-off not requested

## Recommendation

**Accept** as M6 **engineering complete** for harness + dev-host O1 formal batch. **Deny** public capacity publication and M6 maintainer milestone exit.

## Sign-off

- Review recorded: 2026-10-05  
- Maintainer M6 milestone sign-off: **not requested**
