# PRD v0.1 Review Record

> 评审对象：`docs/requirements/prd.md` v0.1（draft），连带其验收标准外链目标 `docs/acceptance/test-plan.md`
> 评审日期：2026-09-28
> 评审人：AI agent（协议与文档链核对）
> 评审结论：**有条件通过** —— A 类 5 项修改完成并复核后方可发布 v0.2

## 评审范围与方法

| 维度 | 方法 | 依据来源 |
|---|---|---|
| 协议正确性 | 逐条核对 RFC 3261 章节号与流程语义 | RFC 3261 全文（curl 抓取 + 切片，逐字核对；见「依据分级与逐字核对状态」）；`testbed/contracts/sip-baseline/` 基线消息（L3 旁证） |
| 需求覆盖度 | PRD §0 定位 vs §1/§2/§3 实际条目 | `AGENT.md` §13 安全红线；`docs/plan.md` §4 里程碑排期 |
| 文档一致性 | PRD ↔ test-plan ↔ AGENT.md ↔ plan.md ↔ ADR 注册表 | 上述文档原文 |

## A 类：阻断项（需求文本本身有误，会带错设计与验收）

| # | 位置 | 问题 | 依据 | 建议修改 | 状态 |
|---|---|---|---|---|---|
| A1 | REQ-F-8 | 协议上不可能成立：PRD 写"向下游发送 BYE → 收到 487"，但 §15.1.2 规定 "the UAS core MUST generate a 2xx response to the BYE" —— BYE 的应答只能是 2xx，487 只能是被 CANCEL 的 INVITE 事务的最终响应（§9.2："If the UAS has not issued a final response for the original request... If the original request was an INVITE, the UAS SHOULD immediately respond to the INVITE with a 487 (Request Terminated)."）。§15 进一步给出取舍："The CANCEL attempts to force a non-2xx response to the INVITE (in particular, a 487). Therefore, if a UAC wishes to give up on its call attempt entirely, it can send a CANCEL. If the INVITE results in 2xx final response(s)... MAY terminate them with BYE." —— **未收到最终响应用 CANCEL，已收到 2xx 才用 BYE**。另漏写"入腿 487 + 上游 ACK"（§6 SIP Transaction："If the request is INVITE and the final response is a non-2xx, the transaction also includes an ACK to the response."）。**结论强度**：§6 的 B2BUA 定义 "Since it is a concatenation of a UAC and UAS, no explicit definitions are needed for its behavior." —— RFC 不规定 B2BUA 的**跨腿编排**，但每条腿各自作为 UAC/UAS 仍受 §9/§15 约束；故"出腿在无最终响应阶段必须能产生 487"是协议约束（只能是 CANCEL），具体编排仍属契约层决策 | RFC 3261 §15、§15.1.2、§9.2、§6（L1，已逐字核对）；POC 基线 `S4-caller-cancel`（L3 旁证，非权威） | ① 删掉"发 BYE → 收 487"：出腿尚无最终响应时用 CANCEL 终止，出腿已 2xx 时用 BYE；② 补"入腿 487 + 上游 ACK"；③ 两分支都要写进需求与验收 | 待修改 |
| A2 | REQ-F-2 与 test-plan REQ-F-2 冲突 | test-plan 断言"上游 INVITE Call-ID(C1) ≠ 上游 BYE Call-ID(C2)"。RFC 3261 §8.1.1.4 原文："The Call-ID header field acts as a unique identifier to group together a series of messages. It MUST be the same for all requests and responses sent by either UA in a dialog." —— 同一对话内 Call-ID 必须相同，故该断言必错。基线实测与 RFC 相符（入腿 INVITE 与入腿 BYE 同为 `48f64baa94fdfcfdd79af4128905d375`，出腿为 `-b2b_1`） | RFC 3261 §8.1.1.4（L1，规范依据，已逐字核对）；`S1-basic-call/01-in-invite-trunk.txt` 与 `13-out-bye-trunk.txt`（L3 旁证） | 断言改为"入腿 Call-ID ≠ 出腿 Call-ID"，并补"同一腿内 INVITE/200/ACK/BYE 的 Call-ID 必须一致" | 待修改 |
| A3 | 多处 RFC 3261 章节号 | 章节号错误：Request-URI 标 §6.2（§6 是 Definitions；应为 §8.1.1.1 / §19.1）；Route 标 §7.1（§7.1 是 Requests；应为 §20.34 + 处理见 §16.4）；Record-Route 反向成 route set 标 §16.13（§16 止于 16.12；实为 §12.1.2）；404 标 §21.4.4（21.4.4 是 403 Forbidden，404 是 **21.4.5**）；603 标 §21.6.5（应为 **21.6.2**）；SDP offer/answer 标 §18（§18 是 Transport；offer/answer 在 §13.2.1/§13.3.1，格式在 RFC 3264）；B2BUA 标 §12（B2BUA 定义在 **§6 Definitions**，§12 是 Dialogs） | RFC 3261 原文目录 | 逐条修正；建议在 PRD 头部加一句"章节号以 RFC 3261 原文为准" | 待修改 |
| A4 | REQ-F-5 | "上游 INVITE 带的 Route 头必须在下游 INVITE 里保留"协议上可疑：按 §16.4/§16.12，Route 由被寻址实体**消费**；复制到出腿会让下游把请求再送回运营商侧代理，可能成环。且 test-plan 只断言字符串相等 —— 错误实现也会通过 | RFC 3261 §16.4 逐字："If the first value in the Route header field indicates this proxy, the proxy MUST remove that value from the request."（L1，正文已核对）+ §6 Route Set / Loose Routing 定义。**适用对象注意**：该 MUST 约束的是 proxy；对我们这个 B2BUA 无直接 MUST（§6：B2BUA 行为未定义），故结论强度为"定义 + proxy 规则类比"，非直接 MUST | 改为"寻址到我们的 Route 必须被消费；需要沿用的路由信息由路由策略显式生成"；验收改为检查下游请求实际发往的目标，而非头域字符串 | 待修改 |
| A5 | REQ-F-11 | "CANCEL 到达后不再 accept 新的最终响应"与 RFC 3261 §9.1 冲突：下游已发 200 OK 时 CANCEL 无效，必须走 BYE 拆对话。test-plan 只断言"我们返回 487"，仅覆盖一个分支 | RFC 3261 §9 逐字："CANCEL has no effect on a request to which a UAS has already given a final response."；§9.1："If the original request has generated a final response, the CANCEL SHOULD NOT be sent, as it is an effective no-op"；§9.2 同上（L1，正文已核对） | 拆两分支：① CANCEL 先于最终响应到达 → 487；② 最终响应已到达 → 200 OK + BYE；两条都要验收 | 待修改 |

