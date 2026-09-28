# M2b 边界 seam 评审记录

> 评审对象：`platform/src/as_platform/sip/`（`__init__.py`、`transport.py`、`adapter.py`）与 `platform/tests/test_transport_seam.py`、`test_sip_adapter_seam.py`
> 评审日期：2026-09-28
> 评审人：AI agent（实跑门禁 + 对照 ADR-0016、ADR-0019、AGENT.md §13）
> 评审结论：**通过** —— 边界 seam 落地，不含栈实现；2 项为过门禁的自改已确认合理

## 门禁证据

| 项 | 结果 |
|---|---|
| `uv run ruff format --check .` | 105 files already formatted |
| `uv run ruff check .` | All checks passed! |
| `uv run mypy` | Success: no issues found in 23 source files |
| `uv run pytest -m "unit or contract" -q` | 145 passed, 2 skipped |
| 结构守卫 | 随内核源文件增加自动多出 3 个参数化用例，全通过 |

## 评审发现

| # | 发现 | 裁决 |
|---|---|---|
| S1 | 对端白名单 `authorize_peer` 为纯函数；策略两集合皆空时返回 `False`（fail-closed），与 `gating` 的默认关一致 | 接受：fail-closed 是边界安全的正确默认（ADR-0016、AGENT.md §13） |
| S2 | 证书维度独立于地址维度，任一命中即放行 | 接受：mTLS 场景下证书是更强的身份证据 |
| S3 | TLS 配置热轮换实现为**不可变重载**（`reload` 返回新 `TransportSeam`，`config_version` 自增），并有测试断言"旧 seam 仍按旧策略判定" | 接受：正是对"热轮换不重启进程、不丢在途呼叫"的可测表达（AGENT.md §13） |
| S4 | `SipAdapter` 只声明 Protocol（`parse` / `respond` / `forward`），不含任何实现与栈依赖 | 接受：M2b 前半的正当范围；绑定 reSIProcate 属后半，且不污染内核（ADR-0019） |
| S5 | `decision_to_status_code`：`DECLINE → 603`（RFC 3261 §21.6.2）、`NOT_FOUND → 404`（§21.4.5）、`FORWARD/TRANSLATE → 0`（继续转发） | 接受：章节号采用 PRD 评审已订正的结论，未沿用错误的 §21.6.5 / §21.4.4 |
| S6 | `to_decision_request` 的 `received_at` 由调用方注入，模块不读时钟 | 接受：保持 `decide()` 纯函数链（AGENT.md §5） |
| S7 | 两处为过门禁的自改：`reload` 返回注解去掉引号（UP037，语义等价）、`authorize_peer` 改布尔直返（SIM103，保留 `# See ADR-0016` 注释） | 接受：均为等价改写，未用 `# type: ignore` 或 `# noqa` 掩盖 |
| S8 | 全仓无 `# type: ignore`、无 `# noqa` | 接受 |

## 缺口（不阻塞）

| # | 缺口 | 去向 |
|---|---|---|
| S9 | `SipAdapter` 无实现，尚无真 socket 的 integration 用例 | M2b 后半（栈绑定）后补 |
| S10 | 证书热轮换的真实加载（读证书文件、握手）未实现，本 seam 只覆盖策略与版本语义 | M2b 后半 |
| S11 | `integration` / `e2e` 层仍零用例，CI 层②③ 仍为 `continue-on-error` | 首个该层用例引入的里程碑必须改为阻塞（AGENT.md §9、plan.md §2.4） |

## 确认签字

| 项 | 值 |
|---|---|
| 评审结论 | 通过 |
| 门禁 | 全绿（145 passed / 2 skipped） |
| 评审人 | AI agent，2026-09-28 |
| 维护者签字 | 待填 |
