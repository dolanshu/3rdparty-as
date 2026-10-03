#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ ! -f .env ]]; then
	echo "Missing ${ROOT}/.env — copy .env.example and set AS_AUDIT_RESOURCE_HMAC_KEY_B64." >&2
	exit 1
fi

# shellcheck disable=SC1091
set -a && source .env && set +a

docker compose --profile setup run --rm migrate
