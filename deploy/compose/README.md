# `deploy/compose/` — developer environment only

Placeholder. Brings up on one machine:

- the two AS use cases, on their own ports
- config-service and console
- Redis and PostgreSQL, single instance, **no** redundancy

Purpose: make the system runnable without a Kubernetes cluster. It is explicitly
not a deployment target, it is not HA, and no capacity figure may be measured
on it (ADR-0013, ADR-0014).
