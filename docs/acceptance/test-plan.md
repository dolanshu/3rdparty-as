# 验收测试计划（Test Plan）— 3rdparty-as

**版本**：v0.2（占位）
**日期**：2026-09-28
**状态**：占位 — 验收标准从 PRD v0.2 同步挪入，具体 test case 待 M2 设计阶段补充

> 本文档从 PRD v0.2（prd.md）的验收标准部分提取而来。
> 具体 test case（步骤、断言、数据准备）由 M2 设计阶段补充。
> **协议章节号说明**：同 PRD，文中 RFC 3261 章节号以 IETF 2002 年发布的 RFC 3261 原文为准。

---

## §1.1 呼叫信令核心路径（REQ-F-1 到 REQ-F-5）

### REQ-F-1 验收标准
- [ ] 启动仿真 S-SBC 和仿真对端（Return UAS）
- [ ] 从仿真 S-CSCF 发送 INVITE（目标号码命中业务规则）
- [ ] 依次断言收到 14 条消息：INVITE(上游) → 100 Trying(下游) → 100 Trying(上游) → 180 Ringing(上游) → 180 Ringing(下游) → 200 OK(上游) → 200 OK(下游) → ACK(下游) → ACK(上游) → BYE(上游) → 200 OK(下游) → BYE(下游) → 200 OK(上游) → BYE 之后的 200 OK 确认
- [ ] 消息方法和响应码严格等于 POC 基线 `testbed/contracts/sip-baseline/S1-basic-call/` 中的 14 条
- [ ] Via branch 参数符合 z9hG4bK 模式（reSIProcate 会产生不同的 hex 值，模式对即算过）
- [ ] 不检查 SDP `o=` 时间戳、不检查头域书写顺序

### REQ-F-2 验收标准
- [ ] 完成 REQ-F-1 的基本呼叫
- [ ] 提取入腿（上游）INVITE Call-ID（记为 C_in）
- [ ] 提取出腿（下游）INVITE Call-ID（记为 C_out）
- [ ] 断言 **C_in ≠ C_out**（两条腿对话独立，RFC 3261 §12 B2BUA 两侧各维护独立对话状态）
- [ ] 提取入腿 200 OK / ACK / BYE 的 Call-ID，断言**全部等于 C_in**（同一对话内 Call-ID 必须相同，RFC 3261 §8.1.1.4）
- [ ] 提取出腿 200 OK / ACK / BYE 的 Call-ID，断言**全部等于 C_out**

### REQ-F-3 验收标准
- [ ] 完成 REQ-F-1 的基本呼叫
- [ ] 提取上游 INVITE 的 Request-URI
- [ ] 提取下游 INVITE 的 Request-URI
- [ ] 断言 host/port 部分不同（路由地址改变）
- [ ] 断言 user 部分：**非翻译场景**保持不变；**翻译场景**按翻译规则改变 —— 基线 S1 即翻译场景（`+8613800138000` → `013800138000`），不得以"user 必须逐字节相等"作为翻译业务用例的验收

> 说明：本条断言已由派生基线测试 `testbed/simulators/tests/test_derived_baseline.py` 对 `S1-basic-call` 的 14 条消息实际执行；归一化后两侧指向同一被叫（`13800138000`）。

### REQ-F-4 验收标准
- [ ] 完成 REQ-F-1 的基本呼叫
- [ ] 提取上游 INVITE 的 SDP body（bytes）
- [ ] 提取下游 INVITE 的 SDP body（bytes）
- [ ] 断言两者逐字节相等
- [ ] 提取上游 200 OK 的 SDP body 和下游 200 OK 的 SDP body，同样逐字节相等

