# E2E 测试计划（草案，待维护者 review）

**日期**：2026-10-09  
**状态**：计划，**未实现**。`pytest -m e2e` 当前 **0 条**。  
**关联**：[`test-plan.md`](test-plan.md) 自动化分层；[`../handoff/2026-10-09-sip-native-testing-plan.md`](../handoff/2026-10-09-sip-native-testing-plan.md)（harness / native CI）；[`../handoff/pre-m8-demo-review-plan.md`](../handoff/pre-m8-demo-review-plan.md)（kind `as-m71`）。

---

## 1. 定义（本仓库里的 e2e）

**E2E** = 一次自动化里同时满足：

1. **产品 SIP 栈**是 `_resip_runtime`（reSIProcate），不是纯 Python 拼包、也不是只解析日志。  
2. **判决走生产缝**：`decide()` / 已激活规则或等价 `RuleSet` + 出腿 hook；**禁止** `accept_all_invites`（及 `early_cancel_harness`）作为被测 AS 的默认模式。  
3. **路径跨过网元边界**：至少「呼叫源 →（仿真或真实）S-CSCF/S-SBC → AS → 对端 UAS」，并断言 **终态**（结果码、必要时出腿用户号、BYE 不挂死）。  
4. 标记 **`@pytest.mark.e2e`**，由 `make test-e2e` / CI job ③ 收集；与 `unit` / `contract` / `integration` 分开，避免 `make gate` 被拉长。

**不是 e2e：**

| 现有东西 | 为什么不算 |
|----------|------------|
| E1 S1 `accept_all_invites` | harness：真栈但旁路 `decide()`，只覆盖 100/180/200 |
| E1 S2/S3 单 socket | 真栈 + `decide()`，但无仿真 S-SBC、无完整 14 消息、无控制台 |
| M6 `as_load` → `load_uas_runtime` | 对端是 accept-all UAS，测容量不测业务 |
| `test_derived_baseline.py` | 对契约 **文件** 做断言，不打产品进程 |
| kind demo 脚本 | 证据层；可 **复用** 步骤，但在升格为 pytest e2e 之前不算本计划「已落地」 |

---

## 2. 现状锚点（实现时复用，不重复造轮）

| 锚点 | 路径 | 已证明 |
|------|------|--------|
| 本地仿真链 + 真栈 + 规则 | `testbed/simulators/tests/test_product_path.py` | T1/T4/T5/F1/F2 结果码、翻译用户号、BYE；UDP/TCP/TLS；**integration**，短时 `as_load` |
| 双腿 / SDP | `platform/tests/test_m7_forward_two_leg_integration.py`、`test_req_f4_sdp_identity_integration.py` | FORWARD 与 SDP 身份；无完整 S-CSCF 链 |
| 契约消息 | `testbed/contracts/sip-baseline/S1-basic-call/` 等 | REQ-F-1 的 14 条 **形状**；尚未对产品栈全文回放 |
| 现场 demo | `scripts/demo-review/story-*.sh`、kind `as-m71` | 客户路径；控制台在 compose，信令在 kind |

**缺口：** 没有 `e2e` 标记；CI ③ `continue-on-error` 且无用例；REQ-F-1 勾选仍 open。

---

## 3. 范围（建议分波，review 时删减）

### Wave 0 — 把门禁说清楚（文档 + 标记约定）

- 本文件 + `test-plan.md` 分层表（已写）。  
- `pyproject.toml` 的 `e2e` marker 说明与实现对齐。  
- CI：在 **至少一条** e2e 稳定前，job ③ 保持 `continue-on-error` **或** 改为 required 但只跑 Wave 1 的 smoke（二选一，见 §6）。

### Wave 1 — 信令 e2e（无控制台）

从 `test_product_path` **升格或拆出** `@pytest.mark.e2e`：

| ID | 场景 | 断言（最小） | 禁止 |
|----|------|----------------|------|
| E2E-SIP-1 | UDP：T1 翻译接通 | 200；出腿用户含翻译结果；BYE 计数与未决会话为 0 | `accept_all_invites` |
| E2E-SIP-2 | UDP：T4 无匹配 | 404；不出腿或不出 BYE 业务腿（与现 `test_product_path` 一致） | harness |
| E2E-SIP-3 | UDP：F2 阻止 | 603 | harness |
| E2E-SIP-4 | TCP、TLS 各一条（可参数化，与现 4 组合对齐或先各 1） | 同 T1 子集 | 测试 CA，不声称 REQ-S-2/S-3 签收 |

