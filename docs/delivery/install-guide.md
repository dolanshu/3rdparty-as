# In-house IMS Application Server（文档暂用名）—— 安装部署指南

> **交付物**：交付形态第三批的**安装指南**（[`../product-packaging-plan.md`](../product-packaging-plan.md) §1 **3.1 / 3.2** 同批次）。目录归属 [`docs/delivery/`](./README.md)。
> **本文边界（硬边界）**：**只讲交付清单、镜像获取与同步、`helm install` 命令序列。Helm 参数、values 语义与渲染行为的唯一权威是 [`../../deploy/helm/README.md`](../../deploy/helm/README.md)** —— 本文**不复制**它的参数表、不逐项解释 `--set` 语义，只给"交付什么、拿什么、按什么顺序敲哪几条命令"（评审 **G-P2-4** 即此边界）。
> **生产形态**：**Helm-only** —— Helm + 标准 K8s 资源是唯一生产形态，不写 Operator，不产生第二套安装器（ADR-0013；评审 G-P1-7）。
> **零容量数字**：O1 容量目标未裁决（`AGENT.md` §2；[`../plan.md`](../plan.md) §5.1）。本文**不给** CPS / 并发 / 时延 / 资源规格推荐值；`useCases[].resources` 默认空，本文不替它填。
> **未在真实集群验证**：M4b-7.2d / M8 7.2d 真实集群证据 **仍 blocked**（[`../plan.md`](../plan.md) §5.4）；**M8 RC 产物就绪 ≠ 退出签字完成**，退出签字仍搁置。本文给的是**可执行动作**，不是"已在生产验证"的结论。**air-gapped 场景**（客户机房无外网）走 [`airgap-package.md`](./airgap-package.md)。

## 1. 适用范围与前置条件

**交付给**：运营商侧负责部署的 K8s 管理员 / 交付实施人。读完本文你应该能：拿到交付包后按顺序装出一个 Helm release，并知道每一步在验什么。**缺一项就别开始装。**

| # | 需要什么 | 判定 / 备注 |
|---|---|---|
| 1 | K8s 集群 | 最低 minor 由 [`preflight.sh`](./preflight.sh) 推导校验（默认 1.23，`--min-k8s` 可覆盖）。**chart 本身没有 `kubeVersion` 声明**，Helm 不会替你挡住太老的集群（§10） |
| 2 | Helm 3.x（chart `apiVersion: v2`）+ `kubectl` | 版本下限由 `preflight.sh` 检查 |
| 3 | 产品镜像可获得 | 客户内网 registry，或用本目录离线包导入节点。`registry.example.com` 是占位地址，**不可拉取** |
| 4 | Redis（运行态）与 PostgreSQL（治理态）**决策** | 二选一：外部实例，或启用 chart 内建 `stateStores.enabled=true`（ADR-0026）。**内建单副本不是 HA**：Sentinel HA 仍是 O5 / D3 未决 |
| 5 | 客户 PKI 签发的 TLS Secret | 键 `tls.crt` / `tls.key` / `ca.crt`。**证书由客户侧 PKI 出**，chart 只引用 `tls.secretName`（ADR-0016）。仓库内 [`../../deploy/kind/m5-gen-certs.sh`](../../deploy/kind/m5-gen-certs.sh) 只是 kind 自签先例，**不是交付物** |
| 6 | 目标命名空间 + 安装账号权限 | 示例命名空间 `as-prod`；chart **不创建** Role/RoleBinding，权限须由客户 K8s 管理员授予 |

**前置校验用 [`preflight.sh`](./preflight.sh)（交付物 3.1），不要跳过**（`--dry-run` 只检查本机工具与 chart 渲染、不连集群；`--skip-network` 跳过依赖服务探测；脚本**不是容量校验工具**，`resources` 为空时只给 `WARN`，不猜数字）：

```sh
docs/delivery/preflight.sh -n as-prod -f deploy/helm/values-onprem.example.yaml
```

