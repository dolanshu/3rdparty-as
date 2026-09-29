"""A fake stack under probe: bindings stand-in plus a local replay server.

This module is **self-check scaffolding** for the E1 probe harness
(``testbed/probe/e1_baseline_probe.py``). Its job is to prove that the harness
can run at all: that the bindings gate opens, that a scenario's ``in-*``
messages reach a peer over a real socket, and that what comes back is framed,
compared and folded into an exit code. A harness that cannot run is worse than
a harness that fails, because ADR-0019 consequence K2 would then stay closed
on a probe nobody ever executed.

It is deliberately **not** a model of reSIProcate. The replay server answers
every message the probe delivers with the next ``out-*`` message of the
baseline, in file order. That is a script, not a SIP stack: there are no
transactions, no dialogs, no retransmissions, no timers and no notion of what
a correct response would be. A green run against this peer says the harness is
wired up and the comparison is live; it says nothing whatsoever about the stack
ADR-0019 selected. The real probe has to be run on a host where the
reSIProcate Python bindings import (see ``probe.BINDING_GUIDANCE``), and only
that run can close E1.

Usage, from a test:

    server = ReplayServer(responses)
    try:
        install_fake_bindings(monkeypatch)          # sys.modules["resip"] = ...
        ... run the probe with --host server.host --port server.port
            --bindings-module "resip" ...
    finally:
        server.close()

The port is assigned by the OS (the listening socket binds to port 0), so a
self-check can never collide with a port another test or a real stack holds.
"""

from __future__ import annotations

import contextlib
import socket
import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest

from as_platform.sip.message import header, parse_message

#: The module name the probe imports unless told otherwise
#: (``e1_baseline_probe`` --bindings-module default).
DEFAULT_BINDINGS_MODULE: Final = "resip"

#: Loopback only: the self-check must not be reachable from anywhere else.
DEFAULT_HOST: Final = "127.0.0.1"

RECV_BYTES: Final = 65536

#: How often the listening and the accepted sockets wake up to notice a close.
POLL_SECONDS: Final = 0.2

#: The empty line that ends the header section, one per accepted line break.
HEAD_BODY_SEPARATORS: Final = (b"\r\n\r\n", b"\n\n", b"\r\r")


def make_fake_bindings(name: str = DEFAULT_BINDINGS_MODULE) -> ModuleType:
    """Build a stand-in for the Python bindings of the stack under probe.

    The probe's bindings gate is ``importlib.import_module``: when the module
    is not importable the probe prints guidance and exits 2, and it never
    skips. This stand-in exists to open that gate in a test, and for nothing
    else --- it carries no stack behaviour at all.

    It exposes no ``create_stack_under_probe`` (``probe.BINDINGS_FACTORY``) on
    purpose. With the factory absent the probe falls back to its own socket
    peer, which is what a self-check wants: the harness is then driven end to
    end over a real socket, instead of being handed an object that answers
    in-process and would quietly skip every byte of framing.

    Args:
        name: The module name to give the stand-in. It must be the name the
            probe is told to import through ``--bindings-module``, because
            that is the name the probe looks up.

    Returns:
        The stand-in module, ready to be placed in ``sys.modules``.
    """
    module = ModuleType(name)
    module.__doc__ = (
        "Stand-in for the Python bindings of the stack under probe. "
        "Self-check scaffolding, not a SIP stack; see probe/tests/fake_stack.py."
    )
    return module


def install_fake_bindings(
    monkeypatch: pytest.MonkeyPatch,
    name: str = DEFAULT_BINDINGS_MODULE,
) -> ModuleType:
    """Put the bindings stand-in where the probe will find it.

    Args:
        monkeypatch: The pytest fixture; it undoes the injection after the
            test, so a stand-in never outlives the test that installed it.
        name: The module name to install under.

    Returns:
        The installed stand-in module.
    """
    module = make_fake_bindings(name)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def outbound_messages(directory: Path) -> tuple[bytes, ...]:
    """Read the ``out-*`` messages of one baseline scenario directory.

    Args:
        directory: A capture directory such as
            ``testbed/contracts/sip-baseline/S1-basic-call``.

    Returns:
        The messages the AS emits, in file order --- the files are numbered,
        so name order is wire order.
    """
    return tuple(path.read_bytes() for path in sorted(directory.glob("*-out-*.txt")))


