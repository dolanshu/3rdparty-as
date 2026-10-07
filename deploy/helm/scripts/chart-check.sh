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

# M5.1 minimal (H-3/H-4): tls.enabled=true requires tls.secretName and an empty
# sip.peerAllowlist fails closed (see ADR-0016). Every render below passes
# explicit testbed inputs; production values come from the customer profile.
SECURE_SET=(
  --set tls.secretName=chart-check-tls
  --set sip.peerAllowlist=10.0.0.0/8
)

echo "==> helm template default (AS-only, expect 7 objects)"
DEFAULT_RENDER="$("${HELM}" template "${RELEASE_NAME}" "${CHART}" "${SECURE_SET[@]}" 2>/dev/null)"
KIND_COUNT="$(printf '%s\n' "${DEFAULT_RENDER}" | grep -c '^kind:' || true)"
if [[ "${KIND_COUNT}" -ne 7 ]]; then
  echo "expected 7 rendered kinds, got ${KIND_COUNT}" >&2
  exit 1
fi

echo "==> helm template tls.enabled without secretName must fail (H-3)"
set +e
H3_MSG="$("${HELM}" template "${RELEASE_NAME}" "${CHART}" --set sip.peerAllowlist=10.0.0.0/8 2>&1)"
H3_CODE=$?
set -e
if [[ "${H3_CODE}" -eq 0 ]]; then
  echo "expected nonzero exit for tls.enabled=true without secretName" >&2
  exit 1
fi
if [[ "${H3_MSG}" != *tls.secretName* ]]; then
  echo "expected tls.secretName required error, got: ${H3_MSG}" >&2
  exit 1
fi

echo "==> helm template empty peerAllowlist must fail (H-4)"
set +e
H4_MSG="$("${HELM}" template "${RELEASE_NAME}" "${CHART}" --set tls.secretName=chart-check-tls 2>&1)"
H4_CODE=$?
set -e
if [[ "${H4_CODE}" -eq 0 ]]; then
  echo "expected nonzero exit for empty sip.peerAllowlist" >&2
  exit 1
fi
if [[ "${H4_MSG}" != *peerAllowlist* ]]; then
  echo "expected peerAllowlist required error, got: ${H4_MSG}" >&2
  exit 1
fi

echo "==> helm template config-service enabled"
"${HELM}" template "${RELEASE_NAME}" "${CHART}" \
  "${SECURE_SET[@]}" \
  --set services.configService.enabled=true \
  --set services.configService.secretName=as-config-runtime \
  --set services.configService.runtimeRole=as_config_runtime \
  >/dev/null

echo "==> helm template config-service ingress (7.2d template path)"
"${HELM}" template "${RELEASE_NAME}" "${CHART}" \
  "${SECURE_SET[@]}" \
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
FAIL_MSG="$("${HELM}" template "${RELEASE_NAME}" "${CHART}" "${SECURE_SET[@]}" --set autoscaling.enabled=true 2>&1)"
FAIL_CODE=$?
set -e
# K-2 (M5.1 minimal): assert the helm exit code, not just the message text —
# a grep-only pass cannot distinguish a real guard from a coincidental string.
if [[ "${FAIL_CODE}" -eq 0 ]]; then
  echo "expected nonzero helm exit for autoscaling.enabled without minReplicas" >&2
  exit 1
fi
if [[ "${FAIL_MSG}" != *minReplicas* ]]; then
  echo "expected minReplicas required error, got: ${FAIL_MSG}" >&2
  exit 1
fi

echo "==> helm template stateStores.enabled (ADR-0026 bundled state)"
STATE_RENDER="$("${HELM}" template "${RELEASE_NAME}" "${CHART}" \
  "${SECURE_SET[@]}" \
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
  "${SECURE_SET[@]}" \
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

echo "==> helm template onprem profile (H-2: values-onprem.example.yaml renders)"
# Test secretName overrides stand in for the customer-managed Secrets; the
# example file itself carries REPLACE_WITH_* placeholders (never real values).
set +e
ONPREM_RENDER="$("${HELM}" template "${RELEASE_NAME}" "${CHART}" \
  -f "${CHART}/values-onprem.example.yaml" \
  --set postgres.secretName=chart-check-pg \
  --set services.configService.secretName=chart-check-config-runtime \
  --set sip.peerAllowlist=10.0.0.0/8 \
  --set tls.secretName=chart-check-tls 2>/dev/null)"
ONPREM_CODE=$?
set -e
# K-2: assert the helm exit code explicitly; an empty render must not pass.
if [[ "${ONPREM_CODE}" -ne 0 ]]; then
  echo "onprem profile failed to render (exit ${ONPREM_CODE})" >&2
  exit 1
fi
if ! printf '%s\n' "${ONPREM_RENDER}" | grep -q 'kind: StatefulSet'; then
  echo "expected StatefulSet for postgres in onprem profile" >&2
  exit 1
fi
if ! printf '%s\n' "${ONPREM_RENDER}" | grep -q 'kind: Deployment'; then
  echo "expected Deployments in onprem profile" >&2
  exit 1
fi

echo "chart-check: OK"