| 退出码 | 含义 | 处置 |
|---|---|---|
| `0` | 没有 `FAIL`（`--strict` 下也没有 `WARN`） | 可进入安装（§4） |
| `1` | 存在 `FAIL` | **停止**；按每行打印的修复指引处理 |
| `2` | 用法错误（参数非法） | 改参数重来 |
| `3` | `--strict` 下存在 `WARN`（无 `FAIL`） | 逐条确认后才继续 |

## 2. 交付清单

| 交付项 | 形式 | 位置 / 来源 | 校验方式 |
|---|---|---|---|
| Helm chart 包 | `3rdparty-as-<version>.tgz` | `bundle-images.sh` 产出／`deploy/helm/`（仓库内直装） | 含于 `SHA256SUMS`；`make chart-check` 渲染通过 |
| 生产值文件样例 | 文本 | [`../../deploy/helm/values-onprem.example.yaml`](../../deploy/helm/values-onprem.example.yaml) | 其中 `REPLACE_WITH_*` 占位必须全部替换（§5） |
| 产品镜像 | 容器镜像 | `3rdparty-as` + **`3rdparty-as-config-service`**（启用控制面时必需）；清单模板 [`scripts/images.txt`](./scripts/images.txt) | `MANIFEST.txt` 的 tag / digest；Pod 无 `ImagePullBackOff` |
| TLS Secret | K8s Secret | **客户 PKI 出**（键 `tls.crt` / `tls.key` / `ca.crt`） | `kubectl -n <ns> get secret <tls-secret>` 存在；密钥**不入仓库** |
| PostgreSQL 凭据 Secret | K8s Secret | 客户提供（`CONFIG_DB_USER`、`CONFIG_DB_PASSWORD`、`CONFIG_DB_OWNER_PASSWORD`、`POSTGRES_SUPERUSER_PASSWORD`、`REDIS_PASSWORD`） | `stateStores.enabled=true` + `bootstrapDevCredentials=false` 时**必需**（§5 第 3 项） |
| config-service 运行时 Secret | K8s Secret | 客户提供（`AS_CONFIG_DSN`（**`as_config_web` 登录**）、`AS_AUDIT_RESOURCE_HMAC_KEY_B64`） | `services.configService.enabled=true` 时**必需**；`AS_CONFIG_DSN` 的登录须能 `SET ROLE` 到预置 `NOLOGIN` 运行时角色 |
| 迁移 Job | K8s Job（一次性） | `stateStores.migrateJob.enabled=true` + `migrateJob.ownerSecretName`（键 `AS_CONFIG_OWNER_DSN`） | `kubectl -n <ns> wait --for=condition=complete job/...`（§6.1） |
| 文档包 | Markdown | 本目录（`README.md` / 本文 / `airgap-package.md` / `preflight.sh`）+ [`../operations/`](../operations/README.md) + [`../product/`](../product/one-pager.md) | — |

chart **只引用**客户凭据、**不创建也不填充**它们；chart 自带的 credentials Secret 是**空字符串占位**（`AGENT.md` §13）。

## 3. 镜像获取与同步

两条路径，二选一。**路径 A**（客户已有内网 registry 时的正确做法）在联网侧构建并推进客户 registry：

```sh
docker build -t <customer-registry>/3rdparty-as:<VERSION> -f deploy/docker/Dockerfile .
docker build -t <customer-registry>/3rdparty-as-config-service:<VERSION> -f deploy/docker/config-service.Dockerfile .
```

推送后把 §4 的 `--set image.repository` / `--set image.tag` 指向它们即可。**路径 B**（air-gapped，无外网；联网侧制作与离线侧安装的完整流程见 [`airgap-package.md`](./airgap-package.md) §3/§4）：

```sh
docs/delivery/scripts/bundle-images.sh --images docs/delivery/scripts/images.txt --out ./airgap-out
docs/delivery/scripts/load-images.sh --bundle ./airgap-in --load --namespace as-prod
```

