#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-as-m5}"
PLATFORM_TAG="${AS_PLATFORM_IMAGE:-as-platform:m5}"
CONFIG_TAG="${AS_CONFIG_IMAGE:-as-config-service:m5}"

cd "${ROOT}"
docker build -t "${PLATFORM_TAG}" -f deploy/docker/Dockerfile .
docker build -t "${CONFIG_TAG}" -f deploy/docker/config-service.Dockerfile .
kind load docker-image "${PLATFORM_TAG}" --name "${CLUSTER_NAME}"
kind load docker-image "${CONFIG_TAG}" --name "${CLUSTER_NAME}"
echo "loaded ${PLATFORM_TAG} and ${CONFIG_TAG} into kind ${CLUSTER_NAME}"
