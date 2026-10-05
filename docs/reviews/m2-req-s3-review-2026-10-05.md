# M2 REQ-S-3 product overlap integration review (2026-10-05)

> **Subject:** `platform/tests/test_req_s3_overlap_integration.py`  
> **Test-plan:** [`test-plan.md`](../acceptance/test-plan.md) §3 REQ-S-3

## REQ-S-3 mapping (engineering)

| Criterion | Disposition |
|-----------|-------------|
| In-flight / legacy path during overlap | **Partial** — legacy `connection_id` uses retiring peer policy |
| New material for new connections | **Partial** — active seam TLS B; overlap hook fires |
| Post-window stale peer | **Partial** — unit tests cover expiry; integration focuses on overlap start |
| No process restart | **Aligned** — `reload_certificates` queued on overlap hook |

## Object

Two local cert pairs (A/B), `install_with_overlap`, assert policy + native `reload_certificates`
invoked (tracked wrapper).

## Conclusion

**Pass** for REQ-S-3 **product overlap integration** engineering slice. Operator PKI / live dialog
preservation on external S-SBC deferred to **M8** env-only evidence.

## Verification

```sh
make m2-platform-resip-build
uv run pytest platform/tests/test_req_s3_overlap_integration.py -m integration -q
```

## Sign-off

- Engineering review recorded: 2026-10-05
- Maintainer sign-off: **pending**