### REQ-F-5 验收标准
- [ ] 完成 REQ-F-1 的基本呼叫，其中上游 INVITE 带一个 Route 头（例如 `Route: <sip:proxy.example.com:5060>`）
- [ ] 断言我们消费了寻址到我们的 Route 头（下游 INVITE 不再保留该 Route 值）
- [ ] 断言下游请求的目标地址是**我们路由策略选定的对端**（不是运营商侧 Route 指向的代理）
- [ ] 构造下游对端返回带 Record-Route 的 200 OK
- [ ] 断言上游的 200 OK 里 Record-Route 头存在且值与下游 Record-Route 一致（RFC 3261 §12.1.2 Route Set 反向推导）

---

## §1.2 路由与策略决策（REQ-F-6 到 REQ-F-7）

### REQ-F-6 验收标准
- [ ] 启动仿真环境，规则表只包含 +86138*（不含 +86199*）
- [ ] 从仿真 S-CSCF 发送 INVITE 到 +861990000000
- [ ] 断言我们返回 404 Not Found（RFC 3261 §21.4.5）
- [ ] 断言不创建 B2BUA 对话（即不发下游 INVITE）
- [ ] 对拍 POC 基线 `testbed/contracts/sip-baseline/S2-no-match-404/` 的 4 条消息
- [ ] 断言匹配对象为目标号码（被叫方向）
- [ ] 断言最长前缀优先匹配

### REQ-F-7 验收标准
- [ ] 启动仿真环境，规则表包含 +86168* → R-BLOCK-90（阻止策略）
- [ ] 从仿真 S-CSCF 发送 INVITE 到 +861681000000
- [ ] 断言我们返回 603 Decline（RFC 3261 §21.6.2）
- [ ] 断言不创建 B2BUA 对话
- [ ] 对拍 POC 基线 `testbed/contracts/sip-baseline/S3-policy-reject-603/` 的 4 条消息
- [ ] 构造一个既匹配"阻止"又匹配"翻译"的优先级冲突场景，断言优先级逻辑正确（**阻止规则 > 翻译规则 > 默认路由**）
- [ ] 断言匹配对象为目标号码；最长前缀优先

---

## §1.3 呼叫生命周期（REQ-F-8 到 REQ-F-11）

### REQ-F-8 验收标准（两分支）

#### 场景 ①：CANCEL 在 180 Ringing **之前**发（无 early dialog）
- [ ] 启动仿真环境，下游 Return UAS 不立即返回 180 Ringing（或返回延迟足够让上游抢先发 CANCEL）
- [ ] 从仿真 S-CSCF 发送 INVITE（命中业务规则）
- [ ] 在 180 Ringing **之前**、对端任何响应到达前，从仿真 S-CSCF 发送 CANCEL
- [ ] 断言收到 CANCEL 后我们立即返回 200 OK（对 CANCEL 的确认）
- [ ] 断言我们向下游发送 CANCEL（不是 BYE——出腿尚无最终响应）
- [ ] 断言下游返回 487 Request Terminated（INVITE 事务被 CANCEL 终止，RFC 3261 §9.2）
- [ ] 断言我们向上游透传 487
- [ ] 断言我们向上游发送 ACK
- [ ] 对拍 POC 基线 `testbed/contracts/sip-baseline/S4-caller-cancel/` 的消息序列

#### 场景 ②：CANCEL 在 180 Ringing **之后**、200 OK **之前**发（有 early dialog）
- [ ] 启动仿真环境，下游 Return UAS 返回 180 Ringing 但延迟返回 200 OK
- [ ] 从仿真 S-CSCF 发送 INVITE（命中业务规则）
- [ ] 在 180 Ringing **之后**、200 OK **之前**，从仿真 S-CSCF 发送 CANCEL
- [ ] 断言我们返回 CANCEL 的 200 OK
- [ ] 断言我们向下游发送 CANCEL（对尚未产生最终响应的 INVITE 事务）
- [ ] 断言对端（Return UAS）回 INVITE 的 487
- [ ] 断言我们向上游透传 487
- [ ] 断言我们向上游发送 ACK

