# `deploy/alerts/` — alert rule set (REQ-NF-14)

`as-alerts.yaml` is the shipped alert rule set for the AS. It is written against
the metrics exported by the OTel instrumentation of ADR-0005 (REQ-NF-13), and it
is plain Prometheus rule format: `groups:` → `rules:`, one file, no templating.

## Loading

Prometheus (static rule files):

```yaml
rule_files:
  - /etc/prometheus/rules/as-alerts.yaml   # or a directory glob
```

Validate before shipping it, and keep this in CI:

```sh
promtool check rules deploy/alerts/as-alerts.yaml
```

kube-prometheus-stack: wrap the file's `groups:` list in a `PrometheusRule`
(`spec.groups`) rather than mounting it, so that a reload is not needed. Keep
this file as the source of truth and generate the CR from it — do not maintain
two copies.

`$AS_NAMESPACE` appears in every kube-state-metrics selector (`ASRestartLoop`,
`ASPodNotReady`, `ASDeploymentReplicasUnavailable`, `ASStatefulSetUnavailable`,
`ASServiceEndpointsAbsent`), so those rules only look at Pods of the AS
namespace. Substitute it at load time (for example with `envsubst`, or by
templating the `PrometheusRule`), or replace it with the namespace of the
customer system — one namespace holds one complete system (REQ-NF-9), which is
the isolation boundary these selectors rely on.

## Naming conventions

| Kind | Convention | Example |
|---|---|---|
| Alert name | `AS` + PascalCase condition | `ASHighErrorRatio` |
| Group name | `as.` + domain | `as.call-path` |
| Metric name | `as_` prefix, snake_case, `_total` for counters, base unit suffix for seconds | `as_sip_responses_total`, `as_active_calls` |
| Labels | `severity` + `component`; metrics carry `use_case` (and `pod` where per-instance) | `severity: critical`, `component: state` |

Every rule carries `annotations.summary` (one line, for the notification
subject) and `annotations.description` (what it means and what to check first).

## Metric contract

These are the metric names the rules expect. They come from the OTel metrics of
ADR-0005; if the exporter renames one, change it here in the same commit — a
rule that silently stops matching is worse than no rule.

The `as_*` set below is **exactly** the set defined in
`platform/src/as_platform/telemetry/metrics.py` — six names, `MetricKind` is
`COUNTER` or `GAUGE` only, and **there is no histogram anywhere in the
repository**. If a metric you want is not in this table, it does not exist yet.

| Metric | Type | Producer (verified by reading the write site) | Consumed by |
|---|---|---|---|
| `as_active_calls{use_case,pod}` | gauge | Always written every 15s by `_start_metrics_loop` in `platform/src/as_platform/__main__.py` (no OTLP dependency). Value comes from `ActiveCallSource`, i.e. real SIP dialog events — or from `AS_M5_SIMULATED_ACTIVE_CALLS`, which is **evidence-only, not production load**. | `ASActiveCallsSurge`, `ASDownscaleBlocked` |
| `as_downscale_removable{use_case,pod}` | gauge | Always written every 15s by the same loop. Value = the ADR-0010 scale-down guard verdict: `0` when the instance still carries calls **or** is already draining. | `ASDownscaleBlocked` (had a writer but no reader until 2026-10-10) |
| `as_state_store_available{use_case}` | gauge | **Conditional:** written only when `REDIS_URL` is non-empty, by a real `PING` (`__main__.py`). When `REDIS_URL` is unset the series is **absent, not 0**. | `ASCallStateStoreUnavailable` |
| `as_sip_responses_total{use_case,status_class,status_code}` | counter | **No production producer.** The only start-up writer is the one-shot probe `AS_M5_PROBE_SIP_STATUS` (`__main__.py:_apply_m5_metrics_probes`), which production on-prem does not set; the real path is `respond_with_metrics` / `record_sip_status_code` and is not wired on every response yet (M7). | `ASHighErrorRatio` |
| `as_rule_hits_total{rule}` | counter | **No caller at all.** `CallMetrics.record_rule_hit` is defined but nothing in `src/` invokes it, so the series is never written. Listed here for completeness, not as an invitation to write a rule against it. | none |
| `as_telemetry_dropped_total{use_case}` | counter | **Conditional, twice over:** only written when the sink is a `BoundedQueueSink`, which `main()` only creates when `OTEL_EXPORTER_OTLP_ENDPOINT` is non-empty (chart default: `null`). Even then the exporter defaults to `NoOpExporter`, so the queue does not fill. | `ASTelemetryDropped` |

