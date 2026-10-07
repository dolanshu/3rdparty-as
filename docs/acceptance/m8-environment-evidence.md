# M8 环境证据记录（Phase D）

> **日期**：2026-10-06
> **依据**：`docs/handoff/2026-10-06-m8-release-candidate-plan.md` §4 Phase D + §3 退出条件第 3–4 项；
> 签收矩阵 `docs/acceptance/m8-test-plan-matrix.md` 中 S-2 / S-3 / NF-1 blocked 行。
> **原则**：维护者缺席期间不编造运营商 / 客户现场证据。本文件只记录**可验证现状 + 缺口 + defer 结论**，
> 不替代维护者签字与 M8 退出评审（`docs/reviews/m8-exit-review-*.md`）。中文编写。
> **脱敏红线**（AGENT §11 / §13）：不得提交私钥、证书明文、真实抓包（pcap/pcapng）、含密钥的日志；
> 证据目录约定见 §0。

## §0 证据目录与脱敏约定

- 证据根目录：`docs/acceptance/artifacts/m8/<date>/`（`<date>` 为采证日期，形如 `2026-10-06`）。
- 按条目分子目录：`req-s-2-pki/`（REQ-S-2）、`req-s-3-rotation/`（REQ-S-3）、`req-nf-1-live/`（REQ-NF-1）。
- 每个子目录必须含 `README.md`（说明采证时间、环境、执行人、版本 tag）+ 脱敏命令 transcript + 脱敏日志摘录。
- 允许提交：命令 transcript（密钥/指纹打码）、版本号 / 镜像 tag、`openssl x509 -noout -subject -issuer -dates` 类元数据输出（序列号/指纹打码或截断）。
- **禁止提交**：`*.key` / `*.pem` 私钥、完整证书明文、`*.pcap` / `*.pcapng` 真实抓包、含口令/ token 的日志。
  `.gitignore` 中 `*.log` / `*.pcap` / `*.pcapng` / `artifacts/` 规则继续有效；
  `!docs/acceptance/artifacts/` 例外已使本目录可被追踪（见 `docs/acceptance/artifacts/m8/README.md`），
  密钥类扩展名仍被忽略，属预期行为。
- Runbook 引用：`docs/acceptance/m4b-8-runbook.md`（dev HTTPS / 浏览器证据方法）、
  `docs/acceptance/m8-native-consistency-runbook.md`（签收前 native 一致性）、
  `docs/acceptance/m5-state-stores-runbook.md`（state stores 现场步骤参考）。
  现场采证时由维护者指定本次适用的 runbook 版本并在子目录 README 中注明。

## D-1 运营商 PKI / 外网 S-SBC（REQ-S-2 / REQ-S-3 尾项）

- **需求链接**：`docs/acceptance/test-plan.md` §3 REQ-S-2（AS↔S-SBC 全 TLS、明文 5060 拒绝、运营商 PKI 签发链验证通过）、
  REQ-S-3（新旧证书并存窗口呼叫不受影响、新连接用新证书）；矩阵 `m8-test-plan-matrix.md` §3 S-2 / S-3 行（均为 `blocked`）。
- **应有证据形状**（维护者环境采证时补）：
  - `req-s-2-pki/`：运营商 PKI 签发链信息（`openssl verify -CAfile <打码路径>` 结论摘录，不贴证书明文）、
    AS→S-SBC TLS 建链命令 transcript（目标地址/端口打码）、明文 5060 被拒绝的命令 transcript（`openssl s_client` / SIP 客户端连接失败摘录）、版本 tag。
  - `req-s-3-rotation/`：轮换窗口起止时间、新旧证书并存证明（元数据命令输出，打码）、轮换期间存量呼叫保持 + 新建连接用新证书的观察记录（脱敏日志摘录）、版本 tag。
- **当前状态（2026-10-06 本环境实测）**：本环境**无运营商 PKI lab、无外网 S-SBC 对端**，无法执行上述采证。
  本地仅有工程侧 TLS 集成测试在 `make gate` 内通过（属工程切片，**不是** REQ-S-2/S-3 现场验收）。
  未执行、未见证任何运营商签发链验证与明文拒绝 live 证明——如实记录为缺口，不补编造数据。
- **结论：明确 defer**（plan §4 Phase D taxonomy：通过 / 有条件通过 / 明确 defer）。
  - defer 内容：运营商 PKI lab + 外网 S-SBC / mTLS 联调 run 由维护者排期；在 M8 窗口内未完成。
  - 影响：REQ-S-2 / REQ-S-3 尾项在签收矩阵中**继续保持 blocked**；M8 不得宣称 S-2/S-3 全绿。
  - 后续：维护者排期后按本文件 §0 约定在 `docs/acceptance/artifacts/m8/<date>/req-s-{2,3}*/` 落脱敏证据，
    或在 M8 总审中书面接受风险并写入 `docs/plan.md` §5 对应行 / ADR。

