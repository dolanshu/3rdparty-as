# `services/console/` — 运维控制台

运营商运维界面：经变更单治理规则、按 Call-ID 查询呼叫轨迹、查看运行指标。正式控制台须满足
[`../../docs/acceptance/test-plan.md`](../../docs/acceptance/test-plan.md) 中 REQ-F-12/13/14/15 与 REQ-S-4 的验收要求。

## D4 决策（2026-10-01）

前端使用纯 HTML/CSS/JavaScript，不引入 bundler、build tool 或前端 runtime 依赖。当前 console
尚无 HTTP/runtime 前端；无构建步骤也更适合简单的 on-premises 交付。此决定只确定实现形态，不代表后端、鉴权或产品工作流已经存在。

## M4b-1 静态预览

可信任的浏览器可直接打开 [`web/index.html`](web/index.html) 查看。若 VS Code 浏览器 sandbox
不允许打开本地文件，可从仓库根目录运行：

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory services/console/web
```

然后访问 <http://127.0.0.1:8765/>。这只是本地预览路由；不添加 build/dependency 或 backend。此交付是第一段
operator UI preview，不是 M4b 完成，也不构成验收证据。

预览包含 Rules、Change orders、Call traces、Operations 四个视图。规则新增、编辑、启用/禁用、删除会在内存中
排入变更单；批准或拒绝、拒绝理由校验、Call-ID fixture 搜索与明细、指标摘要均可在当前页面交互。全部数据为本地
fixture，状态只保留在当前页面内，不使用 localStorage 或网络请求。页面持续显示 `PREVIEW · LOCAL DATA · NOT CONNECTED`。

当前没有接入 API、认证/session backend、PostgreSQL 规则或变更单数据、live telemetry，也没有持久化审计日志。身份位置
是只读的未连接占位；交互不是生产操作，刷新页面会恢复 fixture 状态。

## M4b 剩余验收

- 接通真实 backend/API，实现 REQ-F-12/13/14/15 全流程，包括规则校验、审批、Call-ID 轨迹查询和灰度分发/回滚。
- 集成 REQ-S-4 鉴权与审计：写操作先鉴权；审计记录操作者、时间、操作类型及变更前后值，并满足不可篡改要求。预览不模拟登录，也不声称审计已持久化。
- 接入 PostgreSQL 持久化和真实轨迹/运行数据，并完成 UI 与后端 workflow integration。
- 按 [`../../docs/acceptance/test-plan.md`](../../docs/acceptance/test-plan.md) 完成真实集成及 browser acceptance，记录验收证据。

## 正式产品边界与依赖

- 正式控制台只通过 AS 内部 API（如 `/healthz`、`/metrics`、`/traces`）访问 AS；不得建立私有通道。
- 呼叫轨迹是产品能力，不是调试副作用；按 Call-ID 查询不依赖客户是否部署 trace backend（ADR-0005）。OTel trace 是另一条通道，用同一 Call-ID / TraceID 关联。
- 产品写操作必须经鉴权和审计；当前 [`src/as_console/access.py`](src/as_console/access.py) 是纯访问策略判定，不包含 HTTP、login、session 或 persistence 实现。

| 依赖 | 用途 |
|---|---|
| platform（通过 seam 接口） | 引用内部 API 契约 |
| config-service 内部 API | 规则版本浏览、变更单、审批、灰度分发与回滚 |
| PostgreSQL | 持久化规则版本、变更单与审批记录 |
| OTel SDK | 正式接线后的控制台操作审计、指标与 trace |
