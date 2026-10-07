# M8 环境证据目录（脱敏约定）

> 依据：`docs/handoff/2026-10-06-m8-release-candidate-plan.md` §4 Phase D；
> 记录载体：`docs/acceptance/m8-environment-evidence.md`。

## 目录结构

```text
docs/acceptance/artifacts/m8/
  README.md                # 本文件（约定说明）
  <date>/                  # 采证日期目录，形如 2026-10-06（维护者现场采证时创建）
    req-s-2-pki/           # REQ-S-2：运营商 PKI / S-SBC TLS
    req-s-3-rotation/      # REQ-S-3：证书轮换无损
    req-nf-1-live/         # REQ-NF-1：客户 K8s live kill/restart/BYE
```

占位子目录（`req-s-2-pki/`、`req-s-3-rotation/`、`req-nf-1-live/`，与本 README 同级）
内各有一份 `README.md`，当前状态均为**待维护者环境采证**，不含任何证据伪造。

## `.gitignore` 说明（本次已检查，无需修改）

- 本仓库 `.gitignore` 含 `artifacts/` 但同时含例外 `!docs/acceptance/artifacts/`，
  因此 `docs/acceptance/artifacts/m8/` **可被追踪**（已用 `git check-ignore` 验证：无忽略命中）。
- 密钥类扩展名（`*.log` / `*.pcap` / `*.pcapng` 等）仍被忽略，属**预期行为**：
  M8 要求"可评审的脱敏证据"，真实抓包与密钥本来就不应入库。
- 结论：本次**不修改** `.gitignore`；若未来需要收紧（例如新增 `*.key` 全局忽略），
  须另行评估，避免误伤 `deploy/**/certs/.gitkeep` 等占位文件。

## 脱敏红线（重申）

- **不得提交**：私钥（`*.key`）、证书明文（`*.pem` / `*.crt` 真实内容）、
  真实抓包（`*.pcap` / `*.pcapng`）、含口令 / token / 真实号码的日志。
- 允许提交：命令 transcript（敏感字段打码）、`openssl x509 -noout -subject -issuer -dates`
  类元数据输出（序列号/指纹打码或截断）、版本号与镜像 tag。
