# ADR-0010 评审记录

> 评审对象：`docs/architecture/adr/0010-autoscaling-hpa-downscale-guard.md`（2026-09-28 新建，Status: draft）
> 评审日期：2026-09-28
> 评审人：AI agent（对照 AGENT.md 红线与非目标、PRD REQ、已在册 ADR 交叉核对）
> 评审结论：**通过** —— 转 accepted；共 2 项已知缺口，其中 0 项阻塞

## 评审方法

| 维度 | 方法 |
|---|---|
| 与红线一致性 | 逐条比对 `AGENT.md` §2（非目标：M6 实测之前不发布任何容量数字）、§5（决策模块是纯函数）、§7（ADR 与改动一起写）原文 |
| 与需求一致性 | 核对 PRD v0.2 的 REQ-NF-1（进程重启不丢会话）、REQ-NF-3（可水平扩展：能安全缩容）、REQ-NF-4（ISSU 不掉呼叫） |
| 与既有 ADR 一致性 | 是否与 ADR-0002（无状态 + Redis 会话表 + 亲和性双保险）、ADR-0007（运行态在 Redis）、ADR-0009（draining，skeleton）冲突 |
| 结构完整性 | 是否具备 Context / Decision / Consequences / Alternatives / Evidence / Related，且与 ADR-0002 的章节结构一致 |
| 实现一致性 | 判据是否在 `platform/src/as_platform/ops/downscale_guard.py` 中如实落地，并由 `unit` 层用例锁定 |

## 发现与裁决

| # | 发现 | 裁决 |
|---|---|---|
| 1 | **阈值纪律**：ADR 未给出任何目标利用率、目标 `active_calls`、副本上下限或超时值，全部指向 `deploy/helm/values.yaml` 由 M6 填入；`hpa.yaml` 的 `required` 守卫（"measure it in M6 (O1), do not guess"）已落地为佐证，不是口头承诺 | 接受，作为红线合规的 L1 证据；"阈值是容量结论，保护阈值是安全判据"的区分成立，且两个概念未被混用 |
| 2 | **控制器只产出判定、不操作 K8s**：实现为纯函数（`plan_scale_down` / `may_remove`），无 socket、无时钟、无全局状态；判定与执行分离使缩容保护可在无集群的 CI 层覆盖 | 接受；与 AGENT.md §5"决策模块是纯函数"一致，且把"能不能缩"从"要不要缩"里剥离出来的解耦论证成立 |
| 3 | **与 draining 协同**：选出候选后的摘除必须走 draining（先摘流 → 等归零 → 再删除），且已在 draining 的实例不再被重复选为候选，避免重复下发同一次摘除 | 接受；与 ADR-0009 的 draining 语义一致。ADR-0009 仍是 skeleton，本 ADR 已在 Related 中降级为纯文本，未产生失效链接，也未越权替它做裁决 |
| 4 | **保护阈值是安全判据而非容量数字**：默认 0（非零即保护），并明确"调整理由必须是接受掉呼叫的风险，而不是容量结论" | 接受；`protect_above < 0` 被钳到 0（非法输入不得放宽保护），有用例锁定，安全方向失败即保守，无反向开口 |
| 5 | **实现与测试已同步落地**：`platform/src/as_platform/ops/downscale_guard.py` 与 `platform/tests/test_downscale_guard.py` 同批交付，10 个 `unit` 用例覆盖全零呼叫放行、部分阻塞给部分候选、draining 不重选、排序可复现、非法阈值不放宽、纯度（monkeypatch 后断言无 socket / 时钟调用） | 接受；符合 AGENT.md §7"ADR 与它所授权的改动一起写"，不是事后补记；阻塞时给出可用部分候选的设计使运维不必干等 |
| 6 | 结构完整性：章节与 ADR-0002 对齐（头部四字段 → Context → Decision → Consequences → Alternatives → Evidence → Related），Alternatives 五条均给出 Why not，非走过场 | 接受；consequences 负面段非空，写明接受理由与解决时点 |
| 7 | 已知缺口两项：① 缩容可能被长时间阻塞，超时与强制策略属运维参数未定；② 控制器需要每实例 `active_calls` 指标，比聚合指标更细，指标侧扩展未做 | 接受为**已知缺口**，均不阻塞；① 已写入 Consequences 负面段并标明进 `values.yaml`，② 属 M5 运维接线与指标扩展工作，不属本 ADR 裁决范围 |

## Adjudication 汇总

| 类别 | 条数 | 处置 |
|---|---|---|
| 接受且无需修改 | 5（发现 1、2、3、4、6） | — |
| 接受为已知缺口 | 2（发现 5 无缺口；发现 7 的两项缺口） | 发现 7 ① 进 `deploy/helm/values.yaml` 运维参数；② 随 M5 每实例指标扩展解决 |
| 需要修改 | 0 | — |

## 确认签字

| 项 | 值 |
|---|---|
| 评审结论 | 通过 |
| 状态流转 | ADR-0010 `draft` → `accepted`；注册表同步（`docs/architecture/adr/README.md` 0010 行 skeleton → accepted ✓） |
| 评审人 | AI agent，2026-09-28 |
| 维护者签字 | 待填 |
