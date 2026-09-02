"""Raw, framework-free LLM client + model listing (§3.2, §3.4).

``fabric.llm.client()`` returns an ``AsyncOpenAI`` pointed at the proxy, sharing
the SDK's shared httpx client so attribution/correlation/auth headers and the
retry policy apply. ``client(sync=True)`` returns the blocking ``OpenAI`` with
the same governance. This is the framework-free surface; the per-framework
adapters live in ``integrations/``.

VERIFICATION NOTES (LIVE-VERIFIED 2026-08-28, docs/verified-apis.md §2/§3):
  * The proxy base URL does **NOT** include ``/v1``; it is
    ``https://<ingress-gw>/<instance>/`` (e.g. ``…/openai-sdk/``) and the OpenAI
    SDK appends the route (``/responses`` etc.) directly.
  * Auth is a ``client_id`` + ``client_secret`` REQUEST-header pair
    (client-id-enforcement), NOT a bearer token. The OpenAI SDK still requires a
    non-empty ``api_key`` slot, which the proxy ignores.
  * A ``/models`` endpoint does **NOT** exist (confirmed ``404``). ``list_models``
    therefore never fabricates a ``/models`` path; ``live=True`` reports the
    verified absence rather than guessing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, overload

from ..core.config import FabricConfig
from ..core.errors import ConfigError
from ..core.transport import (
    FabricAsyncClient,
    FabricClient,
    build_sync_http_client,
    proxy_api_key,
    proxy_auth_headers,
)
from .catalog import ModelHandle, heuristic_capabilities

if TYPE_CHECKING:
    from openai import AsyncOpenAI, OpenAI


class LLMClient:
    """The framework-free proxy client factory."""

    def __init__(
        self,
        cfg: FabricConfig,
        http_client: FabricAsyncClient,
        sync_http_client: Callable[[], FabricClient] | None = None,
    ) -> None:
        self._cfg = cfg
        self._http = http_client
        # ``Fabric`` passes its own accessor so it owns the blocking transport's
        # lifecycle; standalone use falls back to one owned here.
        self._sync_http = sync_http_client or self._own_sync_client
        self._owned_sync: FabricClient | None = None

    def _own_sync_client(self) -> FabricClient:
        if self._owned_sync is None:
            self._owned_sync = build_sync_http_client(self._cfg)
        return self._owned_sync

    @overload
    def client(self, *, sync: Literal[False] = ..., **kw: Any) -> AsyncOpenAI: ...

    @overload
    def client(self, *, sync: Literal[True], **kw: Any) -> OpenAI: ...

    def client(self, *, sync: bool = False, **kw: Any) -> AsyncOpenAI | OpenAI:
        """An OpenAI client pointed at the LLM proxy, using our shared http client
        so headers + retries apply.

        Defaults to ``AsyncOpenAI``. Pass ``sync=True`` for the blocking
        ``OpenAI``, which is governed identically — same base URL, same verified
        ``client_id``/``client_secret`` headers, same correlation ID and retry
        policy, via :class:`~agent_fabric.core.transport.FabricClient`.

        The two are declared as overloads on ``Literal`` rather than returning a
        union, so the call site narrows to one concrete class and editors keep
        offering completions on the result.
        """

        self._cfg.validated(need="llm")
        try:
            from openai import AsyncOpenAI, OpenAI
        except ImportError as exc:  # pragma: no cover - install-time guidance
            raise ImportError(
                "The raw LLM client needs the OpenAI SDK. Install it with:\n"
                '    pip install "agent-fabric[llm]"'
            ) from exc

        assert self._cfg.llm_proxy_url is not None  # validated() guarantees this
        shared: dict[str, Any] = {
            "base_url": self._cfg.llm_proxy_url,  # no /v1 at ingress (§2) — verbatim
            "api_key": proxy_api_key(self._cfg),
            "default_headers": proxy_auth_headers(self._cfg),  # client_id/secret (§2/§3)
            "max_retries": 0,  # we retry in transport (§2.3)
            **kw,
        }
        # openai 3.x retyped http_client to httpx2.AsyncClient (a distinct class from
        # a separate distribution); our FabricClient/FabricAsyncClient are httpx
        # subclasses, duck-typed fine at runtime. Typecheck-only mismatch — see
        # docs/verified-apis.md (openai >=3.0 row); no upper pin, by design (§8.4).
        if sync:
            return OpenAI(http_client=self._sync_http(), **shared)  # type: ignore[arg-type]
        return AsyncOpenAI(http_client=self._http, **shared)  # type: ignore[arg-type]

    async def list_models(self, *, live: bool = False) -> list[ModelHandle]:
        """List logical models the proxy exposes.

        The governed proxy has **no** catalog endpoint — ``GET /models`` returns
        ``404`` (LIVE-VERIFIED, §2): model-based-routing only routes requests
        that carry ``model`` in the body. So ``live=True`` cannot be satisfied,
        and we say so plainly rather than guess a path. Use :meth:`resolve` for a
        heuristic :class:`ModelHandle` from a known model id, or source the
        catalog from Exchange / provider config (§3.4).
        """

        if live:
            raise ConfigError(
                "The governed LLM proxy exposes no /models endpoint (GET /models "
                "→ 404, verified §2): it only routes requests carrying `model` in "
                "the body. Live model listing is not available from the proxy. Use "
                "resolve(model_id) or source the catalog from Exchange/provider config."
            )
        raise ConfigError(
            "list_models() has no offline source of truth yet, and the proxy has "
            "no /models endpoint to enumerate (verified §2). Use resolve(model_id) "
            "to get a heuristic ModelHandle, or source models from Exchange (§3.4)."
        )

    def resolve(self, model_id: str, *, provider: str | None = None) -> ModelHandle:
        """A heuristic :class:`ModelHandle` for a known model id (§3.4)."""
        return ModelHandle(
            id=model_id,
            provider=provider,
            capabilities=heuristic_capabilities(model_id),
        )