## B 类：覆盖缺口（有行为或已排期，但没有 REQ 编号 → 追溯链断）

| # | 缺口 | 证据 | 建议修改 | 状态 |
|---|---|---|---|---|
| B1 | §0 宣称的第二类服务对象（业务方：翻译/反欺诈/智能路由提供商）在 §1/§2 完全没有用户故事与 REQ | prd.md §0 vs §1 三个 actor | 补 Actor：业务方用户故事 + 对应 REQ-F；或收回 §0 的承诺 | 待修改 |
| B2 | 控制台/配置管理能力没有 REQ-F：US-1/2/3/4 只映射到 F-1、F-6、F-7、NF-7、NF-10；规则 CRUD、审批流、轨迹查询、灰度分发、回滚本身没有功能需求号。NF-10 讲的是"不走 GitOps"，不是"要有配置治理能力" | prd.md §1 L28-58 | 新增 REQ-F-12… 覆盖规则管理、审批流、轨迹查询、灰度与回滚 | 待修改 |
| B3 | "翻译"主路径无需求：命中翻译规则后做什么（改号？选哪个对端？）没定义；F-1/F-3 只讲序列与 Request-URI 改写 | prd.md §2.1/§2.2 | 补一条"命中翻译规则后的处理"需求 | 待修改 |
| B4 | 规则匹配语义缺失：匹配主叫还是被叫（US-2 说"主叫号码命中"，REQ-F-7 说"目标号码"——自相矛盾）、最长前缀 vs 优先级、冲突裁决；"阻止 > 翻译"只出现在 test-plan 验收里，是隐性需求 | prd.md US-2 vs REQ-F-7 | 在 REQ-F-6/F-7 明确匹配对象与冲突裁决规则 | 待修改 |
| B5 | 无 REQ-S-*（安全）：AGENT.md §13 红线（对端白名单、与 S-SBC 端到端 TLS、证书热轮换、控制台操作鉴权+审计）在 requirement 层没有编号。`reviews/requirements-m1-review.md` Gap 3 裁决"由 NF-5 隐含覆盖"不成立 —— NF-5 只讲桥接语义，不含安全语义 | AGENT.md §13 | 新增 REQ-S-* 分组承接安全红线；M2 引入 TLS 前必须落地 | 待修改 |
| B6 | 无可观测性需求：OTel 三信号、告警规则集已排进 M2/M5，无 REQ 可追溯 | plan.md §4 | 补可观测性 REQ-NF | 待修改 |
| B7 | 指标口径冲突：test-plan REQ-NF-7 写死"轨迹保留期默认 7 天"，而 plan.md O4 把保留期列为未决（客户合规要求） | test-plan.md §2 vs plan.md §5.1 | 两者对齐：保留期标为待定，或在 requirement 层显式裁决默认值 | 待修改 |

