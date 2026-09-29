---
name: context-handoff
description: Notify the maintainer when conversation context approaches its limit, summarize what is already persisted to disk, and present a decision on writing a handoff note and starting a new conversation. Use when a context-usage or compaction reminder appears, when a turn was unusually long, or when the user asks about context state. Do not use for ordinary task turns without context pressure.
---

# Context Handoff

当 context 接近上限时（系统出现 context usage / compaction 提醒，或本轮对话明显超长），执行以下流程。不要静默继续工作直到自动压缩发生。

## 流程

1. **立即通知维护者**：在回复开头明确说明 context 接近上限。
2. **盘点落盘状态**：列出本会话产生的关键决策与文件，逐项确认它们是否已写入磁盘（用 `git status` 核对未提交改动）。规则：凡是"只存在于对话里、丢了就无法恢复"的决策，必须先落盘再谈开新对话。
3. **给出 handoff 决策建议**，包含三选一：
   - **建议开新对话**：当前阶段任务已完成、产出已全部落盘、剩余工作可由磁盘状态恢复；
   - **建议先补落盘再开**：还有决策未落盘，列出需要写入的文件与内容要点；
   - **建议留在本对话**：后续步骤强依赖对话内的原始材料（未保存的错误输出、行号级引用等），并说明预计还能推进多少。
4. **写 handoff 备忘**（维护者同意开新对话时）：把以下内容交给 `new_context` 的 summary —— 当前目标与修正、已裁决的决策清单（含编号）、未决项、下一步顺序、关键文件路径。

## 判据：什么必须落盘

- 维护者的裁决与决策（Q&A 形式的确认）—— 写入对应 ADR / gap review / plan.md
- 推算、调研结论及其来源 —— 写入 docs/ 下的专门文档
- 里程碑状态变化 —— 写入 docs/plan.md
- 未决项的移动 —— 写入 docs/plan.md §5

## 禁止

- 不通知维护者就依赖自动压缩继续工作。
- 把"未落盘的决策"作为开新对话的前提。
