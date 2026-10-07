# M7.1 产品 AS 联调记录（2026-10-07）

> **工程关门（2026-10-07）。** 对照计划 §9。下面是关门所用的这一次 kind 运行。
>
> 路径是页面 / call load → 仿真 S-CSCF → 仿真北向 S-SBC → **产品 Helm AS** → 仿真南向 S-SBC → 被叫。
> 测试 CA 不是运营商 PKI。REQ-S-2 / REQ-S-3 不因本文签 pass。页面没有登录，不签 REQ-S-4。
> 下面的次数和时延只描述这一次运行，不是容量承诺。
> 不提交证书、私钥、pcap。

## 环境

| 项 | 值 |
|---|---|
| 集群 | kind `as-m71`，Calico v3.28.2，单节点 |
| `ims-sim` | 仿真 S-CSCF、北向/南向 S-SBC、被叫、call load 页面。镜像 `ims-sim:dev` |
| `as-sut` | `deploy/helm` release `as-sut`，Deployment `as-sut-translation`。镜像 `as-sut:dev`（带本机编好的 `_resip_runtime`）。Redis `as-sut-redis` 在跑。规则来自 `AS_RULESET_JSON`，不是 config-service 下发 |
| 安装 | `bash testbed/sim-platform/kind-up.sh`，产品 values 在 `testbed/sim-platform/values-product-as.yaml`（不写进生产默认 values） |

F1 / F2 走产品内核的 FORWARD / BLOCK（603），和第一版呼叫类型一致。反诈限频是另一个进程，会抢同一 SIP 端口，这次没有另起。

## 呼叫

从 `call-load` pod 调页面 API。每种传输约 3 秒、5 次/秒，五种类型各 3 次。T4 无匹配规则，404。F2 是 603，没有改成 608。接通的对话（T1 / T5 / F1）BYE 都是 2xx，`unresolved` 为 0。产品把入腿 BYE 转到出腿。404 / 603 不建立对话，没有 BYE。

| 传输 | 结果 | 拆除 |
|---|---|---|
| UDP | 200×9，404×3，603×3 | BYE 2xx，unresolved 0 |
| TCP | 200×9，404×3，603×3 | BYE 2xx，unresolved 0 |
| TLS | 200×9，404×3，603×3。T1 出腿 `sips:013800138000@ssbc-south…:5061` | BYE 2xx，unresolved 0 |

修之前：UDP / TCP 的 BYE 是 415，因为 call load 在空的 ACK / BYE 上带了 `Content-Type: application/sdp`，产品只接受 INVITE 上的这个类型。TLS 的 BYE 超时，因为三种传输同时开着时 Contact 仍指向 5060，下一跳用 TLS 去连明文端口。次数不是容量承诺。

## 直达被网络策略丢掉

这是期望行为，不是缺陷。`call-load` 向产品 Pod 的 UDP 5060 发 INVITE，2 秒内没有 SIP 响应（`TimeoutError`）。产品没有回 403。北向 S-SBC 的 INVITE 能到产品并得到上述响应。产品入向策略只放行北向 S-SBC；call load 的出向只放行 S-CSCF。

## 关门之后

1. **重评 demo，把故事接到这个平台。** 那时再接 config-service 下发。故事 A 已经覆盖提交、批准、编译 bundle，信令桥用 `AS_CONFIG_BUNDLE_PATH`。本关门不改 `scripts/demo-review/`。
2. **发布镜像带上 SIP 监听，放在重新打开 M8 之前。** `deploy/docker/Dockerfile` 仍是 M5 进程壳，不绑定 SIP。`as-sut:dev` 只用于这个 kind 实验。