## C 类：一致性与表述

| # | 位置 | 问题 | 建议修改 | 状态 |
|---|---|---|---|---|
| C1 | US-1 vs US-4 | "保存后规则立即生效" 与 "审批通过才生效" 矛盾 | 裁决草稿态是否生效，两处统一 | 待修改 |
| C2 | §4 | 治理需求标"全部为 P2"，但 §2/§3 只定义了 P0/P1 | 补 P2 定义或改标注 | 待修改 |
| C3 | US-9 | 混入设计语言（"LoadBalancer 自动把新 INVITE 路由到 v1.3.0"），违反已裁决的"PRD 不写设计" | 改为需求语言 | 待修改 |
| C4 | US-8 | "呼叫在 2 秒内恢复"引入无来源的时延承诺，与 AGENT.md L38"M6 前不发布数字"精神冲突 | 删除数字或标为待 M6 冻结 | 待修改 |
| C5 | REQ-NF-9 / REQ-NF-6 | 非目标（单租户 on-prem、不做媒体）被写成 P0 需求，且与 §0 非目标重复三遍 | 移入"边界/非目标"节，不占 REQ-NF 号 | 待修改 |
| C6 | §3.1/§3.2 | 编号乱序（1,2,3,5,9 / 4,6,7,8,10,11,12）；NF-4（ISSU）归入"扩展与治理"，但更像核心连续性能力，且与 NF-1 重叠 | 重排或加注说明 | 待修改 |
| C7 | REQ-G-3 vs REQ-G-4 | G-3 验收要求 `make gate` 含 AST 扫描步骤，G-4/AGENT.md §9 把 `make gate` 定义为四步（format/check/mypy/pytest） | 澄清 AST 扫描属于 gate 还是 CI | 待修改 |
| C8 | 全部 REQ | 27 条 REQ 的验收标准全部外链 test-plan，而 test-plan 自身状态为"占位，具体 test case 待 M2 补" —— v0.1 事实上没有可执行验收 | 在 PRD 头部显式标注此风险 | 待修改 |
| C9 | REQ-NF-6/7/8 | 其依据 ADR-0004/0016/0017 在注册表里仍是 skeleton（无文件）；§6 的"已有 ADR"只列了有文件的 6 个 | 在对应 REQ 后标注"依据 ADR 尚未落地" | 待修改 |
| C10 | REQ-F-9 | "路由依据是 Via branch + Route 头 + Call-ID" 不严谨：对话匹配是 Call-ID + local/remote tag（§12），Via branch 属事务匹配（§17.2.3） | 改为对话匹配表述 | 待修改 |
| C11 | §1 未覆盖表 | 表说 REQ-F-9/10/11 未覆盖，但 §2.3 已写了它们的业务描述（实为"无用户故事"） | 改表头措辞 | 待修改 |
| C12 | test-plan §REQ-F-8 vs 基线 S4 | CANCEL 时点不一致：`S4-caller-cancel/README.md` 写 CANCEL 发在"收到 180 Ringing **之前**"；test-plan 写"在 180 Ringing **之后**、200 OK 之前"。两个窗口的竞态行为不同，验收会跑出两套结果 | 与基线对齐，或明确两个窗口都要覆盖 | 待修改 |

