# `services/console/` — operations console

The operator surface: rule editing through change orders, call trace lookup by
Call-ID, live statistics.

## Rules

- **Read-write, authenticated, audited.** The POC console was read-only and had
  no authentication; that is not acceptable for a product (ADR-0016).
- It reaches an AS **only** through the AS's internal API
  (`/healthz`, `/metrics`, `/traces`). No private channel.
- **Call trace is a product capability, not a debugging side effect.** It is
  queryable by Call-ID without depending on whether the customer deployed a trace
  backend (ADR-0005). The OTel trace of the same call is a separate channel,
  correlated by the same Call-ID / TraceID.

## Open decision

Front-end shape: keep the POC's rule of plain HTML/CSS/JS with no build step, or
accept a toolchain. The product console is considerably larger than the POC's.
Tracked as D4 in [`../../docs/plan.md`](../../docs/plan.md).

## Status

Skeleton.
