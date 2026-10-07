# M8 下一步（2026-10-07）

> **状态**：**仍搁置（2026-10-07）**。M7.1 已工程关门。剩下的搁置条件是 Close 前不做真实运营商 S-SBC / 客户 K8s 测试，见 [`acceptance/m8-environment-evidence.md`](../acceptance/m8-environment-evidence.md)。搁置期间不执行 N1–N4，不填 M8 总审确认栏。重开之前，发布镜像再带上 SIP 监听。  
> **上游**：[`2026-10-06-m8-release-candidate-plan.md`](2026-10-06-m8-release-candidate-plan.md)（阶段 A–E 的总计划，本文不重开）  
> **事实**：`master` / `origin/master` @ `20e3d07`（`M8 part 1`）。工作区唯一未提交文件是 `.github/workflows/ci.yml`。

本文只排 **落地已有产物** 和 **不依赖实验室的维护者裁决**。M8 退出签字、tag、现场采证不在本步。

---

## 1. 现在在哪

| 已在 `20e3d07` | 仍在工作区 |
|---|---|
| F8 字段契约 + 契约测试 + `emit_native_log_event` JSON 富化 | F9：`.github/workflows/ci.yml`（blocking native / chart-check / gate-strict / m7 recovery / m7 two-leg；`performance` 改为阻塞） |
| F6：指纹表淘汰处的 ADR 注释（行为未改） | |
| 最小 M5.1：Helm H-1…H-4 fail-closed、`chart-check` onprem 与退出码断言、kind 脚本 K-1/K-2 | |
| `make gate-strict`、`scripts/ci/check_adr_annotations.py` | |
| 签收矩阵、环境证据、M5 REQ 复评、M8 退出评审、Phase A F6/F8 记录、`report.md` §0 | |

F9 上次推 origin 时因 PAT 无 `workflow` scope 被拒，合入时故意拿掉了 workflow。这次同样：**不要把 `ci.yml` 混进其他提交。**

---

## 2. 顺序

### N1 — workflow 单独待推

- 维持 `ci.yml` 为工作区改动，直到维护者持有 `workflow` scope PAT（或等效授权）。
- 届时只提交该文件，推 `master`，确认 origin 上这些 job 为绿且失败即红：`fast`（含 `chart-check`、`gate-strict`）、`m2-platform-resip`、`m2-native-smoke`、`m7-recovery`、`m7-two-leg`；`performance` 在 nightly/tag/手动触发时阻塞。e2e 仍 `continue-on-error`（0 条用例）。
- 在 origin 变绿之前，adjudication 里 F9 保持「部分修复 / 未 push」。不把 F9 写成已修复。

### N2 — 维护者书面裁决（不依赖实验室，不关门）

每一项改 **正本**，引用处跟着改，避免一处已签、backlog 仍写「未闭合」。

| # | 签署的结论 | 正本 | 须同步 |
|---|---|---|---|
| 1 | 进入 M8 的授权补记（2026-10-06 已发生） | RC 计划 §10「批准进入 M8」 | — |
| 2 | B-1 最小 M5.1；B-2 维持 2026-10-04 工程关门并降级为非 REQ 验收；B-3 故事 C 保持 L1 | [`m5-req-acceptance-review-2026-10-06.md`](../reviews/m5-req-acceptance-review-2026-10-06.md) 确认栏 | RC 计划 §10「阶段 B 范围」 |
| 3 | F8 接受「字段契约已落地」；C++ JSON 回调留在 RC 后 | [`m8-phase-a-f6-f8-note-2026-10-06.md`](../reviews/m8-phase-a-f6-f8-note-2026-10-06.md) §5 | [`callload-remediation-adjudication-2026-10-05.md`](../reviews/callload-remediation-adjudication-2026-10-05.md) F8 行（现为「未闭合」） |
| 4 | F6 **接受 documented limitation**（长连接无 dialog 终止时只靠 2048 指纹 LRU 与 4096 连接上限） | 同上 §5 | adjudication F6 行。结论不是「已修复」 |
| 5 | D6 testbed 客户验收放 **v1.1** | [`m8-environment-evidence.md`](../acceptance/m8-environment-evidence.md) D-3 | 矩阵 `D6-testbed验收` 改为 n-a；RC 计划 §10 |
| 6 | NF-3 标 **n-a**（固定容量数字与 AGENT.md §2 冲突；O1 目标仍不发布） | [`m8-test-plan-matrix.md`](../acceptance/m8-test-plan-matrix.md) | — |
| 7 | 确认四项排除：主叫/正则、PM/AM/UM、D1、D10 极端扩展 | 矩阵对应 n-a 行 `signed_by` | D1 在备注里写成已接受风险，或另立迁移项 |
| 8 | M5D-1…M5D-6 **移出 v1** | `plan.md` §5 新行（维护者写） | M5 REQ 复评会签栏。不落这 6 行，M5 REQ 维持不通过 |
| 9 | M1 / M2 / M6 / M7 签 **工程完成** | M1：[`m1-exit-review.md`](../reviews/m1-exit-review.md) 与 `report.md` 历史 §6；M2/M6/M7：各自 2026-10-05 engineering adjudication | [`m8-exit-review-2026-10-06.md`](../reviews/m8-exit-review-2026-10-06.md) §3 引用，不单独充当正本 |

