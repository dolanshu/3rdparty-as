# ADR-0011 — SIP 栈：双栈并行（sippy 保生产 + go-b2bua 试点）

- **编号**：ADR-0011
- **状态**：**superseded-in-part by ADR-0019**（"双栈并行"框架仍有效；"生产栈 = sippy"前提被推翻）
- **日期**：2026-09-27
- **决定**：[`../新系统整体架构.md`](../新系统整体架构.md) §0 决策 8 —— 采用双栈并行迁移路径：sippy 继续作为生产栈，go-b2bua 作为试点实现。

---

## Context（背景）

POC 已验证 `sippy==2.4.2` 作为 B2BUA 的可行性；同时存在官方 Go 移植 `go-b2bua`。
为降低运行时风险并保留跨实现对拍框架，维护者确认先以 sippy 保生产、go-b2bua 做试点。

---

## Decision（决策）

1. 生产栈继续使用 `sippy==2.4.2`。
2. 同步启动 `go-b2bua` 镜像移植，与 Python 实现共用规则 YAML，通过跨实现契约测试对拍后逐步灰度。
3. 双栈并行的具体所指由 ADR-0019 的选定结果重新解释。

---

## Consequences（后果）

### Positive（正面）

- 风险受控：生产行为不变，新栈逐步验证。
- 保留跨实现对拍作为转正门槛（ADR-0012）。

### Negative / accepted（负面 / 已接受）

- sippy 的上游集中度、Python 3.10 EOL 等风险未被本决策解除；后续由 ADR-0019 处理。
- go-b2bua 无 release，入选后须 commit pin + vendoring。

---

## Alternatives considered（考虑过的备选）

| Option | Why not |
|---|---|
| 直接全面切 go-b2bua | 无充分对拍证据前切换生产风险过高 |
| 继续单一 sippy | 未回应供应链与运行时生命周期风险 |

---

## Evidence（证据）

- [`../新系统整体架构.md`](../新系统整体架构.md) §10.1 / §10.2：双栈迁移状态机。
- `docs/SIP_stack_selection.md`：候选栈清单与许可红线。

---

## Related（相关）

- [`../新系统整体架构.md`](../新系统整体架构.md) §0 决策 8、§10
- [`0019-sip-stack-selection.md`](0019-sip-stack-selection.md)（推翻"生产栈 = sippy"前提）
- ADR-0012（跨实现契约 + 对拍，skeleton）