**校验和纪律** —— 制作侧与接收侧**各跑一次**，用于区分"传输损坏"与"制作错误"（原文见 [`airgap-package.md`](./airgap-package.md) §3 第 5 步 / §4 第 1 步）：

```sh
cd airgap-out && sha256sum -c SHA256SUMS   # 联网侧，输出随介质交给客户
cd airgap-in  && sha256sum -c SHA256SUMS   # 离线侧第一步，不匹配必须中止
```

要点：`images/*.tar` 与 chart tgz **同进** `SHA256SUMS`；离线环境无法 pull，`image.tag` 必须与实际导入的 tag **逐字一致**（否则只得到 `ImagePullBackOff`）；优先按 digest 固定（`repository:tag@sha256:...`，写法先例见 [`scripts/images.txt`](./scripts/images.txt) 头注）；`docker save` 的一个 tar 只承载一个平台，跨架构分别成包、分别校验。

## 4. 安装命令序列

**参数语义不在本文解释** —— `image.*`、`sip.*`、`tls.*`、`services.configService.*`、`stateStores.*` 的含义与渲染行为见 [`../../deploy/helm/README.md`](../../deploy/helm/README.md)。以下命令**原文照抄** [`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) §"Install (on-prem)"，**未改参数顺序**：

```sh
helm upgrade --install as deploy/helm \
  -f deploy/helm/values-onprem.example.yaml \
  --namespace as-prod --create-namespace \
  --set image.repository="<customer>/as-platform" \
  --set image.tag="<release>" \
  --set sip.peerAllowlist="<s-sbc-cidrs>" \
  --set tls.secretName="<tls-secret>" \
  --set services.configService.image.repository="<customer>/as-config-service" \
  --set services.configService.secretName="<runtime-secret>"
```

命名空间 `--namespace as-prod --create-namespace` 一次到位；chart 在**同一命名空间**内渲染；每个业务用例一个 Deployment（ADR-0002）。**air-gapped 装法**只把 chart 路径换成介质里的 tgz（`./airgap-in/<chart>.tgz`）、values 换成客户值文件，其余参数不变 —— 完整命令见 [`airgap-package.md`](./airgap-package.md) §4 第 4 步，**本文不重复**。**kind / lab**（开发凭据、emptyDir PG，**不得用于客户生产**）：`M5_BUNDLED_STATE=1 bash deploy/kind/m5-helm-install.sh`。

## 5. 安装前必填的三项与 fail-closed

以下三项缺任一，**渲染阶段就失败** —— 这是设计意图（fail-closed），**不是 bug**：宁可装不上，也不要带着空证书上线、或让任何能连到 Service 的人注入呼叫。

| # | 键 | 触发条件 | chart 原文报错（[`../../deploy/helm/templates/validate-install.yaml`](../../deploy/helm/templates/validate-install.yaml)） |
|---|---|---|---|
| 1 | `tls.secretName` | `tls.enabled=true`（默认）且为空 | `tls.enabled=true requires tls.secretName (customer PKI Secret; ADR-0016)` |
| 2 | `sip.peerAllowlist` | 为空（trim 后） | `sip.peerAllowlist must be non-empty (ADR-0016 fail-closed)` |
| 3 | `postgres.secretName` | `stateStores.enabled=true` 且 `bootstrapDevCredentials=false` 且为空 | `stateStores.enabled with bootstrapDevCredentials=false requires postgres.secretName (Secret keys: POSTGRES_SUPERUSER_PASSWORD, CONFIG_DB_OWNER_PASSWORD, CONFIG_DB_PASSWORD)` |

值文件里的 `REPLACE_WITH_POSTGRES_SECRET` / `REPLACE_WITH_CONFIG_RUNTIME_SECRET` / `REPLACE_WITH_TLS_SECRET` / `REPLACE_WITH_S_SBC_CIDRS` 四个占位**必须全部替换** —— chart 不会因为值是占位字符串而报错。**本地先验一次渲染**（别把 fail-closed 留到客户集群才发现）：仓库根目录执行 `make chart-check`（等价 `deploy/helm/scripts/chart-check.sh`，对 AS 默认渲染、config-service 开启、ingress 模板路径与 HPA fail-fast 做断言，已纳入 CI ① fast 层）。

## 6. 安装后步骤

按顺序做，**不要跳步**。

**6.1 迁移 Job 与等待** —— `stateStores.migrateJob.enabled=true` 且 `services.configService.enabled=true` 时，原文照抄 [`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md)：