class ReplayServer:
    """A local peer that answers the probe from a fixed list of messages.

    It listens on loopback, on a port the OS assigns, and serves one client at
    a time: for every complete SIP message the client delivers it writes the
    next message of ``responses`` back, in order, and then waits for the next
    one. That is the whole behaviour. It is enough for the probe's request /
    response walk over a scenario, and nothing more.

    Two properties make it usable from a test: :attr:`port` is readable as
    soon as the server exists (so it can be handed to the probe as ``--port``)
    and :meth:`close` shuts the socket and the thread down, so a test can
    release them in a ``finally``.

    When the responses run out the server stops answering and keeps the
    connection open. The probe then waits out its read timeout, gets nothing,
    and reports a message-count difference --- the same verdict a real stack
    that stayed silent would earn.
    """

    def __init__(self, responses: Sequence[bytes], host: str = DEFAULT_HOST) -> None:
        """Bind a loopback port and start serving on a background thread.

        Args:
            responses: The messages to answer with, one per message the probe
                delivers, in order.
            host: The address to listen on; loopback by default.
        """
        self._responses: tuple[bytes, ...] = tuple(responses)
        self._host = host
        self._lock = threading.Lock()
        self._served = 0
        self._closing = threading.Event()

        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((host, 0))
        self._listener.listen(1)
        self._listener.settimeout(POLL_SECONDS)

        self._thread = threading.Thread(
            target=self._accept_loop,
            name="fake-stack-replay",
            daemon=True,
        )
        self._thread.start()

    @property
    def host(self) -> str:
        """The address the server listens on."""
        return self._host

    @property
    def port(self) -> int:
        """The port the OS assigned; hand it to the probe as ``--port``."""
        return int(self._listener.getsockname()[1])

    @property
    def served(self) -> int:
        """How many responses have been handed out so far."""
        with self._lock:
            return self._served

    def close(self) -> None:
        """Shut the server down and release its socket and thread.

        Safe to call more than once.
        """
        self._closing.set()
        with contextlib.suppress(OSError):
            self._listener.close()
        self._thread.join(timeout=2.0)

    def _accept_loop(self) -> None:
        """Serve connections, one at a time, until the server is closed."""
        while not self._closing.is_set():
            try:
                connection, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            try:
                self._serve(connection)
            finally:
                connection.close()

    def _serve(self, connection: socket.socket) -> None:
        """Answer one client until it hangs up or the server is closed.

        Args:
            connection: The accepted socket.
        """
        connection.settimeout(POLL_SECONDS)
        buffer = b""
        while not self._closing.is_set():
            try:
                chunk = connection.recv(RECV_BYTES)
            except TimeoutError:
                continue
            except OSError:
                return
            if not chunk:
                return
            buffer += chunk
            if not _carries_complete_message(buffer):
                continue
            # The probe drives one message at a time and waits for the answer
            # before sending the next, so a complete message is all that can
            # be pending here.
            buffer = b""
            response = self._next_response()
            if response is None:
                continue
            try:
                connection.sendall(response)
            except OSError:
                return

    def _next_response(self) -> bytes | None:
        """Hand out the next response, or ``None`` once they are used up.

        Returns:
            The message to write, or ``None`` when the script is exhausted.
        """
        with self._lock:
            if self._served >= len(self._responses):
                return None
            payload = self._responses[self._served]
            self._served += 1
            return payload


def _carries_complete_message(buffer: bytes) -> bool:
    """Tell whether a buffer already holds one complete SIP message.

    Args:
        buffer: What has been read from the client so far.

    Returns:
        ``True`` once the header section has ended and the body holds at least
        as many bytes as ``Content-Length`` declares (RFC 3261 §20.14). This
        is the same rule the probe's own socket peer applies: on a stream
        transport neither side can know a message ended any other way.
    """
    if not any(separator in buffer for separator in HEAD_BODY_SEPARATORS):
        return False
    try:
        message = parse_message(buffer)
    except ValueError:
        return False
    declared = header(message, "Content-Length")
    if declared is None:
        return True
    try:
        return len(message.body) >= int(declared)
    except ValueError:
        return True