## Adjudication 汇总

| 类别 | 条数 | 阻塞 v0.2 发布 | 处置 |
|---|---|---|---|
| A 阻断 | 5 | 是 | 修改后复核，A1/A2 可能需同步改 test-plan |
| B 覆盖缺口 | 7 | 是（B1-B5） | 补 REQ 编号；B6/B7 与 plan.md 未决项对齐 |
| C 一致性 | 12 | 否 | 随 v0.2 一并清理 |

## 依据分级与逐字核对状态

评审引用的依据分四级。首次核对用 `web_fetch` 抓取 RFC 3261，在第 42 页（§8.1.3.2）处被截断，§9 / §15 / §16.4 未取到正文；随后用 `curl` 抓取全文并切片，**四条待补验已于 2026-09-28 全部补验为 L1**。

| 等级 | 含义 | 条目 |
|---|---|---|
| L1 规范依据（已逐字核对） | RFC / 3GPP 原文逐字确认 | §8.1.1.4 Call-ID；§9（CANCEL 对已发最终响应的请求无效）；§9.1、§9.2（CANCEL→200、INVITE→487）；§15、§15.1.1、§15.1.2（BYE 何时可发、BYE 必回 2xx）；§16.4（顶层 Route 寻址本跳必须移除）；§6（B2BUA 定义、SIP Transaction、Dialog、Route Set、Loose Routing）；§7.1 方法定义；§4 BYE→200（非规范示例）；§5 CANCEL 语义 |
| L2 规范依据（仅目录确认） | 章节存在、标题相符，正文未取得 | 无（原 4 条已全部升为 L1） |
| L3 观察证据（非权威） | POC 基线，只能佐证，不能定义正确性 | `S1-basic-call`、`S4-caller-cancel` |
| L4 内部文档证据 | 证明缺口或排期，不定义正确性 | AGENT.md §13、plan.md §4 / §5.1、ADR 注册表 |

**已补验的关键原文（2026-09-28）**

| 条目 | 原文 |
|---|---|
| §9 | "CANCEL has no effect on a request to which a UAS has already given a final response." |
| §9.2 | "as long as the CANCEL matched an existing transaction, the UAS answers the CANCEL request itself with a 200 (OK) response." / "If the UAS has not issued a final response for the original request... If the original request was an INVITE, the UAS SHOULD immediately respond to the INVITE with a 487 (Request Terminated)." |
| §15 | "A UA MUST NOT send a BYE outside of a dialog. The caller's UA MAY send a BYE for either confirmed or early dialogs, and the callee's UA MAY send a BYE on confirmed dialogs, but MUST NOT send a BYE on early dialogs." / "The CANCEL attempts to force a non-2xx response to the INVITE (in particular, a 487). Therefore, if a UAC wishes to give up on its call attempt entirely, it can send a CANCEL. If the INVITE results in 2xx final response(s)... MAY terminate them with BYE." |
| §15.1.2 | "the UAS core MUST generate a 2xx response to the BYE" |
| §16.4 | "If the first value in the Route header field indicates this proxy, the proxy MUST remove that value from the request." |

