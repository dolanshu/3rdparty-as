"""Rule governance service (layer ③, control plane).

Owns the rule version repository, the change-order state machine and the staged
distribution of a rule version to AS instances. Stateless: every durable fact
lives in PostgreSQL.
"""

__all__: list[str] = []
