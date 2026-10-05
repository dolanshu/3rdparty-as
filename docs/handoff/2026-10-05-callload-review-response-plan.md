# callload 分支评审 — 意见评估与处置计划（2026-10-05）

> **依据**：[`docs/reviews/callload-m2-m6-m7-demo-branch-review-2026-10-05.md`](../reviews/callload-m2-m6-m7-demo-branch-review-2026-10-05.md)（下称 **评审**）。  
> **范围**：工程与验收事实；**不含**版本控制操作（维护者自行处理分支/入库，见 AGENT.md §11）。  
> **目标**：在维护者认可前，明确「评审是否成立 → 做什么 → 什么算闭合」。

---

## 1. 对评审总结论的评估

| 评审结论 | 评估 |
|----------|------|
| **工程切片成立、`make gate` 绿** | **同意**。决策层、M6 方法学、demo 边界话术、checkpoint CAS 等正面项与源码一致。 |
| **按当前形态不批准合并主干 / 直接对客户 Demo** | **同意（有条件）**。根因不是「没写文档」，而是 **产品 runtime 仍按 loopback 实验室形态接线**（F1+F7），且 **恢复/checkpoint 证据链与 REQ 口径有落差**（F2–F4、F3）。 |
| **1 blocker + 10 major** | **数量级合理**；F11 应降级为 **维护者工程卫生**，不作为 agent 修复队列的 P0（见 §3）。 |

**不同意或需收窄的表述**：

| 评审条目 | 调整 |
|----------|------|
| **F10「未合入主干 04afc5a」** | 实质是 **M5 全链结论与 callload 上 Demo 故事 C 话术未对账**，不是「必须先做 git 合并」。处置 = **内容对账**：故事 C 只演示经 M5.1/全链认可的工件，或显式标为 L1/机制演示。 |
| **F11 提交粒度** | 对 **未来** 维护者入库有参考价值；**不**作为 callload 功能修复的阻塞项；agent **不**重组历史。 |
| **「18 条全部待改」** | 应拆成 **P0 产品可部署性**、**P1 M8 证据真实性**、**P2 卫生与 Demo 可重复性**；P2 不挡「内部技术 Demo（loopback）」。 |

---

## 2. 逐类意见评估（是否采纳）

### 2.1 采纳为 P0（客户 Demo「非 loopback」/ 产品进程可配置前必做）

| ID | 评审主张 | 评估 | 处置方向 |
|----|----------|------|----------|
| **F1** | 监听/Contact/SDP 硬编码 `127.0.0.1` | **成立**（`runtime_module.cxx` 多处已核对） | `AS_SIP_BIND_ADDRESS` / `AS_SIP_ADVERTISED_ADDRESS`（或等价）贯穿 C++ config + Contact/SDP；补非环回绑定集成测 |
| **F7** | `SipStackService.from_env` 不读 TLS/peer/bind | **成立**（与 F1 同根） | 从 env/Helm 契约加载证书路径、peer allowlist、fingerprint；TLS 启用且配置无效 → **启动失败**（fail-closed） |
| **F10（内容面）** | Demo 故事 C 与 M5 全链「不通过」矛盾 | **成立** | 更新 `pre-m8-demo-review-plan.md` + `story-c.sh` 话术/范围；全链/M5.1 未闭合项 **不得**对客户称为「已验收运维能力」 |

### 2.2 采纳为 P1（M8 / REQ 硬门槛；可在「内部 loopback Demo」之后做）

