# 从 PRD v0.1 剥离的技术注解

> 本文件收集了从 `docs/requirements/prd.md` v0.1 重写时剥离的全部 27 条"技术注解"段。这些内容是设计暗示，不属于需求文档，但作为 M2 设计阶段的素材来源保留。
>
> **搬运原则**：只搬运原文，不修改内容。每条前标注原位置。

---

## REQ-F-* 功能需求

### REQ-F-1

> 从 PRD v0.1 剥离，原位置 REQ-F-1 "技术注解" 段

B2BUA 模式把一个呼叫拆成两条独立的 SIP 腿——上游（连 S-SBC）和下游（连对端），中间是我们的业务逻辑。这是 RFC 3261 §12 定义的 B2BUA 行为，不是我们额外发明的。

---

### REQ-F-2

> 从 PRD v0.1 剥离，原位置 REQ-F-2 "技术注解" 段

双腿 Call-ID 不同、Request-URI 改写是 B2BUA 模式的直接协议推论，不是我们额外发明的行为。

---

### REQ-F-3

> 从 PRD v0.1 剥离，原位置 REQ-F-3 "技术注解" 段

Request-URI 改写发生在 B2BUA 状态机的 `call_controller` 层；改写规则来自配置的路由策略。

---

### REQ-F-4

> 从 PRD v0.1 剥离，原位置 REQ-F-4 "技术注解" 段

媒体 seam 保留接口定义但不实现生产逻辑，SDP body 在 Transport seam 处做字节级透传。

---

### REQ-F-5

> 从 PRD v0.1 剥离，原位置 REQ-F-5 "技术注解" 段

Route/Record-Route 是 SIP 对话链的"跳转历史"，生产栈（reSIProcate）对此有内置处理。

---

### REQ-F-6

> 从 PRD v0.1 剥离，原位置 REQ-F-6 "技术注解" 段

规则匹配在 `decide()` 决策函数里执行，匹配表来自 config-service 下发的规则版本。"无匹配"是决策函数的 return case 之一。

---

### REQ-F-7

> 从 PRD v0.1 剥离，原位置 REQ-F-7 "技术注解" 段

"阻止"策略是 `decide()` 的另一个 return case，返回值携带"拒绝"判决；决策本身是纯函数，不依赖 SIP 栈。

---

### REQ-F-8

> 从 PRD v0.1 剥离，原位置 REQ-F-8 "技术注解" 段

CANCEL 触发 B2BUA 状态机从 Early 状态转入 Terminating 状态，内部 `DialogState` 标记为 canceling。

---

### REQ-F-9

> 从 PRD v0.1 剥离，原位置 REQ-F-9 "技术注解" 段

POC 有 chained topology 覆盖，但 capture_call.py 不跑这个场景，POC 基线缺失。生产栈 reSIProcate 对此有内置对话匹配机制，但我们需要确保对话状态外置后仍能正确路由。

---

### REQ-F-10

> 从 PRD v0.1 剥离，原位置 REQ-F-10 "技术注解" 段

POC 的 ReturnUas 只返回 200 OK，基线缺失。生产实现需要在 `call_controller` 层对非 2xx 做分支处理，不能硬编码"下游永远成功"。

---

### REQ-F-11

> 从 PRD v0.1 剥离，原位置 REQ-F-11 "技术注解" 段

POC 没有显式竞态测试，基线缺失。生产实现需要在 `DialogState` 里维护一个 `canceling` 状态，CANCEL 到达后置位，之后收到任何最终响应都按"已取消"处理。

---

## REQ-NF-* 非功能需求

### REQ-NF-1

> 从 PRD v0.1 剥离，原位置 REQ-NF-1 "技术注解" 段

POC 使用的 InMemoryStateStore 重启即丢会话。生产实现必须用 StateStore seam + Redis 外置，会话状态存 Redis（Sentinel 冗余），进程内存只做缓存。

---

### REQ-NF-2

> 从 PRD v0.1 剥离，原位置 REQ-NF-2 "技术注解" 段

