# callload → master 合并准备（2026-10-06）

> **状态（2026-10-06）**：**已合入** — `master` @ `764aa75`（工程 fast-forward `4b4566b`）；见 §6 执行记录。  
> **范围**：维护者将 `callload` 工程切片合入 `master` 前的检查清单与口径（历史记录保留）。  
> **依据**：[`2026-10-05-callload-review-response-plan.md`](2026-10-05-callload-review-response-plan.md)、[`callload-remediation-adjudication-2026-10-05.md`](../reviews/callload-remediation-adjudication-2026-10-05.md)、[`cross-milestone-final-adjudication-2026-10-05.md`](../reviews/cross-milestone-final-adjudication-2026-10-05.md)。

---

## 6. 执行记录（2026-10-06）

| 步骤 | 结果 |
|------|------|
| `923a8c1` on `callload` | CI + merge handoff docs |
| `merge master` → `callload` | 拉入 `m5-full-chain-review-2026-10-05.md` |
| `make gate` on `callload` | 964 passed, 2 skipped |
| `merge callload` → `master` | **fast-forward** → `4b4566b` |
| 收尾 `764aa75` | CI 仅 `master` 触发 + 合入记录文档 |
| `origin` push | **未执行** — 维护者按需 `git push origin master` |

## 6b. 维护者签收（可选补签）

| 项 | 维护者 | 日期 | 备注 |
|----|--------|------|------|
| 批准 callload → master | 维护者 chat | 2026-10-06 | |
| 合入后 master SHA | `4b4566b` | 2026-10-06 | 含 merge `master` into `callload` |
| F10 口径已读 | | | 故事 C L1 |

---

## 1. 分支事实（authoring 时）

| 项 | 值 |
|---|---|
| `callload` HEAD | `dc3c951`（`fix`） |
| `master` HEAD | `04afc5a`（`M5 review`） |
| merge-base | `2318f9c` |
| `callload` 独有提交 | 7 个（含 `6778030`…`dc3c951`；见 `git log master..callload`） |
| `master` 独有提交 | **1 个**：`04afc5a` — 新增 [`m5-full-chain-review-2026-10-05.md`](../reviews/m5-full-chain-review-2026-10-05.md)（结论「不通过」） |
| 工作区未提交 | `.github/workflows/ci.yml`、`.gitignore`（见 §2.1） |

**合入方向**：维护者批准后将 `callload` 合并进 `master`（推荐先 `merge master` 进 `callload` 解决分歧，再 fast-forward 或 merge commit 进 `master`）。

---

## 2. 合并前硬门禁

### 2.1 工作区必须先入库

评审 **F9** 与 [`CHANGELOG.md`](../../CHANGELOG.md) 已描述 native CI job，但 **HEAD 上 `.github/workflows/ci.yml` 仍为仅 `master` 触发的旧 workflow**。当前 diff 含：

- `push`/`pull_request` 分支：`master, cur, callload`（合并后应 **收窄为 `master`**，见 §3.3）
- `fast` job：`chart-check`、`alert-check`（M5-0c）
- 新 job：`m2-native-smoke`、`m2-platform-resip`、`m7-recovery`、`m7-two-leg`

**合并前**：在 `callload` 上单独 commit 上述 CI + `.gitignore`（`.cache/`、`!docs/acceptance/artifacts/`），本地或 origin 上跑绿 **至少** `fast` + `m2-platform-resip`（耗时可接受则加 `m7-*`）。

### 2.2 本地验证（维护者）

```bash
make gate
make m2-native-restore m2-native-build m2-platform-resip-build
uv run pytest platform/tests/test_e1_contract_resip_runtime.py \
  platform/tests/test_e1_contract_resip_runtime_full.py -m contract -q
# 可选：m7-platform-recovery-build / two-leg-build + 对应 integration
```

### 2.3 与 `04afc5a` 的内容对账（F10，非阻塞 git）

