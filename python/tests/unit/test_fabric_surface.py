"""Fabric public surface: lazy adapters, curated ImportError, base-package
import safety (working instruction #9)."""

from __future__ import annotations

import pytest

from agent_fabric import Fabric, FabricConfig


def _cfg() -> FabricConfig:
    return FabricConfig(
        llm_proxy_url="https://proxy",
        llm_proxy_client_id="cid",
        llm_proxy_client_secret="csecret",
    )


def test_uninstalled_adapter_raises_curated_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Force "framework not installed" regardless of what happens to be present in
    # the dev env, so the assertion is deterministic: access must raise
    # ImportError with the exact install command, never a bare
    # ModuleNotFoundError (§3.2).
    monkeypatch.setattr("agent_fabric.fabric._framework_installed", lambda _probe: False)
    fab = Fabric(_cfg())
    with pytest.raises(ImportError) as exc:
        _ = fab.langgraph
    assert 'agent-fabric[langgraph]' in str(exc.value)


def test_unknown_attribute_raises_attribute_error() -> None:
    fab = Fabric(_cfg())
    with pytest.raises(AttributeError):
        _ = fab.not_a_framework


def test_openai_agents_adapter_import_error_names_the_new_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Agents SDK adapter lives at ``fabric.openai_agents`` and its curated
    ImportError points at ``agent-fabric[openai-agents]`` (#277)."""
    monkeypatch.setattr("agent_fabric.fabric._framework_installed", lambda _probe: False)
    fab = Fabric(_cfg())
    with pytest.raises(ImportError) as exc:
        _ = fab.openai_agents
    assert 'agent-fabric[openai-agents]' in str(exc.value)


def test_openai_is_a_real_method_not_the_agents_adapter() -> None:
    """``fabric.openai()`` is the raw governed client (`BG §1.1`), returning a
    native ``openai.AsyncOpenAI`` (or ``OpenAI`` with ``sync=True``) — not the
    Agents SDK adapter (#277)."""
    openai = pytest.importorskip("openai")

    with Fabric(_cfg()) as fab:
        assert isinstance(fab.openai(), openai.AsyncOpenAI)
        assert isinstance(fab.openai(sync=True), openai.OpenAI)


def test_openai_never_probes_the_agents_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Because ``openai()`` is a real method it shadows ``__getattr__``: with the
    Agents SDK 'not installed', it still returns a client rather than raising the
    curated ImportError for ``agent-fabric[openai-agents]`` (#277)."""
    openai = pytest.importorskip("openai")
    monkeypatch.setattr("agent_fabric.fabric._framework_installed", lambda _probe: False)

    with Fabric(_cfg()) as fab:
        assert isinstance(fab.openai(), openai.AsyncOpenAI)


def test_run_context_binds_correlation_id() -> None:
    from agent_fabric.core.telemetry import current_correlation_id

    fab = Fabric(_cfg())
    with fab.run_context("abc123") as rid:
        assert rid == "abc123"
        assert current_correlation_id() == "abc123"
    assert current_correlation_id() is None


def test_llm_client_requires_proxy_config() -> None:
    from agent_fabric.core.errors import ConfigError

    fab = Fabric(FabricConfig())  # no proxy creds
    with pytest.raises((ConfigError, ImportError)):
        # ConfigError if openai missing check passes; either way it must not
        # silently build a client without proxy config.
        fab.llm.client()


def test_sync_llm_client_requires_proxy_config() -> None:
    """sync=True must not be a way around the config gate."""
    from agent_fabric.core.errors import ConfigError

    fab = Fabric(FabricConfig())
    with pytest.raises((ConfigError, ImportError)):
        fab.llm.client(sync=True)


def test_client_returns_async_by_default_and_blocking_on_request() -> None:
    openai = pytest.importorskip("openai")

    with Fabric(_cfg()) as fab:
        assert isinstance(fab.llm.client(), openai.AsyncOpenAI)
        assert isinstance(fab.llm.client(sync=True), openai.OpenAI)


def test_both_clients_carry_the_same_governed_configuration() -> None:
    """The blocking client is a transport swap, not a different contract: same
    base URL and same verified client_id/client_secret headers (§2/§3)."""
    pytest.importorskip("openai")

    with Fabric(_cfg()) as fab:
        blocking = fab.llm.client(sync=True)
        asynchronous = fab.llm.client()

    for built in (blocking, asynchronous):
        assert str(built.base_url) == "https://proxy"
        assert built.default_headers["client_id"] == "cid"
        assert built.default_headers["client_secret"] == "csecret"
        assert built.max_retries == 0  # retries belong to the transport (§2.3)


def test_blocking_transport_is_lazy_shared_and_closed_by_the_context_manager() -> None:
    pytest.importorskip("openai")

    fab = Fabric(_cfg())
    assert fab._sync_http is None  # not built until asked for
    with fab:
        fab.llm.client(sync=True)
        transport = fab._sync_http
        assert transport is not None
        fab.llm.client(sync=True)
        assert fab._sync_http is transport  # reused, not rebuilt
    assert transport.is_closed


async def test_aclose_also_closes_a_blocking_transport() -> None:
    """A caller can mix both surfaces; aclose() must not leak the sync pool."""
    pytest.importorskip("openai")

    fab = Fabric(_cfg())
    fab.llm.client(sync=True)
    transport = fab._sync_http
    assert transport is not None
    await fab.aclose()
    assert transport.is_closed
