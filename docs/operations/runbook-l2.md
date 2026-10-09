# L2 运维手册（深度排障与信令分析）— In-house IMS Application Server（文档暂用名）

> **读者**：L2 / 二线工程。日常巡检与告警首响应见 [`runbook-l1.md`](runbook-l1.md)。
>
> **证据口径（必读）**：**E1 / E4 / E5 未验收**（reSIProcate 生产路径行为 / TLS 热轮换 / 状态外置仍 open，[`../plan.md`](../plan.md) §5.1 O2/O3）；**e2e marker = 0**，performance 仅 accept-all harness、**非业务判决路径**；**M4b-7.2d / M8 7.2d 仍 blocked**；**零容量数字**（O1 未裁决；文中 1% / 30% / 3 次每分钟是**既有告警阈值，不是容量指标**）；kind / compose 抓包**不是现网证据**（ADR-0014：testbed 非 v1 交付物）；测试 CA 不签 REQ-S-2 / S-3。
>
> **原件保留**：本页归集自 [`../acceptance/`](../acceptance/) 既有 runbook 与字段契约，原件**不删除、不移动、不改写**。逐节来源见 §10。

## 1. 排障方法论

**顺序固定：部署层 → 接入层 → 控制面层 → 判决层 → 状态存储层。** 反向排（先怀疑判决）是最常见的浪费。各层的边界与典型故障：

- **部署层**（Helm / Secret / ingress-nginx / 状态存储 Pod / 迁移 Job）：CrashLoop、占位 DSN、Job 不到期、注解被改写。
- **接入层**（SIP trunk / TLS / peer 白名单，对端 S-SBC 信任边界 ADR-0016）：403、握手失败、呼叫根本没到。
- **控制面层**（config-service：变更单 / 审批 / 灰度分发 / 版本）：配了不生效、版本漂移。
- **判决层**（纯函数 `decide()`，无 socket / 无时钟 / 无全局状态）：404 / 603 判决结果与预期不符。
- **状态存储层**（Redis：会话 / dialog / 反诈速率窗口，ADR-0002 / ADR-0007）：`as_state_store_available=0`。

**「5 分钟自证不是你的锅」—— AS 侧能自证**：进程 ready 状态（`/health/live`、`/health/ready`）；收到 / 发出过哪些 SIP 消息（按 Call-ID 的运行时日志，§2）；各副本 `CONFIG_VERSION` 是否一致；`as_state_store_available` / `as_downscale_removable` 等 `as_*` 序列；判决路径（纯函数，可重放）。

