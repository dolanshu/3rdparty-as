"""Anti-fraud AS (layer ①, use case).

Single-leg: it screens the caller and either relays the call or answers
`608 Rejected` (RFC 8688) itself. The screening verdict is a pure function; rate
windows and reputation live in the state store, never in process memory.
"""

__all__: list[str] = []