- 合入后仓库 **同时** 持有 M5 全链「不通过」评审与 Pre-M8 **故事 C L1 话术**（[`pre-m8-demo-review-plan.md`](pre-m8-demo-review-plan.md) F10 段）。
- **不得**因 merge 改变对外口径：故事 C 仍仅 chart/告警 **形态** + kind 摘要，不宣称 M5 全链已验收。
- `cur` 上 M5.1 Remediation 闭合后，再更新 pre-m8 F10 段（与合并无关）。

### 2.4 已知开放项（不挡工程合入，挡里程碑/REQ 签收）

| ID | 状态 | 合并后跟踪 |
|----|------|------------|
| F8 | 未闭合 | M8 前结构化日志 |
| F6 | 部分修复 | native transport close 回调 |
| F11 | 维护者 | 历史 commit 形态，不重组 |
| M2/M6/M7 **里程碑退出** | 未签收 | [`plan.md`](../plan.md) §4 |
| REQ-NF-1 / 全 E1 / O1 发布 | 未验收 | M8 |

---

## 3. 建议维护者操作顺序

1. **拍板**：显式批准「`callload` → `master`」（AGENT.md §11）。
2. **Commit** §2.1 工作区；必要时 rebase/merge 前再跑 §2.2。
3. **`git checkout callload && git merge master`**（拉入 `04afc5a`）；冲突时以 **保留两边 review 文档**、代码以 callload 工程切片为准 为原则。
4. **CI 绿** 后 `git checkout master && git merge callload`（或 PR + squash，由维护者定）。
5. **§3.3 收尾 commit**：CI `on.push.branches` / `pull_request.branches` 改回 **`[master]`**  only（`callload` 分支可保留只读或删除，不在本文指派）。
6. 更新 [`plan.md`](../plan.md) §0「当前进行中的步骤」— 标记 callload 已合入；下一入口 **M8**。
7. 可选：在 [`callload-remediation-adjudication-2026-10-05.md`](../reviews/callload-remediation-adjudication-2026-10-05.md) 追加「合入 master @ `<sha>` `<date>`」一行。

---

## 4. 合入后声明（对外 / 对内）

### 4.1 合入 **等于**

- `master` 含 M2 后半 native 产品 runtime、M6 harness + O1 dev-host 报告链、M7 E1/FORWARD/D10 工程切片、Pre-M8 demo 脚本与评审修复（F1–F7、F9–F18 等，见 adjudication）。
- 仓库根 `make m2-native` / `make m2-platform-resip-build` 与 blocking native CI job（F9 落地后）成为 **主干默认** 工程路径。

### 4.2 合入 **不等于**

- M2 / M6 / M7 **维护者里程碑签收**
- M5 全链或 M5.1 **验收通过**
- REQ-S-2/3、REQ-NF-1、对外 O1/SLA、客户 NF-1 正式签收
- Pre-M8 **全量**客户 Demo（故事 C 全量运维叙事仍受 F10 约束）

---

## 5. 关联文档

| 文档 | 角色 |
|------|------|
| [`callload-m2-m6-m7-demo-branch-review-2026-10-05.md`](../reviews/callload-m2-m6-m7-demo-branch-review-2026-10-05.md) | 分支评审原文 + Adjudication 表 |
| [`2026-10-05-callload-review-response-plan.md`](2026-10-05-callload-review-response-plan.md) | P0/P1/P2 处置与跟踪表 |
| [`2026-10-05-milestones-engineering-complete.md`](2026-10-05-milestones-engineering-complete.md) | M2/M6/M7 工程 inventory |
| [`pre-m8-demo-review-plan.md`](pre-m8-demo-review-plan.md) | 客户 Demo 边界（含 F10） |

---

## 6. 维护者签收（历史模板；执行见文首 §6 执行记录）

| 项 | 维护者 | 日期 | 备注 |
|----|--------|------|------|
| 批准 callload → master | | | |
| CI + §2.2 已绿 | | | |
| 合入后 master SHA | | | |
| F10 口径已读 | | | 故事 C L1 |
