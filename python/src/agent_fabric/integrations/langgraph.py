"""LangGraph / LangChain adapter (§3.3). Tier 1.

Header injection: FULL (``default_headers`` + custom async http client). This is
the best-case adapter.

All class names / kwargs are UNVERIFIED until §0.3 — see docs/verified-apis.md §8.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._base import Adapter, default_adapter

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI


class LangGraphAdapter(Adapter):
    extra = "langgraph"

    def connection_kwargs(self) -> dict[str, Any]:
        """Governed kwargs to spread into a ``ChatOpenAI(model=…, **kwargs)`` you
        build yourself (§3.1). Same values the factory uses — one source of
        truth for the proxy connection."""
        conn = self._openai_connection()
        return {
            **conn,  # base_url, api_key, default_headers
            "http_async_client": self._http_client(),  # our client, our hooks
            "max_retries": 0,  # we retry in transport (§2.3)
        }

    def chat_model(self, model: str, **kw: Any) -> ChatOpenAI:
        """Return a native ``ChatOpenAI`` pointed at the proxy (§3.1)."""
        from langchain_openai import ChatOpenAI  # verified name: docs §8

        return ChatOpenAI(model=model, **self.connection_kwargs(), **kw)


def chat_model(model: str, **kw: Any) -> ChatOpenAI:
    """Module-level convenience: a native ``ChatOpenAI`` at the proxy using a
    cached default :class:`~agent_fabric.Fabric` configured from the environment.
    Equivalent to ``Fabric.from_env().langgraph.chat_model(model, **kw)``."""
    return default_adapter(LangGraphAdapter).chat_model(model, **kw)
