# Contributing

## Before you start

Read, in this order:

1. [`AGENT.md`](AGENT.md) — the rules. It binds humans and agents alike.
2. [`docs/README.md`](docs/README.md) — where the documentation lives.
3. [`docs/plan.md`](docs/plan.md) — which milestone is running and what is open.

## Environment

```bash
uv sync            # resolve and lock the whole workspace
make gate          # the pre-commit gate, same order as CI layer ①
```

- Python **3.10**, pinned by `.python-version`: it is the version sippy has been
  verified against. See `docs/plan.md` D1 before changing it.
- `uv` manages everything. Do not use pip inside the workspace.
- `uv.lock` is committed and verified in CI. If `uv sync` rewrites it, commit the
  change with the change that caused it.

## The gate

| Layer | Command | Runs on |
|---|---|---|
| ① fast | `make test-unit` | every push and PR |
| ② integration | `make test-integration` | after ① |
| ③ e2e | `make test-e2e` | after ② |
| ④ performance | `make test-perf` | nightly and tags only |

`make gate` = lint + type + ①②③. Nothing is committed unless it is green first.
The local gate is **not** CI: never present a local re-run as a CI result.

## Adding a workspace member

1. Create `<dir>/pyproject.toml` with `[project]`, `[build-system]` and
   `[tool.hatch.build.targets.wheel] packages = ["src/<package>"]`.
2. Create `src/<package>/__init__.py` with a module responsibility statement.
3. Add the directory to `[tool.uv.workspace].members` in the root
   `pyproject.toml`.
4. Add its `src/` to `[tool.ruff].src`.
5. Add its `src/` to `[tool.mypy].files` and `mypy_path`.
6. If it is not the kernel, add its import root to `FORBIDDEN_ROOTS` in
   `platform/tests/test_library_independence.py`.

Steps 3–6 are asserted by the guards in `tests/`; you cannot forget them quietly.

**Do not** add a `[tool.pytest]`, `[tool.ruff]` or `[tool.mypy]` table to a member.
Tooling has one home: the workspace root.

## Commits

- Conventional Commits, English, one logical change per commit:
  `feat` · `fix` · `docs` · `refactor` · `test` · `chore` · `build`.
- No hook skipping. If a hook blocks the commit, fix the cause.
- Never commit a secret, a certificate or a capture of real traffic.
- Agents do not push, create branches or create tags.

## Reviews

- A PR that adopts POC code cites its triage row in
  [`docs/migration/triage.md`](docs/migration/triage.md).
- A PR with a non-obvious design decision arrives with its ADR.
- A PR containing AI-generated work is marked as such.

## Cross-platform note

`mypy_path` in the root `pyproject.toml` uses the POSIX `:` separator. On Windows
set `MYPYPATH` in the environment instead; the build is Linux-targeted.
