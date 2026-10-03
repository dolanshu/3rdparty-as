# M4 Closure Criteria Adjudication (Maintainer Grill Session)

> **Subject:** M4 / M4b closure criteria, evidence boundaries, and deferred gates  
> **Date:** 2026-10-03  
> **Session:** Maintainer grill (closure adjudication)  
> **Status:** Decisions recorded; **M4 / M4b / REQ acceptance are not claimed complete**

This record persists maintainer-confirmed intent from the 2026-10-03 session. It does not supersede PRD or formal REQ text for unresolved product semantics (see open gaps).

## Adjudicated decisions

| # | Topic | Decision |
|---|--------|----------|
| 1 | **7.2d** — production HTTPS ingress / trusted-proxy proof | Bundled with **M5** cluster acceptance; **not** an M4 hard gate. |
| 2 | **7.5 / REQ-F-15** | Remains **M4** scope: PostgreSQL **instance inventory**, **outbound notify**, and **testbed health probes**; **full AS stack re-test** after integration is complete (补测). |
| 3 | **M4 browser HTTPS** | **Compose / self-signed / local reverse proxy** same-origin evidence suffices for **M4b-8** on M4; formal **7.2d** proof moves to **M5**. |
| 4 | **REQ-F-13 / 7.4** (Call-ID trace) | **Deferred for M4** closure; re-test after signaling/integration stack is complete. |
| 5 | **Rule match axis / M4 console scope** | **Adjudicated 2026-10-03**: **called** number per REQ-F-6/F-7; M4 **called+prefix** only; calling/regex **v1.1**. See [`m4-req-calling-regex-lossless-adjudication-2026-10-03.md`](m4-req-calling-regex-lossless-adjudication-2026-10-03.md). |
| 6 | **ADR-0024** | **Done (2026-10-03):** **Accepted** with maintainer-authorized signoff in [review record](adr-0024-console-password-sessions-review-2026-10-02.md). Does not close REQ-S-4 or M4b acceptance. |
| 7 | **Evidence git line** | M4 acceptance evidence may be collected on a **named commit on branch `cur`**; merge and maintainer sign-off may occur the same week. |
| 8 | **CI** | Local **`make gate`** plus **maintainer-environment PostgreSQL integration** suffice for M4 evidence; **origin CI all-green is not** an M4 hard gate (future acceptance report must state this). |
| 9 | **Instance inventory (7.5)** | **PostgreSQL table**, maintained via **console or internal API**. |
| 10 | **PostgreSQL version** | M4 evidence on **12.22**; **PG16** is a non-blocking follow-up. |
| 11 | **M4b-8 browser execution** | Engineering/AI runs steps and collects **redacted** artifacts; **maintainer reviews materials and signs**. |

## Explicit open gaps (not closed by this adjudication)

| Gap | Notes |
|-----|--------|
| REQ-F-12 calling / regex (v1.1) | M4 scope closed per adjudication; full PRD four-way UI acceptance deferred to v1.1. |
| REQ-F-13 / M4b-7.4 | Trace integration and acceptance **补测** after signaling/integration stack. |
| REQ-F-15 / 7.5 | Implementation of inventory + notifier + health probes; **full AS stack 补测** after integration. |
| 7.2d production proof | Formal ingress/trusted-proxy evidence deferred to **M5** cluster acceptance. |
| M4b-8 | Browser/redacted artifacts collected（`artifacts/m4b-8/2026-10-03/`）；evidence commit `1bca9eee74c090964d48a217abfe41bfcdf73dab`（`cur`）；**维护者签字**已记录（2026-10-04，chat 授权代签）。 |
| ADR-0024 | **Closed for ADR gate:** accepted 2026-10-03 per [`adr-0024-console-password-sessions-review-2026-10-02.md`](adr-0024-console-password-sessions-review-2026-10-02.md) (maintainer authorized agent to record signoff). REQ-S-4 / M4b acceptance still open. |

## What still blocks M4 milestone sign-off

- **Maintainer sign-off on engineering evidence** (M4b slice reviews, M4b-8 artifacts/runbook): **recorded 2026-10-04** per chat authorization; does **not** claim REQ/M4b/M4 acceptance.
- **REQ-F-13** and **full REQ-F-15 AS 补测** remain post-integration / deferred per table above.
- **plan.md** open checkboxes (7.3b–7.6, M4b-8 milestone wording) may still need alignment with delivered engineering vs formal REQ acceptance.

## Sign-off

| Field | Value |
|-------|--------|
| Adjudication recorded by | AI agent (doc-writer), 2026-10-03 |
| Maintainer sign-off | Approved; recorded by AI agent per maintainer authorization in chat (2026-10-04). Engineering evidence and M4b-8 runbook annotations accepted; REQ/M4 acceptance not claimed. |
