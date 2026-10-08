# IMS simulation platform

Testbed only. This chart is not `deploy/helm` and it is not part of the product install.

Two namespaces:

| Namespace | Workloads |
|---|---|
| `ims-sim` | simulated S-CSCF, S-SBC (north and south), callee, call-load UI |
| `as-sut` | the product chart `deploy/helm` with `values-product-as.yaml`: the translation SIP process (lab image `as-sut:dev` from `Dockerfile.product`), Redis, PostgreSQL, and config-service. The released image `deploy/docker/Dockerfile` does not bind SIP yet. |

Call load opens SIP only toward the simulated S-CSCF. The system under test accepts SIP from the north S-SBC. The page is a Service inside `ims-sim`, not an Ingress on the product console, and it does not log in.

TLS material is a test CA created at install time by `kind-up.sh`. It is not an operator PKI. Do not commit the generated keys.

```sh
bash testbed/sim-platform/kind-up.sh
kubectl -n ims-sim port-forward svc/ims-sim-ui 8088:8088
```

If `deb.debian.org` stalls while building the image, set `M71_DEBIAN_MIRROR` to another Debian host and run the script again.

The script creates the cluster without kind's own CNI and installs Calico (`kind-calico.yaml`), because kindnet does not enforce NetworkPolicy. With Calico, call load cannot reach the system under test or the north S-SBC, and only the north S-SBC can reach the system under test. `M71_CNI=kindnet` keeps kind's CNI; then only the system under test's own source check refuses direct SIP, with a 403. To switch an existing cluster between the two, delete it first (`kind delete cluster --name as-m71`).

Each hop advertises its headless Service name in Via, Record-Route and Contact and listens on the pod IP. TLS peers verify that name against the test certificate, so a dialog request that reconnects to a later hop still passes hostname checks.

Open the page, pick call types, transport, CPS, duration, hold time and the concurrent-call cap, then press 启动. The page shows each type's sent, connected and failed counts, response codes and setup latency, plus a total row, peak connected calls, calls not torn down, and the error distribution.

Local path, without kind:

```sh
uv run python -m as_simulators serve
```

The page says 非运营商 PKI. Result counts are the current run, not a capacity commitment.
