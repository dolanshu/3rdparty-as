#!/usr/bin/env bash
set -euo pipefail
CLUSTER_NAME="${KIND_CLUSTER_NAME:-as-m5}"
if ! command -v kind >/dev/null 2>&1; then
  echo "kind not installed" >&2
  exit 1
fi
if kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
  echo "kind cluster ${CLUSTER_NAME} already exists"
  exit 0
fi
kind create cluster --name "${CLUSTER_NAME}" --wait 120s
