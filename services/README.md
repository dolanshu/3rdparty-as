# `services/` — the control plane (layer ③)

| Directory | Responsibility |
|---|---|
| `config-service/` | rule version repository, change orders, staged distribution, rollback |
| `console/` | the operator surface: rules, call trace, statistics |

## Rules

- **Stateless.** Durable state is in PostgreSQL, never in the process.
- **The version repository is ours.** Approval may be delegated to the
  operator's OSS or ticketing system; the rule version repository may not —
  rule availability must not depend on a foreign system's availability
  (ADR-0006).
- The console talks to an AS **only** through the AS's internal API
  (`/healthz`, `/metrics`, `/traces`), never through a private channel.

## Not GitOps

Operators must not have to learn Git to change a number range. Versions are
rows in PostgreSQL behind a change-order state machine, not commits. The
reasoning is recorded in `docs/新系统整体架构.md` §5.1 and ADR-0006.
