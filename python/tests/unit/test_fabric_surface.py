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
