"""Operations primitives: the verdicts that drive scaling, not the actuators.

This package decides **what may be done** to a running deployment; it never
does it. Nothing here talks to Kubernetes, to Helm or to a cluster API: the
modules are pure functions over the load a caller reports, and the caller —
the operations layer — carries the verdict out and acts on it. Keeping the
two apart is what makes the verdict testable without a cluster (AGENT.md §5:
decision modules are pure, no socket, no clock, no global state).

See ADR-0010.
"""