```sh
helm upgrade --install as deploy/helm -f deploy/helm/values-onprem.example.yaml ...
kubectl -n <ns> delete job/as-3rdparty-as-config-migrate --ignore-not-found
kubectl -n <ns> wait --for=condition=complete job/as-3rdparty-as-config-migrate --timeout=300s
```

**每个 schema 版本跑一次**。生产用法：预先创建 Secret `as-config-migrate-owner`（键 `AS_CONFIG_OWNER_DSN`，owner 登录）；`bootstrapDevCredentials=true` 的 Job 内联 owner DSN 只适用于 kind/dev。手工迁移（受控环境或 `as-config-service` 镜像 Job），原文照抄：

```sh
export AS_CONFIG_OWNER_DSN="postgresql://as_config_owner:<password>@127.0.0.1:15432/as_config"
export AS_CONFIG_RUNTIME_ROLE=as_config_runtime
export AS_AUDIT_SCHEMA=console_audit
export AS_CONFIG_SCHEMA=as_config
uv run as-config-migrate
```

**6.2 PostgreSQL 角色与 DSN** —— `as_config_owner` = 迁移 / bootstrap 的 owner DSN（`AS_CONFIG_OWNER_DSN`，**只**用于人工命令与迁移 Job）；**`as_config_web`** = 运行时 Secret 里 `AS_CONFIG_DSN` 的登录，必须能被 `SET ROLE` 到 `as_config_runtime`（**`NOLOGIN` 最小权限**，由 DBA 预置）。**owner DSN 绝不进 Deployment** —— 不允许出现在 Helm values、chart 管理的 Secret、外部运行时 Secret 或 web Pod 中（[`../../deploy/helm/README.md`](../../deploy/helm/README.md) 原文）。chart 与服务**都不建角色、不做授权**；运行时启动**不做** DDL / 迁移 / 授权。`configSchema`（默认 `as_config`）与 `auditSchema`（默认 `console_audit`）必须不同，且都不能是 `public`。

