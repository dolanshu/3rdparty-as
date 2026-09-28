# M2 设计评审记录（HLD / LLD）

> 评审对象：`docs/architecture/hld.md`、`docs/architecture/lld.md`（2026-09-28 新建）
> 评审日期：2026-09-28
> 评审人：AI agent（对照实现、test-plan §5、AGENT.md §5、已 accepted 的 ADR-0002/0003/0005/0007/0016/0019）
> 评审结论：**有条件通过** —— 3 项签名漂移已按"以代码为准"回改 LLD；3 项缺口列入后续里程碑

## 评审方法

| 维度 | 方法 |
|---|---|
| 与需求一致性 | 对照 `docs/acceptance/test-plan.md` §5（M2 内核验收）逐条 |
| 与 ADR 一致性 | ADR-0002 / 0003 / 0005 / 0007 / 0016 / 0019 / 0020 |
| 与实现一致性 | 对照 `platform/src/as_platform/` 落地代码逐项（发现签名漂移） |
| 与编码约定一致性 | `AGENT.md` §5（纯函数、类型标注、禁用模块名、ADR 标注） |

## 发现与裁决

| # | 发现 | 裁决 | 状态 |
|---|---|---|---|
| D1 | LLD §5 门控签名 `is_enabled(source, name, scope)` 与实现 `is_enabled(name, scope, source)` 不一致；`ToggleSource` 单一 `value()` 无法表达"部署级 / 运行态"两层来源 | 以**代码为准**回改 LLD：两方法 `deployment_value` / `runtime_override` | 已修改 |
| D2 | LLD §4 `build_key(..., id)` 用内置名 `id`，触发 ruff A002；实现用 `entity_id` | 以代码为准回改 LLD | 已修改 |
| D3 | LLD §6 遥测丢弃计数写作 `dropped`，实现暴露的是 `dropped_count` / `export_failure_count` | 以代码为准回改 LLD | 已修改 |
| D4 | HLD §7.3 裁决"M2 只落门控 seam，不引入新开关"，实现一致（未引入任何新开关） | 接受；避免开关债务 | 已确认 |
| D5 | LLD §2 定义了 `CallState`，M2a 未实现（StateStore 为通用键值存储） | 接受为缺口：CallState 由用例层在 M3 落，内核只提供存储原语 | 待 M3 |
| D6 | HLD §3 模块视图含 SIP adapter 与 TLS transport（M2b），代码未实现 | 接受：与 HLD §1.2 的 M2a / M2b 切分一致 | 待 M2b |
| D7 | HLD §8 REQ/ADR 追溯表覆盖 17 个 REQ，但 REQ-S-4（控制台鉴权）落在 M4 | 接受；已在 HLD §1.3 非目标与 ADR-0016 中声明归属 | 待 M4 |
| D8 | 门控实现依据的 ADR-0020 仍为 draft | 接受为**依赖缺口**：不阻塞 M2a（只落 seam），但在 M4 控制面落地前必须完成 ADR-0020 评审 | 待评审 |

## Adjudication 汇总

| 类别 | 条数 | 处置 |
|---|---|---|
| 签名漂移（以代码为准回改文档） | 3（D1-D3） | 已改 LLD |
| 确认一致 | 1（D4） | — |
| 接受为缺口 | 4（D5-D8） | 分列 M3 / M2b / M4 / ADR 评审 |

## 确认签字

| 项 | 值 |
|---|---|
| 评审结论 | 有条件通过 |
| 状态流转 | hld.md / lld.md：`draft` → `reviewed` |
| 评审人 | AI agent，2026-09-28 |
| 维护者签字 | 待填 |
