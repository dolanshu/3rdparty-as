#!/usr/bin/env bash
# M5-0c: helm lint + template guards for deploy/helm (ADR-0013, plan.md §4.4.4).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
CHART="${REPO_ROOT}/deploy/helm"
RELEASE_NAME="${HELM_RELEASE_NAME:-as}"

if [[ -n "${HELM_BIN:-}" && -x "${HELM_BIN}" ]]; then
  HELM="${HELM_BIN}"
elif command -v helm >/dev/null 2>&1; then
  HELM=helm
elif [[ -x /tmp/linux-amd64/helm ]]; then
  HELM=/tmp/linux-amd64/helm
else
  echo "helm not found; install helm 3.x or set HELM_BIN" >&2
  exit 1
fi

echo "==> helm lint ${CHART}"
"${HELM}" lint "${CHART}"

echo "==> helm template default (AS-only, expect 7 objects)"
DEFAULT_RENDER="$("${HELM}" template "${RELEASE_NAME}" "${CHART}" 2>/dev/null)"
KIND_COUNT="$(printf '%s\n' "${DEFAULT_RENDER}" | grep -c '^kind:' || true)"
if [[ "${KIND_COUNT}" -ne 7 ]]; then
  echo "expected 7 rendered kinds, got ${KIND_COUNT}" >&2
  exit 1
fi

echo "==> helm template config-service enabled"
"${HELM}" template "${RELEASE_NAME}" "${CHART}" \
  --set services.configService.enabled=true \
  --set services.configService.secretName=as-config-runtime \
  --set services.configService.runtimeRole=as_config_runtime \
  >/dev/null

echo "==> helm template config-service ingress (7.2d template path)"
"${HELM}" template "${RELEASE_NAME}" "${CHART}" \
  --set services.configService.enabled=true \
  --set services.configService.secretName=as-config-runtime \
  --set services.configService.runtimeRole=as_config_runtime \
  --set services.configService.proxyHeaders=true \
  --set 'services.configService.trustedProxies={10.0.0.0/8}' \
  --set services.configService.ingress.enabled=true \
  --set services.configService.ingress.host=console.example.test \
  --set services.configService.ingress.tlsSecretName=console-tls \
  >/dev/null

echo "==> autoscaling.enabled without minReplicas must fail"
set +e
FAIL_MSG="$("${HELM}" template "${RELEASE_NAME}" "${CHART}" --set autoscaling.enabled=true 2>&1)"
set -e
if [[ "${FAIL_MSG}" != *minReplicas* ]]; then
  echo "expected minReplicas required error, got: ${FAIL_MSG}" >&2
  exit 1
fi

echo "==> helm template stateStores.enabled (ADR-0026 bundled state)"
STATE_RENDER="$("${HELM}" template "${RELEASE_NAME}" "${CHART}" \
  --set stateStores.enabled=true \
  --set stateStores.bootstrapDevCredentials=true 2>/dev/null)"
STATE_KIND_COUNT="$(printf '%s\n' "${STATE_RENDER}" | grep -c '^kind:' || true)"
if [[ "${STATE_KIND_COUNT}" -lt 12 ]]; then
  echo "expected >= 12 rendered kinds with bundled state, got ${STATE_KIND_COUNT}" >&2
  exit 1
fi
if ! printf '%s\n' "${STATE_RENDER}" | grep -q 'kind: StatefulSet'; then
  echo "expected StatefulSet for postgres" >&2
  exit 1
fi
if ! printf '%s\n' "${STATE_RENDER}" | grep -q 'component: state-redis'; then
  echo "expected state-redis component" >&2
  exit 1
fi

echo "==> helm template stateStores + config-migrate Job"
MIGRATE_RENDER="$("${HELM}" template "${RELEASE_NAME}" "${CHART}" \
  --set stateStores.enabled=true \
  --set stateStores.bootstrapDevCredentials=true \
  --set stateStores.migrateJob.enabled=true \
  --set services.configService.enabled=true \
  --set services.configService.runtimeRole=as_config_runtime 2>/dev/null)"
if ! printf '%s\n' "${MIGRATE_RENDER}" | grep -q 'kind: Job'; then
  echo "expected migrate Job when stateStores.migrateJob.enabled" >&2
  exit 1
fi
if ! printf '%s\n' "${MIGRATE_RENDER}" | grep -q 'as-config-migrate'; then
  echo "expected as-config-migrate command in Job" >&2
  exit 1
fi

echo "chart-check: OK"
