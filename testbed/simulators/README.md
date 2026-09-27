# `testbed/simulators/`

Simulated operator network elements. What we do not deliver has to be modelled,
or integration tests have nowhere to run.

| Simulator | Stands in for | Must model |
|---|---|---|
| S-SBC | the operator's boundary | **transparent bridging** and topology hiding, in both directions. The AS's single ISC semantic depends on it (ADR-0003) |
| P-CSCF / S-CSCF | the IMS core | iFC chaining: S-CSCF#1 → S-SBC → AS → S-SBC → S-CSCF#2 … |

Built on the same SIP stack as the AS, so both sides of a test speak identical
protocol behaviour — the same rule the POC applied, and the reason this package
depends on `as-platform`.

Research and CI asset. **Not a v1 deliverable** (ADR-0014).
