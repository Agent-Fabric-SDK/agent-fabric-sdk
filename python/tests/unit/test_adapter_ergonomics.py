"""The two additive adapter ergonomics (§3.1/§3.3), alongside the existing
``fabric.<framework>.<factory>()`` methods:

  1. ``connection_kwargs()`` — governed kwargs you spread into the framework's
     own constructor yourself.
  2. module-level factories (e.g. ``langgraph.chat_model``) backed by a cached
     default env-configured adapter.

These are framework-free where possible: ``connection_kwargs`` and the default
adapter build without importing any framework (adapter modules import their
framework lazily inside the native factory only). Tests that must construct the
native object ``importorskip`` the framework.
"""

from __future__ import annotations

import pytest

from agent_fabric.core.config import FabricConfig
from agent_fabric.core.errors import ConfigError
from agent_fabric.core.transport import build_http_client
from agent_fabric.integrations import _base
from agent_fabric.integrations._base import default_adapter
from agent_fabric.integrations.langgraph import LangGraphAdapter


def _cfg() -> FabricConfig:
    return FabricConfig(
        llm_proxy_url="https://proxy",
        llm_proxy_client_id="cid",
        llm_proxy_client_secret="csecret",
    )


def _adapter() -> LangGraphAdapter:
    cfg = _cfg()
    return LangGraphAdapter(cfg, build_http_client(cfg, None))


def test_connection_kwargs_carry_governed_values() -> None:
    kw = _adapter().connection_kwargs()
    assert kw["base_url"] == "https://proxy"
    assert "client_id" in kw["default_headers"]
    assert "client_secret" in kw["default_headers"]
    assert kw["max_retries"] == 0  # we retry in transport, not the framework
    assert kw["http_async_client"] is not None  # our shared, hooked client
    # No model id — the caller supplies that: ChatOpenAI(model=…, **kw)
    assert "model" not in kw


def test_connection_kwargs_requires_proxy_config() -> None:
    cfg = FabricConfig()  # no proxy creds
    adapter = LangGraphAdapter(cfg, build_http_client(cfg, None))
    with pytest.raises(ConfigError):
        adapter.connection_kwargs()


def test_adk_connection_kwargs_use_litellm_names() -> None:
    # LiteLLM uses api_base/extra_headers rather than base_url/default_headers,
    # and owns its own transport (no shared http client injected).
    from agent_fabric.integrations.adk import ADKAdapter

    cfg = _cfg()
    kw = ADKAdapter(cfg, build_http_client(cfg, None)).connection_kwargs()
    assert kw["api_base"] == "https://proxy"
    assert "client_id" in kw["extra_headers"]
    assert "base_url" not in kw
    assert "http_client" not in kw


def test_default_adapter_is_cached_per_class(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_FABRIC_LLM_PROXY_URL", "https://proxy")
    monkeypatch.setenv("AGENT_FABRIC_LLM_PROXY_CLIENT_ID", "cid")
    monkeypatch.setenv("AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET", "csecret")
    _base._DEFAULT_ADAPTERS.clear()

    a1 = default_adapter(LangGraphAdapter)
    a2 = default_adapter(LangGraphAdapter)
    assert a1 is a2  # cached
    assert isinstance(a1, LangGraphAdapter)


def test_module_level_factory_matches_method(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langchain_openai")
    monkeypatch.setenv("AGENT_FABRIC_LLM_PROXY_URL", "https://proxy")
    monkeypatch.setenv("AGENT_FABRIC_LLM_PROXY_CLIENT_ID", "cid")
    monkeypatch.setenv("AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET", "csecret")
    _base._DEFAULT_ADAPTERS.clear()

    from agent_fabric.integrations.langgraph import chat_model

    model = chat_model("gpt-4o", temperature=0.1)
    assert type(model).__name__ == "ChatOpenAI"  # native object, no wrapper
    assert model.openai_api_base == "https://proxy"
    assert model.temperature == 0.1  # kwargs pass through