#### 场景 ③：CANCEL 在 200 OK **之后**发（对话已建立）
- [ ] 启动仿真环境，下游 Return UAS 正常回 200 OK
- [ ] 完成基本呼叫（REQ-F-1），对话建立后（200 OK + ACK 完成）
- [ ] 上游发送 CANCEL
- [ ] 断言 CANCEL 对已建立对话无效（RFC 3261 §9）
- [ ] 断言我们走 BYE 拆对话：向下游发 BYE → 对端回 200 OK → 向上游透传 BYE 到对话清理完成

### REQ-F-9 验收标准
- [ ] 启动仿真环境
- [ ] 完成一次基本呼叫（REQ-F-1），建立对话
- [ ] 对话建立后，从仿真 S-CSCF 发送一个 re-INVITE（携带正确的 Route 头 + 正确的 Call-ID + 匹配的 local/remote tag）
- [ ] 断言我们把 re-INVITE 路由到了正确的下游对端（不是新建对话、不是丢到黑洞）
- [ ] 同样测试 UPDATE 和 BYE 的 in-dialog 路由
- [ ] M2 阶段用 `testbed/simulators/` 写完整的 in-dialog 对拍场景

### REQ-F-10 验收标准
- [ ] 启动仿真环境，下游对端配置为返回 486 Busy Here
- [ ] 从仿真 S-CSCF 发送 INVITE
- [ ] 断言我们向下游发出 INVITE 后收到 486
- [ ] 断言我们向上游转发 486（不是改成 404 或 200 OK）
- [ ] 同样测试下游返回 480 和 408 的场景
- [ ] 验证对话状态在收到非 2xx 后正确清理

### REQ-F-11 验收标准（两分支）

#### 场景 ①：CANCEL 先于最终响应到达（RFC 合法路径）
- [ ] 启动仿真环境，用可控延迟或 mock 注入让 CANCEL 先于对端最终响应到达
- [ ] 从仿真 S-CSCF 发送 INVITE
- [ ] 向入腿注入 CANCEL（早于出腿最终响应返回）
- [ ] 断言出腿下游返回 INVITE 的 487
- [ ] 断言我们向上游透传 487 + 发送 ACK
- [ ] 对话状态最终为 Terminated，无悬挂对话

#### 场景 ②：最终响应已到达（CANCEL 对出腿无效）
- [ ] 启动仿真环境，下游 Return UAS 正常返回 200 OK 或非 2xx 最终响应
- [ ] 在我们已收到下游最终响应之后，上游才发 CANCEL
- [ ] 断言 CANCEL 对出腿无效（RFC 3261 §9）
- [ ] 断言我们走 BYE 拆对话（若 200 OK）或直接清理（若非 2xx）
- [ ] 对话状态最终为 Terminated

---

## §1.4 控制台与配置管理（REQ-F-12 到 REQ-F-15）

### REQ-F-12 验收标准
- [ ] 控制台界面存在：规则列表、创建、编辑、删除按钮
- [ ] 创建规则时能填写：匹配对象（主叫/被叫，下拉选择）、匹配模式（前缀/正则）、目标业务类型（翻译/反欺诈/路由/阻止/默认）、启用/禁用开关
- [ ] 规则保存后进入审批队列（REQ-F-14 联动）
- [ ] 审批通过后规则生效，禁用的规则不参与匹配
- [ ] 规则 CRUD 操作生成审计日志（REQ-S-4）

### REQ-F-13 验收标准
- [ ] 控制台提供按 Call-ID 查询入口
- [ ] 查询结果展示完整的 SIP 消息轨迹：每条消息包含方向（入/出）、时间戳、方法、响应码、Call-ID、From/To
- [ ] 轨迹查询结果中能看到翻译规则命中信息（REQ-F-16 联动）
- [ ] 业务方（Actor 4）也能通过接口查询同一条轨迹

### REQ-F-14 验收标准
- [ ] 规则创建/更新/删除提交后，状态变为"待审批"
- [ ] 审批人在审批队列中能看到待审批项
- [ ] 批准后规则生效，状态变为"已生效"
- [ ] 拒绝必须填写拒绝理由；规则状态变为"已拒绝"
- [ ] 全流程有审计日志（REQ-S-4）

