# REQ-S-2 现场证据（待维护者环境采证）

> **状态**：待采证。本目录当前无证据文件，占位说明而已。
> 需求：`docs/acceptance/test-plan.md` §3 REQ-S-2；记录：`docs/acceptance/m8-environment-evidence.md` D-1。

## 采证时应提交的文件（脱敏）

1. `README.md`（本文件更新为采证记录）：采证日期、环境（运营商 PKI lab 名称打码）、执行人、被测版本 tag、runbook 版本。
2. `tls-handshake.transcript.md`：AS→S-SBC TLS 建链命令 transcript（目标地址/端口打码），结论为建链成功。
3. `plaintext-rejected.transcript.md`：明文 5060 连接被拒绝的命令 transcript（失败摘录）。
4. `pki-chain.txt`：`openssl verify -CAfile <打码路径>` 结论摘录 + `openssl x509 -noout -subject -issuer -dates`
   元数据输出（序列号/指纹打码或截断，不贴证书明文）。

## 禁止提交

**不得提交密钥、证书明文、真实抓包**（`*.key` / `*.pem` 真实内容 / `*.pcap` / `*.pcapng` /
含口令或真实号码的日志）。违例文件会被 `.gitignore` 拦截或须在评审中直接拒绝入库。
