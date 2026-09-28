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

`$AS_NAMESPACE` appears in `ASRestartLoop` (a kube-state-metrics selector, so
the rule only looks at AS Pods). Substitute it at load time (for example with
`envsubst`, or by templating the `PrometheusRule`), or replace it with the
namespace of the customer system — one namespace holds one complete system
(REQ-NF-9).

## Naming conventions

| Kind | Convention | Example |
|---|---|---|
| Alert name | `AS` + PascalCase condition | `ASHighErrorRatio` |
| Group name | `as.` + domain | `as.call-path`, `as.control-plane` |
| Metric name | `as_` prefix, snake_case, `_total` for counters, base unit suffix for seconds | `as_sip_responses_total`, `as_tls_certificate_expiry_seconds` |
| Labels | `severity` + `component`; metrics carry `use_case` (and `pod` where per-instance) | `severity: critical`, `component: state` |

Every rule carries `annotations.summary` (one line, for the notification
subject) and `annotations.description` (what it means and what to check first).

## Metric contract

These are the metric names the rules expect. They come from the OTel metrics of
ADR-0005; if the exporter renames one, change it here in the same commit — a
rule that silently stops matching is worse than no rule.

| Metric | Type | Meaning |
|---|---|---|
| `as_sip_responses_total{use_case,status_class,status_code}` | counter | SIP responses by class and code |
| `as_active_calls{use_case,pod}` | gauge | calls currently in flight |
| `as_telemetry_dropped_total{use_case}` | counter | `dropped_count` of ADR-0005 (queue full) |
| `as_state_store_available{use_case}` | gauge | 1 = Redis reachable, 0 = unreachable |
| `as_config_rollbacks_total{use_case}` | counter | automatic config rollbacks (ADR-0006) |
| `as_config_version_in_sync{use_case,pod}` | gauge | 1 = reported version == latest version |
| `as_tls_certificate_expiry_seconds{use_case}` | gauge | seconds until the serving certificate expires |
| `kube_pod_container_status_restarts_total{...}` | counter | kube-state-metrics, for restart loops |

## Why there is no capacity alert

There is intentionally no rule with a CPS ceiling or a concurrent-session
ceiling. O1 — the capacity target — is an open item: it is measured in M6 with a
real-socket harness, and `AGENT.md` §2 / §6 forbid publishing a capacity figure
before that measurement exists (`docs/plan.md` §5.1).

Every threshold in `as-alerts.yaml` is therefore one of:

- a **ratio** (failure responses over all responses),
- a **relative change** (active calls against their own trailing average),
- a **state condition** (store reachable or not, version in sync or not,
  certificate expires within N days, restart count over a fixed window).

None of them is the answer to O1, and each `description` says so explicitly —
so that nobody later mistakes a threshold here for a measured capacity limit.

Capacity alerts are added **after** M6, from its measurement, in a new group
(for example `as.capacity`). Until then, an unexplained load problem is
investigated with `ASActiveCallsSurge` and the M6 harness, not with a number
invented in advance.

## Adding a rule

1. Make sure the metric is already exported (ADR-0005 / REQ-NF-13) and named per
   the contract above.
2. Keep the threshold ratio-, relative- or state-based. If it needs an absolute
   capacity number, stop and route it through M6 instead.
3. Add `summary` and `description`; state in the description that the threshold
   is not a capacity figure.
4. Run `promtool check rules` and update the metric contract table above.