sippy 自带阻塞 ED2.loop()，天然一进程一用例。进程边界 = 故障域边界 = 独立灰度/扩缩容边界。

---

### REQ-NF-3

> 从 PRD v0.1 剥离，原位置 REQ-NF-3 "技术注解" 段

进程无状态（REQ-NF-1）是水平扩展的硬前提。Redis 会话表做亲和兜底，LB 层再用 `sessionAffinity: ClientIP` 双保险。

---

### REQ-NF-5

> 从 PRD v0.1 剥离，原位置 REQ-NF-5 "技术注解" 段

这是 §0 产品概述中"单一 ISC 语义"的直接推论。S-SBC 是运营商侧网元，不属于我方交付物；testbed 中必须有 S-SBC 仿真器来验证这个认知。

---

### REQ-NF-9

> 从 PRD v0.1 剥离，原位置 REQ-NF-9 "技术注解" 段

单租户意味着 Helm chart 产出一个完整系统，每个客户一套 K8s namespace。

---

### REQ-NF-4

> 从 PRD v0.1 剥离，原位置 REQ-NF-4 "技术注解" 段

前提事实：生产栈（reSIProcate）SIP 事务/对话状态在进程内存，无法"把在途呼叫无缝移交给新版本"——所以 ISSU 只能走 draining，不能走零流量切换。

---

### REQ-NF-6

> 从 PRD v0.1 剥离，原位置 REQ-NF-6 "技术注解" 段

媒体 seam 只定义接口，不实现生产逻辑。

---

### REQ-NF-7

> 从 PRD v0.1 剥离，原位置 REQ-NF-7 "技术注解" 段

呼叫轨迹同时是运维信号（走 OTel trace 后端）和产品能力（走 AS 自身 `/api/v1/traces` 查询通道），两条通道用同一 Call-ID/TraceID 关联。

---

### REQ-NF-8

> 从 PRD v0.1 剥离，原位置 REQ-NF-8 "技术注解" 段

生产代码中无 LI / IRI / Intercept 相关实现。

---

### REQ-NF-10

> 从 PRD v0.1 剥离，原位置 REQ-NF-10 "技术注解" 段

不是运维直接 UPDATE 数据库，也不是用 git 仓库管理配置。schema 版本化 + 兼容矩阵是 ISSU（REQ-NF-4）的硬前置。

---

### REQ-NF-11

> 从 PRD v0.1 剥离，原位置 REQ-NF-11 "技术注解" 段

由 `tests/test_version_consistency.py` 守卫；CI 阻断任何 VERSION 与 pyproject 漂移的提交。

---

### REQ-NF-12

> 从 PRD v0.1 剥离，原位置 REQ-NF-12 "技术注解" 段

这是架构决策账本的落地。

---

## REQ-G-* 治理需求

### REQ-G-1

> 从 PRD v0.1 剥离，原位置 REQ-G-1 "技术注解" 段

两层门控：部署级总开关（PG 版本库）+ 运行态细粒度覆盖（Redis，号段/呼叫/用户/百分比级别）。

---

### REQ-G-2

> 从 PRD v0.1 剥离，原位置 REQ-G-2 "技术注解" 段

文档链在 AGENT.md §3 定义。PR checklist 中必须包含"上游文档已更新"项；review record 必须标注对应 REQ-*。

---

### REQ-G-3

> 从 PRD v0.1 剥离，原位置 REQ-G-3 "技术注解" 段

由 AST 扫描守卫（`tests/` 目录下的扫描脚本）强制——新增"违反 ADR 标注纪律"的代码会被 CI 阻断。

---

### REQ-G-4

> 从 PRD v0.1 剥离，原位置 REQ-G-4 "技术注解" 段

CI 跑同样的四层（快 → 集成 → e2e → 性能）。M0 阶段 integration/e2e/performance 层无测试，用 `continue-on-error` 绕过；首个引入某层测试的里程碑必须同步把该层改为阻塞。