### REQ-F-15 验收标准
- [ ] 灰度分发能分批（每批 N 个实例）通知 AS 实例加载新规则版本
- [ ] 每批分发后有健康检查（实例 active_calls 正常、无进程重启）
- [ ] 某批分发失败时，自动回滚到上一版本
- [ ] 运维能手动触发回滚
- [ ] 全流程有审计日志

---

## §1.5 业务决策链（REQ-F-16）

### REQ-F-16 验收标准
- [ ] 启动仿真环境，配置翻译规则 +86755* → +852755*
- [ ] 从仿真 S-CSCF 发送 INVITE 到 +867551234567
- [ ] 断言我们提取被叫号码 +867551234567，按规则翻译为 +8527551234567
- [ ] 断言下游 INVITE 的 Request-URI 为 sip:+8527551234567@<路由目标>
- [ ] 通过 REQ-F-13 轨迹查询能看到：翻译前号码、翻译后号码、匹配的规则 ID 与版本号、路由目标

---

## §2 非功能需求（REQ-NF-*）

### REQ-NF-1 验收标准
- [ ] 启动仿真环境
- [ ] 发起一个基本呼叫（REQ-F-1），等待对话建立（ACK 交换完成）
- [ ] 在呼叫中途（对话活跃状态），强行 kill 承载该呼叫的进程
- [ ] 进程被 K8s 拉起后自动重启
- [ ] 从上游（S-CSCF/S-SBC）发送 BYE
- [ ] 断言重启后的新进程**仍能把 BYE 正确路由到对端**（说明对话状态没有丢失）
- [ ] 对话状态校验：Redis 中该 Call-ID 的对话记录完整存在

### REQ-NF-2 验收标准
- [ ] 目录结构：`apps/translation/` 和 `apps/anti-fraud/` 各自独立（不是一个进程里跑两个用例）
- [ ] K8s Deployment：每个用例一个 Deployment，副本数独立配置
- [ ] kill 承载 translation 用例的 Pod，断言 anti-fraud 用例不受影响（anti-fraud Pod 不重启、负载不掉）

### REQ-NF-3 验收标准
- [ ] 配置 HPA：translation Deployment 基于 active_calls（阈值 500）
- [ ] 注入 1000 并发基本呼叫
- [ ] 断言 translation Deployment 的副本数从 3 扩到 ≥ 5
- [ ] 停止注入，等待 30 秒，断言副本数缩回到阈值以下
- [ ] 在扩缩过程中，已建立的呼叫不丢失（REQ-NF-1 同步验证）

### REQ-NF-4 验收标准
- [ ] 发起滚动升级
- [ ] 在升级过程中注入基本呼叫
- [ ] 新呼叫被路由到新版本副本（旧版本副本已摘流）
- [ ] 旧版本副本上存量呼叫正常完成（BYE → 200 OK）
- [ ] 旧版本副本的 active_calls 归零后，Pod 被 K8s 删除
- [ ] 升级全程无呼叫丢失

### REQ-NF-5 验收标准
- [ ] testbed 中有一个 S-SBC 仿真器：它接收仿真 S-CSCF 发来的消息，转发给我们 AS；接收我们 AS 的响应，转回给仿真 S-CSCF
- [ ] AS 的代码中没有任何 "is_intranet" / "is_extranet" / "network_mode" 类型的分支判断
- [ ] 换一个不同实现的 S-SBC 仿真器（比如用 Kamailio），断言 AS 侧行为一致

### REQ-NF-6 验收标准
- [ ] grep 生产代码，没有 RTP / G.711 / G.729 / DTMF / 转码 相关实现
- [ ] seam 文件存在（接口定义），生产实现是 stub / raise NotImplementedError / 空函数
- [ ] seam 注释写明"触发条件"和"什么情况下才需要实现"

