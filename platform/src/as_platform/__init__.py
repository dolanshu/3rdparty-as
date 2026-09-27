"""Kernel of the third-party IMS Application Server.

This package owns what every AS instance shares and nothing that belongs to a
specific use case: the process shell, the B2BUA state machine, the ``decide()``
decision seam, and the two pluggable seams (``Transport``, ``StateStore``).

It must never import an application, a service or the testbed. That one-way rule
is asserted by ``tests/test_library_independence.py`` in this directory.
"""

__all__: list[str] = []
