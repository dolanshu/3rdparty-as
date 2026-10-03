# ADR-0025 — Managed Rule Runtime Bundle Contract

- **Status**: draft · pending maintainer review
- **Date**: 2026-10-03
- **Decides**: M4b-7.3b lossless mapping from management-plane `ManagedRule` rows to internal API `ConfigBundle` / `RuleDTO` (REQ-F-12 → runtime kernel)
- **回应 REQ**: REQ-F-12, REQ-F-14, REQ-NF-10

## Context（背景）

- REQ-F-12 stores rules in the control plane with match object (calling/called), match mode (prefix/regex), target business type (translation / anti-fraud / routing / block / default), enablement, and optional routing detail.
- The internal API contract (`RuleDTO` v0.1.0, `INTERNAL_API_VERSION`) carries only `rule_id`, normalized `prefix`, `action` (`forward` | `translate` | `block`), and optional `target`. The kernel `RuleSet` matches **called** numbers only, using **prefix** semantics (`as_platform.decision.rules`, REQ-F-6).
- M4b-7.3b is blocked until this mapping is explicit and test-backed. Placeholder bundles or silently dropped non-compilable rules are forbidden.

## Decision（决策）

### Management → `RuleDTO` field mapping

| `ManagedRule` field | `RuleDTO` field | Rule |
|---|---|---|
| `rule_id` | `rule_id` | Copied verbatim (already canonicalized at the management boundary). |
| `match_value` (v1 subset) | `prefix` | `normalize_number(match_value)` from `as_platform.decision.rules`. |
| `target_service` + `target_detail` | `action` + `target` | See table below. |
| `enabled` | — | Disabled rules are **omitted** from the bundle (not an error). |
| `name` | — | Management metadata only; not distributed on the internal API. |
| `match_field` | — | v1: only `CALLED` compiles; see rejections below. |
| `match_mode` | — | v1: only `PREFIX` compiles; see rejections below. |

### v1 compilable subset

A rule compiles only when **all** of the following hold:

- `enabled` is ignored at single-rule compile time; bundle assembly skips `enabled=false`.
- `match_field == CALLED`
- `match_mode == PREFIX`

`match_field == CALLING` and `match_mode == REGEX` are **not representable** in `RuleDTO` v0.1.0 / kernel `RuleSet` today. The compiler **must reject** such rules with a typed error (`rule_id` + reason); it must not silently drop them.

### `TargetService` → kernel `action` / `target`

Kernel `Action` strings on the wire match `as_platform.decision.rules.Action` values.

| `TargetService` | `action` | `target` |
|---|---|---|
| `TRANSLATION` | `translate` | `target_detail` (required non-empty after management validation) |
| `ROUTING` | `forward` | `target_detail` if set, else `None` |
| `DEFAULT` | `forward` | `target_detail` if set, else `None` |
| `ANTI_FRAUD` | `forward` | `target_detail` if set, else `None` (anti-fraud use case applies screening on forward hits) |
| `BLOCK` | `block` | `None` (`target_detail` is ignored) |

`target_detail` is passed through unchanged when present; it is not re-normalized as a phone number.

### Bundle assembly

- Pure functions live in `as_config_service.runtime_bundle` (`compile_managed_rule`, `compile_bundle`). See ADR-0025 in code for non-obvious branches.
- `compile_bundle(version, rules)` produces `ConfigBundle(version=version, rules=..., toggles=())`.
- **Ordering**: compiled rules are sorted by `rule_id` ascending (Unicode code point order) for stable, diff-friendly bundles.
- If any **enabled** rule fails compilation, the whole bundle compile fails with **all** per-rule errors (no partial bundle).
- **Empty rules**: `rules=()` is valid when the caller supplies an explicit `version` (unit tests, dry-run compile). Distribution / activation paths that publish a version to the fleet must not ship an empty rule set without an explicit product decision elsewhere; this ADR does not authorize placeholder fleet publish.

### Prefix normalization

Use `normalize_number` on `match_value` so management prefixes align with runtime longest-prefix matching (separators dropped, leading `+` ensured when digits remain).

## Consequences（后果）

### Positive（正面）

- Management and runtime share one tested mapping; blocked features fail loudly instead of publishing lossy bundles.
- Disabled rules stay in PostgreSQL but never reach AS instances.

### Negative / accepted（负面 / 已接受）

- **Calling-party rules** need a future internal API / `RuleSet` contract bump; v1 rejects them.
- **Regex rules** need executable semantics and wire fields; v1 rejects them.
- **Per-use-case bundles** (translation vs anti-fraud filtering) are not split here; one compiled bundle is shared. Fleet filtering by process remains a follow-up if needed.
- Anti-fraud “hard block” vs “screen forward” is expressed only via `TargetService` (`BLOCK` vs `ANTI_FRAUD`); rate-limit policy stays in the anti-fraud app layer.

## Evidence（证据）

- Unit tests: `services/config-service/tests/test_runtime_bundle.py` (marker `unit`).
- Implementation: `services/config-service/src/as_config_service/runtime_bundle.py`.

### Activation and version repository (M4b-7.3b slice 2)

- After a managed-rule mutation in `apply_distributed_change`, the coordinator calls `compile_active_bundle` on the shared PostgreSQL connection, then appends the result via `VersionStore.append(..., commit=False)` in the same transaction as the rule write and `mark_applied` transition. Only `PostgresVersionStore` on the same connection participates in that atomicity; `InMemoryVersionStore` is test-only and does not share DB transactions.
- `ConfigBundle.version` on fleet publish is the distribution plan’s monotonic integer rendered as a decimal string (e.g. plan version `12` → bundle version `"12"`), not the internal `ConfigVersion.version` row counter.
- Production activation with `version_store` set **rejects** an empty compiled `rules` tuple (`EmptyActiveBundleError`); unit-test `compile_bundle` may still emit `rules=()` when explicitly requested.

## Related（相关）

- [ADR-0006 — Configuration Governance](0006-config-governance.md)
- [ADR-0002 — Per-use-case process](0002-per-usecase-process-state-redis.md)
- [`as_platform.api.contract`](../../../platform/src/as_platform/api/contract.py)
- [`as_platform.decision.rules`](../../../platform/src/as_platform/decision/rules.py)
