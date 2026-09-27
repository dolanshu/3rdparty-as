# `deploy/helm/` — production delivery form

Placeholder. The chart arrives with the deployment milestone.

Planned shape: one chart `as/`, one subchart or values block per component
(`apps.translation`, `apps.antiFraud`, `services.configService`,
`services.console`), plus a values schema that makes the operator-grade knobs
explicit rather than emergent:

- `replicaCount` / `minReplicas` per use case, from the traffic model
- `draining.preStopSeconds`, `draining.graceWindowSeconds`, `draining.forceRelease`
- `peers.allowlist`, `transport.tls.enabled`, `transport.tls.secretRef`
- `state.redis.sentinel.*`, `state.postgres.*` (external)
- `observability.otlpEndpoint`, `observability.exportMode` (must be
  non-blocking; see ADR-0005)

No Operator in v1: Helm plus plain Deployment / ConfigMap / Secret is enough
(ADR-0013).