### REQ-NF-7 验收标准
- [ ] 控制台能按 Call-ID 查询完整的 SIP 消息轨迹（INVITE 到 BYE 的全部消息，入/出方向、时间戳、方法、响应码）
- [ ] 轨迹保留期待定——验证清理任务能正确执行即可，具体天数 M4 冻结
- [ ] 清理任务：PG 定时执行，删除过期轨迹行；手动触发清理命令可立即执行
- [ ] grep 生产代码，没有 CDR / 批价 / 计费 相关实现

### REQ-NF-8 验收标准
- [ ] grep 生产代码，没有 lawful_intercept / IRI / intercept 相关实现
- [ ] 架构文档 §9.2 明确"LI 由 S-CSCF/SBC 网内出，不在我方交付边界"

### REQ-NF-9 验收标准
- [ ] Helm chart 能独立部署一个完整系统到指定 namespace
- [ ] namespace 之间无共享（独立的 Redis、独立的 PG、独立的 AS Pod 组）
- [ ] 一个 namespace 中的故障（Redis 挂了、AS 进程崩了）不影响另一个 namespace

### REQ-NF-10 验收标准
- [ ] 控制台能提交规则草稿、发起变更单、触发审批
- [ ] 审批通过后，config-service 写入 PG 新版本（不可变）
- [ ] 灰度分发：分批通知 AS 实例加载新版本，每批有健康检查
- [ ] 分发异常时自动回滚到上一版本
- [ ] 全流程有审计日志落 PG
- [ ] grep 代码，没有 git / github / gitlab 相关的配置加载逻辑

### REQ-NF-11 验收标准
- [ ] 根目录存在唯一的 `./VERSION` 文件
- [ ] `grep -r "VERSION=" platform/ apps/ services/` 无结果（各组件不拥有 VERSION 文件）
- [ ] `tests/test_version_consistency.py` 通过
- [ ] 修改根 VERSION 后，所有组件报告的产品版本号同步变化

### REQ-NF-12 验收标准
- [ ] `pyproject.toml` 包含 `[tool.uv.workspace]` 配置
- [ ] 运行 `uv sync` 能一次性拉齐所有依赖
- [ ] `git clone` 本仓库后直接 `make dev` 能起服务，不需要额外 `git clone` 其他仓库

### REQ-NF-13 验收标准
- [ ] 启动 AS 实例，Prometheus/Grafana 侧能采集到 active_calls、cps、规则匹配率、4xx 率、5xx 率 指标
- [ ] 每通呼叫有完整的 trace span 链：入腿 INVITE → 业务决策 → 出腿 INVITE → BYE
- [ ] JSON 日志中每条包含 trace_id，可与 metrics/traces 关联
- [ ] 结构化 JSON 日志字段包含：timestamp、level、trace_id、call_id、direction、method

### REQ-NF-14 验收标准
- [ ] Prometheus Alertmanager 中有预设告警规则：
  - active_calls 突增 > 30%（5 分钟窗口）
  - 5xx 率 > 1%（5 分钟窗口）
  - 进程重启循环（1min 内 > 3 次）
  - 证书到期 30 天内
- [ ] 手动触发上述任一条件，断言 Alertmanager 正确发出告警（通知通道待定，M2 冻结）

---

## §3 安全需求（REQ-S-*）

### REQ-S-1 验收标准
- [ ] config-service 中存在白名单配置（IP:port 或证书指纹）
- [ ] 从白名单外对端发 SIP 消息到我们，断言消息被丢弃或返回 403
- [ ] 从白名单内对端发消息，断言正常处理
- [ ] 白名单变更需经过审批流程（REQ-F-14）

### REQ-S-2 验收标准
- [ ] AS 与 S-SBC 之间所有 SIP 信令走 TLS（端口 5061 或其他加密端口）
- [ ] 明文连接（TCP 端口 5060）被拒绝（握手失败或连接被关闭）
- [ ] TLS 证书链由运营商 PKI 签发，验证通过