**方法论裁定**：requirement 层的正确性只能由 RFC / 3GPP 定义；`testbed/` 下的 POC 基线用于**对拍等价性**（重写后行为不变），不是**正确性标准**（AGENT.md §12、ADR README：POC 决策不导入）。据此，本记录中所有以 testbed 为唯一依据的条目已降级为 L3 旁证。

**工具注记**：`web_fetch` 对长 RFC 会在前 ~42 页截断，不足以核对后半部分章节；改用 `curl` 下载全文 + `sed` 切片可完整核对。后续核对协议原文优先用后者。

## 正面确认

- 非目标（不做媒体 / CDR / LI / Diameter Sh / 多租户 / 非 GitOps）写得干净，理由可追溯。
- 用户故事让非技术读者可读，三个 actor 的场景叙述具体。
- 协议引用意识正确（虽然章节号需订正）。
- §6 补课说明对"requirement 晚于 ADR"这一顺序倒置诚实交代，且给出 M2 起的流程约束。

## 确认签字

| 项 | 值 |
|---|---|
| 评审结论 | 有条件通过 |
| 发布 v0.2 的前置条件 | A 类 5 项已修改并复核；B1-B5 已补 REQ 编号 |
| 评审人 | AI agent，2026-09-28 |
| 维护者签字 | 待填 |

---

## 修改后 Status 更新（2026-09-28，PRD v0.2 落盘）

**裁决结果**：24 个 Gap **全部接受**，对应修改已全部落盘至 `docs/requirements/prd.md` v0.2 + `docs/acceptance/test-plan.md` v0.2。0 驳回。

### A 类：阻断项（协议硬伤）—— 5 项全部已修改

| # | 位置 | 修改内容 | 原状态 → 新状态 |
|---|---|---|---|
| A1 | REQ-F-8 | 改写为两分支（早取消 CANCEL → 487 / 对话已建立 BYE → 200 OK）；业务描述开头加 CANCEL vs BYE 区分说明；test-plan 拆三个时点场景 | 待修改 → **已修改** |
| A2 | REQ-F-2 + test-plan | PRD 业务描述不变（已正确）；test-plan 全改：断言入腿≠出腿 Call-ID + 同一腿内 INVITE/200/ACK/BYE Call-ID 一致 | 待修改 → **已修改** |
| A3 | 全文 RFC 章节号 | 7 处章节号逐条修正；PRD 头部加"协议章节号说明" | 待修改 → **已修改** |
| A4 | REQ-F-5 | 改写业务描述为"消费寻址本跳 Route + 路由策略显式生成"；test-plan 验收改为检查下游目标地址而非头域字符串 | 待修改 → **已修改** |
| A5 | REQ-F-11 | 拆两分支（CANCEL 先到 → 487 / 最终响应先到 → 走 BYE）；加 RFC 3261 §9.1/§9.2 引用；test-plan 拆两分支验收 | 待修改 → **已修改** |

### B 类：覆盖缺口 —— 7 项全部已修改

