# `services/config-service/` — rule governance

Owns three things and nothing else:

| Responsibility | Note |
|---|---|
| **Rule version repository** | immutable versions in PostgreSQL; diff and rollback |
| **Change-order state machine** | draft → validation → approval → staged distribution → effective |
| **Distribution** | staged rollout to AS instances, with automatic rollback on unhealthy reports |

## Why it is not GitOps

Operators must not have to learn Git to change a number range. A self-hosted Git
server would also put the availability of rule changes behind the availability of
another distributed system — for a network element that must be able to change a
number range at 03:00. Reasoning in
[`../../docs/architecture/新系统整体架构.md`](../../docs/architecture/新系统整体架构.md) §5.1,
recorded as ADR-0006.

## Boundary

The version repository is **ours**. Approval may be delegated to the operator's
OSS or ticketing system through the `ApprovalGate` abstraction — rule
availability must never depend on a foreign system's availability.

## Contract with an AS instance

An AS instance reports **the rule version it currently has loaded**. That report
is what makes a rolling upgrade safe: during ISSU two versions coexist, so the
rule schema must be bidirectionally compatible (risk R4, ADR-0009).

## Status

Skeleton.