### REQ-S-3 验收标准
- [ ] 证书轮换时（新旧证书并存窗口），正在进行的呼叫不受影响
- [ ] 轮换期间新建 TLS 连接使用新证书
- [ ] 旧证书过期后，仍持有旧证书的对端连接被正确拒绝（或已在窗口内完成切换）
- [ ] 轮换过程无进程重启

### REQ-S-4 验收标准
- [ ] 控制台所有写操作（规则 CRUD、审批、回滚）必须先通过鉴权
- [ ] 鉴权方式：RBAC 角色 + 密码或客户端证书
- [ ] 所有操作生成审计日志，包含：操作者、时间戳、操作类型、变更前后值
- [ ] 审计日志不可篡改（追加写入、无 UPDATE/DELETE 权限）

---

## §4 治理需求（REQ-G-*）

### REQ-G-1 验收标准
- [ ] 每个 feature 的 HLD 节包含 "Enablement" 子节，写明默认态、灰度策略、移除条件
- [ ] feature 开关的开/关两态都有测试覆盖
- [ ] 代码中没有"开关存在了但没写移除条件"的情况（AST 扫描守卫）

### REQ-G-2 验收标准
- [ ] PR checklist 包含"已更新 REQ-* / ADR / 设计文档 / 契约用例 / 验收记录"
- [ ] review record 能追溯到至少一个 REQ-* 编号
- [ ] 代码改动能追溯到 requirement（通过 ADR 或直接引用）

### REQ-G-3 验收标准
- [ ] `make gate` 四步（format/check/mypy/pytest）不包含 AST 扫描（AST 扫描属于 CI 前置门禁或 `make gate-strict` 额外目标）
- [ ] 故意写一行不标注的架构性代码，断言 AST 扫描阻断（通过 `make gate-strict` 或 CI 流水线）
- [ ] 扫描覆盖率：所有非 trivial 的架构性代码都有 ADR 标注

### REQ-G-4 验收标准
- [ ] `make gate` 退出码为 0
- [ ] CI 流水线中 `make gate` 失败时阻断后续步骤
- [ ] pre-commit hook 在本地提交前运行 `make gate` 的 lint/format 部分

---

## §5 M2 内核验收（unit / contract 层）

> 本节是 M2 内核（platform）的验收标准，对应 `docs/architecture/lld.md`。
> 层与 marker：`unit` = 纯逻辑，无 socket；`contract` = 语言无关契约用例，对**每一个**实现重放。
> 决策逻辑（`decide()`、规则匹配）按 AGENT.md §6 **强制 TDD**：红 - 绿 - 重构。

### 5.1 `decide()` 判决矩阵（marker: unit）

规则集（测试夹具）：
| 前缀 | action | 说明 |
|---|---|---|
| `+86755` | translate（target = `return-uas`） | 翻译业务 |
| `+8675512` | translate（target = `return-uas`） | 更长前缀，用于验证最长前缀优先 |
| `+86138` | forward | 直接转发 |
| `+86168` | block（603） | 反诈阻止 |

| # | 被叫号码 | 期望 action | 期望 reason_code | 断言要点 |
|---|---|---|---|---|
| 1 | `+867550123456` | TRANSLATE | `MATCH_TRANSLATE` | 命中 `+86755`，target 为 `return-uas` |
| 2 | `+8675512345678` | TRANSLATE | `MATCH_TRANSLATE` | 同时匹配 `+86755` 与 `+8675512`，**断言命中更长的前缀** `+8675512`（`matched_rule_id` 可区分） |
| 3 | `+861681000000` | DECLINE | `MATCH_BLOCK` | 返回 603，且**不创建出腿**（REQ-F-7） |
| 4 | `+8613800000000` | FORWARD | `MATCH_FORWARD` | 直接转发 |
| 5 | `+869990000000` | NOT_FOUND | `NO_MATCH` | 返回 404，且不创建出腿（REQ-F-6） |
| 6 | `867551234567`（无 `+`） | TRANSLATE | `MATCH_TRANSLATE` | 号码归一化后匹配，等价用例 1 |
| 7 | 号码同时命中 block 与 translate（如 `+86168` block 与 `+8616` translate） | DECLINE | `MATCH_BLOCK` | **block 优先于 translate**（与 §1.2 REQ-F-7 验收一致） |

