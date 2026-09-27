# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
SemVer, with `./VERSION` as the single home of the product release version
(ADR-0018).

## [0.1.0] - Unreleased

### Added

- Repository skeleton: uv workspace with seven members under
  `platform/`, `apps/`, `services/` and `testbed/`.
- Structural guards: dependency direction (`platform/tests/`), workspace layout
  and version consistency (`tests/`).
- Four-layer CI gate: fast → integration → e2e → performance.
- `AGENT.md` — rules of engagement for the product.
- ADR register mapping the 18 confirmed decisions to ADR numbers, plus the ADR
  template.
- `docs/plan.md` — milestones and the open-item register.
- `docs/migration/triage.md` — inventory and opening classification of the POC
  and library code, with the triage rules that gate adoption.
- `docs/architecture/新系统整体架构.md` — the confirmed design baseline.

### Notes

- No product code yet: the skeleton is deliberately empty of business logic so
  the structure can be reviewed before code moves in.
- CI layers ② ③ ④ are non-blocking until the milestone that first adds a test of
  that kind. See `docs/plan.md` §2.4.