Consequence worth stating plainly: of the six `as_*` metrics, **only
`as_active_calls` and `as_downscale_removable` have a producer that runs in a
default on-prem deployment.** The other four are gated on configuration that
production does not set, or have no caller at all. A rule can be syntactically
perfect and still never fire.

### Kubernetes standard series (kube-state-metrics)

These come from **kube-state-metrics**, which is provided by the cluster, not by
this repository and not by this chart. Nothing here works unless the operator
has installed kube-state-metrics; if they have not, all five rules below are
silent.

| Metric | Used by |
|---|---|
| `kube_pod_container_status_restarts_total` | `ASRestartLoop` |
| `kube_pod_status_ready{condition="true"}` | `ASPodNotReady` |
| `kube_deployment_spec_replicas` / `kube_deployment_status_replicas_available` | `ASDeploymentReplicasUnavailable` |
| `kube_statefulset_replicas` / `kube_statefulset_status_replicas_ready` | `ASStatefulSetUnavailable` |
| `kube_endpoint_address_available` | `ASServiceEndpointsAbsent` |

These selectors are **namespace-scoped** (`$AS_NAMESPACE`), which is the
isolation boundary REQ-NF-9 gives us: one namespace holds one complete system.
They are deliberately *not* narrowed by `app.kubernetes.io/component`, because
kube-state-metrics only exposes Pod/Deployment labels as `label_*` series when
it is configured with a metric-labels allowlist — a cluster-side setting this
chart cannot assume. If a customer namespace hosts non-AS workloads, these rules
will see them too; use the `pod` / `deployment` / `statefulset` label on the
series to attribute correctly.

Control-plane alerts for config rollback, drift, and TLS expiry are **deferred**
until those metrics are exported from the config-service / SIP transport paths.
Do not add PromQL rules for metrics that are not emitted.

## Scrape wiring status

**This is a known, unclosed gap. The rules above are not "live".**

Verified 2026-10-10 by reading the chart:

- The AS Pod template (`deploy/helm/templates/deployment.yaml`) carries **no
  `prometheus.io/scrape` annotation**. Its only annotation is
  `checksum/config`.
- The chart contains **no `ServiceMonitor` and no `PodMonitor`** — the strings
  do not appear anywhere under `deploy/helm/templates/`.
- The `/metrics` endpoint exists and works
  (`platform/src/as_platform/runtime/health.py`), and the `health-http` port is
  declared on the container. Nothing is wired to it.

So in a standard deployment the process produces a correct exposition on
`:8080/metrics` and **no scraper collects it**. Prometheus therefore has no
`as_*` series, and every `as_*` rule stays `no data` regardless of how healthy
the process is. The kube-state-metrics rules are unaffected by this — that
source has its own scrape configuration, which the operator provides.

Closing this gap means adding either the Pod annotations or a `PodMonitor` /
`ServiceMonitor` to the chart, plus pointing an OTLP collector at
`OTEL_EXPORTER_OTLP_ENDPOINT` for the export path. That is chart work and
deployment-side configuration; it is tracked with the rest of the alert/delivery
backlog, and it is **not** done by editing this directory. Until it lands, no
document may describe the `as_*` rules as firing in production. Fetching the
endpoint by hand (`kubectl port-forward` + `curl :8080/metrics`) is the current
workaround and is what `runbook-l1.md` §1 check 4 tells the operator to do.

## New rules (2026-10-10, delivery 2.2)

Added because delivery 2.2 asks for the key-path alerts to be filled in. Every
one of them reads either a cluster-provided Kubernetes series or an `as_*`
metric this repository really writes; none of them invents a metric. **The five
original rules in group `as.call-path` were not touched.**

