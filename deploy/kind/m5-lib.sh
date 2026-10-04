# Shared helpers for M5 kind evidence (source from other m5-*.sh scripts).
# shellcheck shell=bash

m5_repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

# IP on the docker bridge that kind nodes use to reach services on the Docker host (compose PG).
m5_kind_host_gateway() {
  local cluster="${KIND_CLUSTER_NAME:-as-m5}"
  local node="${cluster}-control-plane"
  if docker inspect "${node}" >/dev/null 2>&1; then
    docker inspect "${node}" --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}' | head -1
    return 0
  fi
  echo "172.17.0.1"
}

m5_compose_pg_port() {
  echo "${POSTGRES_PUBLISH_PORT:-55432}"
}

# Runtime DSN for config-service Pods (as_config_web role from compose init).
m5_compose_runtime_dsn() {
  local host_ip="${1:-$(m5_kind_host_gateway)}"
  local port="${2:-$(m5_compose_pg_port)}"
  local user="${AS_CONFIG_WEB_USER:-as_config_web}"
  local pass="${AS_CONFIG_WEB_PASSWORD:-as_config_web_dev}"
  local db="${AS_CONFIG_DB:-as_config}"
  echo "postgresql://${user}:${pass}@${host_ip}:${port}/${db}"
}

# Start compose Postgres if needed; wait until TCP accepts connections on the published port.
m5_ensure_compose_postgres() {
  local root="${1:-$(m5_repo_root)}"
  local port
  port="$(m5_compose_pg_port)"
  cd "${root}/deploy/compose"
  if ! docker compose ps --status running postgres 2>/dev/null | grep -q postgres; then
    echo "==> starting deploy/compose postgres (published :${port})"
    docker compose up -d postgres
  else
    echo "==> compose postgres already running"
  fi
  local deadline=$((SECONDS + 120))
  while ((SECONDS < deadline)); do
    if (echo >/dev/tcp/127.0.0.1/"${port}") 2>/dev/null; then
      echo "==> postgres accepting connections on 127.0.0.1:${port}"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: postgres not reachable on 127.0.0.1:${port} after 120s" >&2
  return 1
}

# curl/wget on the host should not traverse corporate HTTP proxies for loopback checks.
m5_noproxy_env() {
  local host="${M5_INGRESS_HOST:-console.m5.test}"
  export NO_PROXY="127.0.0.1,localhost,${host}"
  export no_proxy="127.0.0.1,localhost,${host}"
}
