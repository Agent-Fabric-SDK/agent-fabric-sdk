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


class _RecordingAsync(FabricAsyncClient):
    """Overrides the logical hooks with counters, to assert call-once semantics."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.requests = 0
        self.responses: list[int] = []

    async def _on_request(self, request: httpx.Request) -> None:
        self.requests += 1

    async def _on_response(self, request: httpx.Request, response: httpx.Response) -> None:
        self.responses.append(response.status_code)


class _RecordingSync(FabricClient):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.requests = 0
        self.responses: list[int] = []

    def _on_request(self, request: httpx.Request) -> None:
        self.requests += 1

    def _on_response(self, request: httpx.Request, response: httpx.Response) -> None:
        self.responses.append(response.status_code)


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


# --- lifecycle hooks (BG §1.1, #179) --------------------------------------
# The four seams every Phase 1 feature attaches to: _on_request / _on_response
# fire exactly once per logical send(); _on_refusal is defined but has no caller
# until classify() (#181); _transport is swappable on a live client.


async def test_default_hooks_are_noop_seams() -> None:
    """All four seams exist and the defaults are no-ops (byte-identical
    behaviour to a hookless client — the rest of this module asserts that)."""
    async with _client(lambda r: httpx.Response(200)) as client:
        req = httpx.Request("GET", "https://x")
        assert await client._on_request(req) is None
        assert await client._on_response(req, httpx.Response(200)) is None
        assert await client._on_refusal(None) is None


async def test_on_request_called_once_across_retries() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200)

    client = _RecordingAsync(
        FabricConfig(max_retries=3), None, transport=httpx.MockTransport(handler)
    )
    async with client:
        resp = await client.get("https://x")
    assert resp.status_code == 200
    assert client.requests == 1  # logical request hook fires once, not per wire retry
    assert client.responses == [200]  # response hook sees only the final response


async def test_on_response_not_called_when_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = _RecordingAsync(FabricConfig(), None, transport=httpx.MockTransport(handler))
    async with client:
        with pytest.raises(httpx.ConnectError):
            await client.get("https://x")
    assert client.requests == 1  # request hook ran before the send
    assert client.responses == []  # transport error is never masked by a response hook


async def test_swap_transport_takes_effect_on_the_next_request() -> None:
    async with _client(lambda r: httpx.Response(500)) as client:
        assert (await client.get("https://x")).status_code == 500  # 500 is non-retryable
        client._swap_transport(httpx.MockTransport(lambda r: httpx.Response(200)))
        assert (await client.get("https://x")).status_code == 200


def test_sync_on_request_called_once_across_retries() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200)

    client = _RecordingSync(FabricConfig(max_retries=3), transport=httpx.MockTransport(handler))
    with client:
        resp = client.get("https://x")
    assert resp.status_code == 200
    assert client.requests == 1
    assert client.responses == [200]


def test_sync_on_response_not_called_when_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = _RecordingSync(FabricConfig(), transport=httpx.MockTransport(handler))
    with client:
        with pytest.raises(httpx.ConnectError):
            client.get("https://x")
    assert client.requests == 1
    assert client.responses == []


def test_sync_swap_transport_takes_effect_on_the_next_request() -> None:
    with _sync_client(lambda r: httpx.Response(500)) as client:
        assert client.get("https://x").status_code == 500
        client._swap_transport(httpx.MockTransport(lambda r: httpx.Response(200)))
        assert client.get("https://x").status_code == 200