**AS 侧不能自证**：S-CSCF → S-SBC 段的 iFC 触发上下文与结果（该段**完全不经过 AS**）；S-SBC → AS trunk 段**对端**侧的信令落地结果（对端**各自抓本侧**）；出腿信令在下游网元侧收到了什么；**容量边界**（O1 未裁决，任何容量数字都不成立，`AGENT.md` §2）；呼叫轨迹的长期保留与查询（O4 / D5 未裁决）。**AS 侧证据不足时不得先行定界** —— 先与 OP-NOC 拉双方时间线联合对齐（[`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §4）。

## 2. 日志取证

**检索契约。** REQ-NF-13 的取证挂载点是 JSON 日志，字段固定为 **`timestamp` / `level` / `trace_id` / `call_id` / `direction` / `method`**（`trace_id` 即 Call-ID）。权威文件是**字段契约**（不是 runbook）：[`../acceptance/m8-resip-runtime-log-contract.md`](../acceptance/m8-resip-runtime-log-contract.md)。该契约冻结 C++ 绑定（`platform/native/resip_runtime/runtime_module.cxx`）以 `cout/cerr` 输出的 `key=value` 行；解析器 `platform/src/as_platform/sip/resip_runtime_log_contract.py`（`parse_resip_runtime_log_line` / `is_resip_runtime_log_line` / `ResipRuntimeLogEvent.to_nf13_fields`），由 `platform/tests/test_resip_runtime_log_contract.py`（`contract` marker，13 例）守卫 —— **C++ 改名或改键即红**。

**事件 → 字段 → NF-13 映射（原文照抄契约表）**

| event（C++ 行位置） | fields | NF-13 映射（`to_nf13_fields`） |
|---|---|---|
| `RESIP_RUNTIME_LISTENING`（`runListener`，udp/tcp/tls 三行） | `address, advertised, udp_port/tcp_port/tls_port` | `level=info`，其余 `None`（无呼叫上下文） |
| `RESIP_RUNTIME_UAC_INVITE_SENT`（`onNewSession` 转发） | `outgoing_call_id, inbound_call_id, route_uri` | `call_id/trace_id=outgoing_call_id`，`direction=outbound`，`method=INVITE` |
| `RESIP_RUNTIME_UAC_NEW_SESSION`（`onNewSession` UAC） | `outgoing_call_id` | 同上（`outbound/INVITE`） |
| `RESIP_RUNTIME_UAC_FAILURE`（`onFailure`） | `outgoing_call_id, status` | 同上（`outbound/INVITE`，`level=info`：下游失败是业务事件） |
| `RESIP_RUNTIME_UAS_FAILURE_MAPPED`（`onFailure` 映射后） | `outgoing_call_id, downstream_status, upstream_status` | 同上（`outbound/INVITE`） |
| `RESIP_RUNTIME_OUTBOUND_CANCEL_FORWARD`（`onTerminated` RemoteCancel） | `inbound_call_id` | `call_id/trace_id=inbound_call_id`，`direction=inbound`，`method=CANCEL` |
| `RESIP_RUNTIME_UAS_ANSWER_RELAYED`（`onAnswer` 200 中继） | `outgoing_call_id` | `outbound/INVITE` |
| `RESIP_RUNTIME_RELOAD_CERTIFICATES`（`runListener`） | `detail=invoked`（唯一无 `=` 的固定字面） | `level=info`，其余 `None` |
| `*_ERROR / *_CALLBACK_ERROR / *_CORRELATION_MISS / *_WORKER_ERROR`（各 `cerr` 点） | `message=<单字>` 或对应 id 字段；**含空格的 message 行按格式漂移 fail-closed（返回 `None`）** | `level=error`，`call_id/trace_id` 取 `outgoing_call_id/inbound_call_id`（若有） |

**示例行（原文照抄，可直接用于检索）**

```text
RESIP_RUNTIME_LISTENING address=127.0.0.1 advertised=127.0.0.1 udp_port=5060
RESIP_RUNTIME_UAC_INVITE_SENT outgoing_call_id=out-1@127.0.0.1 inbound_call_id=in-1@127.0.0.1 route_uri=sip:downstream@127.0.0.1:5070
RESIP_RUNTIME_UAC_NEW_SESSION outgoing_call_id=out-1@127.0.0.1
RESIP_RUNTIME_UAC_FAILURE outgoing_call_id=out-1@127.0.0.1 status=486
RESIP_RUNTIME_UAS_FAILURE_MAPPED outgoing_call_id=out-1@127.0.0.1 downstream_status=486 upstream_status=486
RESIP_RUNTIME_OUTBOUND_CANCEL_FORWARD inbound_call_id=in-1@127.0.0.1
RESIP_RUNTIME_UAS_ANSWER_RELAYED outgoing_call_id=out-1@127.0.0.1
```

**读法**：① 一次 B2BUA 呼叫的锚点是 **`RESIP_RUNTIME_UAC_INVITE_SENT`** —— 唯一同时带 `inbound_call_id` 与 `outgoing_call_id` 的事件，**跨腿关联的唯一入口**（§3）。② 只有 `inbound_call_id`、无对应 `outgoing_call_id` → 出腿未发出（查下游 / 判决）。③ 只有 `outgoing_call_id`、无 `inbound_call_id` → 关联缺失，查 `*_CORRELATION_MISS`。④ `*_ERROR` 行含空格 → 解析器**返回 `None`**（fail-closed）；**不要**手工拼字段去凑，用 `message=` 单字形式的事件与相邻时间戳定位。

**Python 侧 JSON 富化与其边界。** `platform/src/as_platform/sip/resip_runtime.py::emit_native_log_event`（~30 行新增）：解析一行 native 行 → 用 `to_nf13_fields()` 补 `timestamp`（`time.time()`，可注入）、`level/trace_id/call_id/direction/method`（`trace_id` 可覆盖）→ 经 `as_platform.sip.resip_runtime.native` logger 输出 `json.dumps` 单行。三条边界：① native 行**本身不经过 Python logging**，富化发生在**采集转发侧**（抓 worker 控制台后逐行调用），集群没做这一步时 Pod 日志里仍是 `key=value` 原生行、**不是** JSON；② **这不是完整的 OTel 三信号** —— **traces 没有**，OTLP exporter 当前为 `NoOpExporter`，真实后端接线**仍未完成**，不要用「trace 视图里没有」推断「调用路径没发生」；③ 完整的 C++→Python JSON 回调 **defer 到 post-RC**，届时本节事件 / 字段表即回调 payload 的 schema 起点。

## 3. 信令抓包与对齐

逐段责任方表见 [`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §3：**S-CSCF → S-SBC（ISC 触发）与 AS → 下游（出腿）两段由对方抓**（AS 侧无前一段的 iFC 触发日志，也不持有出腿落地结果）；**S-SBC → AS trunk（SIP over TLS `5061`）双方各自抓本侧**；**AS 内部与 `testbed/` 仿真链路由我方抓**（仿真结果**不是现网证据**）。

**方法**

1. 双方各自在**本侧**对本侧进程 / 网元抓包。**TLS 下解密属各方责任，密钥不跨方共享**；AS 侧**不接受**为解密而复制对端私钥。
2. 关联键：AS 侧用 §2 的 `inbound_call_id` / `outgoing_call_id`。**双腿 B2BUA 的两腿 Call-ID 不同** —— 跨腿关联用「**时间戳 + Route / Record-Route**」：以入腿 `inbound_call_id` 为起点，沿 `route_uri` 与下游返回的 `Record-Route` 走，再对齐出腿的 `outgoing_call_id`。
3. 先对齐时间基准再比对；窗口不足时**不要**用「看起来同时」当证据。
4. **绝不提交真实抓包**（`AGENT.md` §11 / §13）。只提交脱敏后的字段 / 文本行 —— §2 的 `key=value` 行本身就是可提交形态。

## 4. 分层故障树

判定归属时联动 [`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §4 与 [`../product/compliance-matrix.md`](../product/compliance-matrix.md)（后者持有 file:line 证据）。

### 4.1 呼叫未到达 AS（无入腿日志）

1. Pod 与 Service Endpoints（`kubectl -n <ns> get pods -l app.kubernetes.io/part-of=3rdparty-as`）异常 → **AS（部署层）**。
2. `as_downscale_removable{use_case,pod}` 全为 0（draining 中被保护）→ **AS（draining 未收敛）**，转 §4.7。
3. ingress / 网络策略拒收对端，或 `AS_PEER_ALLOWED_ADDRESSES` / `AS_PEER_ALLOWED_CERT_FINGERPRINTS` 未命中 → **AS（边界策略）**，见 §4.2。
4. `/metrics` 中该 `use_case` 有序列但无入腿日志 → **对方（OP-SBC / OP-NET）**，转下一跳对齐。**AS 侧无证据时不得先行定界。**

### 4.2 AS 侧 403（对端白名单 / 明文被拒）

**明文在要求 TLS 时被拒**与**对端白名单未命中**两者**共用 403**（`sip/resip_runtime.py:39,334-346`；`sip/ingress.py:178-194`，`tls` / `sips` 之外的 transport 一律拒）→ 归属 **AS 侧（边界策略）**。下一步：确认对端是否以 TLS 发起；确认 `AS_TLS_CA_PATH` 指向的 CA 包含对端签发链；确认对端地址 / 指纹在 `AS_PEER_ALLOWED_ADDRESSES` / `AS_PEER_ALLOWED_CERT_FINGERPRINTS` 内。策略正确而对端仍被拒 → 转客户 PKI / 网络部。**旁证**：宿主机 `http_proxy` 让 `curl localhost` 走代理 → **403 / 000**（§4.6），这类 403 是**采证路径**问题，不是产品故障。

### 4.3 AS 侧 404 / 603 —— **符合预期行为，不是故障**

| 码 | 业务含义 | 下一步 |
|---|---|---|
| `404 Not Found` | **无匹配规则**，判决链默认结果（`adapter.py:25`；契约场景 S2） | 查号段 / 前缀规则是否覆盖该被叫；本应命中 → 规则问题，走**变更单**（ADR-0006） |
| `603 Decline` | **策略拒绝 / 策略判决拒绝**，如反诈超限（`adapter.py:24`；契约场景 S3） | 查生效规则版本与命中策略；与预期不符 → 走变更单回滚 |

**`603` 与 `404` 通常都不是故障**：先问「预期判决是什么」，再问「为什么没命中」。`608` 口径差见 §8。

### 4.4 下游失败码

**逐码透传集合 `{408, 480, 486, 503, 504}`**（`sip/call_controller.py:19-21,98-104`；native 同逻辑 `runtime_module.cxx:466-484`），其余非 2xx **映射为 `502`**。⚠️ **native 产品路径只对 `486` 有端到端测试**（`test_resip_two_leg_integration.py`、`test_m7_forward_two_leg_integration.py`），**其余四码无产品路径证据** —— 在 native 产品路径上看到 408 / 480 / 503 / 504 时**先不要**当已验证行为上报缺陷。完整码表与 file:line 见 [`../product/compliance-matrix.md`](../product/compliance-matrix.md) §3.6。

### 4.5 状态存储不可用

`as_state_store_available{use_case}` 为 `0` 持续 `2m` → `ASCallStateStoreUnavailable`（critical），归属 **AS 侧**；在途呼叫状态（会话 / dialog / 反诈速率窗口）都在 Redis（ADR-0002 / ADR-0007），**Redis 不可用 = 在途呼叫无法维持**。注意 `REDIS_URL` 未配置时**该序列不存在（不是 0）**，规则永不触发 —— 别把「没数据」读成「故障」。Sentinel 拓扑与脑裂窗口判定属未决 **O5 / D3** → 需裁决时升级维护者。

### 4.6 config-service CrashLoop / Ingress 不 Ready

来源：[`../acceptance/m5-7.2d-ingress-runbook.md`](../acceptance/m5-7.2d-ingress-runbook.md)（检查项 1–6、M5-1d、admission webhook、公司 HTTP 代理、7.2d 口径分档）与 [`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) §Re-run config-service + ingress。

| 现象 | AS 侧检查 | 处置 / 口径 |
|---|---|---|
| config-service **CrashLoop** | DSN 主机名是不是占位 `postgres:5432` | 占位 DSN **仅集群内 Service 名**；compose 未装进 kind（或客户集群无同名 Service）时 CrashLoop。Ingress 对象仍可创建，但 **Ready 证据**依赖 M5-1d → 用外部 PG / 外部 Service 名 |
| **403 Forbidden**（控制台 / API） | controller 是否保留 `nginx.ingress.kubernetes.io` annotation **prefix**（`kubectl describe ingress` 看注解键名） | 被改写 → 前缀被覆盖，重建 Ingress |
| **403 / 000**（宿主机 curl） | 是否设了 `http_proxy` | 用 `NO_PROXY=127.0.0.1,localhost kubectl port-forward` 或 `make m5-kind-verify` —— **采证路径问题，不是产品 403** |
| **empty reply（curl 52）** | kind 默认 `m5-kind-up.sh` **未**映射 hostPort 80/443 | **empty reply 视为未过关**，需修环境（`extraPortMappings`）或换采证路径；**不得**在 plan 里勾 7.2d 关门 |
| **port-forward 200 但 7.2d 未过关** | 区分两档口径 | **M5-1c / §4.5 切片证据**：Ingress 对象 + 注解（检查项 1–3、6）+ config-service **Ready** + port-forward HTTP 200 即可；**M5 维护者签字 / §217③ / M4b-7.2d 关门**：**必须**完成检查项 **4–5**（经 ingress 的 301/308 + 浏览器仅 HTTPS），**port-forward 不能顶替** |
| admission webhook Job 超时 / 失败 | `kubectl -n ingress-nginx get jobs,pods` | 脚本 **WARN** + log `admission_job_ok=0` → **不要无记录地删 VWC**；kind 开发例外须在 evidence log 记原因，生产路径必须 Job 成功或按客户 ingress 规范配置。⚠️ `m5-state-stores-runbook.md` 里的 `kubectl delete validatingwebhookconfigurations ingress-nginx-admission 2>/dev/null \|\| true` 是**开发环境**回退写法，**生产照抄等于放弃关门证据** |
| trusted-proxy 误配 | `forwarded_allow_ips` / `AS_CONFIG_TRUSTED_PROXIES` | 必须**显式 IP / CIDR**；**不接受 `*`、不接受默认路由 `0.0.0.0/0`**（`services/config-service/src/as_config_service/runtime.py:105-116` fail-closed）；启用 proxy headers 而未设该项 → `AS_CONFIG_TRUSTED_PROXIES must be set when proxy headers are enabled` |
| TLS Secret 未挂载 | `tls.enabled=true` 且 `tls.secretName` 为空 | 渲染期 fail-closed；上线前必须提供客户 PKI Secret（NOTES.txt §1） |

### 4.7 缩容不掉话 / draining 不收敛

现象：Pod 已 cordon / 已删，但 `as_active_calls` 不降、`as_downscale_removable` 长期为 0。AS 侧检查：readiness 是否为 **503**；Endpoint 是否摘流；`AS_DOWNSCALE_GUARD_ENABLED` / `AS_DOWNSCALE_GUARD_PROTECT_ABOVE` 是否被 Helm 正确注入；是否走了 `preStop sleep` + SIGTERM（**不得 SIGKILL**）。四步操作见 [`runbook-l1.md`](runbook-l1.md) §3.1 与 [`../acceptance/m5-downscale-runbook.md`](../acceptance/m5-downscale-runbook.md)。⚠️ **证据边界**：现有 draining / 缩容证据用 `AS_M5_SIMULATED_ACTIVE_CALLS=N` **模拟**在途呼叫（SIGTERM 后每秒减 1），是 kind 上的机制证据；**真实 SIP 负载下的不掉呼叫待 M7 / M8 验收**（G-P1-1），**不得**用模拟证据向对方承诺「生产不掉话」。完整剧本见 [`fault-demarcation.md`](fault-demarcation.md)（**已落盘**；但完整剧本的真实集群证据仍 blocked，M8 7.2d 未解锁）。

## 5. 变更与灰度排障

**两个状态机**（ADR-0006；`services/config-service/src/as_config_service/change_order.py:17-23`、`distributor.py:49-55`）：

```text
变更单： DRAFT → submitted → approved → distributing → applied
                                          ↓ roll_back        ↓ roll_back
                                      rolled_back        rolled_back
         （submitted → rejected 为终态；REJECTED / APPLIED / ROLLED_BACK 均为终态）
分发：  pending → in_progress → completed   /   rolled_back
```

- **配置改了但不生效**：变更单是否走到「生效」态；灰度分发是否 `completed`；各实例上报 `CONFIG_VERSION` 是否一致（`printenv CONFIG_VERSION`，L1 §1 #3）。
- **判断不了规则命中** —— ⚠️ **`as_rule_hits_total` 当前无生产调用方**（`platform/src/as_platform/telemetry/metrics.py:254-260` 定义了写入接口，但生产路径无调用方，且**不在** `deploy/alerts/README.md` 指标契约表内）→ **不能靠它判断命中**。用 `call_id` + 生效规则版本 + 判决路径（纯函数，可重放）判断。
- **灰度期行为不一致**：运行态覆盖粒度 = 号段 + **稳定哈希百分比**（ADR-0021，`FNV-1a 32-bit(call_id)`）。同一号段内不同呼叫行为不同是**设计预期**，第一步看 `call_id` 落在哪个桶；查不到任何命中项时返回 `None`（fail-closed）。
- **规则改完导致大面积异常**：走变更单回滚（`rolled_back`），**不要**直接改数据库（配置不走 GitOps，`AGENT.md` §2）。
- **硬前置**：规则 schema 的**双向兼容**是 ISSU 升级的硬前置 —— 新旧实例并存期间任一方向不兼容即构成阻塞。`as-alerts.yaml` 里**没有**配置回滚 / 漂移类告警（`deploy/alerts/README.md` 明确 defer）；`deploy/helm/templates/NOTES.txt:39-42,57-60` 提到的 `ASConfigDrift` / `ASConfigRollbackTriggered` **不在规则文件中**（§8）。
- **iFC / 摘流边界**：iFC 触发逻辑属 S-CSCF / HSS，**不在 AS 侧**；AS 只实现 ISC 触发后的业务判决与运行态覆盖，且**不主动摘在途呼叫**。按号段 / 百分比的 iFC 触发需 S-CSCF / HSS 侧配合配置；完整流程见 [`rollback-playbook.md`](rollback-playbook.md)（**已落盘**；但依赖 S-CSCF / HSS 侧配合配置，真实集群演练仍 blocked，G-P1-10）。

## 6. 数据库与迁移排障

来源：[`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) §Schema migrate / §Helm migrate Job / §PostgreSQL HA / PITR 与 [`../acceptance/m5-7.2d-ingress-runbook.md`](../acceptance/m5-7.2d-ingress-runbook.md) §M5-1d。**排障第一件事：分清手里是哪条 DSN。**

| 用途 | 角色 / 环境变量 | 硬规则 |
|---|---|---|
| 迁移 | `AS_CONFIG_OWNER_DSN`（`as_config_owner`） | **owner DSN 绝不进 Deployment / runtime Secret**；只在可信主机或一次性 Job 中使用 |
| 运行时（config-service Pod） | `AS_CONFIG_DSN`，角色必须是 **`as_config_web`**（非 owner）；另有 `AS_AUDIT_RESOURCE_HMAC_KEY_B64` | 用错角色的表现是接口权限错，不是崩溃 |
| 最小权限 | `as_config_runtime`（`NOLOGIN`） | 审计 append-only 相关 |

**迁移命令原文（每个 schema 版本跑一次）**

```sh
kubectl -n <ns> port-forward pod/as-3rdparty-as-postgres-0 15432:5432
export AS_CONFIG_OWNER_DSN="postgresql://as_config_owner:<password>@127.0.0.1:15432/as_config"
export AS_CONFIG_RUNTIME_ROLE=as_config_runtime
export AS_AUDIT_SCHEMA=console_audit
export AS_CONFIG_SCHEMA=as_config
uv run as-config-migrate
```

**Helm migrate Job（生产 / 可重复）**：Secret `as-config-migrate-owner` 的键 `AS_CONFIG_OWNER_DSN`（仅 owner 登录）。

```sh
helm upgrade --install as deploy/helm -f deploy/helm/values-onprem.example.yaml ...
kubectl -n <ns> delete job/as-3rdparty-as-config-migrate --ignore-not-found
kubectl -n <ns> wait --for=condition=complete job/as-3rdparty-as-config-migrate --timeout=300s
```

⚠️ **Job 复用坑**：同名 Job 不重建 → 必须先 `delete job ... --ignore-not-found` 再 `wait`，否则会**等到一个已完成的旧 Job 而误判成功**。**顺序与依赖**：新库为空必须先跑 migrate（owner DSN，手动）；compose init 已建 role 时通常只需 schema 与 M4b 一致；内建 PG 用 **headless** Service，DSN host 形如 `…-postgres-0.…-postgres`（`deploy/helm/templates/_helpers.tpl`）；首启 PG 后仍需 `as-config-migrate`。

**首次管理员引导（migrate 之后）**

```sh
kubectl -n <ns> exec -it deploy/as-3rdparty-as-config-service -- \
  as-config-bootstrap-admin   # reads env; interactive getpass
```

> 原件注明：确切 CLI 名以 `pyproject.toml` console script / 镜像入口文档为准 —— 执行前先核实。

**排障对照**：① config-service CrashLoop → DSN 是否占位 `postgres:5432`、runtime Secret 是否被塞 owner DSN（§4.6）；② 迁移 Job 秒失败 → Secret `as-config-migrate-owner` 是否存在且键名正确、库是否可达；③ `as-config-migrate` 报权限错 → 你用的是 owner DSN 还是 runtime DSN；④ audit 写不进去 → audit 表 append-only（`BEFORE UPDATE OR DELETE` / `BEFORE TRUNCATE` 触发器），写入路径须用正确角色。

**PG HA / PITR 与 restore drill**：chart 只发**单副本** StatefulSet，生产 HA 由客户拥有（Patroni / 云 RDS，或外部 `postgres.host` + `stateStores.enabled=false`）；客户须记录 **RPO / RTO**，用 `pg_dump -Fc`（命令见 [`runbook-l1.md`](runbook-l1.md) §3.5）或 WAL 归档到集群外；restore drill = 恢复到新实例 → 若 schema 版本变了重跑 `as-config-migrate` → runtime Secret 指向新主机。**演练记录属交付物 2.5，见 [`backup-restore.md`](backup-restore.md)（已落盘；真实集群 restore drill 记录仍 blocked，依赖真实集群，M8 7.2d）**。Redis HA 仍是 **O5 / D3**，chart 单 Redis 非 HA。

## 7. 测试与签收环境准备

来源：[`../acceptance/m8-native-consistency-runbook.md`](../acceptance/m8-native-consistency-runbook.md)（该文件一句话，命令原文照抄）。**顺序不可颠倒：签收跑前必须先构建与被测证据对应的 native 扩展。**

```sh
make m2-platform-resip-build
# 行使 two-leg / recovery 证据时另加：
make m7-platform-two-leg-build
make m7-platform-recovery-build
```

随后运行签收命令：

```sh
AS_REQUIRE_NATIVE_EXTENSIONS=1 uv run pytest platform/tests/test_e1_contract_resip_runtime_full.py -m contract -q
AS_REQUIRE_NATIVE_EXTENSIONS=1 uv run pytest platform/tests/test_m7_forward_two_leg_integration.py platform/tests/test_req_f4_sdp_identity_integration.py -m integration -q
```

**关键行为（排障时最常误读的一点）**：**缺 native 扩展时用例 fail，而不是 skip**（`AS_REQUIRE_NATIVE_EXTENSIONS=1`；CI 中 `m2-platform-resip` / `m2-native-smoke` / `m7-*` 为阻塞式 job）。因此**忘记 `make m2-platform-resip-build` 会得到一片红**，而这**会被误读为产品缺陷** —— 看到 native 相关用例集体 fail，第一步先确认扩展是否构建过，再谈缺陷。

> **口径歧义提示**：原件写「随后运行计划 §7 命令」，但 `docs/plan.md` 的 §7 是「风险登记」，`docs/acceptance/test-plan.md` 无 §7 —— 该引用**无法解析到具体章节**。上列两条 `pytest` 命令即原件给出的全部命令，本页按**命令原文**照抄，不代为推断其它用例集。

## 8. 已知会误导排障的坑

| # | 坑 | 事实 |
|---|---|---|
| 1 | **把模拟 `active_calls` 当生产不掉话证据** | `AS_M5_SIMULATED_ACTIVE_CALLS=N` 是**仅测试 / 证据**用的模拟在途呼叫；真实 SIP 不掉呼叫待 M7 / M8 验收（G-P1-1） |
| 2 | **把 accept-all harness 当生产路径** | performance 层仅 accept-all harness，**非业务判决路径**（不经过 `decide()` 的规则匹配）；harness 覆盖 100/180/200 **不等于** 14 条 B2BUA 全文回放已签收 |
| 3 | **以为测试 CA 能验 REQ-S-2 / S-3** | **测试 CA 不签 REQ-S-2 / S-3**，测试页不签 REQ-S-4；kind 上的 TLS 证据是 testbed-only 窄范围证据 |
| 4 | **以为 `AS_M5_PROBE_SIP_STATUS` 能持续产生响应计数** | 它是**进程启动时的一次性探针**（`__main__.py:88-97`，生产 on-prem 不设）；用它推导 `ASHighErrorRatio` 会得到错误结论 |
| 5 | **以为 Prometheus 能抓到 AS 的指标** | ⚠️ **chart 未接线抓取**：Pod 模板**无** `prometheus.io/scrape` 注解，chart 内**无** ServiceMonitor / PodMonitor（`deploy/helm/templates/` 全目录无命中）。`/metrics` 端点存在且渲染出 `health-http` 端口，但**没有任何采集器被 chart 接线到它** → 标准部署下 Prometheus **收不到**这些序列 |
| 6 | **以为 NOTES.txt 里的告警名都存在** | `templates/NOTES.txt:39-42,57-60` 提到 `ASConfigDrift` / `ASConfigRollbackTriggered`，但 `as-alerts.yaml` 里**没有**；`deploy/alerts/README.md` 明确列为 **deferred**。按它们名去查告警系统会一无所获 |
| 7 | **把 `608 Rejected` 当产品拒绝码** | 产品路径**当前只发 `603 Decline`**；`608` 只出现在 POC 抓包基线的**运营商侧对端**声明中（[`../product/compliance-matrix.md`](../product/compliance-matrix.md) §3.8） |
| 8 | **把 403 一律当白名单问题** | 403 两条成因共用同一码（明文被拒 / 白名单未命中），另有宿主机代理导致 curl 403/000 的采证路径问题（§4.2 / §4.6） |
| 9 | **把 `as_state_store_available` 的「没数据」当 0** | 仅当 `REDIS_URL` 非空时才探测并写序列；未配置时**序列不存在（不是 0）** |
| 10 | **把 404 / 603 当故障** | 404 = 无匹配规则、603 = 策略拒绝，**都是预期判决**（§4.3）；另：用容量数字定界也不成立 —— O1 未裁决、`as-*` 无容量类规则、不得引用 M6 dev-host 数字（`AGENT.md` §2） |
| 11 | **把「改完就生效」当默认** | 配置**不走 GitOps**；必须走变更单状态机 + 灰度分发 + 实例上报版本（§5） |

## 9. 升级边界

**L2 自己的边界**：**不能**自行修改未决项、不能推翻既有裁决、不能把未验收项说成已验收（`AGENT.md` §15）。**升级到维护者**：① 需要裁决产品口径（如某状态码是否算缺陷）；② 需要动未决项（O1 / O4 / O5、D3 / D5）；③ 需要推翻 M5 工程关门或 M8 RC 的任何结论；④ 需要在**真实集群 / 真实对端**取证（依赖 S-CSCF / HSS 侧配合与客户环境，G-P1-10，AS 侧无法单方完成）；⑤ 涉及 Sh / 计费 / CDR / 媒体（**不在范围内**，改提对应范围的方案）。

**明确 N/A（出现即按 N/A 处理并给理由）**：Diameter Sh（数据来自自有数据面）；CDR / 话单 / 计费（以按 Call-ID 的呼叫轨迹替代，轨迹**不是**话单，ADR-0017）；媒体 / RTP / 转码 / DTMF / MRF（ADR-0004）；LI / IRI（属网内网元职能，ADR-0016）。

## 10. 来源映射

| 本页章节 | 原文件与位置 | 归集方式 |
|---|---|---|
| 状态块 | [`../acceptance/report.md`](../acceptance/report.md) §0；[`../plan.md`](../plan.md) §0 / §5.1；[`../product-packaging-plan.md`](../product-packaging-plan.md) §0.3 | 摘要 |
| §1 自证边界 | [`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §3/§4 | 摘要 |
| §2 全章 | [`../acceptance/m8-resip-runtime-log-contract.md`](../acceptance/m8-resip-runtime-log-contract.md) §1–§5（**字段契约表与 7 行示例日志原文照抄**） | 索引链接 + 原文照抄 |
| §3 抓包 | [`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §3 | 索引链接 + 摘要 |
| §4.1–§4.3 / §4.7 | [`../product/responsibility-matrix.md`](../product/responsibility-matrix.md) §4；[`../product/compliance-matrix.md`](../product/compliance-matrix.md) §3.6 | 摘要 |
| §4.2 / §4.4 | `sip/resip_runtime.py:39,334-346`、`sip/ingress.py:178-194`、`sip/call_controller.py:19-21,98-104`、`platform/native/resip_runtime/runtime_module.cxx:466-484` | 自核实（与合规矩阵一致） |
| §4.6 | [`../acceptance/m5-7.2d-ingress-runbook.md`](../acceptance/m5-7.2d-ingress-runbook.md)（检查项 1–6、M5-1d、admission webhook 表、代理节、7.2d 口径分档）；[`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) §Re-run config-service + ingress | 重写操作正文 + **冲突标注** |
| §5 | `change_order.py:17-23`；`distributor.py:49-55`；[ADR-0021](../architecture/adr/0021-runtime-override-granularity.md)；`telemetry/metrics.py:254-260` | 自核实 + 索引链接 |
| §6 | [`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) §Schema migrate / §Helm migrate Job / §PG HA / PITR；[`../acceptance/m5-7.2d-ingress-runbook.md`](../acceptance/m5-7.2d-ingress-runbook.md) §M5-1d | 重写操作正文（命令原文照抄） |
| §7 | [`../acceptance/m8-native-consistency-runbook.md`](../acceptance/m8-native-consistency-runbook.md)（**全文**） | 重写操作正文 |
| §8 | `report.md` §0.5 / §0.6；[`../product/ne-datasheet.md`](../product/ne-datasheet.md) §5；`deploy/alerts/README.md`；`deploy/helm/templates/NOTES.txt`；[`../plan.md`](../plan.md) §0 | 摘要 + 自核实 |