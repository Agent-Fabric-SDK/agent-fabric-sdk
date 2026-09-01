"""Transport: header injection, retry policy, no-retry-on-policy-rejection,
401 refresh (§2.3). Uses httpx MockTransport so no network is touched."""

from __future__ import annotations

import httpx
import pytest

from agent_fabric.core._verify import UnverifiedValueWarning
from agent_fabric.core.auth import StaticToken
from agent_fabric.core.config import FabricConfig
from agent_fabric.core.telemetry import run_context
from agent_fabric.core.transport import (
    CORRELATION_HEADER,
    FabricAsyncClient,
    proxy_auth_headers,
)


def _client(handler, cfg=None, auth=None) -> FabricAsyncClient:
    c = FabricAsyncClient(cfg or FabricConfig(), auth, transport=httpx.MockTransport(handler))
    return c


async def test_correlation_and_attribution_headers_injected() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200)

    cfg = FabricConfig(application_name="hr-agent", business_group="finance")
    async with _client(handler, cfg) as client:
        with pytest.warns(UnverifiedValueWarning):  # placeholder header names warn (§0.3)
            with run_context("run-1"):
                await client.get("https://x/thing")

    assert seen[CORRELATION_HEADER.lower()] == "run-1"
    # Attribution header values present (names are unverified placeholders).
    assert "hr-agent" in seen.values()
    assert "finance" in seen.values()


def test_proxy_auth_headers_carry_verified_client_id_secret() -> None:
    """§2/§3 (LIVE): the direct-proxy auth is a client_id/client_secret request-
    header pair — verified names, no warning, no bearer."""
    cfg = FabricConfig(
        llm_proxy_url="https://proxy",
        llm_proxy_client_id="cid",
        llm_proxy_client_secret="csecret",
    )
    headers = proxy_auth_headers(cfg)
    assert headers["client_id"] == "cid"
    assert headers["client_secret"] == "csecret"
    assert "Authorization" not in headers  # NOT a bearer credential


def test_proxy_auth_headers_omit_absent_credentials() -> None:
    assert proxy_auth_headers(FabricConfig(llm_proxy_url="https://proxy")) == {}


async def test_retries_on_503_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200)

    async with _client(handler, FabricConfig(max_retries=3)) as client:
        resp = await client.get("https://x")
    assert resp.status_code == 200
    assert calls["n"] == 3


async def test_does_not_retry_4xx_policy_rejection() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400)

    async with _client(handler, FabricConfig(max_retries=3)) as client:
        resp = await client.get("https://x")
    assert resp.status_code == 400
    assert calls["n"] == 1  # terminal — NOT retried (§2.4)


async def test_401_triggers_single_token_refresh() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401) if calls["n"] == 1 else httpx.Response(200)

    async with _client(handler, FabricConfig(), StaticToken("t")) as client:
        resp = await client.get("https://x")
    assert resp.status_code == 200
    assert calls["n"] == 2  # refreshed once, retried once (§2.2)
