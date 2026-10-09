# Handoff — SIP native testing gate补齐计划 (2026-10-09)

> **Purpose:** 下一 session 执行：真栈（`_resip_runtime`）测试分层、CI 守门、E1/S1 harness 修复。  
> **Not:** 本文件本身不签收 REQ / 里程碑；维护者 commit / push 自行完成。  
> **Prerequisite:** `cur` 分支已删除（内容在 `master` `c2d56e4` 及之后）；`callload` 已删。

---

## 0. 现状摘要（为何要做）

| 事实 | 说明 |
|------|------|
| 产品 SIP | C++ **reSIProcate** → Python 模块 **`_resip_runtime`**（`make m2-platform-resip-build`） |
| `make gate` | `pytest -m "unit or contract"` ≈1012 条；**绝大多数不经过真栈** |
| E1 真栈烟测 | `test_e1_contract_resip_runtime*.py` 共 **7** 条（有 `.so` 才跑；无则 **skip**） |
| CI `fast` job | **不**编 native → E1 **全 skip**，merge 门禁**未验** UDP/TLS 产品栈 |
| 本机有 `.so` 时 | **2 failed**：S1 + `accept_all_invites` + SDP → 期望 **200**，实际 **400**（harness 应答 SDP / `minimalHarnessAnswer`） |
| 原则 | **凡 SIP flow 行为验收，应走真栈**；7 条 smoke **不够**（见 `docs/acceptance/test-plan.md` REQ-F-*） |

**失败用例（先修）：**

- `platform/tests/test_e1_contract_resip_runtime.py::test_e1_s1_accept_all_harness_returns_200`
- `platform/tests/test_e1_contract_resip_runtime_full.py::test_e1_s1_accept_all_from_contract_invite`

**根因（已定位）：** `platform/native/resip_runtime/runtime_module.cxx` 中 `acceptHarnessSession` / `minimalHarnessAnswer` 生成的应答 SDP 在 `provideAnswer` → `accept(200)` 时被 reSIProcate 拒绝（Parse 失败或 “Can't provide an answer”）。**不是** ims-sim 模拟器问题。

**同路径集成测（修好后应一并绿）：**

- `platform/tests/test_resip_runtime_integration.py::test_accept_all_invites_harness_mode_returns_200`（`integration` 标记，不在默认 gate）

---

## 1. Phase A — 修复 S1 harness（下一 session 第一步）

### A.1 调查

1. 读 `runtime_module.cxx`：`minimalHarnessAnswer`、`acceptHarnessSession`、`onOffer` / `onOfferRequired`。
2. 对比 reSIProcate 对 `SdpContents` / `HeaderFieldValue` 的构造方式（是否需 `\n` vs `\r\n`、是否应 `session->provideAnswer` 用 offer 派生而非手写）。
3. 本地复现：

```bash
make m2-platform-resip-build
uv run pytest platform/tests/test_e1_contract_resip_runtime.py::test_e1_s1_accept_all_harness_returns_200 -vv
# 或打印 400 body（见会话记录：ParseBuffer expected 'v'）
```

### A.2 实现

- 修 C++ harness 应答生成，使带 SDP 的 INVITE 在 `accept_all_invites=True` 下稳定 **200**。
- 保持 **生产路径**不变：`accept_all_invites` 仅 testbed（`ResipRuntimeListener` 文档已说明）。
- 重编：

```bash
make m2-platform-resip-build
```

### A.3 验证（Phase A 完成标准）

```bash
uv run pytest \
  platform/tests/test_e1_contract_resip_runtime.py::test_e1_s1_accept_all_harness_returns_200 \
  platform/tests/test_e1_contract_resip_runtime_full.py::test_e1_s1_accept_all_from_contract_invite \
  platform/tests/test_resip_runtime_integration.py::test_accept_all_invites_harness_mode_returns_200 \
  -q
```

再跑完整 E1 契约文件（确保 S2/S3/S4 未回退）：

```bash
uv run pytest platform/tests/test_e1_contract_resip_runtime.py platform/tests/test_e1_contract_resip_runtime_full.py -m contract -q
```

最后：

```bash
make gate   # 本机已编扩展时应 0 failed（E1 相关）
```

### A.4 可选文档

- 在 `platform/native/resip_runtime/README.md` 或 `platform/src/as_platform/sip/README.md` 加一句：`accept_all_invites` 与 S1 harness 的边界。

---

## 2. Phase B — 本地「真栈门禁」命令（短平快）

在 CI 改完前，维护者本地约定：

```bash
make m2-platform-resip-build
AS_REQUIRE_NATIVE_EXTENSIONS=1 make gate
# 或显式：
AS_REQUIRE_NATIVE_EXTENSIONS=1 uv run pytest -m "unit or contract" -q
```

`AS_REQUIRE_NATIVE_EXTENSIONS=1` 时，缺扩展 **fail** 而非 skip（`platform/tests/native_extensions.py`）。

**Makefile 可选增强（下一 session）：**

- 增加 `make gate-native`：`AS_REQUIRE_NATIVE_EXTENSIONS=1` + 依赖 `m2-platform-resip-build`（或检测 `.so` 存在）。
- 将未提交的 `Makefile` **UV / `.local/bin` 解析** 与 `repo-toolchain` 改动 **commit 到 master**（当前工作区可能仍有未提交 diff）。

---

## 3. Phase C — CI 编扩展并阻塞 merge

参考：`docs/handoff/2026-10-07-m8-next-step-plan.md`（规划了 `m2-platform-resip` job）、`docs/reviews/callload-m2-m6-m7-demo-branch-review-2026-10-05.md` **F9**。

