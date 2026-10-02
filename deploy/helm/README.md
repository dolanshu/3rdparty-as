# `deploy/helm/` — 生产交付形态

当前仓库包含 AS workload Helm chart，以及 M4b-7.2c config-service 的代码级 workload 切片（默认关闭）。可选 Ingress 模板仅支持 ingress-nginx，并固定配置重定向及强制 HTTPS；新增 config-service 模板尚未通过 Helm lint/template/render，专用镜像构建及真实 HTTPS ingress/trusted-proxy 部署也未验证。下文 M5 addendum 记录的早期 AS workload chart 渲染证据不覆盖这些新增资源。

历史计划形态：一个 chart `as/`、每个组件一个 subchart 或 values 块
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
| `templates/config-service-deployment.yaml` | optional non-root config-service Deployment; disabled by default; references external runtime Secret keys and pre-provisioned runtime role |
| `templates/config-service-service.yaml` | optional ClusterIP Service for config-service HTTP on port 8000 |
| `templates/config-service-ingress.yaml` | optional ingress-nginx-only same-origin Ingress for `/` and `/internal/v1`; requires hostname, TLS Secret, proxy headers, and explicit trusted proxy addresses; always redirects and forces HTTPS |

The three config-service templates above are code-level delivery only. Helm lint/template/render and the dedicated Docker image build were blocked by unavailable tooling/registry access; no rendered-chart or deployed-ingress proof is claimed. These additions do not change the existing capacity guards below.

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

## Config-service control plane (M4b-7.2c engineering slice)

The config-service workload is disabled by default. Enable it only after
publishing the dedicated image built from the repository root:

```sh
docker build -t registry.example.com/3rdparty-as-config-service:0.1.0 \
  -f deploy/docker/config-service.Dockerfile .
```

Example values (replace the documentation-only hostname/CIDR with customer
infrastructure details):

```yaml
services:
  configService:
    enabled: true
    image:
      repository: registry.example.com/3rdparty-as-config-service
      tag: "0.1.0"
    secretName: config-service-runtime
    runtimeRole: as_config_runtime
    configSchema: as_config
    auditSchema: console_audit
    proxyHeaders: true
    trustedProxies:
      - 192.0.2.0/24
    ingress:
      enabled: true
      className: nginx
      host: console.example.com
      tlsSecretName: console-example-tls
```

Set `services.configService.enabled: true`, its image repository/tag, a
customer-managed `services.configService.secretName`, and
`services.configService.runtimeRole`. The external Secret must contain the
required keys `AS_CONFIG_DSN` and `AS_AUDIT_RESOURCE_HMAC_KEY_B64`; the
chart only references those keys and never writes their values into Helm values,
ConfigMaps or rendered manifests. Do not point this at `postgres.secretName`:
that Secret has a separate AS-workload contract. The database login in the DSN
must be allowed to `SET ROLE` to the pre-provisioned least-privilege `NOLOGIN`
runtime role. The DBA must pre-provision both the login role and the dedicated
`NOLOGIN` runtime role; no role creation is performed by the chart or service.

Before installing/enabling the config-service workload, run the owner-only
`as-config-migrate` command manually from an authorized environment, then run
`as-config-bootstrap-admin` once to create the first administrator. Migration
uses `AS_CONFIG_OWNER_DSN` and `AS_CONFIG_RUNTIME_ROLE`; it creates/verifies the
dedicated schemas, runs store schema setup, and grants the runtime role only its
required config-table/column permissions. `configSchema` defaults to
`as_config`; it and `auditSchema` must differ and neither may be `public`.
Runtime startup performs no DDL, migration, role provisioning, or grants.

Never put `AS_CONFIG_OWNER_DSN` in Helm values, chart-managed/external runtime
Secrets, or the web Pod. Helm references only the runtime Secret containing
`AS_CONFIG_DSN` and the audit HMAC key; the owner DSN is used only by the
operator's manual migration and bootstrap commands.

The service exposes a ClusterIP HTTP endpoint on port 8000. The application
serves both the console at `/` and API under `/internal/v1` from that same
origin; there is no separate console workload. For production, enable
`services.configService.ingress` and set its customer hostname and externally
managed TLS Secret name. This template supports ingress-nginx only and fails
unless `className` is `nginx`; it always sets the ingress-nginx SSL redirect
and force-redirect annotations to `"true"`, which user values cannot override.
Other ingress controllers require separately reviewed external configuration
and must not be represented by this template. Ingress requires
`proxyHeaders: true` and a non-empty
`trustedProxies` list of the actual ingress proxy IPs/CIDRs. Wildcards and
default routes (`*`, `0.0.0.0/0`, `::/0`, and other `/0` entries) are rejected.
Do not broaden proxy trust to make forwarded HTTPS work; configure the exact
controller source ranges and its forwarded-scheme behavior. TLS must be active
for login, and console plus API must remain on the same HTTPS origin.

The standalone Python `http.server` preview is for static `?preview=1` UI work
only; it does not serve the API and is not a deployment option. These image and
Helm resources are code-level delivery evidence only, not deployed HTTPS,
trusted-proxy, browser-workflow, M4b, or REQ acceptance evidence.

### M4b-7.2d ingress-nginx deployment prerequisites (BLOCKED)

The Ingress annotations are chart-level requests only; they cannot configure
the external ingress-nginx controller. Before claiming HTTPS behavior, verify
all of the following against the actual customer/test deployment:

- Retain the default ingress-nginx annotation prefix,
  `nginx.ingress.kubernetes.io`; a customized prefix can cause these chart
  annotations to be ignored.
- Verify the controller's `no-tls-redirect-locations` setting does not exempt
  `/` (and thus this same-origin console/API route) from HTTPS redirects.
- Configure the Ingress to use the customer-managed TLS Secret containing the
  certificate for the deployed hostname.
- From an external client, test actual HTTP access to `/` and `/internal/v1`:
  confirm HTTP is redirected to HTTPS or rejected, then verify in a real
  browser that login credentials are never submitted over HTTP.
- Verify forwarded scheme headers are trusted only when received from the
  explicitly configured ingress proxy IPs/CIDRs; do not trust arbitrary
  clients or broaden `trustedProxies` to make the scheme appear secure.

Keep 7.2d **BLOCKED** until controller configuration, deployed HTTP/HTTPS
behavior, trusted-proxy behavior, and browser/network evidence from the real
deployment are recorded. Template annotations alone are not redirect proof.
