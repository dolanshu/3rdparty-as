# Domain docs

This repo is a single-context product. Its application, platform, services, and testbed are parts of one product domain, not separate domain contexts.

## Before exploring

- Read `CONTEXT.md` at the repo root if it exists. Its absence is not a reason to stop or create one pre-emptively.
- Read relevant architecture decisions under `docs/architecture/adr/` before proposing changes in their area.
- Use `docs/architecture/hld.md`, `docs/architecture/lld.md`, and `docs/plan.md` for system design and milestone context where relevant.

## Domain vocabulary

Use the product terms established in `docs/requirements/prd.md` and the architecture documents. When a term is not defined there, preserve the terminology used by the nearest existing requirement or ADR rather than introducing a synonym.

## ADR conflicts

If a proposal or finding contradicts an existing ADR, name the ADR and surface the conflict explicitly. Do not silently override an accepted decision.