说明：用例 1 的号码刻意避开 `+8675512`，以保证"命中 `+86755`"与用例 2"命中更长前缀"是两条互不重叠的断言。

通用断言：`decide()` 为纯函数 —— 同输入必同输出；无 socket、无时钟读取、无全局状态（可由"注入的 received_at 不参与判决"与"连续两次调用结果相等"间接断言）。

### 5.2 StateStore 契约（marker: contract）

同一套用例对**两个实现**重放：`InMemoryStateStore` 与 `RedisStateStore`（Redis 用例在无 Redis 环境时 skip，但契约本身必须存在）。

| # | 用例 | 断言 |
|---|---|---|
| 1 | `get` 不存在的键 | 返回 `None`，不抛异常 |
| 2 | `set(k, v, ttl)` 后 `get(k)` | 返回与 `v` 逐字节相等的 bytes |
| 3 | 同键同值写两次 | 结果一致，无异常（**幂等**） |
| 4 | `set(ttl=1)`，注入时钟推进超过 TTL | `get` 返回 `None`；实现**不得**在内部读系统时钟 |
| 5 | `delete(k)` 后 `get(k)`；再 `delete(k)` | 第一次返回 `None`，第二次不抛异常 |
| 6 | 键格式 | 形如 `as:{case}:{kind}:{id}` |
| 7 | 写入顺序交换 | 最终值一致（幂等语义，承受 Redis 脑裂窗口重放） |

### 5.3 feature 门控两态（marker: unit）

| # | 用例 | 断言 |
|---|---|---|
| 1 | 未注册的开关名 | `is_enabled` 返回 `False`（**fail-closed**） |
| 2 | 部署级默认态 | 返回 `False`（**默认关**） |
| 3 | 部署级置为开 | 返回 `True` |
| 4 | 运行态覆盖开 / 关 | 覆盖值优先于部署级 |
| 5 | 同一 scope 重复求值 | 结果一致（**判定幂等**） |
| 6 | 判定入口不依赖真实 Redis | 通过注入 `ToggleSource` 完成，测试无 socket |

两态（开 / 关）都必须被覆盖（ADR-0020、REQ-G-1）。

### 5.4 遥测不阻塞（marker: unit）

| # | 用例 | 断言 |
|---|---|---|
| 1 | 呼叫路径调用 `emit()` | 不产生任何网络 IO（以 NoOp / 假 exporter 断言 socket 未被调用） |
| 2 | 队列写满后继续 `emit()` | 不抛异常、不阻塞；`dropped` 计数自增 |
| 3 | 默认 sink | 为 `NoOpSink`（未配置 exporter 时不报错） |
| 4 | 导出线程 | 在独立线程消费队列，呼叫路径不等待导出完成 |

### 5.5 进程壳 draining（marker: unit）

| # | 用例 | 断言 |
|---|---|---|
| 1 | `active_calls == 0` 时收到 SIGTERM | 停止接收新请求并退出 |
| 2 | `active_calls > 0` 时收到 SIGTERM | **不退出**；新请求被拒；待归零后退出 |
| 3 | 归零超时（可配上限） | 强制退出并记录；不得无限等待 |

### 5.6 与需求/设计的追溯

| 本节 | 对应 REQ | 对应设计 |
|---|---|---|
| 5.1 | REQ-F-1、REQ-F-6、REQ-F-7 | `lld.md` §2、§3 |
| 5.2 | REQ-NF-1、REQ-NF-2 | `lld.md` §4（ADR-0002、ADR-0007） |
| 5.3 | REQ-G-1 | `lld.md` §5（ADR-0020） |
| 5.4 | REQ-NF-13 | `lld.md` §6（ADR-0005） |
| 5.5 | REQ-NF-4 | `lld.md` §7（ADR-0009） |

