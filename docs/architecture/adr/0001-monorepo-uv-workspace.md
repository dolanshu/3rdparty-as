# ADR-0001：单一 monorepo + uv workspace

- **Status**: accepted
- **Date**: 2026-09-28
- **Decides**: §0 决策 3 —— 仓库组织：单 monorepo + uv workspace
- **回应 REQ**: REQ-NF-12, REQ-G-2

---

## Context（背景）

产品前身为两个仓库：`3rtparty_AS_POC` 与 `as_platform`。这两个仓库的物理分离在 POC 阶段暴露了三类硬伤：

1. **CI 每 job 都要 `git clone ../as_platform`。** 任何跨仓引用都依赖兄弟仓库在 CI runner 上恰好在同一相对路径存在，每次 CI 都要 checkout 两次。构建上下文、测试并行化、缓存命中率全部为此受损。
2. **`deploy/Dockerfile.as` 因构建上下文在仓外而失败。** Docker 构建上下文限制在单仓目录内，`COPY ../as_platform` 在标准 CI 环境下不可用。构建脚本必须手动把两个仓合成一个临时目录，额外一层脆弱的胶水。
3. **版本漂移已发生。** 根 `VERSION` 文件是 `0.2.0`，各组件自己的 `pyproject.toml` 却写着 `0.1.0`——两个数字两个家，没有任何自动化守卫阻止这个漂移（详见 ADR-0018）。

本产品全部组件（内核 `platform/`、用例 `apps/translation` / `apps/anti-fraud`、控制面 `services/config-service` / `services/console`、测试平台 `testbed/`）均使用 Python 实现。`uv` 作为现代 Python 包管理工具，原生支持 workspace 概念：一个顶层 `pyproject.toml` 声明 `[tool.uv.workspace]`，所有成员共享同一工具链配置（lint、format、type check），每个成员独立发布但受统一结构守卫约束。

分层规则（`AGENT.md` §4）明确 **内核绝不能 import 应用、服务或 testbed**。但在 monorepo 中，任何 import 都能被解析成功 —— 仓库边界本身不再是防线，防线必须搬到测试里。

## Decision（决策）

采用**单仓 + uv workspace** 作为本产品的仓库组织形态。所有组件同属一个 workspace：

```
as-product/                       # 单仓 · uv workspace
├── platform/                     # 内核库（原 as_platform，并入）
├── apps/
│   ├── translation/              # 号码翻译 AS（原 as_app）
│   ├── anti-fraud/               # 反诈 AS（原 anti_fraud_as）
│   └── <future>/
├── services/
│   ├── config-service/           # 规则版本库 + 变更单 + 分发
│   └── console/                  # 运维控制台
├── testbed/
├── deploy/
├── docs/architecture/adr/
└── AGENT.md
```

"不反向依赖"**不靠仓库边界保证，靠测试保证**。`platform/tests/test_library_independence.py` 使用 AST 扫描 `APPLICATION_PACKAGES`，搬进 monorepo 后继续跑并把守卫范围扩到 `services/`、`testbed/`。结构本身由 `tests/test_workspace_layout.py` 守卫。

## Consequences（后果）

### Positive（正面）

- **一次性消除 POC 三大硬伤**：兄弟仓库 checkout 不再需要；Docker 构建上下文全部在单仓内；版本漂移问题通过 ADR-0018 的根 `VERSION` + `pyproject` 接口版本治理解决。
- **workspace 统一工具配置**：顶层 `pyproject.toml` 集中声明 `[tool.ruff]`、`[tool.mypy]` 等工具链配置，每个成员只需引用，不会出现"同一项目不同成员 lint 规则不同步"的情况。
- **每个组件版本独立但受统一守卫约束**：`pyproject.toml` 中接口版本由各组件自主声明，根 `VERSION` 是产品 release 的唯一源头，二者的 SemVer 合法性由 `tests/test_version_consistency.py` 自动校验。
- **CI/CD 简化**：不再需要兄弟仓库 checkout，`uv sync` 一次搞定全部依赖。缓存命中率提升。

### Negative / accepted（负面 / 已接受）

- **monorepo 体积变大**：所有组件、testbed 仿真器、压测 harness、契约用例集都在一个仓里。通过 `AGENT.md` §4 的分层规则和 `test_library_independence.py` 的 AST 守卫防止互相污染。
- **"不反向依赖"从编译时防线变为测试防线**：在多仓模式下内核引用应用代码会在 import 时报错；monorepo 下任何 import 都能解析，防线退化为 pytest（CI 门禁一层）。已接受，因为 AST 扫描测试在 `make gate` 第一层即阻塞 PR。

## Alternatives considered（考虑过的备选）

| Option | Why not |
|---|---|
| 多仓库保持不变 | 已在 POC 中证明失败：每次 CI 都要 clone 兄弟仓库；Docker 构建上下文跨仓不可用；版本漂移无自动化守卫 |
| lerna / nx 等 JS 生态的 Python 替代（pants / buck） | 额外引入工具链复杂度；uv workspace 原生支持足够本仓库需求 |

## Evidence（证据）

- `tests/test_workspace_layout.py` 已实现并通过，检查 workspace 成员清单、成员路径格式、顶层 `pyproject.toml` 存在性。
- `platform/tests/test_library_independence.py` 已实现并通过，使用 AST 扫描验证内核不引用 `apps/`、`services/`、`testbed/`。
- `uv sync` 在本仓库成功解析 workspace，成员间相互引用的依赖关系正确。

## Related（相关）

- [`../新系统整体架构.md`](../新系统整体架构.md) §11.1 monorepo 结构
- [`../../plan.md`](../../plan.md) §2.1 目录结构
- [`../../AGENT.md`](../../AGENT.md) §4 分层规则
- [ADR-0018](0018-release-versioning.md) 统一产品 release 版本治理
