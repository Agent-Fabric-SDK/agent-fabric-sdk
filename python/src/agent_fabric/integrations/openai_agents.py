"""OpenAI Agents SDK adapter (``fabric.openai``) (§3.3). Tier 1.

The OpenAI Agents SDK (pip ``openai-agents``, import ``agents``) models a
provider as an ``OpenAIChatCompletionsModel`` wrapping an ``AsyncOpenAI`` client.
Because we construct that client ourselves, header AND transport injection are
both available (full injection) — the preferred pattern anywhere a framework
accepts a pre-built OpenAI client (§3.3).

Point the SDK's *model* at the proxy per-agent rather than mutating the global
default client, so one process can mix governed and ungoverned models.

Class names / kwargs UNVERIFIED — docs/verified-apis.md §8.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._base import Adapter, default_adapter

if TYPE_CHECKING:
    from agents import OpenAIChatCompletionsModel


class OpenAIAgentsAdapter(Adapter):
    extra = "openai"

    def _proxy_openai_client(self) -> Any:
        """A native ``AsyncOpenAI`` client bound to the proxy: our shared http
        client + the verified consumer-auth headers. One source of truth for the
        governed connection (§3.1)."""
        conn = self._openai_connection()
        from openai import AsyncOpenAI

        return AsyncOpenAI(
            base_url=conn["base_url"],
            api_key=conn["api_key"],
            default_headers=conn["default_headers"],
            http_client=self._http_client(),
            max_retries=0,  # we retry in transport (§2.3)
        )

    def model(self, model: str, **kw: Any) -> OpenAIChatCompletionsModel:
        """Return a native ``OpenAIChatCompletionsModel`` pointed at the proxy,
        ready to pass into ``agents.Agent(model=...)`` (§3.1)."""
        from agents import OpenAIChatCompletionsModel  # verified: docs §8

        return OpenAIChatCompletionsModel(
            model=model,
            openai_client=self._proxy_openai_client(),
            **kw,
        )


def model(model: str, **kw: Any) -> OpenAIChatCompletionsModel:
    """Module-level convenience: a native ``OpenAIChatCompletionsModel`` at the
    proxy using a cached default env-configured Fabric. Equivalent to
    ``Fabric.from_env().openai.model(model, **kw)``."""
    return default_adapter(OpenAIAgentsAdapter).model(model, **kw)
