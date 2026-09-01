"""Google ADK adapter (§3.3). Tier 1.

ADK is Gemini-first and reaches other providers through the ``LiteLlm`` wrapper,
which takes LiteLLM-format model strings.

Header injection: via LiteLLM's ``extra_headers``. We CANNOT inject our httpx
client — LiteLLM owns the transport. Consequence: transport retries and
correlation-ID-per-run degrade to per-client. This is a documented, asserted
conformance exemption (§8.1 ``correlation_id_propagated``). A LiteLLM custom
logger callback may later recover trace correlation.

Class names / kwargs UNVERIFIED — docs/verified-apis.md §8. ADK requires
``litellm>=1.84`` (floor, not ceiling).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._base import Adapter, default_adapter

if TYPE_CHECKING:
    from google.adk.models.lite_llm import LiteLlm


class ADKAdapter(Adapter):
    extra = "adk"

    def connection_kwargs(self) -> dict[str, Any]:
        """Governed kwargs for a ``LiteLlm(model="openai/<id>", **kwargs)`` you
        build yourself. LiteLLM uses ``api_base``/``extra_headers`` (not
        ``base_url``/``default_headers``) and owns its own transport, so the
        shared http client is not injected here (§3.3 exemption §8.1)."""
        conn = self._openai_connection()
        return {
            "api_base": conn["base_url"],
            "api_key": conn["api_key"],
            "extra_headers": conn["default_headers"],
        }

    def model(self, model: str, **kw: Any) -> LiteLlm:
        from google.adk.models.lite_llm import LiteLlm  # verified: docs §8

        # LiteLLM's OpenAI-compatible route needs the ``openai/`` prefix.
        return LiteLlm(model=f"openai/{model}", **self.connection_kwargs(), **kw)


def model(model: str, **kw: Any) -> LiteLlm:
    """Module-level convenience: a native ``LiteLlm`` at the proxy using a cached
    default env-configured Fabric. Equivalent to
    ``Fabric.from_env().adk.model(model, **kw)``."""
    return default_adapter(ADKAdapter).model(model, **kw)