## D-2 客户 K8s REQ-NF-1 live 基线（kill / restart / BYE）

- **需求链接**：`docs/acceptance/test-plan.md` §2 REQ-NF-1（kill 重启状态不丢：基本呼叫 ACK 建 dialog 后 kill/重启，
  BYE 对拍、Redis 状态恢复）；`docs/plan.md` §5.2 D10（"REQ-NF-1 验收 checkbox 仍 M8 维护者（K8s live baseline）"）；
  矩阵 `m8-test-plan-matrix.md` §2 REQ-NF-1 行（`blocked`，live 证据归 Phase D D-2）。
- **应有证据形状**（客户 K8s 采证时补）：
  - `req-nf-1-live/`：集群与版本信息（K8s 版本、镜像 tag、Helm values 版本）、kill/restart 命令 transcript
    （`kubectl delete pod / rollout restart` 对象名打码）、重启前后 dialog 状态对比（脱敏日志摘录，Call-ID 打码或截断）、
    BYE 对拍结论、版本 tag。引用 runbook（见 §0）。
- **当前状态（2026-10-06 本环境实测）**：本环境**无客户 K8s 集群**，未执行 live kill/restart/BYE 基线。
  工程侧仅有 M7 D10 切片证据（**工程 harness，非 live 验收**）：
  - `platform/tests/test_d10_product_recovery_integration.py`（M7.6 产品集成切片）
  - `platform/tests/test_d10_req_nf1_harness_integration.py`（M7.7 进程壳 + REQ-NF-1 工程 harness）
  - `platform/tests/test_d10_req_nf1_redis_integration.py`、`platform/tests/test_d10_process_restart_integration.py`
  - 矩阵头注：`test_d10_product_recovery_integration.py → 1 passed`（ACK-established-dialog 工程切片）。
  以上均不构成 REQ-NF-1 live 签收——如实区分，不冒充。
- **结论：明确 defer**。
  - defer 内容：客户 K8s live kill/restart/BYE 基线待维护者协调客户环境后采证；在 M8 窗口内未完成。
  - 影响：REQ-NF-1 在签收矩阵中**继续保持 blocked**；M8 不得宣称 NF-1 通过。
  - 后续：采证后按 §0 约定落 `docs/acceptance/artifacts/m8/<date>/req-nf-1-live/` 脱敏证据，
    或在 M8 总审中有条件通过并列出 defer 清单（须维护者授权）。

## D-3 D6 testbed 是否 v1 客户验收（维护者裁决 pending）

- **需求链接**：`docs/plan.md` §5.2 D6（"testbed 是否必须在 v1 支持客户验收测试；架构文档把它推迟到 v1.1"）；
  矩阵 `m8-test-plan-matrix.md` 条件行 `D6-testbed验收`（`blocked`，归 Phase D D-3）。
- **应有证据形状**：维护者裁决记录（v1 纳入 vs v1.1；若纳入则补客户验收用例与证据目录，若不纳入则关闭本项）。
- **当前状态**：维护者缺席，**无裁决**。本文件不代裁决，仅记录建议。
- **结论：维护者裁决 pending；建议 v1.1**（除非客户明确要求 v1 验收）。
  - 理由：架构既有推迟到 v1.1 的基线；M8 窗口内无客户验收输入，纳入 v1 只会新增 open 项而不增加可验证证据。
  - 后续二选一（须维护者书面确认）：(a) 接受建议 → D-3 关闭，D6 行按 v1.1 处理（矩阵 `D6-testbed验收` 转终态，附理由）；
    (b) 客户要求 v1 → D-3 转为采证任务，证据落 `docs/acceptance/artifacts/m8/<date>/` 并补 ADR 或 `plan.md` §5 行。
  - 在裁决前：D6 在矩阵中**继续保持 blocked**；M8 总审前须有终态（关闭或采证计划），不得以 open 状态签字。

## 与 M8 退出的关系

- D-1、D-2 为**明确 defer**：对应 REQ-S-2 / REQ-S-3 / REQ-NF-1 在矩阵中保持 `blocked`；
  按 RC 计划 §3 第 3 项，M8 签字时须在总审中列出 defer 清单（须维护者授权），**不得宣称 M8 全绿**。
- D-3 为**裁决 pending**：须维护者在 M8 总审前给出 v1/v1.1 结论；本文件建议 v1.1 仅供参考，不生效力。
- 本文件创建的 `docs/acceptance/artifacts/m8/` 占位 README 均为"待采证"状态，不含任何伪造证据。