| ID | 评审主张 | 评估 | 处置方向 |
|----|----------|------|----------|
| **F2** | 恢复 BYE Contact/route_set | **成立** | 用通告地址；BYE 带 checkpoint `route_set`；补 Record-Route 恢复集成测 |
| **F3** | UAC checkpoint 占位 tag/CSeq | **成立**（`sip_stack_service.py` 硬编码） | native 回调真实 UAC dialog 字段；集成测断言下游接受 BYE，而非仅日志 |
| **F4** | 非 486 → 502，违 REQ-F-10 | **成立** | C++ + `call_controller` 透传 408/480/486/503/504 等；改 `test_outbound_non486_final_maps_to_502`；补契约 |
| **F9** | gate/CI 不构建 native → 核心测 skip | **成立** | CI 增加 **native build + 必选 contract/integration**（扩展缺失时 **fail**，非 skip）；本地 `make gate` 策略与 plan 对齐（AGENT.md §9） |
| **F5** | fingerprint 缓存无界 | **成立** | 连接关闭淘汰或 LRU/上限；长跑或单测 |
| **F6** | connection 只注册不注销 | **成立** | transport 关闭回调 `unregister_connection`；overlap 语义修正 |
| **F8** | C++ cout/cerr | **成立（M8 前）** | 事件回调 Python 结构化日志，或 C++ 字段契约 + 测试；可排在 P1 末 |

### 2.3 采纳为 P2（不挡「工程认可」，挡「发布候选 / 对外口径」）

| ID | 评估 | 处置 |
|----|------|------|
| **F12** | 成立 | `as_load` 增加成功率/退出码策略 |
| **F13** | 成立 | demo 脚本 `--strict` + PASS/SKIP/FAIL 汇总写 artifact |
| **F14** | 成立 | `AS_M6_OUTPUT_ROOT` |
| **F15** | 成立 | M8 打包前 CHANGELOG/VERSION（DoD） |
| **F16** | 成立 | `CallController` 恢复 unit |
| **F18** | 成立 | story 加 S4 或删 demo 计划中的 487 承诺 |
| **F17** | 部分成立 | vendor 源码保留；prebuilt 文档化保质期/重建；是否迁出 git 由维护者决策 |

### 2.4 不纳入本计划执行项

| ID | 说明 |
|----|------|
| **F11** | 历史提交形态：**维护者**入库规范；不指派 agent「修复」。 |

---

## 3. 处置计划（执行顺序）

### 阶段 0 — 裁决与口径（1 次维护者拍板，无代码）

- [x] **D0-1** 确认本计划 P0/P1/P2 划分；确认「内部 loopback Demo」是否允许在 P0 完成前进行（建议：**仅故事 B/E + 文档**，故事 A 信令桥接、故事 C 全量 **暂缓**）。
- [x] **D0-2** 对 M5 全链 +（若存在）`cur` M5.1 结论做 **Demo 对账表**：故事 C 每一句交付能力 → 引用评审/adjudication 状态（见 [`pre-m8-demo-review-plan.md`](pre-m8-demo-review-plan.md) F10 段）。
- [x] **D0-3** 在 `docs/plan.md` 或 handoff 记录：**callload 评审 F1–F18 跟踪表**（本文 §4）为单一 backlog，不重复开第三条线（合入清单见 [`2026-10-06-callload-merge-to-master.md`](2026-10-06-callload-merge-to-master.md)）。

### 阶段 1 — P0：离开 loopback（产品可配置）

**目标**：进程在容器/VM 上可绑定非环回地址、可加载 TLS/peer 配置；Demo 话术与 M5 对齐。

| 任务 | 交付物 | 验证 |
|------|--------|------|
| **P0-1 F1+F7** | C++ transport config + Python `SipStackService`/env 文档；Contact/SDP 用 advertised 地址 | 非 `127.0.0.1` 绑定集成测；`make m2-platform-resip-build` 后 E1 至少 1 条在非环回场景跑通 |
| **P0-2 F10** | 更新 `pre-m8-demo-review-plan.md`、`scripts/demo-review/story-c.sh` 注释与对客户展示块 | 维护者签字「故事 C 范围」 |
| **P0-3 评审落盘** | 本文 + §4 跟踪表；F1/F7/F10 标为「修复中/已修复」 | 对照评审 Adjudication 表 |

**阶段 1 闭合标准**：维护者认可「产品进程具备 **可配置监听与 TLS/peer 接缝**」；**不**宣称 REQ-S-2/NF-9 已验收。

### 阶段 2 — P1：证据与 REQ 对齐（M8 前硬项）

