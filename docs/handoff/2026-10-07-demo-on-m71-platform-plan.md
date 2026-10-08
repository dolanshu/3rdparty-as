# Demo 接到 M7.1 平台 — 准备（2026-10-07）

> **状态**：第 4、5 步已跑通（2026-10-08）。故事 C 的集群镜头是 kind `as-m71`（`ims-sim` 五个仿真 Deployment，`as-sut` 的翻译、Redis、config-service；反诈没起），仍是 L1。7.2d 留在 `kind-as-m5`，本场跳过。故事 D 口播加上 `as-sut` Redis 不是客户 K8s 的 REQ-NF-1。故事 E 口播加上测试页几秒计数不进 O1 报告。测量脚本没改。M8 仍搁置。
> **上游**：[`2026-10-07-m7.1-sim-platform-plan.md`](2026-10-07-m7.1-sim-platform-plan.md) §11，证据 [`../acceptance/m71-sim-platform-evidence.md`](../acceptance/m71-sim-platform-evidence.md)。
> **不在本文**：重开 M8；改 `deploy/docker/Dockerfile`（SIP 监听留到重开 M8 之前）；签 REQ-S-2 / REQ-S-3 / REQ-S-4；把计数写成容量承诺。

客户 demo 仍是 [`pre-m8-demo-review-plan.md`](pre-m8-demo-review-plan.md) 的五个故事。变的是信令在哪条网上跑，以及故事 A 的规则从哪来。

---

## 1. 现在两条网

| | 现有脚本 | 这次要接到的 |
|---|---|---|
| 信令 | loopback、契约测试、`AS_CONFIG_BUNDLE_PATH` 口播 | kind `as-m71`：call load → 仿真 S-CSCF → 仿真北向 S-SBC → 产品 Helm AS → 仿真南向 S-SBC → 被叫 |
| 集群 | 故事 C 看 `kind-as-m5` | 同一场改看 `as-m71` 的 `ims-sim` 与 `as-sut` |
| 规则 | 故事 A 用本机 compose Postgres 的集成测；产品进程用 `AS_RULESET_JSON` | 故事 A 在这个集群上走 config-service：提案、批准、编译，翻译进程吃编译结果 |
| 控制台 | `https://localhost:8443`（compose） | 仍是产品控制台。`ims-sim` 的测试页不是控制台，无登录，不挂产品 Ingress |

测试页只用来选呼叫类型、设负载、看这一次的结果。页上写明非运营商 PKI。

---

## 2. 口播不改的

- 测试 CA 不是运营商 PKI。不签 REQ-S-2 / REQ-S-3。
- 测试页无登录，不签 REQ-S-4。产品控制台的登录仍只在故事 A 的控制面里讲。
- 结果页的次数和时延是这一次运行，不是容量承诺。故事 E 仍是研究方法。
- F2 在这条产品路径上是 **603**，不说成 608。608 只属于单独的反诈进程；那个进程这次不和翻译抢 5060。
- 故事 C 仍是 L1：不说 M5 全链已验收，不说生产告警或缩容已闭环。
- 故事 D 不是客户 K8s 上的 REQ-NF-1。Close 前不做那种采证。
- 明文 5060 仍是可选传输。不演示「只要 TLS 就拒绝明文」。
- call load 直达产品 SIP 被网络策略丢掉，这是要给观众看的限制，不是故障。

---

## 3. 五个故事怎么接

### 故事 A — 开通翻译号段

控制面和信令拆开，都要在场。

1. 控制台仍讲双角色、被叫+前缀、变更单、审批。compose 的 `https://localhost:8443` 可以继续当控制台镜头。
2. 已接到 `as-sut`（2026-10-08）：`scripts/demo-review/publish-m71-bundle.sh` 对集群 Postgres 走提案、另一人批准、分发报告、激活，四条判决编译进版本库。翻译进程读 `AS_CONFIG_BUNDLE_PATH`，不再读 `AS_RULESET_JSON`。`+86` 去掉再加 `0` 仍是 `AS_TRANSLATION_RULES_JSON`。进程不拉包，脚本把已激活的 JSON 挂进 Pod。生产默认 `services.configService.enabled` 仍是 false。控制台 HTTPS 登录不在这个集群。
3. 信令验证改走测试页，不再把 `test_e1_s2_*` 和双腿集成测当作现场。观众看到：T1 改号后 200，T4 404。出腿用户是 `013800138000`。

