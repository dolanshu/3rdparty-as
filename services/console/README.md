# `services/console/` — 运维控制台

运营商运维界面：经变更单治理规则、按 Call-ID 查询呼叫轨迹、查看运行指标。正式控制台须满足
[`../../docs/acceptance/test-plan.md`](../../docs/acceptance/test-plan.md) 中 REQ-F-12/13/14/15 与 REQ-S-4 的验收要求。

## D4 决策（2026-10-01）

前端使用纯 HTML/CSS/JavaScript，不引入 bundler、build tool 或前端 runtime 依赖。config-service ASGI app
从 `/` 提供 console 静态 assets，API routers 位于 `/internal/v1`；源码运行时可从 `services/console/web` 提供 assets，安装的 as-console wheel 包含所需文件。无构建步骤也更适合简单的 on-premises 交付。当前已有代码级 ASGI factory/CLI，但这不证明已部署 ingress 或完整产品工作流。

config-service 现提供代码级 ASGI factory/CLI，可从仓库根目录运行
`uv run --directory services/config-service as-config-service`。部署所需环境变量、预配置 least-privilege PostgreSQL runtime role、
外部数据库 setup 以及 HTTPS/proxy 要求见 [`config-service README`](../config-service/README.md#runtime)。此 factory 不是部署证据：
生产 HTTPS ingress 与 trusted-proxy 行为尚未验证，M4b/M4 acceptance 仍未完成。

## M4b-1 静态预览与首个 live integration slice

可信任的浏览器可直接打开 [`web/index.html`](web/index.html) 查看。若 VS Code 浏览器 sandbox
不允许打开本地文件，可从仓库根目录运行：

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory services/console/web
```

然后访问 <http://127.0.0.1:8765/?preview=1>。fixture 交互只在显式 `?preview=1` 模式启用；默认页面尝试连接 live API。
此 Python `http.server` 仅用于 `?preview=1` 静态预览，不提供 `/internal/v1` API；不要将它用于 live mode。当前代码级 ASGI serving/package 与 UI/API integration slices 不代表 M4b-7 完成，也不构成验收证据。

预览包含 Rules、Change orders、Call traces、Operations 四个视图。规则新增、编辑、启用/禁用、删除会在内存中
排入变更单；批准或拒绝、拒绝理由校验、Call-ID fixture 搜索与明细、指标摘要均可在当前页面交互。全部数据为本地
fixture，状态只保留在当前页面内，不使用 localStorage 或网络请求。页面持续显示 `PREVIEW · LOCAL DATA · NOT CONNECTED`。

## Live console integration

当使用 config-service ASGI app 时，它在 `/` 提供 console，在 `/internal/v1` 提供 API。默认模式使用 same-origin API 和 `credentials: 'same-origin'`，恢复 session 后读取 managed rules 与 change orders。
外部部署必须通过同一 HTTPS origin 暴露 console 与 API，并保留 `/internal/v1` 路径；ingress/reverse proxy 必须保留可信的 HTTPS scheme 行为，供 ASGI app 正确识别原始请求 scheme。代码级 ASGI factory/CLI 已交付，但当前没有 deployed HTTPS ingress/trusted-proxy 证据。
不要以 HTTP 直接登录：服务端会拒绝登录，且 session/CSRF cookies 使用 `Secure` 属性。

除登录/session/logout、规则与变更单读取外，live Change orders table/modal 仅支持 creator 提交既有 draft，以及由不同 approver 批准或拒绝 submitted order；提交/决策后从 server 重新加载状态，写请求带 CSRF。此 workflow 不启用 ManagedRule create/edit/enable/delete 或其他规则写入；runtime bundle mapping/compiler 与 regex semantics 未解决前，规则写入仍被阻塞。Live change-order modal 含 **distribution start / batch report / rollback**（需 approver/admin、已登记 fleet 实例）；仍无 Call-ID trace UI。没有 live Call-ID 查询或遥测端点，对应视图会明确显示 unavailable。API 请求失败时显示错误，不会回退到 fixture。认证信息不存入 localStorage，也不会写入日志。preview 仍只操作本地 fixture，不调用 live API。

## M4b 剩余验收

- 完成 M4b-7 剩余 API/UI 工作流：解决 lossless runtime rule mapping/compiler 与 regex semantics 后实现 ManagedRule CRUD/规则审批；接入 live Call-ID 查询，以及 AS inventory、notification 与 health 后端后实现真实灰度分发/回滚。当前既有 ChangeOrder submit/approve/reject UI 仅为 engineering slice，不表示这些需求已满足。
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
