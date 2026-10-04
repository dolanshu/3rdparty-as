# M5 §4.6 — in-cluster PostgreSQL & Redis (ADR-0026)

> Plan: [`plan.md`](../plan.md) §4.6 · Chart: `deploy/helm/` · Profile: [`values-onprem.example.yaml`](../../deploy/helm/values-onprem.example.yaml)

## Scope

| In scope | Out of scope (other milestones) |
|----------|----------------------------------|
| Same namespace as AS / config-service | **IMS operator PG** (forbidden as AS DSN) |
| Helm `stateStores.enabled=true` | **D3** Sentinel / split-brain (M2) |
| NetworkPolicy (default on) | **PG streaming HA** detail (customer + ADR-0008) |
| Owner migrate + runtime DSN wiring | M5 maintainer sign-off (after §4.6 checklist) |

## Install (on-prem)

```sh
helm upgrade --install as deploy/helm \
  -f deploy/helm/values-onprem.example.yaml \
  --namespace as-prod --create-namespace \
  --set image.repository="<customer>/as-platform" \
  --set image.tag="<release>" \
  --set sip.peerAllowlist="<s-sbc-cidrs>" \
  --set tls.secretName="<tls-secret>" \
  --set services.configService.image.repository="<customer>/as-config-service" \
  --set services.configService.secretName="<runtime-secret>"
```

**kind / lab** (dev credentials, emptyDir PG):

```sh
M5_BUNDLED_STATE=1 bash deploy/kind/m5-helm-install.sh
```

## Schema migrate (owner DSN — not in runtime Pod)

1. Port-forward governance Postgres:

   ```sh
   kubectl -n <ns> port-forward pod/as-3rdparty-as-postgres-0 15432:5432
   ```

2. Run migrate **once per schema version** from a trusted host (or `as-config-service` image job):

   ```sh
   export AS_CONFIG_OWNER_DSN="postgresql://as_config_owner:<password>@127.0.0.1:15432/as_config"
   export AS_CONFIG_RUNTIME_ROLE=as_config_runtime
   export AS_AUDIT_SCHEMA=console_audit
   export AS_CONFIG_SCHEMA=as_config
   uv run as-config-migrate
   ```

   Roles `as_config_owner` / `as_config_web` / `as_config_runtime` are created on first PG init when using chart init script (`state-postgres.yaml`); production may use DBA-provisioned roles instead.

3. Runtime Secret for config-service Pod must contain `AS_CONFIG_DSN` ( **`as_config_web`** ) and `AS_AUDIT_RESOURCE_HMAC_KEY_B64`. Never put owner DSN in the Deployment.

### Helm migrate Job (production / repeatable)

When `stateStores.migrateJob.enabled=true` and `services.configService.enabled=true`:

- **Production** (`values-onprem.example.yaml`): create Secret `as-config-migrate-owner` with key `AS_CONFIG_OWNER_DSN` (owner login only). Run once per schema version:

  ```sh
  helm upgrade --install as deploy/helm -f deploy/helm/values-onprem.example.yaml ...
  kubectl -n <ns> delete job/as-3rdparty-as-config-migrate --ignore-not-found
  kubectl -n <ns> wait --for=condition=complete job/as-3rdparty-as-config-migrate --timeout=300s
  ```

- **kind/dev** (`bootstrapDevCredentials=true`): Job may inline owner DSN from dev values; still **not** for customer production.

## PostgreSQL HA / PITR (customer ops — ADR-0008 / ADR-0026 §4)

Chart ships a **single-replica** StatefulSet for governance PG. Production HA is **customer-owned**:

| Tier | Minimum expectation |
|------|---------------------|
| **Lab / kind** | emptyDir or single PVC; backup optional |
| **On-prem prod** | Document **RPO/RTO**; use `pg_dump -Fc` (above) or WAL archive to off-cluster storage; failover via customer Postgres HA (Patroni, cloud RDS, etc.) **or** external `postgres.host` with `stateStores.enabled=false` |
| **Restore drill** | Restore dump to a fresh instance, re-run `as-config-migrate` if schema version changed, point runtime Secret at new host |

Redis HA remains **O5 / D3** (Sentinel); chart single Redis is not HA.

## Bootstrap first admin (after migrate)

```sh
kubectl -n <ns> exec -it deploy/as-3rdparty-as-config-service -- \
  as-config-bootstrap-admin   # reads env; interactive getpass
```

(Exact CLI name per `pyproject.toml` console script — use image entrypoint docs.)

## Backup & restore (ADR-0008 minimum)

**PostgreSQL** (governance — must retain audit chain):

```sh
kubectl -n <ns> exec as-3rdparty-as-postgres-0 -- \
  pg_dump -U postgres -d as_config -Fc -f /tmp/as_config.dump
kubectl -n <ns> cp as-3rdparty-as-postgres-0:/tmp/as_config.dump ./as_config.dump
```

Schedule via customer backup tooling (Velero, cron Job, or off-cluster WAL archive for HA). Chart does not ship backup Jobs.

**Redis** (runtime — ADR-0007: loss ≈ call failure, backup optional):

- Document RPO/RTO with customer; single-replica chart Redis is **not** HA until O5/D3.

## Upgrade discipline (ISSU vs state)

| Change | Suggested command focus |
|--------|-------------------------|
| AS image / SIP knobs only | `helm upgrade` with only `image.*`, `sip.*`, `useCases` |
| PG image / PVC | Maintenance window; follow Postgres upgrade runbook |
| Redis | Maintenance window; expect brief runtime unavailability |

Label selectors: `app.kubernetes.io/component=state-postgres|state-redis` vs use-case Deployments.

## Verify (§4.6 evidence)

```sh
make chart-check
make m5-kind-verify   # kind; expects postgres + redis + AS when M5_BUNDLED_STATE=1
kubectl -n as-m5 get pods -l app.kubernetes.io/part-of=3rdparty-as
kubectl -n as-m5 exec deploy/as-3rdparty-as-translation -- printenv REDIS_URL CONFIG_DB_HOST
```

## Re-run config-service + ingress (7.2d)

```sh
# If ingress admission webhook times out on kind:
kubectl delete validatingwebhookconfigurations ingress-nginx-admission 2>/dev/null || true
bash deploy/kind/m5-ingress-evidence.sh
```

Requires `as-config-migrate` (owner DSN) after first PG start. Bundled PG uses **headless** Service + DSN host `…-postgres-0.…-postgres` (see `_helpers.tpl`).

## §4.6 closure evidence (2026-10-04)

```sh
make gate && make chart-check && make test-integration-compose && make m5-kind-verify
kubectl -n as-m5 get pods
# expect: postgres-0, redis, translation, anti-fraud, config-service (when ingress enabled)
```