| # | 缺口 | 修改内容 | 原状态 → 新状态 |
|---|---|---|---|
| B1 | 缺 Actor 4 业务方 | 加 Actor 4 + US-10（翻译查询）+ US-11（反欺诈查询） | 待修改 → **已修改** |
| B2 | 控制台/配置管理无 REQ-F | 新增 §2.4 控制台与配置管理：REQ-F-12（规则 CRUD）/ F-13（轨迹查询）/ F-14（审批流程）/ F-15（灰度分发与回滚） | 待修改 → **已修改** |
| B3 | 翻译主路径无 REQ | 新增 §2.5 业务决策链：REQ-F-16 命中翻译规则后的处理 | 待修改 → **已修改** |
| B4 | REQ-F-6/F-7 匹配语义缺失 | REQ-F-6 追加匹配对象=被叫、最长前缀优先；REQ-F-7 追加同上 + 阻止>翻译>默认路由 | 待修改 → **已修改** |
| B5 | 无 REQ-S-*（安全） | **推翻 M1 Gap 3 裁决**。新增 PRD §4 安全需求：REQ-S-1（白名单校验）/ S-2（端到端 TLS）/ S-3（证书热轮换）/ S-4（控制台鉴权与审计） | 待修改 → **已修改（推翻裁决）** |
| B6 | 无可观测性需求 | 新增 REQ-NF-13（OTel 三信号导出）、REQ-NF-14（告警规则集） | 待修改 → **已修改** |
| B7 | 轨迹保留期冲突 | PRD REQ-NF-7 + test-plan REQ-NF-7 改"保留期待定——M4 冻结" | 待修改 → **已修改** |

### C 类：一致性与表述 —— 12 项全部已修改

| # | 位置 | 修改内容 | 原状态 → 新状态 |
|---|---|---|---|
| C1 | US-1 | "立即生效"→"提交草稿 → 审批 → 生效" | 待修改 → **已修改** |
| C2 | §4 治理 → §5 治理 | 治理节开头加 P2 优先级定义说明 | 待修改 → **已修改** |
| C3 | US-9 | "LoadBalancer 自动路由 v1.3.0"→ 需求语言（新版本就绪后新请求路由到新版本，存量在老版本完成） | 待修改 → **已修改** |
| C4 | US-8 | "2 秒内恢复"→"呼叫不中断" + 时延承诺待 M6 冻结 | 待修改 → **已修改** |
| C5 | §0 非目标 | 末尾加 formalize 说明，指向 REQ-NF-6/7/8 和 REQ-S-* | 待修改 → **已修改** |
| C6 | §3.1/§3.2 | REQ-NF-4 从 §3.2 扩展与治理 移到 §3.1 核心架构约束 | 待修改 → **已修改** |
| C7 | REQ-G-3 / AGENT.md §9 | 同步澄清 AST 扫描归属：不在 `make gate` 四步内，属 CI 额外步骤或 `make gate-strict` | 待修改 → **已修改** |
| C8 | PRD 头部 | 加"验收标准状态"占位声明 | 待修改 → **已修改** |
| C9 | REQ-NF-6/7/8 | 各末尾加"依据 ADR-0004/0017/0016，当前为 skeleton 状态，M2 补" | 待修改 → **已修改** |
| C10 | REQ-F-9 | "Via branch + Route + Call-ID"→"Call-ID + local/remote tag（RFC 3261 §12 Dialogs）" | 待修改 → **已修改** |
| C11 | §1 未覆盖表 | 表头"未覆盖"→"暂缺用户故事 + POC 基线"，备注说明已有业务描述 | 待修改 → **已修改** |
| C12 | test-plan REQ-F-8 | 拆三时点场景：180 前（无 early dialog）/ 180 后 200 前（有 early dialog）/ 200 后（对话已建立 BYE） | 待修改 → **已修改** |

### 验收结果

| 类别 | 原条数 | 裁决结果 | 已修改 | 状态 |
|---|---|---|---|---|
| A 阻断 | 5 | 全部接受 | 5/5 | PRD v0.2 已发布 |
| B 覆盖缺口 | 7 | 全部接受（含 1 项推翻 M1 裁决） | 7/7 | PRD v0.2 已发布 |
| C 一致性 | 12 | 全部接受 | 12/12 | PRD v0.2 已发布 |
| **合计** | **24** | **全部接受，0 驳回** | **24/24** | **PRD v0.2 released** |