**6.3 首个管理员 bootstrap** —— 原文照抄 [`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md)：

```sh
kubectl -n <ns> exec -it deploy/as-3rdparty-as-config-service -- \
  as-config-bootstrap-admin   # reads env; interactive getpass
```

**必须先迁移、再 bootstrap**；命令的确切入口以镜像 entrypoint 文档 / `pyproject.toml` console script 为准。

**6.4 接入 S-SBC trunk 与对端白名单** —— SIP trunk：UDP `5060`、TCP `5060`（TCP 监听需 `AS_SIP_ENABLE_TCP` 开启，默认不监听）、TLS `5061`（mTLS，默认启用）。`sip.peerAllowlist` 填 S-SBC 侧地址段，空即 fail-closed（ADR-0016）。trunk 是**不信任**边界：对端按白名单校验，且与 S-SBC 端到端终止 TLS。完整接入步骤见 [`../product/ne-datasheet.md`](../product/ne-datasheet.md) §2 与 [`../product/responsibility-matrix.md`](../product/responsibility-matrix.md)。

**6.5 iFC 触发验证** —— 由 **S-CSCF / HSS 侧**配置 iFC 触发 ISC；**iFC 不在 AS 侧**，AS 侧只实现 ISC 触发后的业务判决（评审 G-P0-5 / G-P1-10）。验证需 S-CSCF / HSS 侧配合，属**跨域联调**，不是单方安装动作。

**6.6 控制台与 ingress-nginx** —— 控制台与 API **同一 HTTPS origin**（`/` 与 `/internal/v1`，ClusterIP HTTP `8000`），无独立 console workload。生产启用 `services.configService.ingress`，要求：`className` 必须是 `nginx`（本模板**只支持 ingress-nginx**，非 `nginx` 即渲染失败；其它 controller 需另行评审的外部配置，**不得**用本模板代表）；`tlsSecretName` 指向客户托管 Secret；`proxyHeaders: true` + **显式 `trustedProxies` CIDR 列表**（`*`、`0.0.0.0/0`、`::/0` 及其它 `/0` 项被拒绝，**不得为了"让转发的 HTTPS 看起来安全"而放宽代理信任**）。> ⚠️ **M4b-7.2d 仍 blocked**：真实集群的 controller 配置、HTTP→HTTPS 重定向行为、trusted-proxy 行为与浏览器 / 网络证据尚未取得并记录，**chart 注解不是重定向证据**（[`../../deploy/helm/README.md`](../../deploy/helm/README.md) §"M4b-7.2d ingress-nginx deployment prerequisites (BLOCKED)"）。

## 7. 验证清单

| 检查项 | 命令 / 方法 | 期望 | 依据 | 证据等级 |
|---|---|---|---|---|
| chart 渲染守卫 | `make chart-check` | 通过（lint + 模板断言） | `Makefile` / `deploy/helm/scripts/chart-check.sh` | **CI ① fast 层，已绿** |
| Pod 与 ready | `kubectl -n as-prod get pods -l app.kubernetes.io/part-of=3rdparty-as` | 各用例 Pod `Running`、READY 为真 | NOTES.txt §2 | kind/dev 已验；**生产未验收** |
| 滚动完成 | `kubectl -n <ns> rollout status deploy --selector app.kubernetes.io/part-of=3rdparty-as` | 全部 rollout 完成、无 Pod 长时间 `Progressing` | NOTES.txt §3（ADR-0009 draining） | 模板层已验；**生产未验收** |
| 版本上报一致 | `kubectl -n <ns> exec deploy/<release>-<use-case> -- printenv CONFIG_VERSION` | 各副本相同且等于控制面生效版本 | NOTES.txt §2（ADR-0006） | kind/dev 已验；**生产未验收** |
| 健康端点 | `kubectl -n as-prod port-forward deploy/<release>-<use-case> 8080:8080` 后访问 `/health/live`、`/health/ready` | live 200；ready 200（**draining 期间 503 属正常摘流**） | [`../operations/runbook-l1.md`](../operations/runbook-l1.md) §1 检查 2 | kind/dev 已验；**生产未验收** |
| 指标端点 | 同上端口，`curl -s localhost:8080/metrics \| grep '^as_'` | 列出会话 / 判决相关 `as_*` 序列 | `../operations/runbook-l1.md` §1 检查 4 | **仅 kind/dev**；chart **无 scrape 注解、无 ServiceMonitor** → 标准部署 Prometheus **采不到**（§10） |
| 状态存储可达 | 指标 `as_state_store_available{use_case}` | `1`（**序列不存在 ≠ 0**：`REDIS_URL` 为空时不产出） | `deploy/alerts/README.md` 指标契约 | kind/dev 已验；**生产未验收** |
| 内建状态存储 | `make m5-kind-verify`；`kubectl -n as-m5 get pods -l app.kubernetes.io/part-of=3rdparty-as` | postgres-0 / redis / translation / anti-fraud / config-service 就绪 | [`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) §"Verify" | **仅 kind（`as-m5`）** |
| 控制台 HTTPS | `curl -I -H 'Host: <ingress-host>' http://ingress-nginx-controller.ingress-nginx.svc/` | **301 / 308**；`empty reply`（curl 52）视为**未过关** | `../operations/runbook-l1.md` §1 检查 5 | **7.2d blocked，生产未验收**；port-forward 200 **不能顶替**此项 |
| 回滚命令可用 | `helm -n <ns> history as` → `helm -n <ns> rollback as <revision>` | 命令可执行、revision 存在 | [`../../deploy/helm/templates/NOTES.txt`](../../deploy/helm/templates/NOTES.txt) §3 | 模板层已验；**真实集群回滚未演练** |

