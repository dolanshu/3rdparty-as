# M4b-8 浏览器验收 Runbook（dev HTTPS 同源栈）

**映射**：[`test-plan.md`](test-plan.md) §1.4「M4b-8 浏览器验收执行程序」步骤 1–5。  
**栈**：[`deploy/compose/README.md`](../../deploy/compose/README.md)（PostgreSQL 12.22 + config-service + Caddy 自签 TLS）。  
**状态**：工程/AI 可执行检查清单；**不**构成 M4b/M4/REQ 验收通过；维护者签字见 [`report.md`](report.md) M4b-8 节（2026-10-04 已记录）。

## 0. 准备

- [ ] WSL2/Linux 上 Docker 可用
- [ ] 完成 compose README 快速开始：`gen-certs` → `postgres` → `migrate` → `bootstrap-admin` → `up` → `smoke-https.sh` 通过
- [ ] 记录环境：git commit、`docker compose images`、`.env` 中**非 secret** 项（勿提交密码/HMAC）
- [ ] 准备第二个账号（approver）：在首个 admin 登录后通过用户管理 API/UI 创建（若 UI 未就绪则用 API）；记录角色分配
- [ ] 7.2d 生产 ingress preflight：本 runbook **不**覆盖；保持 **BLOCKED**（见 test-plan §1.4）

## 1. 步骤 1 — operator 规则 CRUD → 审批请求

**验收意图**：创建/编辑/禁用/删除测试规则；每项提交审批；刷新后 live 状态与队列一致；无 fixture fallback。

| 检查 | 结果 | 备注 |
|---|---|---|
| 以 operator HTTPS 登录 | ☐ PASS / ☐ FAIL / ☑ **BLOCKED** | 栈就绪后可测登录；规则写路径见下 |
| 创建/编辑/禁用/删除规则并提交审批（**被叫 + 前缀**） | ☐ PASS / ☐ FAIL | 裁决已接受；live console 仅暴露被叫+前缀；PG E2E `test_postgres_managed_rule_pipeline_integration.py` |
| 主叫 / 正则规则 | **N/A（v1.1）** | 不纳入 M4；见 [`m4-req-calling-regex-lossless-adjudication-2026-10-03.md`](../reviews/m4-req-calling-regex-lossless-adjudication-2026-10-03.md) |
| 审批队列与 live 表一致 | ☐ PASS / ☐ FAIL | 依赖被叫+前缀规则变更路径 |

**证据**：脱敏截图、Network 中 HTTPS API 调用（无 cookie/token 明文）。

## 2. 步骤 2 — approver 批准/拒绝

**验收意图**：不同 approver；批准有效变更；拒绝须理由；creator 不得自批/自拒；状态与审计一致。

| 检查 | 结果 | 备注 |
|---|---|---|
| approver 登录 | ☐ PASS / ☐ FAIL | 需步骤 0 第二账号 |
| 批准/拒绝既有 ChangeOrder（7.3a 范围） | ☐ PASS / ☐ FAIL | 可针对 DB 中已有 draft/submitted order 验证 submit/approve/reject |
| creator 自批/自拒被拒绝 | ☐ PASS / ☐ FAIL | API 已有回归；浏览器再确认 |
| 空拒绝理由被拒绝 | ☐ PASS / ☐ FAIL | |

**证据**：脱敏截图、order 状态前后对比。

## 3. 步骤 3 — Call-ID live trace

**验收意图**：按已知 Call-ID 查询 live trace，核对 SIP 字段与规则命中。

| 检查 | 结果 | 备注 |
|---|---|---|
| 控制台 trace 查询 | ☑ **BLOCKED** | **REQ-F-13 / M4b-7.4**：M4 关门裁决延期；无 live trace source/API |
| 字段与规则命中核对 | ☑ **BLOCKED** | 同上 |

**证据**：N/A（后端缺失时标注 `BLOCKED: missing backend`）。

## 4. 步骤 4 — 分批 distribution / 健康 / 回滚

**验收意图**：分批通知、版本加载、健康检查；失败批自动回滚；手动回滚。

| 检查 | 结果 | 备注 |
|---|---|---|
| 注册 testbed 实例（health URL） | ☐ PASS / ☐ FAIL | 可用 compose `testbed-health`（`AS_TESTBED_HEALTH_URL`） |
| Operations fleet inventory（实例 CRUD） | ☐ PASS / ☐ FAIL | M4b-7.5 console UI（notify/health URL） |
| Change order 内 start / report / rollback | ☐ PASS / ☐ FAIL | M4b-7.6 modal UI；需 enabled fleet 实例与健康探针 |
| API 级 notify + health probe（7.5 slice） | ☐ PASS / ☐ FAIL | 可用 internal API + curl；非步骤 4 完整浏览器验收 |
| 注入健康失败 → 自动回滚 | ☐ PASS / ☐ FAIL / ☑ **BLOCKED** | 依赖完整 distribution 链路与 AS 栈 |
| 手动回滚 | ☐ PASS / ☐ FAIL / ☑ **BLOCKED** | 同上 |

**证据**：distribution report JSON（脱敏）、health probe 日志。

## 5. 步骤 5 — 审计与 fail-closed

**验收意图**：§3 审计字段；脱敏；append-only；显式写入拒绝；失败路径 fail-closed。

| 检查 | 结果 | 备注 |
|---|---|---|
| 登录/登出/ChangeOrder 操作产生审计 | ☐ PASS / ☐ FAIL | 在步骤 2 可操作范围内验证 |
| 导出/查询 audit 无 password/token | ☐ PASS / ☐ FAIL | |
| runtime 角色拒绝 INSERT/UPDATE/DELETE/TRUNCATE audit | ☐ PASS / ☐ FAIL | 可用 `psql` 以 `as_config_web` + `SET ROLE` 验证 |
| audit unavailable 等 fail-closed | ☐ PASS / ☐ FAIL | 按需注入；谨慎操作 |

**证据**：脱敏 audit 行、psql 拒绝输出。

## 6. 产物归档

将脱敏材料放入维护者指定目录（占位）：

```
artifacts/m4b-8/<YYYY-MM-DD>/
```

在 [`report.md`](report.md) § M4b-8 填写路径、commit、阻塞项摘要；维护者签字已记录（2026-10-04）。

## 7. Playwright 自动化（可选）

```sh
cd deploy/compose
export M4B8_E2E_PASSWORD='<12+ chars, dev-only>'   # 脚本会用 owner DSN 同步 admin / ops-e2e / mgr-e2e
./scripts/m4b-8-browser-evidence.sh
```

产物默认写入 `artifacts/m4b-8/<date>/`（截图 + JSON log）。Ubuntu 20.04 若无法 `playwright install chromium`，脚本会回退到 `mcr.microsoft.com/playwright` 容器（`--network host`）。

## 8. 手动浏览器要点（无自动化时）

1. 打开 `https://localhost:8443/` → 接受自签证书 → 确认无 mixed-content。
2. DevTools → Network：确认 API 为 **同一 origin** 的 `https://localhost:8443/internal/v1/...`。
3. 登录失败/成功时 scheme 仍为 HTTPS；勿通过 `http://` 访问。
4. 保存截图前遮盖 cookie、session、CSRF、密码字段。
