# `deploy/`

| 目录 | 角色 |
|---|---|
| `helm/` | **生产交付形态。** Kubernetes + Helm，一个 chart 管整个系统 |
| `compose/` | 仅开发环境。绝不用于交付 |

Helm 是唯一生产形态（ADR-0013）。Compose 的存在是为了让开发者能在笔记本上拉起 AS + config-service +
console + Redis + PostgreSQL；它不是部署目标，不带任何 HA 语义。

## chart 必须表达的东西

- AS service 上的 `sessionAffinity: ClientIP`，加上 Redis 会话表作为第二道防线（ADR-0002）。
- `preStop` draining、延长的 `terminationGracePeriodSeconds`、ISSU 用的 PodDisruptionBudget（ADR-0009）。
- Redis 与 PostgreSQL 作为外部依赖，而非 chart 内的有状态负载：运营商的冗余要求决定它们怎么跑。
- 证书来自 Secret 或客户 PKI；轮换绝不能重启 AS pod（ADR-0016）。

## 状态

占位符。chart 随部署里程碑落地；顺序见 `docs/plan.md`。