> 完整巡检清单（含 Redis / PostgreSQL / 控制台登录）见 [`../operations/runbook-l1.md`](../operations/runbook-l1.md) §1。**以上没有任何一项可读作"已在生产验证"**：签收矩阵现状 pass 9 / fail 0 / blocked 12 / open 24（[`../acceptance/report.md`](../acceptance/report.md) §0.5）。

## 8. 升级与回滚

**两种"回滚"不是一回事**（NOTES.txt §3 原文区分）：**(a) 配置回滚**（ADR-0006）是在控制台 / config-service 侧回滚变更单、旧配置版本重新灰度分发到实例，这是 `ASConfigRollbackTriggered` 的语义，**回滚后必须人工确认**；**(b) 镜像 / manifest 回滚**是回退 Helm release、让 Deployment 自己把 Pod 滚回去，**出场时走 draining**（ADR-0009）。命令原文照抄 [`../../deploy/helm/templates/NOTES.txt`](../../deploy/helm/templates/NOTES.txt) §3（原文是 Go 模板 `helm -n {{ include "as.namespace" . }} history {{ .Release.Name }}`，上文按 §4 的 release 名 `as` 与现场命名空间渲染，**逐字未改参数顺序**）：

```sh
helm -n <ns> history as
helm -n <ns> rollback as <revision>
kubectl -n <ns> rollout status deploy --selector app.kubernetes.io/part-of=3rdparty-as
```

| 变更内容 | 升级路径 |
|---|---|
| **AS 镜像 / SIP 旋钮** | `helm upgrade`，只动 `image.*`、`sip.*`、`useCases` |
| **PostgreSQL 镜像 / PVC** | **维护窗口**，走客户 Postgres 升级流程（`stateStores.migrateJob` 只是一次性 schema 迁移，**不是**备份、也不是 PG 升级通道） |
| **Redis** | **维护窗口**，预期短暂运行态不可用 |

处置细节见 [`../operations/rollback-playbook.md`](../operations/rollback-playbook.md)（业务摘流 / 回退 + iFC 侧配合）与 [`../operations/runbook-l1.md`](../operations/runbook-l1.md) §3.2；版本支持周期与 EOL 见 [`../product/version-lifecycle.md`](../product/version-lifecycle.md)。证书轮换是**配置热更新**，不重启进程（ADR-0016）。

## 9. 与其它文档的边界

| 主题 | 权威文档 | 本文 |
|---|---|---|
| Helm 参数、values 语义、渲染守卫、fail-closed 行为 | [`../../deploy/helm/README.md`](../../deploy/helm/README.md) | **不复制参数表**，只引用 |
| 部署前环境校验 | [`preflight.sh`](./preflight.sh) | §1 给命令与退出码 |
| 离线安装包（air-gapped）制作与使用 | [`airgap-package.md`](./airgap-package.md) | §3 只给两条路径与校验和命令 |
| 迁移 / owner DSN / 备份恢复细节 | [`../acceptance/m5-state-stores-runbook.md`](../acceptance/m5-state-stores-runbook.md) | §4 / §6.1–6.3 **原文照抄**，不展开 |
| 日常巡检、告警处置、深度排障 | [`../operations/runbook-l1.md`](../operations/runbook-l1.md) | §7 只给安装后验证项 |
| 定位 / 容量模型 / 接口清单 / 资源规格、合规（PDPO）、生命周期与 EOL | [`../product/`](../product/one-pager.md)（`one-pager` / `ne-datasheet` / `security-privacy` / `version-lifecycle`） | 不重复 |

