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
    assert 'mulesoft-agent-fabric[langgraph]' in str(exc.value)


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
