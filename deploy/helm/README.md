# `deploy/helm/` — 生产交付形态

占位符。chart 随部署里程碑落地。

计划形态：一个 chart `as/`、每个组件一个 subchart 或 values 块
（`apps.translation`、`apps.antiFraud`、`services.configService`、`services.console`），外加一个
values schema，把运营商级的旋钮显式化，而非 emergent：

- `replicaCount` / `minReplicas` 每用例，来自话务模型
- `draining.preStopSeconds`、`draining.graceWindowSeconds`、`draining.forceRelease`
- `peers.allowlist`、`transport.tls.enabled`、`transport.tls.secretRef`
- `state.redis.sentinel.*`、`state.postgres.*`（外部）
- `observability.otlpEndpoint`、`observability.exportMode`（必须非阻塞；见 ADR-0005）

v1 不写 Operator：Helm + 标准 Deployment / ConfigMap / Secret 足够（ADR-0013）。
