"""Conformance-suite fixtures.

The ``simulator_base_url`` fixture boots the local gateway simulator (BG §1.4) on
a real ephemeral TCP port via uvicorn, in a daemon thread, and tears it down
after the session. This is the out-of-process path a stock client hits exactly
like the real proxy — distinct from the in-process ``httpx.ASGITransport`` path
the unit tests use.

Only ``local_gateway``-marked tests request it, and that marker is deselected by
default (``addopts`` in ``pyproject.toml``), so the server is never booted on a
plain ``pytest -q``. ``importorskip`` keeps it honest when the ``[local]`` extra
is absent even under ``pytest -m local_gateway``.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator

import pytest


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port: int = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture(scope="session")
def simulator_base_url() -> Iterator[str]:
    uvicorn = pytest.importorskip("uvicorn")
    pytest.importorskip("starlette")
    from donkey_kit.simulator import build_app

    port = _free_port()
    config = uvicorn.Config(build_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10.0
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5.0)
        raise RuntimeError("local gateway simulator did not start within 10s")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10.0)
