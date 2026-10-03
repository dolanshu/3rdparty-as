#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ ! -f .env ]]; then
	echo "Missing ${ROOT}/.env — copy .env.example and set AS_AUDIT_RESOURCE_HMAC_KEY_B64." >&2
	exit 1
fi

if [[ ! -f certs/tls.crt ]]; then
	echo "Missing TLS certs — run: ./scripts/gen-certs.sh" >&2
	exit 1
fi

docker compose up -d --build postgres testbed-health config-service caddy
echo "HTTPS console/API: https://localhost:${HTTPS_PUBLISH_PORT:-8443}/ (trust self-signed cert in browser)"
