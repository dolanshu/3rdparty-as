# `testbed/contracts/` — the language-agnostic contract

This directory holds **data, not code**: the case set that every implementation
of an AS use case must satisfy, expressed without reference to Python or Go.

It is the entry ticket for the Go migration (ADR-0012): an implementation may be
promoted only when it reproduces this case set output-for-output against the
Python implementation.

## What belongs here

| Contract | Content |
|---|---|
| rule schema | the declarative rule document, versioned |
| `decide()` case set | inbound request → verdict, one file per scenario |
| OTel semantics | metric names, units, attribute keys, log field set |
| internal API | `/healthz`, `/metrics`, `/traces` request and response shapes |
| configuration distribution | the config-service ↔ AS interface |
| call trace format | the per-message record a Call-ID lookup returns |

## Rules

- A case is **declarative**: input document + expected output document. No
  assertions written in a host language.
- Adding or changing a contract case is an **interface change**: it needs an ADR
  and it re-runs every implementation's gate.
- An implementation that cannot express a case has found a real difference
  between the stacks, not a reason to relax the case.
