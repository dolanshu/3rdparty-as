#!/usr/bin/env bash
# Generate self-signed TLS material for local M4b-8 HTTPS (localhost + 127.0.0.1).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="${ROOT}/certs"
mkdir -p "${CERT_DIR}"

openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes \
	-keyout "${CERT_DIR}/tls.key" \
	-out "${CERT_DIR}/tls.crt" \
	-subj "/CN=localhost" \
	-addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

chmod 0644 "${CERT_DIR}/tls.crt"
chmod 0600 "${CERT_DIR}/tls.key"
echo "Wrote ${CERT_DIR}/tls.crt and tls.key"
