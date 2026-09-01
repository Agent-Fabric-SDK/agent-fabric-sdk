"""Raw, framework-free LLM client + model listing (§3.2, §3.4).

``fabric.llm.client()`` returns an ``AsyncOpenAI`` pointed at the proxy, sharing
the SDK's shared httpx client so attribution/correlation/auth headers and the
retry policy apply. This is the framework-free surface; the per-framework
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

from typing import TYPE_CHECKING, Any

from ..core.config import FabricConfig
from ..core.errors import ConfigError
from ..core.transport import FabricAsyncClient, proxy_api_key, proxy_auth_headers
from .catalog import ModelHandle, heuristic_capabilities

if TYPE_CHECKING:
    from openai import AsyncOpenAI


class LLMClient:
    """The framework-free proxy client factory."""

    def __init__(self, cfg: FabricConfig, http_client: FabricAsyncClient) -> None:
        self._cfg = cfg
        self._http = http_client

    def client(self, **kw: Any) -> AsyncOpenAI:
        """An ``AsyncOpenAI`` pointed at the LLM proxy, using our shared http
        client so headers + retries apply."""

        self._cfg.validated(need="llm")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - install-time guidance
            raise ImportError(
                "The raw LLM client needs the OpenAI SDK. Install it with:\n"
                '    pip install "mulesoft-agent-fabric[llm]"'
            ) from exc

        assert self._cfg.llm_proxy_url is not None  # validated() guarantees this
        return AsyncOpenAI(
            base_url=self._cfg.llm_proxy_url,  # no /v1 at ingress (§2) — verbatim
            api_key=proxy_api_key(self._cfg),
            default_headers=proxy_auth_headers(self._cfg),  # client_id/secret (§2/§3)
            http_client=self._http,
            max_retries=0,  # we retry in transport (§2.3)
            **kw,
        )

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
