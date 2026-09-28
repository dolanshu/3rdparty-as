# 贡献指南（Contributing）

## 开始之前

按此顺序阅读：

1. [`AGENT.md`](AGENT.md) —— 规则。对人和 agent 同样有约束力。
2. [`docs/README.md`](docs/README.md) —— 文档在哪里。
3. [`docs/plan.md`](docs/plan.md) —— 当前在跑哪个里程碑、哪些还开放。

## 环境

```bash
uv sync            # 解析并锁定整个 workspace
make gate          # 提交前门禁，顺序同 CI 第①层
```

- Python **3.10**，由 `.python-version` 锁定：这是 sippy 已验证过的版本。要改之前先看 `docs/plan.md` D1。
- `uv` 管一切。workspace 内不要用 pip。
- `uv.lock` 提交进仓库并在 CI 中校验。如果 `uv sync` 重写了它，连带着引起改动的那个 commit 一起提交。

## 门禁（The gate）

| 层 | 命令 | 运行时机 |
|---|---|---|
| ① fast | `make test-unit` | 每次 push 和 PR |
| ② integration | `make test-integration` | 在 ① 之后 |
| ③ e2e | `make test-e2e` | 在 ② 之后 |
| ④ performance | `make test-perf` | 仅 nightly 和 tag |

`make gate` = lint + type + ①②③。本地门禁不绿，什么都不能提交。
本地门禁**不是** CI：绝不要把本地重跑冒充成 CI 结果。

## 新增一个 workspace 成员

1. 创建 `<dir>/pyproject.toml`，含 `[project]`、`[build-system]` 和
   `[tool.hatch.build.targets.wheel] packages = ["src/<package>"]`。
2. 创建 `src/<package>/__init__.py`，写明模块职责。
3. 把该目录加入根 `pyproject.toml` 的 `[tool.uv.workspace].members`。
4. 把它的 `src/` 加入 `[tool.ruff].src`。
5. 把它的 `src/` 加入 `[tool.mypy].files` 和 `mypy_path`。
6. 如果它不是内核，把它的 import 根加入 `platform/tests/test_library_independence.py` 的
   `FORBIDDEN_ROOTS`。

第 3–6 步由 `tests/` 里的守卫断言；你没法悄悄漏掉。

**不要**给成员加 `[tool.pytest]`、`[tool.ruff]` 或 `[tool.mypy]` 表。工具配置只有一个家：workspace 根。

## 提交（Commits）

- Conventional Commits，英文，一次 commit 一个逻辑改动：
  `feat` · `fix` · `docs` · `refactor` · `test` · `chore` · `build`。
- 不跳过 hook。如果 hook 挡住了 commit，去修原因。
- 绝不提交密钥、证书或真实流量抓包。
- Agent 不 push、不创建分支、不创建 tag。

## 评审（Reviews）

- 采纳了 POC 代码的 PR，要在 [`docs/migration/triage.md`](docs/migration/triage.md) 中引用对应的甄别行。
- 带有非显而易见设计决策的 PR，要带着它的 ADR 一起过来。
- 含 AI 生成工作的 PR 要标注出来。

## 跨平台注意

根 `pyproject.toml` 里的 `mypy_path` 用的是 POSIX 的 `:` 分隔符。在 Windows 上改用环境变量
`MYPYPATH`；本构建以 Linux 为目标。
