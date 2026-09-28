# `deploy/compose/` — 仅开发环境

占位符。在单机上拉起：

- 两个 AS 用例，各自用自己的端口
- config-service 与 console
- Redis 与 PostgreSQL，单实例，**无**冗余

目的：让系统无需 Kubernetes 集群即可运行。它明确不是部署目标、不是 HA，且任何容量数字都不能在它上面
测（ADR-0013、ADR-0014）。
