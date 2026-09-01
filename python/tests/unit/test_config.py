"""Config resolution + all-at-once validation (§2.1)."""

from __future__ import annotations

import pytest

from agent_fabric.core.config import FabricConfig
from agent_fabric.core.errors import ConfigError


def test_validated_reports_all_missing_control_plane_fields_at_once() -> None:
    cfg = FabricConfig()  # nothing set
    with pytest.raises(ConfigError) as exc:
        cfg.validated(need="control_plane")
    msg = str(exc.value)
    # All three must appear in ONE error (§2.1), not one-per-run.
    assert "client_id" in msg
    assert "client_secret" in msg
    assert "org_id" in msg


def test_validated_llm_is_independent_of_control_plane() -> None:
    cfg = FabricConfig(
        llm_proxy_url="https://proxy",
        llm_proxy_client_id="cid",
        llm_proxy_client_secret="csecret",
    )
    # LLM creds present, control-plane absent: llm validation passes (§2.2).
    assert cfg.validated(need="llm") is cfg
    with pytest.raises(ConfigError):
        cfg.validated(need="control_plane")


def test_validated_llm_requires_client_id_and_secret_not_bearer() -> None:
    # Verified auth (§2/§3) is a client_id/secret pair — a bare url + api-key is
    # NOT sufficient, and the error names BOTH missing header credentials at once.
    cfg = FabricConfig(llm_proxy_url="https://proxy", llm_proxy_key="k")
    with pytest.raises(ConfigError) as exc:
        cfg.validated(need="llm")
    msg = str(exc.value)
    assert "llm_proxy_client_id" in msg
    assert "llm_proxy_client_secret" in msg


def test_env_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANYPOINT_CLIENT_ID", "cid")
    monkeypatch.setenv("ANYPOINT_REGION", "eu")
    monkeypatch.setenv("MULESOFT_TELEMETRY", "false")
    cfg = FabricConfig.from_env()
    assert cfg.client_id == "cid"
    assert cfg.region == "eu"
    assert cfg.telemetry is False
    assert cfg.control_plane_url.startswith("https://eu1")


def test_unknown_region_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANYPOINT_REGION", "mars")
    with pytest.raises(ConfigError):
        FabricConfig.from_env()
