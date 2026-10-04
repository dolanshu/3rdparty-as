# M5 Helm 模板与告警规则评审记录

> 评审对象：`deploy/helm/`（values 契约与 templates）、`deploy/alerts/`
> 评审日期：2026-09-28
> 评审人：AI agent（对照 ADR-0002 / 0009 / 0013 / 0016、AGENT.md §2 与 plan.md §6、REQ-NF-13 / NF-14 / NF-9）
> 评审结论：**有条件通过** —— Helm 渲染校验已完成，PostgreSQL 接线与真实数据库闭环（H11）亦已完成；剩余缺口为运维接线与容量类告警（H10 / H12）

## 评审发现

| # | 发现 | 裁决 |
|---|---|---|
| H1 | 全仓库未出现 CPS 或并发会话绝对值；HPA 阈值与副本上下限全部为 `null` 并标注"待 M6 实测（O1）" | 接受：符合 AGENT.md §2/§6"M6 之前不发布任何容量数字" |
| H2 | `hpa.yaml` 三重守卫 + `required`：开启自动扩缩但未填阈值时**安装直接失败**，而不是用猜测值兜底 | 接受：宁可安装失败，也不要一个来源不明的容量数字上线 |
| H3 | `pdb.yaml` 无容量默认值，`minAvailable` 为空即不渲染 | 接受：与 H2 同一原则 |
| H4 | 告警只用比例 / 相对量 / 状态量（`ASActiveCallsSurge` 用"当前 > 1.3 × 30 分钟均值"），每条 description 明写"不是容量数字" | 接受：把 REQ-NF-14 的"突增"实现成纯相对量，避免顺手引入容量承诺 |
| H5 | draining 由 `preStop` + 延长 `terminationGracePeriodSeconds` 表达 | 接受：ADR-0009 的 draining 语义 |
| H6 | `sessionAffinity: ClientIP` 的注释写明它只是双保险之一（另一半是应用层 Redis 会话表），且 S-SBC 复用源端口时它并不充分 | 接受：避免把亲和性当成正确性保证 |
| H7 | 凭据为占位值 + `as.3rdparty/credentials: placeholder-replace-before-install` annotation；TLS 不落入 Secret 模板，只引用客户 PKI 的 Secret 挂载（热轮换不重启） | 接受：AGENT.md §13 不提交密钥；ADR-0016 证书热轮换 |
| H8 | 一个用例一个 Deployment / Service，用 `range` 遍历 `useCases`；`enabled: false` 跳过；`replicaCount` 为空时渲染 `replicas: 1` 并紧跟注释"这是渲染兜底，不是容量结论" | 接受：ADR-0002 一用例一进程；兜底值已显式去容量化 |

## 缺口（不阻塞本次交付，但阻塞 M5 完成）

| # | 缺口 | 处置 |
|---|---|---|
| H9 | ~~未做 `helm template` 渲染校验（环境无 helm 二进制）~~ **已于 2026-09-28 完成验证。** 历史：评审时环境无 helm 二进制，只做了纯 YAML 解析 + 模板静态配平自查。现状：用 helm v3.16.2 跑通 `helm lint deploy/helm`（0 failed）与 `helm template as deploy/helm`（exit 0）；首次渲染即暴露 `_helpers.tpl` 两处左裁剪（`as.labels` 与 `as.useCaseLabels` 内的 `{{- include ... }}` 吃掉前一行换行，标签被拼接、全模板 YAML 解析失败），已改为不带左裁剪的 `{{ include ... }}`；反例 `--set autoscaling.enabled=true` 按预期失败并给出 `required` 提示 | **已完成验证，不再是缺口**；证据见 `docs/acceptance/report.md` M5 段 |
| H10 | 缩容保护控制器已落地；kind 运维接线证据：`m5-plan-scale-down-from-metrics.sh` + `m5-issu-scale-evidence.sh`（2026-10-04） | **kind 已证据** |
| H11 | PostgreSQL 版 `VersionStore` 接线（M4 转入）与其 integration 用例 | **已完成（2026-09-28）。** `services/config-service/src/as_config_service/postgres_store.py` 已实现：版本只做**不可变追加**（无 UPDATE / 无 DELETE，回滚靠写回上一版本内容而不是改历史）；表名走白名单（标识符不经字符串拼接进入 SQL，防注入与误表）；`psycopg` 为**惰性 import**（不装驱动也能导入模块与跑单测）。integration 用例 9 条（`services/config-service/tests/test_postgres_store_integration.py`）**真连 `127.0.0.1:55432` 的 PostgreSQL 16 容器跑通**，含治理闭环：审批 → 落库 → 分发 → 自动回滚 → 取回上一版本；`pytest -m integration` 全仓共 **12 passed**（9 条 PG + 3 条遥测导出） |
| H12 | 容量类告警（CPS / 并发）与 HPA 阈值 | 受 O1 / M6 阻塞，M6 之后单独加 `as.capacity` 组 |
| H13 | kind `as-m5` 上 ISSU/draining + `plan_scale_down` 路径（`artifacts/m5/*/issu-scale-evidence.log`） | **kind 已执行（2026-10-04）** |

## 确认签字

| 项 | 值 |
|---|---|
| 评审结论 | **M5-a/b 工程 Accept**（2026-10-04 裁决）；H10/H13 kind 已证据；H12 → M6 |
| 评审人 | AI agent，2026-09-28；2026-10-04 更新 |
| 维护者签字 | **Approved 2026-10-04**（chat 授权代签；见 [m5-closure-adjudication-2026-10-04.md](m5-closure-adjudication-2026-10-04.md)） |
| M5 索引 | [m5-task-register-2026-10-04.md](m5-task-register-2026-10-04.md)；证据指针 [`m5-evidence-summary.md`](../acceptance/m5-evidence-summary.md) |