## 10. 已知缺口与未决

| 项 | 状态 | 阻塞源 |
|---|---|---|
| chart 无 `kubeVersion` 声明 | 缺口 —— Helm 不拦太老的集群 | [`../../deploy/helm/Chart.yaml`](../../deploy/helm/Chart.yaml) 无该字段；`preflight.sh` 按模板实际使用的 API 推导下限兜底 |
| Chart `version` / `appVersion` 与根 `VERSION` 不同步 | 缺口 —— 仍是骨架值（`0.0.0-skeleton` / `0.0.0`） | ADR-0018；打包时人工核对三者 |
| `useCases[].resources` 默认空 | **刻意留空** —— chart 不渲染 requests/limits，**本文不给推荐值** | 与 O1 同源；sizing 待 O1 裁决后由 NE datasheet 给出 |
| Pod 无 `prometheus.io/scrape` 注解、无 ServiceMonitor | 缺口 —— **所有依赖 `as_*` 的看板与告警在标准部署中不会被采集**；OTLP exporter 当前为 `NoOp` | 抓取接线未闭环（§7 指标行） |
| 7.2d 生产 ingress / trusted-proxy | **blocked** —— 生产 ingress、真实 HTTPS 与浏览器证据缺失 | [`../plan.md`](../plan.md) §5.4；§6.6 |
| M8 退出签字 | **仍搁置** —— RC 产物就绪 ≠ 关门 | 维护者退出签字未完成 |
| E1 / E4 / E5 未验收；e2e = 0 | reSIProcate 生产路径行为、TLS 热轮换、状态外置与恢复均未验收；完整呼叫 + 控制台端到端路径无自动化证据 | O2 / O3；`pytest e2e` marker 数量为 0 |
| D1 Python 3.10 EOL；O5 / D3 Redis HA；PG HA / PITR | **未决** / 客户侧责任 —— 内建 Redis 单副本**不是 HA**，`redis.sentinel.masters` / `.addresses` 故意留空；chart 交付单副本 PG StatefulSet，**不交付备份 Job** | D1 生命周期终点；客户 SLA 未定（ADR-0008）；恢复演练待真实集群（[`../operations/backup-restore.md`](../operations/backup-restore.md)） |

## 11. 追溯

| 项 | 内容 |
|---|---|
| 对应交付物 | [`../product-packaging-plan.md`](../product-packaging-plan.md) §2 目录结构中的 `delivery/install-guide.md`；交付形态第三批 **3.1 / 3.2** 同批次（同 [`./README.md`](./README.md)）。工程事实约束见该计划 §0.3 |
| 边界裁决 | **G-P2-4**（`install-guide.md` 与 `deploy/helm/README.md` 内容重叠）：本文只做**交付清单 + 镜像同步 + 命令序列**，参数与行为归 `deploy/helm/README.md`，两文档互链不重复。评审记录 [`../reviews/product-packaging-plan-review-2026-10-09.md`](../reviews/product-packaging-plan-review-2026-10-09.md) |
| 引用的 ADR | [ADR-0013](../architecture/adr/0013-helm-only-production.md)（Helm-only 生产形态）、[ADR-0016](../architecture/adr/0016-in-boundary-security.md)（边界内安全：TLS + 对端白名单 fail-closed）、[ADR-0026](../architecture/adr/0026-in-cluster-state-stores-proposal.md)（集群内状态存储）；相关：ADR-0002（一用例一进程）、ADR-0006（配置治理 / 配置回滚）、ADR-0008（冗余）、ADR-0009（ISSU = draining） |
| 未做的事 | 不给容量 / 资源规格 / 恢复时长数字；不把未验收写成已验收；不引用 M6 dev-host 测量；不复制 Helm 参数表；不写第二套安装形态 |