config-service 镜像、Secret、runtime role 按 chart 现有约定接，不把仿真开关写进生产默认 values。实验室材料仍放 `testbed/sim-platform/`。

### 故事 B — 拦截诈骗号段

现场改走测试页，同一条产品路径：

| 类型 | 观众看到 |
|---|---|
| T5 | 200 |
| T4 | 404 |
| F2 | 603，不是 608 |
| T1 | 200，被叫已改号 |

反诈单测里的 608 可以留在脚本后半，口播说那是另一个进程，这条网上没有起。BYE 要能 2xx 结束，出腿也拆。UDP、TCP、TLS 至少各走一轮短跑，不做成容量场。

### 故事 C — 平台能运维

`chart-check`、指标/draining 单测、告警 YAML 形态保留。集群镜头已改到 `as-m71`（2026-10-08）：

- `ims-sim`：S-CSCF、北向/南向 S-SBC、被叫、call-load
- `as-sut`：`as-sut-translation`、Redis、config-service。反诈进程是停的，因为会和翻译抢 5060

7.2d Ingress 登录仍挂在原来的 M5 集群证据上，不搬进 `as-m71`，也不把测试页说成那个登录。F10 的 L1 边界保留。

### 故事 D — 通话不随便丢

脚本没改：Redis、recovery 构建、工程 harness 仍是原来的。口播已加上：`as-sut` 里 Redis 在跑，但这不是客户集群上的杀 Pod 验收。

### 故事 E — 我们能扛多少

O1 报告和「不是 SLA」的口播保留。测量脚本没加测试页短跑。口播已写明：`as-m71` 的几秒计数不进 O1 报告。

---

## 4. 顺序

| # | 做完能看到什么 | 还不动 |
|---|---|---|
| 1 | 本文被当作执行单。`pre-m8-demo-review-plan.md` 文首指向这里 | 脚本 |
| 2 | 已跑通（2026-10-08）。故事 B 和故事 A 的信令步走 `as-m71` 测试页，T1/T4/T5/F1/F2，BYE 2xx | config-service |
| 3 | 已跑通（2026-10-08）。判决规则来自 config-service 编译 bundle，进程读 `AS_CONFIG_BUNDLE_PATH`。改号表仍是 `AS_TRANSLATION_RULES_JSON` | 生产默认 values、发布 Dockerfile、控制台登录搬到 `as-m71` |
| 4 | 已跑通（2026-10-08）。故事 C 看 `as-m71` 两个命名空间，L1 话术还在。`as_active_calls` 从翻译 Pod 读到 | 7.2d 搬集群、M8 |
| 5 | 已改口播（2026-10-08）。D：`as-sut` Redis 不是客户 K8s 的 REQ-NF-1。E：测试页计数不进 O1 | 测量脚本和 harness |

口播不要把改号表说成 bundle 里的字段，也不要说 SIP 进程自己拉了包。控制台网页仍在 compose 的 `https://localhost:8443`。

---

## 5. 准备完成的样子

- 五个故事的步骤表和 `scripts/demo-review/README.md` 写的是 `as-m71` 这条路径，而不是 loopback / `kind-as-m5` 当信令现场。
- 故事 A 能在这个集群上从批准后的 bundle 打出 T1 改号。
- 故事 B 的现场响应码是 200 / 404 / 603。
- 故事 C 仍不能被听成 M5 全链签收。
- 证据落在 `artifacts/demo-review/<date>/`，不提交 pcap、私钥、测试 CA 长期密钥。
- 亲手验收按 [`pre-m8-demo-review-plan.md`](pre-m8-demo-review-plan.md) §4。每步分「做什么 / 看什么 / 说明什么」。
