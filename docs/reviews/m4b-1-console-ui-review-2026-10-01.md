# M4b-1 Console UI Engineering Preview Review

> 评审对象：D4 与 M4b 范围；[`services/console/README.md`](../../services/console/README.md)、[`index.html`](../../services/console/web/index.html)、[`console.css`](../../services/console/web/console.css)、[`console.js`](../../services/console/web/console.js)；[`plan.md`](../plan.md) 的 M4b / D4 状态；[`test-plan.md`](../acceptance/test-plan.md) §1.4 REQ-F-12/13/14/15、§3 REQ-S-4
> 评审日期：2026-10-01
> 评审方式：每个 M4b-1 工作步骤后的独立只读评审；本记录按工作步骤汇总发现与修复
> 评审结论：**通过，仅限 M4b-1 工程预览切片；不是 M4b 验收或 M4 完成**

## 范围与判定边界

D4 选择纯 HTML/CSS/JavaScript，不引入 bundler、build tool 或前端 runtime 依赖。预览包含 Rules、Change orders、Call traces、Operations 四个 view；只使用本地 fixture 与当前页面内存，显著标注 `PREVIEW · LOCAL DATA · NOT CONNECTED`。本评审只确认 M4b-1 静态工程预览切片及其交互证据，不把它视为正式控制台验收。整体 M4 保持开放。

## 独立评审发现与修复

| 顺序 | 发现 | 修复 |
|---|---|---|
| 1 | 批准文案容易被理解为已影响生产路由。 | 明确批准只影响本地预览；页面说明没有 routing backend。 |
| 2 | 仅空白的 match 值可能通过校验。 | 拒绝空白值并显示 `Enter a match value.`；无效输入不增加变更单队列。 |
| 3 | 移动端 Rules 隐藏了 Match criteria。 | 保留 Match criteria；只隐藏 version/updated。 |
| 4 | 仅空白的规则名称或 target detail 未拦截。 | 分别拒绝并显示 `Enter a rule name.`、`Enter target detail.`。 |
| 5 | 键盘操作后焦点可能丢失。 | 选择轨迹、筛选结果、批准或拒绝后恢复焦点到相应 Call-ID、搜索框或当前页标题。 |
| 6 | trace fixture 不完整，且两腿 Call-ID 显示容易混淆。 | 补齐 14 条按时间排序的双腿消息；每行显示其所属腿的 Call-ID，任一腿 Call-ID 均可检索同一轨迹。 |
| 7 | 100 Trying 的 fixture 方向错误。 | 修正 100 Trying 所属方向。 |
| 8 | README 只说明直接打开 `web/index.html`，未记录 VS Code sandbox 拒绝 `file://` 时使用的 loopback 预览方式。 | 保留可信浏览器直接打开选项，并补充从仓库根目录启动 `python3 -m http.server 8765 --bind 127.0.0.1 --directory services/console/web`、再访问 `http://127.0.0.1:8765/` 的本地预览说明；不增加 build/dependency 或 backend。 |

最后一轮完整 trace fixture 评审无发现；修复后的 focus-only 复核也无发现。

## 浏览器验证

- 浏览器 sandbox 拒绝不可信 `file://`，因此经 `http://127.0.0.1:8765/` loopback 打开页面。这是浏览器环境限制，不是应用错误。
- Rules 的创建、编辑、启用/禁用、删除只排入本地 change orders。空白名称、match、target 与无效 regex 分别得到 `Enter a rule name.`、`Enter a match value.`、`Enter target detail.`、`Enter a valid regular expression.`；无效输入不增加队列，合法 regex 会排队。
- 空拒绝理由会阻止拒绝操作；填写理由后变更单显示 `Rejected` 并展示理由。批准措辞说明只影响本地 preview，不连接 routing backend。
- 14 条 trace fixture 包含两条独立腿的 Call-ID、两腿 INVITE 与 100/180/200 响应、两腿 ACK、入站与出站 BYE、下游与上游 200。任一腿 Call-ID 可检索同一 trace；每条消息显示自己的 leg Call-ID。
- 390px viewport 下四个 view root 与 body 均为 375px。Rules 保留 Match criteria，仅隐藏 version/updated；Change orders 仅隐藏 requested-by/submitted metadata；Call-trace details 的七个字段均保留在内部表格滚动区，root 无 overflow。1440px viewport 下 root 宽度均不超过 1440px，Call traces 为 1425px。
- Enter 选择 trace 后焦点回到所选 Call-ID；筛选掉当前 trace 后焦点留在搜索框；从 Rules 批准或从 Change orders 拒绝后焦点回到当前页标题。拒绝理由验证正常。

## 本地验证与限制

- `node --check services/console/web/console.js`：通过（主 agent 执行）。
- 最新本地 `make gate`：ruff format 190 files formatted；Ruff 全通过；mypy 36 source files clean；pytest **417 passed, 2 known skips, 15 deselected**。未运行 CI。
- 当前无 backend/API、auth/session、persistent audit、database、live telemetry、production routing、persisted trace store 或 workflow connection。预览只包含本地内存状态，不满足 REQ-F-12/13/14/15 与 REQ-S-4 的正式工作流验收。

## 评审结论

**Pass for M4b-1 slice only / not M4 completion.** M4b 的实现、集成与验收仍开放；M4 整体未完成。维护者签字：**Approved**（2026-10-04；chat 授权 AI 代签）。