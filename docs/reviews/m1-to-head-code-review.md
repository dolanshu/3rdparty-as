# M1 至 HEAD 代码评审记录

> 评审对象：`d63cfb70b5b917a6575af1d271b3bef2efd600a1` 至 `cbbd2eccc4025367147fa1c6eb64c01dc80d1371`（`git diff d63cfb7...HEAD`；48 commits，203 changed files）
> 评审日期：2026-09-30
> 评审人：AI agent
> 规格依据：`docs/plan.md`
> 评审结论：**待裁决** —— 本记录保留 Standards 与 Spec 两轴发现，不作通过或不通过裁决。

## Standards

| # | 严重性 | 发现与证据 |
|---|---|---|
| 1 | [blocking] | `testbed/simulators/resip-probe/resip_probe.cxx` 中的中文代码注释、日志和错误信息违反已提交 `AGENT.md` §5“产物的语言：英文”要求。证据：文件第 1、428、467 行。 |
| 2 | [blocking] | `ProbeInviteHandler::onConnected` 中执行阻塞调用 `std::this_thread::sleep_for(std::chrono::milliseconds(200))`，违反 `AGENT.md` §5 关于不得在 SIP 回调中执行阻塞操作的要求。证据：`testbed/simulators/resip-probe/resip_probe.cxx:250`。 |
| 3 | [suggestion, judgement call: Duplicated Code] | 最长前缀候选项的 `max` 选择逻辑重复：`apps/anti-fraud/src/as_anti_fraud/decision.py:90` 与 `apps/translation/src/as_translation/decision.py:96` 均使用 `return max(candidates, key=lambda candidate: candidate[0])[1]`。 |
| 4 | [suggestion, judgement call: Duplicated Code] | `_load_bindings` 中的导入、`ImportError` 指引及 `SystemExit` 逻辑重复：`testbed/probe/e1_baseline_probe.py:267` 与 `testbed/probe/tls_hot_rotation_probe.py:144`。 |

格式、lint、类型等工具强制检查项未重复报告。

## Spec

| # | 严重性 | 发现与证据 |
|---|---|---|
| 1 | [important] | M5 要求“缩容不掉呼叫”（`docs/plan.md:120`），但缩容保护仅给出判定结果，未接入执行路径：守卫位于 `platform/src/as_platform/ops/downscale_guard.py:19,91`；HPA 直接以 Deployment 为目标，见 `deploy/helm/templates/hpa.yaml:38,40`；`plan_scale_down` 在运行时守卫模块之外没有使用点。 |
| 2 | [important] | M5 要求“滚动升级不掉呼叫”（`docs/plan.md:120`），但进程入口注入 `active_calls=lambda: 0`，使 drain 完成判定与真实在途呼叫脱离。证据：`platform/src/as_platform/__main__.py:78`。 |
| 3 | [praise] | 计划透明记录 M5 仍在进行中，并说明真实集群滚动升级与缩容验证尚未完成。证据：`docs/plan.md:120`。 |
| 4 | 范围检查 | 未发现有行为意义的范围蔓延。 |

## 当前状态与确认签字

| 项 | 状态 |
|---|---|
| 发现裁决 | 待裁决 |
| 修复 | 未应用 |
| 维护者签字 | 待定 |
| 评审范围外 | 当前工作区中 `AGENT.md` 与 `docs/agents/` 的设置变更不属于本次评审范围 |

## 轴别摘要

| 评审轴 | 记录摘要 |
|---|---|
| Standards | 4 项：2 项 [blocking]，2 项 [suggestion]（均为判断性意见）。 |
| Spec | 4 项：2 项 [important]、1 项 [praise]、1 项范围检查（未发现有行为意义的范围蔓延）。 |
| Standards 最严重发现 | 本轴最严重问题是 SIP probe 的两项 [blocking] 发现：非英文注释、日志和错误文本，以及 SIP 回调中的阻塞 sleep。 |
| Spec 最严重发现 | 本轴最严重问题是 M5 保呼叫验收未满足/未完成：缩容保护未接入执行路径，且运行时 drain 计数器硬编码为零。 |

以上发现均未裁决，未应用修复，维护者签字待定。
