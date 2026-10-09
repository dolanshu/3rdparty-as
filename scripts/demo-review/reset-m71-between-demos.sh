#!/usr/bin/env bash
# Remove the as-m71 demo environment, or check that it is already gone.
# Does not stop Docker, delete other kind clusters, or remove base-image cache.
set -euo pipefail

# shellcheck source=scripts/demo-review/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# shellcheck source=scripts/lib/repo-toolchain.sh
source "${REPO_ROOT}/scripts/lib/repo-toolchain.sh"
repo_toolchain_prepend_path "${REPO_ROOT}"

CHECK_ONLY=0
case "${1:-}" in
  --check) CHECK_ONLY=1 ;;
  "") ;;
  *) demo_die "Usage: $0 [--check]" ;;
esac

CLUSTER="as-m71"
LAB_IMAGES=(ims-sim:dev as-sut:dev as-config-service:m71-lab)

stop_page_forwards() {
  while read -r pid args; do
    case "${args}" in
      kubectl*"port-forward"*"ims-sim-ui"*"8088:8088"*|\
      kubectl*"port-forward"*"as-sut-postgres-0"*"15432:5432"*)
        demo_log "stop port-forward pid ${pid}"
        kill "${pid}" >/dev/null 2>&1 || true
        ;;
    esac
  done < <(ps -eo pid=,args=)
}

page_forward_running() {
  local pid args
  while read -r pid args; do
    case "${args}" in
      kubectl*"port-forward"*"ims-sim-ui"*"8088:8088"*|\
      kubectl*"port-forward"*"as-sut-postgres-0"*"15432:5432"*)
        return 0
        ;;
    esac
  done < <(ps -eo pid=,args=)
  return 1
}

cluster_exists() {
  kind get clusters 2>/dev/null | grep -qx "${CLUSTER}"
}

image_exists() {
  docker image inspect "$1" >/dev/null 2>&1
}

redis_container_exists() {
  docker container inspect as-d10-redis >/dev/null 2>&1
}

assert_clean() {
  local image
  if cluster_exists; then
    demo_die "kind cluster ${CLUSTER} still exists"
  fi
  for image in "${LAB_IMAGES[@]}"; do
    if image_exists "${image}"; then
      demo_die "lab image ${image} still exists"
    fi
  done
  if page_forward_running; then
    demo_die "ims-sim-ui port-forward is still running"
  fi
  if redis_container_exists; then
    demo_die "container as-d10-redis still exists"
  fi
  demo_log "as-m71 demo environment is clean"
}

if [[ "${CHECK_ONLY}" -eq 1 ]]; then
  assert_clean
  exit 0
fi

stop_page_forwards
if cluster_exists; then
  demo_log "delete kind cluster ${CLUSTER}"
  kind delete cluster --name "${CLUSTER}"
fi
for image in "${LAB_IMAGES[@]}"; do
  if image_exists "${image}"; then
    demo_log "remove image ${image}"
    docker rmi "${image}"
  fi
done
if [[ -d "${REPO_ROOT}/testbed/sim-platform/.image-native" ]]; then
  demo_log "remove testbed/sim-platform/.image-native"
  rm -rf "${REPO_ROOT}/testbed/sim-platform/.image-native"
fi
if redis_container_exists; then
  demo_log "remove container as-d10-redis"
  docker rm -f as-d10-redis >/dev/null
fi
assert_clean