**完成标准：** `AS_REQUIRE_NATIVE_EXTENSIONS=1 uv run pytest -m e2e -q` 在已 `make m2-platform-resip-build` 的机器上绿；缺 `.so` 则 **fail**（与 native-contract 策略一致），不 skip。

**明确不做（Wave 1）：** 14 条逐条 header 对拍、控制台、kind、容量数字。

### Wave 2 — REQ-F-1 形状（仍无控制台）

在 Wave 1 拓扑上，对 **一通** T1：

- 采集入/出腿关键消息（方法 + 最终响应码序列，或与 `S1-basic-call` **归一化**对比）。  
- 断言 **C_in ≠ C_out**（REQ-F-2 子集）。  
- SDP offer 入腿与出腿 **逐字节**（REQ-F-4）若实现成本可接受；否则单列 follow-up。

**完成标准：** `test-plan.md` REQ-F-1 勾选改为「自动化子集已覆盖 / 全文仍 open」并链到本用例名，**不**在未对拍 14 条时打勾全文。

### Wave 3 — 控制面 + 信令（可选，重）

- compose 或 test client：规则变更 → 激活 bundle → **重启或热加载策略以仓库实际能力为准** → 再跑 E2E-SIP-1。  
- 与 demo story A 对齐；**不**把浏览器手工步骤写进第一版 CI。

### Wave 4 — kind `as-m71`（发布前证据，默认可选 CI）

- 复用 `kind-up.sh` + `publish-m71-bundle.sh` + 测试页或 `as_load` 打 **产品 Deployment**（非 `load_uas_runtime`）。  
- 标记 `e2e` + `kind`（需新 marker 或 env `AS_E2E_KIND=1`），**nightly / workflow_dispatch**，不进每次 PR，除非维护者要求。

**明确排除：**

- M6 容量 / O1 报告（`performance`）。  
- `accept_all` harness 作为被测 AS。  
- 运营商真 S-SBC / 客户 PKI（M8 环境证据，见 `m8-environment-evidence.md`）。

---

## 4. 与 harness / call load 的边界（写进用例 docstring）

| 被测进程 | 允许 |
|----------|------|
| E2E 里的 AS | `ResipRuntimeListener` 或产品进程壳，**`accept_all_invites=False`**，规则来自 `demo_rules()` 或 bundle |
| 负载发生器 | `as_load` 可以（它是客户端）；**对端 UAS 用 `PeerUas` / 仿真被叫**，不用 `load_uas_runtime.py` |
| 仿真 S-CSCF/S-SBC | `as_simulators` 或 kind `ims-sim`；标注「非运营商」 |

---

## 5. 建议文件布局（实现时）

```text
testbed/simulators/tests/test_product_path.py   # 可保留 integration；或改为 e2e
testbed/e2e/test_sip_first_edition.py           # Wave 1 新文件（推荐，避免 integration 语义混淆）
```

CI（Wave 1 落地后）：

- job `e2e`：`needs: [native-contract]` 或自带 `m2-platform-resip-build`；  
- `AS_REQUIRE_NATIVE_EXTENSIONS=1 uv run pytest -m e2e -q`；  
- 去掉 `continue-on-error` **仅当** Wave 1 在 `ubuntu-latest` 稳定（OpenSSL 3 与本地缓存路径需在实现时验证）。

---

## 6. 待你 review 的决定

1. Wave 1 是否 **直接改** `test_product_path` 的 marker 为 `e2e`（少文件）还是 **新文件复制断言**（integration 仍给开发者本地快跑）？  
2. 缺 native 时 e2e 是 **fail** 还是 **skip**？（建议与 `native-contract` 一致：**fail**。）  
3. Wave 2 的 14 条对拍是 **本迭代必须** 还是 **单开 issue**？  
4. kind e2e 是否 **永不**进 PR required checks？

---

## 7. 验收（计划本身）

- [ ] 维护者确认 §1 定义与 §6 四项决定  
- [ ] Wave 1 用例进 `master` 且 CI ③ 行为与决定一致  
- [ ] `test-plan.md` REQ-F-1 勾选状态与 Wave 2 是否做完一致（未做完不打勾全文）
