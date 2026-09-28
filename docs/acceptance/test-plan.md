# 验收测试计划（Test Plan）— 3rdparty-as

**版本**：v0.1（占位）
**日期**：2026-09-28
**状态**：占位 — 验收标准从 PRD 挪入，具体 test case 待 M2 设计阶段补充

> 本文档从 PRD（prd.md）的验收标准部分提取而来。
> 具体 test case（步骤、断言、数据准备）由 M2 设计阶段补充。

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
- [ ] 提取上游 INVITE Call-ID（记为 C1）和上游 BYE Call-ID（记为 C2）
- [ ] 断言 C1 ≠ C2（两条腿对话独立）
- [ ] 提取上游 200 OK 的 Call-ID，断言等于 C1
- [ ] 提取上游 BYE 的 Call-ID，断言等于 C2

### REQ-F-3 验收标准
- [ ] 完成 REQ-F-1 的基本呼叫
- [ ] 提取上游 INVITE 的 Request-URI
- [ ] 提取下游 INVITE 的 Request-URI
- [ ] 断言两者 host/port 部分不同（上游是运营商 S-SBC，下游是我们内部选定的对端）
- [ ] 断言 user@部分一致（号码不变，只是路由地址变了）

### REQ-F-4 验收标准
- [ ] 完成 REQ-F-1 的基本呼叫
- [ ] 提取上游 INVITE 的 SDP body（bytes）
- [ ] 提取下游 INVITE 的 SDP body（bytes）
- [ ] 断言两者逐字节相等
- [ ] 提取上游 200 OK 的 SDP body 和下游 200 OK 的 SDP body，同样逐字节相等

### REQ-F-5 验收标准
- [ ] 完成 REQ-F-1 的基本呼叫，其中上游 INVITE 带一个 Route 头（例如 `Route: <sip:proxy.example.com:5060>`）
- [ ] 断言下游 INVITE 的 Route 头存在且内容等于上游 INVITE 的 Route 头
- [ ] 构造下游对端返回带 Record-Route 的 200 OK
- [ ] 断言上游的 200 OK 里 Record-Route 头存在且值与下游 Record-Route 一致

---

## §1.2 路由与策略决策（REQ-F-6 到 REQ-F-7）

### REQ-F-6 验收标准
- [ ] 启动仿真环境，规则表只包含 +86138*（不含 +86199*）
- [ ] 从仿真 S-CSCF 发送 INVITE 到 +861990000000
- [ ] 断言我们返回 404 Not Found
- [ ] 断言不创建 B2BUA 对话（即不发下游 INVITE）
- [ ] 对拍 POC 基线 `testbed/contracts/sip-baseline/S2-no-match-404/` 的 4 条消息

### REQ-F-7 验收标准
- [ ] 启动仿真环境，规则表包含 +86168* → R-BLOCK-90（阻止策略）
- [ ] 从仿真 S-CSCF 发送 INVITE 到 +861681000000
- [ ] 断言我们返回 603 Decline
- [ ] 断言不创建 B2BUA 对话
- [ ] 对拍 POC 基线 `testbed/contracts/sip-baseline/S3-policy-reject-603/` 的 4 条消息
- [ ] 构造一个既匹配"阻止"又匹配"翻译"的优先级冲突场景，断言优先级逻辑正确（阻止 > 翻译）

---

## §1.3 呼叫生命周期（REQ-F-8 到 REQ-F-11）

### REQ-F-8 验收标准
- [ ] 启动仿真环境
- [ ] 从仿真 S-CSCF 发送 INVITE（命中业务规则，下游 Return UAS 不立即返回 200 OK）
- [ ] 在 180 Ringing 之后、200 OK 之前，从仿真 S-CSCF 发送 CANCEL
- [ ] 断言收到 CANCEL 后我们立即返回 200 OK（对 CANCEL 的确认）
- [ ] 断言我们向下游发出 BYE
- [ ] 断言下游返回 487 Request Terminated
- [ ] 断言我们向下游返回 ACK
- [ ] 对拍 POC 基线 `testbed/contracts/sip-baseline/S4-caller-cancel/` 的 12 条消息

### REQ-F-9 验收标准
- [ ] 启动仿真环境
- [ ] 完成一次基本呼叫（REQ-F-1），建立对话
- [ ] 对话建立后，从仿真 S-CSCF 发送一个 re-INVITE（携带正确的 Route 头 + 正确的 Call-ID + Via branch 匹配）
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

### REQ-F-11 验收标准
- [ ] 启动仿真环境
- [ ] 在 INVITE 发出后、对端 200 OK 即将返回前（用可控延迟或 mock 注入），同时注入 CANCEL 和 200 OK
- [ ] 断言 CANCEL 被优先处理：我们返回 487 Request Terminated（canceling 的最终状态）
- [ ] 断言后续的 BYE/ACK 序列正确完成
- [ ] 对话状态最终为 Terminated，无悬挂对话

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
- [ ] 轨迹保留期可配置（默认 7 天，通过 PG 清理任务执行）
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

---

## §3 治理需求（REQ-G-*）

### REQ-G-1 验收标准
- [ ] 每个 feature 的 HLD 节包含 "Enablement" 子节，写明默认态、灰度策略、移除条件
- [ ] feature 开关的开/关两态都有测试覆盖
- [ ] 代码中没有"开关存在了但没写移除条件"的情况（AST 扫描守卫）

### REQ-G-2 验收标准
- [ ] PR checklist 包含"已更新 REQ-* / ADR / 设计文档 / 契约用例 / 验收记录"
- [ ] review record 能追溯到至少一个 REQ-* 编号
- [ ] 代码改动能追溯到 requirement（通过 ADR 或直接引用）

### REQ-G-3 验收标准
- [ ] `make gate` 包含 AST 扫描步骤
- [ ] 故意写一行不标注的架构性代码，断言 CI 阻断
- [ ] 扫描覆盖率：所有非 trivial 的架构性代码都有 ADR 标注

### REQ-G-4 验收标准
- [ ] `make gate` 退出码为 0
- [ ] CI 流水线中 `make gate` 失败时阻断后续步骤
- [ ] pre-commit hook 在本地提交前运行 `make gate` 的 lint/format 部分