| Alert | Group | severity / component | Trigger condition (semantics) | Data source | Why it is not a capacity figure | Currently triggerable? |
|---|---|---|---|---|---|---|
| `ASPodNotReady` | `as.runtime` | `critical` / `runtime` | The Pod's `Ready` condition has been `false` for 5m. Readiness is the AS process refusing new work (`/health/ready` = 503 while draining, ADR-0009). | kube-state-metrics `kube_pod_status_ready` | It is a binary readiness state. It says nothing about how many calls per second the system carries — that is O1, measured in M6. | Yes, if the cluster runs kube-state-metrics. Note it also fires for a Pod that is legitimately mid-roll; check `/health/ready` before escalating. |
| `ASDeploymentReplicasUnavailable` | `as.runtime` | `warning` / `runtime` | Available replicas < desired replicas for the same Deployment, for 10m. | kube-state-metrics `kube_deployment_spec_replicas` / `..._status_replicas_available` | It compares two integers Kubernetes already publishes, and deliberately does **not** state how many replicas the system *should* have — that count is O1 / M6. | Yes, if kube-state-metrics is installed. Namespace-scoped, so it also covers the bundled `state-redis` and `config-service` Deployments. |
| `ASDownscaleBlocked` | `as.runtime` | `warning` / `runtime` | `as_downscale_removable == 0` while `as_active_calls == 0` for the same `pod`/`use_case`, for 30m. The ADR-0010 guard blocks removal for exactly two reasons — calls in flight, or already draining — so this means a drain that never completes. | `as_downscale_removable` + `as_active_calls` (both written every 15s, no OTLP dependency) | A binary guard state plus a zero count. No CPS, concurrency or session target is implied; O1 is untouched. | Series are always produced, so yes in principle — **but see the scrape gap above**. Its value also depends on real SIP dialog activity, so it stays quiet in a demo with no traffic. |
| `ASStatefulSetUnavailable` | `as.platform` | `critical` / `state` | A StatefulSet reports fewer ready replicas than it wants, for 5m. In this chart that is the governance PostgreSQL (ADR-0008): config versions, change orders, append-only audit. | kube-state-metrics `kube_statefulset_replicas` / `..._status_replicas_ready` | A replica readiness state. The bundled store being single-replica is a design fact (HA is the customer's; Redis HA is still O5 / D3) and is **not** a statement about how much traffic one replica carries — O1 / M6. | Yes, if kube-state-metrics is installed. |
| `ASServiceEndpointsAbsent` | `as.platform` | `warning` / `state` | A Service has zero available endpoint addresses for 5m, so clients cannot be routed. In this chart it covers the `state-redis` and `config-service` Services. | kube-state-metrics `kube_endpoint_address_available` | A routing state derived from ready endpoints. It says the Service is empty, not that the system is too busy; it carries no throughput number. | Yes, if kube-state-metrics is installed. Distinct failure mode from `ASCallStateStoreUnavailable` (which reports "AS cannot reach Redis"); this one reports "the Service has no backend at all". |

Still deferred, with reasons and exit conditions, in the table below.

## Deferred alerts (explicitly postponed)

Each row is something an operator could reasonably expect to find here, with why
it is absent and what would have to become true before it can be added. Adding
any of them early would mean writing PromQL against a metric that does not
exist — which `deploy/alerts/README.md` forbids and which produces a rule that
looks covered and is not.

| Candidate alert | Why it cannot be added now | Exit condition — what must be true first |
|---|---|---|
| **Latency / processing-time** (per-request duration, P95/P99, ISC trigger timeout) | No latency metric is exported. `MetricKind` has only `COUNTER` and `GAUGE`; **the repository has no histogram and no summary**, so there is nothing to compute a quantile from. Any `histogram_quantile` rule would reference an empty series forever. | A latency instrument (histogram or summary) is added to `telemetry/metrics.py`, a producer writes it on the real SIP path (M7, not the start-up probe), and the chart scrapes it. Note the O1 discipline also applies to any *absolute* latency target — a ratio or a relative regression is acceptable, a "must answer within N ms" number is not, until M6 measures it. |
| **ISC timeout / no response from the S-CSCF leg** | Same as above: no timeout counter or duration is exported, and ISC trigger handling is the S-CSCF's side of the boundary in any case (`docs/product/responsibility-matrix.md`). | An ISC-timeout counter is exported from the SIP adapter path with a real producer, **and** the ownership question of who declares a timeout is settled with the operator's S-CSCF side. |
| **Session leak** (calls in flight that never terminate) | There is no "expected" call count to leak *against* — `as_active_calls` is an absolute gauge, and using it as a leak baseline would be exactly the invented capacity number AGENT.md §2 forbids. `as_downscale_removable` tells you a drain is stuck, which is adjacent but not the same failure. | Either O1 settles what a legitimate in-flight call population is (from the M6 measurement), or a dedicated "sessions opened vs. sessions closed" counter pair is exported so a leak becomes a *ratio* rather than a threshold. |
| **TLS certificate expiry** | The metric does not exist. `as_tls_certificate_expiry_seconds` appears **only** as an illustrative name in the naming-convention table above; there is no such constant in `telemetry/metrics.py` and no producer. | The SIP transport exports a certificate-expiry gauge per `tls.secretName`, refreshed on the ADR-0016 hot-rotation path, and the scrape wiring is closed so the rule can see it. Rotation is a config hot reload (AGENT.md §13), so the alert is for the operator's PKI calendar, not a restart trigger. |
| **Config drift / rollback** (`ASConfigDrift`, `ASConfigRollbackTriggered`) | No config-plane metric is exported from config-service. These two names *are* mentioned in `deploy/helm/templates/NOTES.txt`, which is a known trap — a name in NOTES.txt is not a rule (see `runbook-l2.md` §8 item 6). | config-service exports drift and rollback-event series into the same scrape path. Until then, L1 checks the change-order state machine directly (`runbook-l1.md` §3.3). |
| **Rule-hit anomaly** (`as_rule_hits_total`) | The series has no caller: `CallMetrics.record_rule_hit` is defined but nothing invokes it, so it is never written. | A decision-path producer records rule hits, **and** an anomaly threshold is defined relative to a rolling baseline of the same series. An absolute "hits must be below N" rule would be a capacity figure in disguise. |
| **Capacity** — CPS ceiling, concurrent-session ceiling, per-Pod load threshold (`as.capacity` group) | **O1 is unresolved.** It is measured in M6 with a real-socket harness; AGENT.md §2 / §6 forbid publishing a capacity figure before that measurement exists. `AGENT.md` §2 and `docs/plan.md` §5.1 hold the open item. | O1 is decided by the maintainer from the M6 result. Only then is a new `as.capacity` group added, with values taken **from** the measurement. Nothing in this file may be read as pre-declaring it. |
| **Diameter Sh** — anything Sh-related | **N/A, not deferred.** Sh is a decided non-goal: the data comes from our own data plane (`AGENT.md` §2), and review item G-P0-4 removed the Sh alerts that had been drafted. | None. This is out of scope permanently for this product; if an Sh requirement appears it is a new requirement and a new ADR, not a new alert. |
| **CDR / billing / charging** alerts | **N/A, not deferred.** CDR, charging and rating are non-goals; call traces keyed by Call-ID (ADR-0017) replace the CDR. | None. |
| **Media / RTP / transcoding** alerts | **N/A, not deferred.** No media plane exists (ADR-0004), so there is nothing to alert on. | None. |

## Why there is no capacity alert

There is intentionally no rule with a CPS ceiling or a concurrent-session
ceiling. O1 — the capacity target — is an open item: it is measured in M6 with a
real-socket harness, and `AGENT.md` §2 / §6 forbid publishing a capacity figure
before that measurement exists (`docs/plan.md` §5.1).

Every threshold in `as-alerts.yaml` is therefore one of:

- a **ratio** (failure responses over all responses),
- a **relative change** (active calls against their own trailing average),
- a **state condition** (store reachable or not, restart count over a fixed window).

None of them is the answer to O1, and each `description` says so explicitly —
so that nobody later mistakes a threshold here for a measured capacity limit.

Capacity alerts are added **after** M6, from its measurement, in a new group
(for example `as.capacity`). Until then, an unexplained load problem is
investigated with `ASActiveCallsSurge` and the M6 harness, not with a number
invented in advance.

## Adding a rule

1. **Prove the metric has a producer before writing any PromQL.** Grep for the
   metric name and read the write site. A name in this table, a name in
   `NOTES.txt`, or a plausible-looking name you invented are not producers. If
   the only writer is a start-up probe, a test harness, or nothing at all, the
   rule cannot fire — fix the wiring or leave the rule out. (`ASHighErrorRatio`
   and `ASTelemetryDropped` are the cautionary examples: both are correct rules
   against series that a default production deployment never writes.)
2. Make sure the metric is already exported (ADR-0005 / REQ-NF-13) and named per
   the contract above.
3. Keep the threshold ratio-, relative- or state-based. If it needs an absolute
   capacity number, stop and route it through M6 instead.
4. Add `summary` and `description`; state in the description that the threshold
   is not a capacity figure.
5. Add `severity` and `component` labels. If it reads kube-state-metrics, use the
   `$AS_NAMESPACE` placeholder rather than a hard-coded namespace.
6. Update the metric contract table and the deferred-alerts table above in the
   same commit — a metric moves from "deferred" to "in use", or a new deferred
   row appears, and both are part of the change.
7. Run `promtool check rules deploy/alerts/as-alerts.yaml`, or `make
   alert-check`, which does the same thing and fails loudly if `promtool` is
   missing. Keep it in CI.
8. Record the new alert in `docs/operations/alert-response-matrix.md` (§2 has a
   per-alert row: trigger, first action, escalation, evidence) and in
   `docs/product/ne-datasheet.md` §6. An alert with no documented first action
   is not finished.