N2 完成后，M5 REQ 级仍是不通过，M8 仍是「RC 就绪、待退出签字」。

### N3 — 矩阵里证据已经对齐的行

N2 之后、N1 之前都可以做。签字备注写「工程证据接受」，不把 test-plan 整句标成全绿。

- 已标 pass 的 9 行：NF-6、NF-8、NF-11、NF-12、KERNEL-§5；G-1/G-2/G-3 注明逐次 PR 仍由维护者审；G-4 注明本地 `make gate` 绿、e2e 仍非阻塞。
- open 里可签的 7 行：F-1、F-2、F-3、F-6、F-7、F-12、F-14。F-12/F-14 范围是被叫+前缀。

### N4 — 停止线

本步结束时下面各项保持原样：

- M8 总审确认栏不填；不打 tag（AGENT.md §10.4）。
- `plan.md` §4 M8 行保持「RC就绪、待维护者退出签字」。
- 这 16 个 open 行不改成 pass：F-4、F-5、F-8、F-9、F-10、F-11、F-16、NF-2、NF-5、NF-9、NF-10、NF-13、NF-14、NF-15、S-1、S-4，以及 D12/O5-HA。F-5 在 Route/Record-Route 补采前明确不签 pass。
- 12 个 blocked 只可写成 defer 或 v1.1，不能写成 pass：F-13、5.4-F-13、F-15、5.4-F-15 真 AS、NF-1、NF-4、NF-7、S-2、S-3、ADR-0008 演练；NF-3 与 D6 若已按 N2 改成 n-a，则从这份 blocked 清单划出。
- D-1（运营商 PKI / 外网 S-SBC，矩阵 S-2/S-3）与 D-2（客户 K8s NF-1 live）本步不采证。这两条单独写成 defer，也不够填 M8 总审确认栏。

---

## 3. 本步之后才发生的事

N1 和 D-1/D-2 都闭合，仍然不能签 M8。确认栏只在下面每一行都已是终态（通过 / n-a / 书面 defer 或 v1.1）之后才填；只要还留着 defer，结论是有条件通过，不是全绿。tag 仅在该栏填写之后由维护者执行（AGENT.md §10.4）。

| 之后的动作 | 它能闭合的行 | 它闭合不了的行 |
|---|---|---|
| N1：origin CI 绿，F9 改为已修复 | F9 | N4 的其余 open / blocked |
| 排期采证，或书面接受 D-1 / D-2 | S-2、S-3、NF-1 | F-4、F-5、F-8、F-9、F-10、F-11、F-13、F-15、F-16、NF-2、NF-4、NF-5、NF-7、NF-9、NF-10、NF-13、NF-14、NF-15、S-1、S-4、D12/O5-HA、ADR-0008 |
| 对其余行逐项补证据，或写成 n-a / defer / v1.1 | 上表右列 | — |

右列里的行在写成终态之前，M8 总审确认栏保持空白，`plan.md` §4 M8 行保持「RC就绪、待维护者退出签字」。