| 任务 | 依赖 | 验证 |
|------|------|------|
| **P1-1 F9** | 无 | CI native job 绿；无扩展时相关测 **fail**；本地文档写清 `make m2-platform-resip-build` 与 gate 关系 |
| **P1-2 F4** | native | 契约测 + 改固化错误行为的单测 |
| **P1-3 F3+F2** | native + recovery | 真实 checkpoint 字段；恢复 BYE 集成测 |
| **P1-4 F5+F6** | native | 断连/轮换相关单测或集成测 |
| **P1-5 F8** | 可选与 P1-4 并行 | 日志字段契约测 |

**阶段 2 闭合标准**：评审 Adjudication 中 P1 项改为「已修复」；`test-plan` 相关条目 **可进入 M8 执行**（仍非自动绿）。

### 阶段 3 — P2：卫生与 Demo 可重复性

- 按 §2.3 逐项实施；**F15** 对齐 M8 打包里程碑。
- **F18**：`story-b.sh` 或 `story-sip.sh` 增加 `test_e1_s4_*` 一步，或修订 demo 计划 §5。

### 阶段 4 — 重新评审与合入准备

- [x] 产出：[`callload-remediation-adjudication-2026-10-05.md`](../reviews/callload-remediation-adjudication-2026-10-05.md)（Adjudication 表状态列）。
- [x] 合入 `master` 准备：[`2026-10-06-callload-merge-to-master.md`](2026-10-06-callload-merge-to-master.md)（维护者执行 merge；**待** CI 工作区 commit + 显式批准）。
- 输入：§4 跟踪表除 F8/F6 部分/F11 外已闭合；残余风险见 merge handoff §2.4。
- **仍不**等于 M2/M6/M7 里程碑退出或 REQ 全绿。

---

## 4. 跟踪表（执行时更新状态列）

| ID | 优先级 | 状态 | 负责人 | 验证命令 / 证据 |
|----|--------|------|--------|-----------------|
| F1 | P0 | 已修复 | agent | `transport_env` + `runtime_module.cxx` |
| F7 | P0 | 已修复 | agent | `test_transport_env.py` |
| F10 | P0 | 已修复 | agent | story-c + pre-m8 §故事 C |
| F9 | P1 | 部分修复 | agent | `native_extensions.py`；**blocking CI job 未上 origin**（需 PAT `workflow` scope） |
| F4 | P1 | 已修复 | agent | `test_call_controller.py` |
| F3 | P1 | 已修复 | agent | FORWARD `uac_leg` native 回调 |
| F2 | P1 | 已修复 | agent | `recovery_module.cxx` |
| F5 | P1 | 已修复 | agent | fingerprint 上限 |
| F6 | P1 | 部分修复 | agent | 注册上限 + 终止注销 |
| F8 | P1 | 未闭合 | agent | REQ-NF-13 待 M8 前 |
| F12–F18 | P2 | 已修复 | agent | CHANGELOG 0.2.0 / demo / as_load / M6 root |
| F11 | — | 维护者 | 维护者 | 不跟踪 agent |

---

## 5. 与分支/里程碑的关系（陈述事实，不指派 git 操作）

- **callload** 承载 M2 后半 / M6 / M7 / Pre-M8 Demo 工程；评审正确指出其与 **loopback 实验室形态** 的差距。
- **master / cur** 上另有 **M5 全链 / M5.1** 线；Demo **故事 C** 必须跨分支 **内容对账**，而非假设「合并即解决」。
- **M6/M7 工程成果**（harness、O1 报告、E1 形状、FORWARD 486）在 P0/P1 修复后 **保留**；不需因评审全盘回滚。
- **2026-10-06**：维护者准备将 `callload` 合入 `master` 时，按 [`2026-10-06-callload-merge-to-master.md`](2026-10-06-callload-merge-to-master.md) 执行；合入 **不** 改变 §5 里程碑/REQ 边界。

---

## 6. 建议的下一 session 起手式

1. 维护者确认 **阶段 0**（D0-1～D0-3）。  
2. 实施 **P0-1**（F1+F7）单线，直到非环回集成测绿。  
3. 并行 **P0-2** 文档（Demo 故事 C 收窄）。  
4. **P1-1 F9** 尽早做，避免后续修复在无 native 门禁下反复。
