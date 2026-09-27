# Documentation map

Read by audience. Everything is plain text — Mermaid or ASCII diagrams, never a
rendered image that cannot be diffed.

## Decide what to build

| Document | What it is |
|---|---|
| [`architecture/新系统整体架构.md`](architecture/新系统整体架构.md) | **the design baseline.** Every confirmed decision, its rationale, the open list and the risk register |
| [`architecture/adr/`](architecture/adr/) | decision records; start at its README for the register |
| [`plan.md`](plan.md) | the delivery plan: milestones, sequence, exit criteria |
| [`migration/triage.md`](migration/triage.md) | how POC code is triaged before anything is adopted |

## Build it

| Document | What it is |
|---|---|
| [`../AGENT.md`](../AGENT.md) | **read before writing code.** Rules of engagement, layering, TDD policy, CI gates, git rules |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | environment setup, the local gate, commit and review conventions |
| [`../README.md`](../README.md) | positioning, repository tour, quickstart |

## Run it

| Document | What it is |
|---|---|
| `operations/` | deployment, runbook, troubleshooting — lands with the deployment milestone |
| `acceptance/` | acceptance criteria with evidence per item — lands with the first release milestone |

## Reference

| Document | What it is |
|---|---|
| `glossary.md` | IMS / SIP terminology — lands with the first code milestone |
| `specs/` | normative references (RFC 3261, RFC 4566, RFC 8688, TS 24.229) and message samples |
