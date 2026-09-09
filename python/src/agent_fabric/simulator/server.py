"""``serve`` — run the local gateway simulator on a real TCP port (BG §1.4).

A real port (not just the in-process ``httpx.ASGITransport`` path #190's
``simulate()`` uses) is what lets a stock ``openai`` client, ``curl``, or another
process point ``AGENT_FABRIC_LLM_PROXY_URL`` at the simulator and hit it exactly
like the real proxy.

``uvicorn`` is imported lazily inside :func:`serve`, so importing this module
needs no ``[local]`` extra — only *calling* :func:`serve` does. The
``agent-fabric mock`` CLI command relies on that: it translates the
``ImportError`` from a missing ``[local]`` extra into an actionable
``pip install`` message.
"""

from __future__ import annotations

from .app import SimulatorConfig, build_app

__all__ = ["serve"]


def serve(
    *, host: str = "127.0.0.1", port: int = 8080, config: SimulatorConfig | None = None
) -> None:
    """Boot the simulator on ``host:port`` via uvicorn (blocking).

    Raises ``ImportError`` if the ``[local]`` extra (``uvicorn``/``starlette``) is
    not installed — the caller (the CLI) turns that into install guidance.
    """
    import uvicorn  # lazy: provided by the [local] extra

    print(
        f"Agent Fabric local gateway simulator on http://{host}:{port} — every "
        "response carries 'x-fabric-simulator: true'. This is a fixture replay, "
        "NOT a real gateway: it enforces no policy and forwards no traffic.",
        flush=True,  # surface the honesty banner before uvicorn's own startup logs
    )
    uvicorn.run(build_app(config), host=host, port=port, log_level="info")
