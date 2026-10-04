#!/usr/bin/env bash
# ADR-0026 / M5 §4.6 (D12): bundled in-cluster PG+Redis for kind (dev credentials only).
set -euo pipefail
cat <<'EOF'
--set stateStores.enabled=true
--set stateStores.bootstrapDevCredentials=true
--set stateStores.networkPolicy.enabled=true
EOF
