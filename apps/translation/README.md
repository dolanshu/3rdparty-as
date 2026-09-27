# `apps/translation/` — number translation AS

Two-legged B2BUA. It terminates the trunk INVITE from the S-SBC (UAS), applies
the translation and routing decision, and originates a new INVITE back through
the S-SBC (UAC) with a new Call-ID.

**In scope here:** the decision. Declarative rules in, a verdict out.

**Not in scope here:** SIP mechanics (they live in `platform/`), session state
(it lives in Redis), rule storage and approval (they live in
`services/config-service/`).

## Shape

| Concern | Where |
|---|---|
| `decide()` implementation | this package, over the kernel's seam |
| translation and routing rules | pure functions, no sockets, no clock, TDD'd |
| rule documents | delivered by config-service, versioned, with a compatibility matrix |
| session state | Redis through the `StateStore` seam |

## Status

Skeleton. The decision module is the first thing written here, and it is written
test-first: it is the highest-value TDD target in the repository.
