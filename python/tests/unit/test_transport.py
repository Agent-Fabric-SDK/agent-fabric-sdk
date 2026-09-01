"""Transport: header injection, retry policy, no-retry-on-policy-rejection,
401 refresh (§2.3). Uses httpx MockTransport so no network is touched."""

from __future__ import annotations

import httpx
import pytest

from agent_fabric.core._verify import UnverifiedValueWarning
from agent_fabric.core.auth import StaticToken
from agent_fabric.core.config import FabricConfig
from agent_fabric.core.telemetry import current_correlation_id, run_context
from agent_fabric.core.transport import (
    CORRELATION_HEADER,
    FabricAsyncClient,
    FabricClient,
    proxy_auth_headers,
)


def _client(handler, cfg=None, auth=None) -> FabricAsyncClient:
    c = FabricAsyncClient(cfg or FabricConfig(), auth, transport=httpx.MockTransport(handler))
    return c


def _sync_client(handler, cfg=None) -> FabricClient:
    return FabricClient(cfg or FabricConfig(), transport=httpx.MockTransport(handler))


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


# --- blocking twin (client(sync=True)) ------------------------------------
# The point of FabricClient is that a synchronous caller is governed on exactly
# the same terms, so these mirror the async cases above.


def test_sync_correlation_and_attribution_headers_injected() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200)

    cfg = FabricConfig(application_name="hr-agent", business_group="finance")
    # No pytest.warns here: _verify warns once per key per process, so the async
    # case above has already consumed it. That contract is asserted there.
    with _sync_client(handler, cfg) as client:
        with run_context("run-1"):
            client.get("https://x/thing")

    assert seen[CORRELATION_HEADER.lower()] == "run-1"
    assert "hr-agent" in seen.values()
    assert "finance" in seen.values()


def test_sync_requests_do_not_pin_a_correlation_id_to_the_process() -> None:
    """A blocking call outside run_context() must not bind its ID to the ambient
    context: doing so would make every later unrelated call report the same run.
    Async gets away with binding because asyncio.run() isolates the Context."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers[CORRELATION_HEADER])
        return httpx.Response(200)

    with _sync_client(handler) as client:
        client.get("https://x")
        client.get("https://x")

    assert seen[0] != seen[1]  # each call is its own run
    assert current_correlation_id() is None  # nothing leaked out


def test_sync_requests_share_one_id_inside_a_run_context() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers[CORRELATION_HEADER])
        return httpx.Response(200)

    with _sync_client(handler) as client, run_context("run-7"):
        client.get("https://x")
        client.get("https://x")

    assert seen == ["run-7", "run-7"]


def test_sync_retries_on_503_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200)

    with _sync_client(handler, FabricConfig(max_retries=3)) as client:
        resp = client.get("https://x")
    assert resp.status_code == 200
    assert calls["n"] == 3


def test_sync_does_not_retry_4xx_policy_rejection() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400)

    with _sync_client(handler, FabricConfig(max_retries=3)) as client:
        resp = client.get("https://x")
    assert resp.status_code == 400
    assert calls["n"] == 1  # terminal — NOT retried (§2.4)


def test_sync_401_is_terminal_because_there_is_no_token_to_refresh() -> None:
    """The async client retries a 401 once after refreshing. FabricClient takes
    no AuthProvider (async-only protocol), so a 401 is a real credential failure
    and must not be retried."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401)

    with _sync_client(handler, FabricConfig(max_retries=3)) as client:
        resp = client.get("https://x")
    assert resp.status_code == 401
    assert calls["n"] == 1
