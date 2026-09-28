#!/usr/bin/env bash
# Generate self-signed TLS certificate for resip-probe E4 TLS scenario.
# Output: cert.pem + key.pem in current directory (1 day validity).

set -euo pipefail

openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem \
  -days 1 -nodes -subj "/CN=127.0.0.1"

echo "[gen-cert] Generated cert.pem + key.pem (CN=127.0.0.1, validity=1 day)"