### C.1 新 job 或扩展现有 job（建议）

| Step | 内容 |
|------|------|
| 依赖 | `ubuntu-latest` + apt：`build-essential` `cmake` `libssl-dev` 等（对齐 `docs/acceptance/m2-native-build-matrix.md`） |
| Build | `make m2-native-restore`（若需要）+ `make m2-platform-resip-build` |
| Test | `AS_REQUIRE_NATIVE_EXTENSIONS=1 uv run pytest -m "unit or contract" -q` |
| 可选 | 同 job 跑 `pytest -m integration` 中与 `_resip_runtime` 相关的子集（见 §4 矩阵） |

### C.2 与现有 `fast` 的关系

- **方案 1（推荐）：** `fast` 保持无 native（快）；**新增 required** `native-contract` job。
- **方案 2：** `fast` 内增加 native build（变慢，单 job 简单）。

### C.3 验收

- PR 上 native job **红则不可 merge**。
- 故意破坏 `minimalHarnessAnswer` 时 job 必须失败。

---

## 4. Phase D — 覆盖率矩阵（相对 `sip-baseline` / test-plan）

**目标：** 从「7 条 E1 smoke」扩展到与 `docs/acceptance/test-plan.md` 对齐的**分阶段**真栈回放。

| 契约目录 | REQ / 含义 | 当前自动化（真栈） | 目标 |
|----------|------------|-------------------|------|
| S1-basic-call | REQ-F-1…F-5 基础 | E1：S1 harness 200（**红**）；无 14 条全文回放 | Phase A 修 harness；**D1** 增加 14 消息回放或 derived + 真栈 |
| S2-no-match-404 | REQ-F-6 | E1 **绿**（有 .so） | 保持；CI 必跑 |
| S3-policy-reject-603 | REQ-F-7 | E1 **绿** | 保持 |
| S4-caller-cancel | REQ-F-8 等 | E1 full **487 绿** | 保持 |
| S5–S11 | F-2/F-4/路由等 | 部分 **integration** / 未覆盖 | **D2** 按优先级加 `test_e1_*` 或 integration |

**`make gate` 外的真栈用例（应在 Phase C/D 纳入 CI integration 或 native job）：**

| 文件 | 标记 | 约条数 |
|------|------|--------|
| `test_resip_runtime_integration.py` | integration | 3 |
| `test_resip_runtime_tcp_integration.py` | integration | 1 |
| `test_resip_runtime_tls_integration.py` | integration | 3 |
| `test_resip_runtime_tls_policy_integration.py` | integration | 2 |
| `test_m7_forward_two_leg_integration.py` | integration | 1 |
| `test_resip_two_leg_integration.py` | integration | 1 |
| `test_req_f4_sdp_identity_integration.py` | integration | 3 |
| `test_req_s3_overlap_integration.py` | integration | 1 |
| D10 `test_d10_*_integration.py` | integration | 若干 |
| `testbed/simulators/tests/test_product_path.py` | integration | 4 |

**非真栈（勿与 SIP flow 混淆）：** `test_resip_runtime_log_contract.py`（日志解析）、`test_resip_runtime_call_controller.py`（unit）。

---

## 5. Phase E — M2 smoke 与 demo 边界（证据层）

真栈但不替代契约全集：

```bash
make m2-native-smoke
make m2-native-smoke-tcp-runtime
make m2-native-smoke-tls-runtime
```

Demo / kind：`docs/handoff/pre-m8-demo-review-plan.md`（`as-m71`）— 人工 + 脚本证据，**不**并入 `make gate`，但发布前应跑 story A/B。

---

## 6. 建议执行顺序（给下一 session）

1. **Phase A** — 修 `minimalHarnessAnswer` / harness 200，三条 pytest 绿。  
2. **Commit** — C++ + 任何 Python/文档；未提交的 `Makefile`（UV）、`publish_m71_bundle.py`（ruff）一并整理。  
3. **Phase B** — 本地 `AS_REQUIRE_NATIVE_EXTENSIONS=1 make gate` 习惯化；可选 `make gate-native`。  
4. **Phase C** — `.github/workflows/ci.yml` 增加 native required job。  
5. **Phase D** — 按矩阵逐场景加测试（先 S1 14 条或子集，再 S5/S7/S8…）。  
6. **Phase E** — 里程碑/demo 前跑 M2 smoke + demo reset 检查。

---

## 7. 相关路径

| 项 | 路径 |
|----|------|
| 原生模块 | `platform/native/resip_runtime/` |
| Python 缝 | `platform/src/as_platform/sip/resip_runtime.py` |
| E1 测试 | `platform/tests/test_e1_contract_resip_runtime*.py` |
| 契约消息 | `testbed/contracts/sip-baseline/` |
| 扩展 skip/fail | `platform/tests/native_extensions.py` |
| 评审 F9 | `docs/reviews/callload-m2-m6-m7-demo-branch-review-2026-10-05.md` |
| M7 E1 签收范围 | `docs/reviews/m7-e1-contract-review-2026-10-05.md`（未含 S1 harness 200） |

---

## 8. `cur` / `callload` 清理（已完成 2026-10-09）

- **`origin/callload`** — 已删。  
- **`cur` / `origin/cur`** — 已删；M5.1 与 toolchain 在 **`master`**（含 `c2d56e4` 等）。  
- 克隆若仍见本地 `cur`：`git fetch --prune && git branch -D cur`。

---

## Sign-off（本计划）

- [ ] Phase A 完成（3 条 S1/harness pytest 绿）  
- [ ] Phase C CI job 绿且 required  
- [ ] Phase D 至少 S1 全链或明确推迟项写入 `test-plan.md` / `plan.md`
