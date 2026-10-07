# REQ-NF-1 live 现场证据（待维护者环境采证）

> **状态**：待采证。本目录当前无证据文件，占位说明而已。
> 需求：`docs/acceptance/test-plan.md` §2 REQ-NF-1；`docs/plan.md` §5.2 D10；
> 记录：`docs/acceptance/m8-environment-evidence.md` D-2。
> 工程 harness（非 live 验收）见 `platform/tests/test_d10_product_recovery_integration.py`、
> `platform/tests/test_d10_req_nf1_harness_integration.py` 等 M7 D10 切片。

## 采证时应提交的文件（脱敏）

1. `README.md`（本文件更新为采证记录）：集群信息（版本、节点数）、镜像 tag、Helm values 版本、
   kill/restart 时间线、执行人、引用 runbook 版本。
2. `kill-restart.transcript.md`：`kubectl delete pod / rollout restart` 命令 transcript（对象名打码）。
3. `dialog-recovery.redacted.md`：重启前后 dialog 状态对比（脱敏日志摘录，Call-ID 打码或截断）。
4. `bye-verdict.txt`：BYE 对拍结论（双腿挂断行为符合预期的文字结论 + 脱敏摘录）。

## 禁止提交

**不得提交密钥、证书明文、真实抓包**（`*.key` / `*.pem` 真实内容 / `*.pcap` / `*.pcapng` /
含口令或真实号码/ Call-ID 明文全量的日志）。违例文件会被 `.gitignore` 拦截或须在评审中直接拒绝入库。
