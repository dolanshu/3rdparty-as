#!/bin/bash
# Create the M7.1 kind namespaces.
# ims-sim runs the simulated S-CSCF, S-SBC, callee, and call-load UI.
# as-sut runs deploy/helm: the product AS (translation rules, Redis), not the
# Python decision front.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CLUSTER="${M71_KIND_CLUSTER:-as-m71}"
CHART="$ROOT/testbed/sim-platform/chart"
CERT_DIR="${M71_CERT_DIR:-$(mktemp -d)}"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing $1" >&2
    exit 1
  }
}

need kind
need kubectl
need helm
need docker
need uv

# calico (default) enforces NetworkPolicy. kindnet is kind's own CNI and does not.
CNI="${M71_CNI:-calico}"
CALICO_VERSION="${M71_CALICO_VERSION:-v3.28.2}"

if ! kind get clusters | grep -qx "$CLUSTER"; then
  if [ "$CNI" = "calico" ]; then
    kind create cluster --name "$CLUSTER" --config "$ROOT/testbed/sim-platform/kind-calico.yaml"
  else
    kind create cluster --name "$CLUSTER"
  fi
fi

kubectl config use-context "kind-$CLUSTER"
if [ "$CNI" = "calico" ]; then
  if ! kubectl -n kube-system get daemonset calico-node >/dev/null 2>&1; then
    kubectl apply -f "https://raw.githubusercontent.com/projectcalico/calico/${CALICO_VERSION}/manifests/calico.yaml"
  fi
  kubectl -n kube-system rollout status daemonset/calico-node --timeout=600s
  kubectl wait --for=condition=Ready nodes --all --timeout=300s
else
  echo "kindnet does not enforce NetworkPolicy. Only the SUT's own source check refuses direct SIP."
fi
kubectl create namespace ims-sim --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace as-sut --dry-run=client -o yaml | kubectl apply -f -

uv run --project "$ROOT" python -m as_simulators issue-certs \
  --out "$CERT_DIR" \
  --dns "scscf,ssbc-north,ssbc-south,uas,sut,scscf.ims-sim.svc.cluster.local,ssbc-north.ims-sim.svc.cluster.local,ssbc-south.ims-sim.svc.cluster.local,uas.ims-sim.svc.cluster.local,sut.as-sut.svc.cluster.local,as-sut-translation.as-sut.svc.cluster.local"

for ns in ims-sim as-sut; do
  kubectl -n "$ns" create secret generic ims-sim-test-ca \
    --from-file=ca.crt="$CERT_DIR/ca.crt" \
    --from-file=server.crt="$CERT_DIR/server.crt" \
    --from-file=server.key="$CERT_DIR/server.key" \
    --dry-run=client -o yaml | kubectl apply -f -
done

docker build -t ims-sim:dev \
  --build-arg "DEBIAN_MIRROR=${M71_DEBIAN_MIRROR:-deb.debian.org}" \
  --build-arg "HTTP_PROXY=${http_proxy:-}" \
  --build-arg "HTTPS_PROXY=${https_proxy:-}" \
  --build-arg "http_proxy=${http_proxy:-}" \
  --build-arg "https_proxy=${https_proxy:-}" \
  -f "$ROOT/testbed/sim-platform/Dockerfile" "$ROOT"
kind load docker-image ims-sim:dev --name "$CLUSTER"

NATIVE="$ROOT/testbed/sim-platform/.image-native"
mkdir -p "$NATIVE"
cp -f "$ROOT"/platform/native/resip_runtime/build/_resip_runtime*.so "$NATIVE"/
cp -f "$ROOT"/.cache/m2-resiprocate/build/resip/dum/libdum-1.14.so "$NATIVE"/
cp -f "$ROOT"/.cache/m2-resiprocate/build/resip/stack/libresip-1.14.so "$NATIVE"/
cp -f "$ROOT"/.cache/m2-resiprocate/build/rutil/librutil-1.14.so "$NATIVE"/
docker build -t as-sut:dev \
  --build-arg "HTTP_PROXY=${http_proxy:-}" \
  --build-arg "HTTPS_PROXY=${https_proxy:-}" \
  --build-arg "http_proxy=${http_proxy:-}" \
  --build-arg "https_proxy=${https_proxy:-}" \
  -f "$ROOT/testbed/sim-platform/Dockerfile.product" "$ROOT"
kind load docker-image as-sut:dev --name "$CLUSTER"

docker build -t as-config-service:m71-lab \
  --build-arg "HTTP_PROXY=${http_proxy:-}" \
  --build-arg "HTTPS_PROXY=${https_proxy:-}" \
  --build-arg "http_proxy=${http_proxy:-}" \
  --build-arg "https_proxy=${https_proxy:-}" \
  -f "$ROOT/deploy/docker/config-service.Dockerfile" "$ROOT"
kind load docker-image as-config-service:m71-lab --name "$CLUSTER"

helm upgrade --install ims-sim "$CHART" \
  --namespace ims-sim \
  --set image.repository=ims-sim \
  --set image.tag=dev

# Replace the earlier Python decision front if that release is still installed.
if helm -n as-sut status as-sut >/dev/null 2>&1; then
  chart_name="$(helm -n as-sut list -o json | uv run --project "$ROOT" python -c 'import json,sys; rows=json.load(sys.stdin); print(next(row["chart"] for row in rows if row["name"]=="as-sut"))')"
  case "$chart_name" in
    ims-sim-*) helm -n as-sut uninstall as-sut ;;
  esac
fi

kubectl -n as-sut create secret generic as-sut-test-tls \
  --from-file=tls.crt="$CERT_DIR/server.crt" \
  --from-file=tls.key="$CERT_DIR/server.key" \
  --from-file=ca.crt="$CERT_DIR/ca.crt" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n as-sut delete job as-sut-config-migrate --ignore-not-found
helm_files=(-f "$ROOT/testbed/sim-platform/values-product-as.yaml")
if kubectl -n as-sut get configmap as-sut-runtime-bundle >/dev/null 2>&1; then
  helm_files+=(-f "$ROOT/testbed/sim-platform/values-product-as-bundle.yaml")
fi
helm upgrade --install as-sut "$ROOT/deploy/helm" \
  --namespace as-sut \
  "${helm_files[@]}" \
  --set image.repository=as-sut \
  --set image.tag=dev

kubectl apply -f "$ROOT/testbed/sim-platform/product-as-networkpolicy.yaml"

# The image tag and the secret name do not change between runs, so restart to pick up both.
kubectl -n ims-sim rollout restart deploy
kubectl -n as-sut rollout restart deploy
for deploy in scscf ssbc-north ssbc-south uas call-load; do
  kubectl -n ims-sim rollout status "deploy/$deploy" --timeout=180s
done
kubectl -n as-sut rollout status deploy/as-sut-translation --timeout=180s
kubectl -n as-sut rollout status deploy/as-sut-redis --timeout=180s
kubectl -n as-sut rollout status deploy/as-sut-config-service --timeout=180s
kubectl -n as-sut wait --for=condition=complete job/as-sut-config-migrate --timeout=180s

echo "UI: kubectl -n ims-sim port-forward svc/ims-sim-ui 8088:8088"
echo "非运营商 PKI. Counts on the page are this run only."
