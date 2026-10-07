# REQ-S-3 现场证据（restriction：Close 前不采证）

> **状态**：restriction（2026-10-07）。Close 前不做真实对端上的运营商证书轮换采证。本目录保持空白。
> 需求：`docs/acceptance/test-plan.md` §3 REQ-S-3；记录：`docs/acceptance/m8-environment-evidence.md` D-1。

## 采证时应提交的文件（脱敏）

1. `README.md`（本文件更新为采证记录）：轮换窗口起止时间、环境、执行人、被测版本 tag、新旧证书元数据对照。
2. `rotation-window.txt`：新旧证书并存证明（`openssl x509 -noout -subject -issuer -dates` 元数据输出，打码）。
3. `calls-unaffected.log.redacted.md`：轮换期间存量呼叫不受影响的观察记录（脱敏日志摘录，Call-ID 打码或截断）。
4. `new-connections.txt`：轮换期间新建 TLS 连接使用新证书的验证摘录（命令 transcript，打码）。

## 禁止提交

**不得提交密钥、证书明文、真实抓包**（`*.key` / `*.pem` 真实内容 / `*.pcap` / `*.pcapng` /
含口令或真实号码的日志）。违例文件会被 `.gitignore` 拦截或须在评审中直接拒绝入库。
