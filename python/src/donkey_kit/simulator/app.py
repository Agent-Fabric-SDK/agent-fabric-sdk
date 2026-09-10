"""``build_app`` — the local gateway simulator's ASGI application (BG §1.4).

A pure-Python HTTP stand-in for the governed LLM proxy. It **replays the same
captured fixtures** ``core.errors.classify()`` is tested against (via
:mod:`donkey_kit.simulator.fixtures`) so a stock ``openai``/``httpx`` client —
or ``donkey.llm.client()`` — sees byte-identical rejection bodies and the exact
discriminator headers, and the SDK's typed refusals light up locally without a
real Anypoint sandbox.

What it is NOT: it enforces no policy, evaluates nothing, and forwards no live
traffic. It is a separate process serving static fixtures. Every response
carries ``x-donkey-simulator: true`` so it can never be mistaken for a real
gateway (BG §1.4, non-negotiable).

Framework isolation (§1.1): ``starlette`` is imported **lazily inside**
:func:`build_app`, never at module top, so ``import donkey_kit.simulator``
stays green under the base-only CI job (``[dev]`` only, no ``[local]`` extra).
The public return type is a framework-free ASGI ``Protocol`` so no ``starlette``
type leaks across the boundary under ``mypy --strict``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from .fixtures import (
    LIMIT_HEADER,
    REMAINING_HEADER,
    RESET_HEADER,
    Fixture,
    load,
    replay_headers,
)

__all__ = ["ASGIApp", "SimulatorConfig", "SIMULATOR_HEADER", "SIM_MODEL_PREFIX", "build_app"]

# BG §1.4 honesty rule: stamped on EVERY response so nothing the simulator emits
# can be mistaken for a real gateway. The bytes form is used by the ASGI wrapper
# (:class:`_HonestyStamp`) that also stamps framework-generated 405/500 responses.
SIMULATOR_HEADER = "x-donkey-simulator"
_SIMULATOR_HEADER_BYTES = SIMULATOR_HEADER.encode("latin-1")

# The ONE fixed, documented, simulator-owned rejection-selection trigger (the
# configurable --scenario engine is a linked follow-up, not #187). A request
# whose model id is "donkey-sim/<shape>" is served that rejection shape. This is
# a simulator control surface only — NEVER a real Omni Gateway behaviour (§0.3).
SIM_MODEL_PREFIX = "donkey-sim/"

# Shapes selectable via the model-id sentinel: the six documented rejections
# plus the consumer-auth 401.
_REJECTION_SHAPES = frozenset(
    {
        "token-rate-limit",
        "pii-detected",
        "injection-protection",
        "content-moderation",
        "model-not-found",
        "upstream-5xx",
        "client-id-missing",
    }
)

class ASGIApp(Protocol):
    """The framework-free ASGI callable :func:`build_app` returns — so callers
    (``httpx.ASGITransport``, ``uvicorn.run``) and ``mypy`` never see a
    ``starlette`` type."""

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[MutableMapping[str, Any]]],
        send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
    ) -> None: ...


@dataclass(frozen=True)
class SimulatorConfig:
    """Tunables for the happy-path ``x-token-*`` synthesis (BG §1.4 / #185/#186).

    The live success capture carries no ``x-token-*`` headers (they are per-request
    stateful counters), so the simulator synthesises a plausible, monotonically
    decreasing budget window. This is a serve-time OVERLAY, recorded as UNVERIFIED
    real-proxy behaviour in ``docs/verified-apis.md`` pending a sandbox capture
    (#253) — it exists so a developer can exercise :class:`~donkey_kit.Budget`
    and its pacing against the simulator.
    """

    token_limit: int = 100_000
    token_step: int = 500
    token_reset_ms: int = 60_000


class _Simulator:
    """Holds the mutable ``x-token-*`` counter (guarded by an ``asyncio.Lock`` so
    concurrent requests can't race it) and builds every response."""

    def __init__(self, config: SimulatorConfig) -> None:
        self._config = config
        self._remaining = config.token_limit
        self._lock = asyncio.Lock()

    def _response(self, fixture: Fixture, extra: dict[str, str] | None = None) -> Any:
        """Build a starlette Response for a resolved fixture, always honesty-stamped."""
        from starlette.responses import Response

        headers = replay_headers(fixture)
        if extra:
            headers.update(extra)
        headers[SIMULATOR_HEADER] = "true"
        return Response(
            content=fixture.body,
            status_code=fixture.status,
            headers=headers,
            media_type=fixture.content_type,
        )

    async def _synth_token_headers(self) -> dict[str, str]:
        """Next synthesised ``x-token-*`` window, decrementing under the lock."""
        async with self._lock:
            self._remaining = max(0, self._remaining - self._config.token_step)
            remaining = self._remaining
        return {
            LIMIT_HEADER: str(self._config.token_limit),
            REMAINING_HEADER: str(remaining),
            RESET_HEADER: str(self._config.token_reset_ms),
        }

    async def dispatch(self, request: Any) -> Any:
        path = request.url.path
        if request.method == "POST" and path.endswith("/responses"):
            return await self._responses(request)
        if request.method == "GET" and path.endswith("/models"):
            # No catalog endpoint is verified; mirror the captured 404 rather
            # than fabricate a model list (§0.3).
            return self._response(load("models-notfound"))
        # Unknown route: an honest, honesty-stamped 404.
        return self._response(load("models-notfound"))

    async def _responses(self, request: Any) -> Any:
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001 — a malformed/empty body is just "happy path"
            payload = {}
        model = payload.get("model") if isinstance(payload, dict) else None
        if isinstance(model, str) and model.startswith(SIM_MODEL_PREFIX):
            shape = model[len(SIM_MODEL_PREFIX) :]
            if shape in _REJECTION_SHAPES:
                return self._response(load(shape))
            # Unknown sentinel suffix falls through to the happy path.
        token_headers = await self._synth_token_headers()
        if isinstance(payload, dict) and payload.get("stream") is True:
            # The captured stream sample is a single, truncated `response.created`
            # event — a real capture, NOT a complete SSE stream ending in
            # `data: [DONE]`. It is replayed verbatim rather than fabricating the
            # remaining events (§0.3: never invent gateway output); a complete
            # SSE capture is a follow-up. It still carries the synthesised budget
            # window, like any happy path.
            return self._response(load("stream"), extra=token_headers)
        return self._response(load("success"), extra=token_headers)


class _HonestyStamp:
    """ASGI wrapper enforcing BG §1.4's *non-negotiable* honesty rule on **every**
    response — including the ``405`` (unsupported method) and ``500`` that
    starlette generates itself, which never pass through
    :meth:`_Simulator._response`. It adds ``x-donkey-simulator: true`` to any
    ``http.response.start`` that does not already carry it (so it never
    duplicates the header ``_response`` already sets)."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[MutableMapping[str, Any]]],
        send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":  # lifespan/websocket: pass through untouched
            await self._app(scope, receive, send)
            return

        async def _stamped(message: MutableMapping[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                headers = message.setdefault("headers", [])
                if not any(key == _SIMULATOR_HEADER_BYTES for key, _ in headers):
                    headers.append((_SIMULATOR_HEADER_BYTES, b"true"))
            await send(message)

        await self._app(scope, receive, _stamped)


def build_app(config: SimulatorConfig | None = None) -> ASGIApp:
    """Build the simulator's ASGI app. ``starlette`` is imported here, lazily, so
    the module stays importable without the ``[local]`` extra.

    Drive it in-process with ``httpx.ASGITransport(app=build_app())`` for
    zero-network tests, or hand it to ``uvicorn`` via
    :func:`donkey_kit.simulator.server.serve` for a real TCP port.

    The app is wrapped in :class:`_HonestyStamp` so the ``x-donkey-simulator``
    header lands on framework-generated ``405``/``500`` responses too.
    """
    from starlette.applications import Starlette
    from starlette.routing import Route

    sim = _Simulator(config or SimulatorConfig())
    routes = [Route("/{path:path}", sim.dispatch, methods=["GET", "POST"])]
    return _HonestyStamp(cast(ASGIApp, Starlette(routes=routes)))
