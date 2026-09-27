# `deploy/`

| Directory | Role |
|---|---|
| `helm/` | **the production delivery form.** Kubernetes + Helm, one chart for the system |
| `compose/` | developer environment only. Never used to deliver |

Helm is the only production form (ADR-0013). Compose exists so a developer can
bring up AS + config-service + console + Redis + PostgreSQL on a laptop; it is
not a deployment target and carries no HA semantics.

## What the chart must express

- `sessionAffinity: ClientIP` on the AS service, plus the Redis session table as
  the second line of defence (ADR-0002).
- `preStop` draining, an extended `terminationGracePeriodSeconds` and a
  PodDisruptionBudget for ISSU (ADR-0009).
- Redis and PostgreSQL as external dependencies, not as in-chart stateful
  workloads: the operator's redundancy requirements decide how they are run.
- Certificates from a Secret or the customer PKI; rotation must not restart an
  AS pod (ADR-0016).

## Status

Placeholders. The chart lands with the deployment milestone; see
`docs/plan.md` for the sequence.
