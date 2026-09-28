# `deploy/helm/` — 生产交付形态

占位符。chart 随部署里程碑落地。

计划形态：一个 chart `as/`、每个组件一个 subchart 或 values 块
（`apps.translation`、`apps.antiFraud`、`services.configService`、`services.console`），外加一个
values schema，把运营商级的旋钮显式化，而非 emergent：

- `replicaCount` / `minReplicas` 每用例，来自话务模型
- `draining.preStopSeconds`、`draining.graceWindowSeconds`、`draining.forceRelease`
- `peers.allowlist`、`transport.tls.enabled`、`transport.tls.secretRef`
- `state.redis.sentinel.*`、`state.postgres.*`（外部）
- `observability.otlpEndpoint`、`observability.exportMode`（必须非阻塞；见 ADR-0005）

v1 不写 Operator：Helm + 标准 Deployment / ConfigMap / Secret 足够（ADR-0013）。

---

## M5 addendum — what the chart renders, and what it refuses to render

Written in English: deployment artifacts follow the artifact language rule
(`AGENT.md` §5). The section above is the historical Chinese plan text and is
kept as-is.

### Layout

| File | Renders |
|---|---|
| `templates/_helpers.tpl` | naming and labels (`as.fullname`, `as.useCaseLabels`, …) |
| `templates/serviceaccount.yaml` | one ServiceAccount, no API token mounted |
| `templates/configmap.yaml` | non-sensitive config; sensitive values stay in Secrets |
| `templates/secret.yaml` | **placeholder** credentials Secret (empty strings) |
| `templates/deployment.yaml` | one Deployment per entry in `useCases` (ADR-0002) |
| `templates/service.yaml` | one Service per use case, `sessionAffinity: ClientIP` |
| `templates/hpa.yaml` | one HPA per use case — only when thresholds exist |
| `templates/pdb.yaml` | one PDB per use case — only when `minAvailable` is set |
| `templates/NOTES.txt` | post-install checks: version reporting, rollback |

### Keys left empty on purpose (O1 / M6)

O1 — the capacity target — is measured in M6 with a real-socket harness.
`AGENT.md` §2 / §6 and `docs/plan.md` §5.1 forbid publishing a CPS or
concurrency figure before that, so every capacity-bearing key ships as `null`
and its **template refuses to render the resource** rather than fall back to a
guess:

| Key | Behaviour when empty / null |
|---|---|
| `autoscaling.targetCPUUtilizationPercentage` | no CPU metric block in the HPA |
| `autoscaling.targetMemoryUtilizationPercentage` | no memory metric block in the HPA |
| `autoscaling.customMetric.name` / `.targetValue` | no custom-metric block in the HPA |
| `autoscaling.enabled: false` (default) | `hpa.yaml` renders nothing at all |
| `autoscaling.minReplicas` / `.maxReplicas` | `required` — install **fails** with an explicit message when autoscaling is enabled. There is no default, because a default would be a guessed capacity number |
| `useCases[].replicaCount` | Deployment renders `replicas: 1` with an inline comment: a rendering fallback, **not** a capacity conclusion |
| `podDisruptionBudget.minAvailable` | `pdb.yaml` renders nothing — an availability floor invented here would be a decision nobody made |
| `useCases[].resources` | no requests/limits block (sizing is downstream of the same M6 measurement) |

**Real capacity thresholds are filled in after M6, from its measurement. Do not
guess one before then** — an invented threshold is worse than no HPA, because it
looks authoritative and silently caps or over-scales the system.

### Other empty keys (not capacity, but still not ours to invent)

| Key | Why |
|---|---|
| `redis.sentinel.masters` / `.addresses` | topology depends on unresolved O5 (N+1 vs N+M) and D3 (Sentinel wiring, split-brain window) |
| `postgres.host` / `.database` | customer-specific, external store (ADR-0007) |
| `tls.secretName` | customer PKI; the chart only references it (ADR-0016) |
| `telemetry.otlpEndpoint` | customer's collector; empty means NoOp export, which is safe for the call path (ADR-0005) |
| `sip.peerAllowlist` | S-SBC allowlist; empty must be treated as fail-closed (ADR-0016) |

### Render guards, in one sentence each

- `deployment.yaml` / `service.yaml` range over `useCases`; `enabled: false`
  renders nothing.
- `hpa.yaml` renders only when `autoscaling.enabled` **and** at least one target
  threshold is non-null; `minReplicas` / `maxReplicas` are then `required`.
- `pdb.yaml` renders only when `podDisruptionBudget.minAvailable` is non-null.
- `secret.yaml` renders only when `postgres.secretName` is empty (otherwise the
  customer-managed Secret is the single source).

### Notes for operators

- **Credentials**: the shipped Secret contains empty strings. Replace it, or set
  `postgres.secretName` to a customer-managed Secret. Real credentials,
  certificates or addresses are never committed (`AGENT.md` §13).
- **TLS**: certificates are mounted from `tls.secretName` and reloaded hot; a
  Pod is never restarted for a rotation (ADR-0016).
- **Session affinity**: `sessionAffinity: ClientIP` on the Service is one half
  of a double safeguard; the other half is the application-level Redis session
  table. Neither alone is sufficient (ADR-0002).
- **Draining**: `preStop` plus an extended `terminationGracePeriodSeconds` let
  in-flight calls finish. ISSU is draining, not state migration (ADR-0009).
- **Capacity**: see the table above. Nothing in this chart states a CPS or
  concurrency figure.
