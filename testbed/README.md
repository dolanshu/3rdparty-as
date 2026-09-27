# `testbed/` — the test platform (layer ⑥)

Three layers, all of them gating:

| Layer | Directory | What it proves |
|---|---|---|
| ① contract / unit | `contracts/` + each package's `tests/` | the decision is right, and every implementation agrees |
| ② simulated integration | `simulators/` | the AS works against a peer that behaves like the operator's |
| ③ performance | `load/` | where the capacity boundary actually is |

## Why the simulators are a first-class asset

In the delivery environment the S-CSCF and the S-SBC are the operator's network
elements. Locally they can only be simulated. If the iFC chain and the S-SBC
transparent bridge cannot be simulated, integration tests have nowhere to run.

## Rules

- **Load must go over real sockets.** A harness that calls callbacks directly
  measures business logic, not capacity.
- **v1 does not ship the testbed** as a deliverable. It is a research asset;
  customer acceptance-test capability is v1.1.
- SIPp is acceptable here. It is GPL, used **internally only and never
  distributed with the product**.
