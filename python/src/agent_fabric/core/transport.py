"""Transport — the single place headers get injected (§2.3).

This is the most important piece of engineering in the SDK. Every framework has
a different mechanism for setting request headers, and several have none. The
solution is one shared HTTP client that every adapter is handed.

The client:
  * injects, via a request event hook, on every outbound request:
      - correlation ID (uuid4 per logical agent run, from a contextvar, §2.5)
      - attribution headers (application, business group) — header NAMES are
        UNVERIFIED (docs/verified-apis.md §3), emitted via loud placeholders
      - bearer token, refreshed lazily
  * retries on 429/502/503/504 with exponential backoff + jitter, honouring
    Retry-After
  * does NOT retry other 4xx — gateway policy rejections are terminal (§2.4)
  * refreshes the token and retries exactly once on 401 (§2.2)

For frameworks that only accept a ``default_headers`` dict (not a client), pass
:func:`attribution_headers` — a snapshot — and accept that the correlation ID is
per-client rather than per-run. Document that degradation per adapter (§3.3).
"""

from __future__ import annotations

import asyncio
import random

import httpx

from . import _verify
from .auth import AuthProvider
from .config import FabricConfig
from .telemetry import ensure_correlation_id

CORRELATION_HEADER = "X-Correlation-Id"
# The OpenAI-compatible SDKs reject an empty ``api_key``. The governed proxy
# authenticates on the client_id/client_secret headers (client-id-enforcement,
# §2/§3) and ignores the bearer, so we fill the slot with a harmless sentinel
# whenever no explicit key is configured.
PROXY_API_KEY_SENTINEL = "client-id-enforced"
_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 30.0


def attribution_headers(cfg: FabricConfig) -> dict[str, str]:
    """A snapshot of attribution headers for frameworks that only accept a
    ``default_headers`` dict. Does NOT include the correlation ID (which must be
    per-run) or the bearer token (which must be refreshed lazily).

    Header NAMES are UNVERIFIED (§0.3 / §3): the live direct-proxy path did NOT
    surface application/business-group as request headers (docs §3), so these
    remain loud, overridable placeholders. The verified per-agent attribution
    unit is the ``client_id`` credential — see :func:`proxy_auth_headers`.
    """

    headers: dict[str, str] = {}
    if cfg.application_name:
        headers[_verify.ATTRIBUTION_APP_HEADER.get()] = cfg.application_name
    if cfg.business_group:
        headers[_verify.ATTRIBUTION_BUSINESS_GROUP_HEADER.get()] = cfg.business_group
    return headers


def proxy_auth_headers(cfg: FabricConfig) -> dict[str, str]:
    """The LLM-proxy consumer-auth request headers, LIVE-VERIFIED (docs §2/§3):
    a ``client_id`` + ``client_secret`` pair enforced by ``client-id-enforcement``.
    This pair IS the per-agent attribution identity, NOT a bearer token.

    Combined here with :func:`attribution_headers` so a single ``default_headers``
    snapshot carries both when handed to a native framework client. Missing
    credentials are simply omitted — :meth:`FabricConfig.validated` is where the
    absence is reported with actionable guidance.
    """

    headers = attribution_headers(cfg)
    if cfg.llm_proxy_client_id:
        headers[_verify.LLM_PROXY_CLIENT_ID_HEADER] = cfg.llm_proxy_client_id
    if cfg.llm_proxy_client_secret:
        headers[_verify.LLM_PROXY_CLIENT_SECRET_HEADER] = cfg.llm_proxy_client_secret
    return headers


def proxy_api_key(cfg: FabricConfig) -> str:
    """The value for the OpenAI-compatible SDK's mandatory ``api_key`` slot: the
    configured key if any, else :data:`PROXY_API_KEY_SENTINEL` (the proxy ignores
    it and enforces the client_id/secret headers instead)."""
    return cfg.llm_proxy_key or PROXY_API_KEY_SENTINEL


class FabricAsyncClient(httpx.AsyncClient):
    """An ``httpx.AsyncClient`` that injects attribution/correlation/auth headers
    and applies the SDK's retry policy. Every adapter that accepts a custom HTTP
    client MUST be given one of these."""

    def __init__(
        self,
        cfg: FabricConfig,
        auth: AuthProvider | None,
        **kw: object,
    ) -> None:
        self._cfg = cfg
        # NB: httpx.AsyncClient uses ``self._auth`` internally, so we must NOT
        # store our token provider there — super().__init__() would clobber it.
        self._token_provider = auth
        super().__init__(
            timeout=cfg.timeout_s,
            event_hooks={"request": [self._inject_headers]},
            **kw,  # type: ignore[arg-type]
        )

    async def _inject_headers(self, request: httpx.Request) -> None:
        request.headers[CORRELATION_HEADER] = ensure_correlation_id()
        for name, value in attribution_headers(self._cfg).items():
            request.headers[name] = value
        if self._token_provider is not None:
            token = await self._token_provider.token()
            # Control plane uses OAuth2 client_credentials → ``Authorization:
            # Bearer`` (VERIFIED §12.1). The LLM proxy (data plane) instead uses
            # client_id/client_secret headers and gets NO token provider, so it
            # never reaches here; ``setdefault`` also yields to the OpenAI SDK's
            # own Authorization if one was set at the call site.
            request.headers.setdefault("Authorization", f"Bearer {token}")

    async def send(
        self,
        request: httpx.Request,
        **kwargs: object,
    ) -> httpx.Response:
        attempts = self._cfg.max_retries + 1
        refreshed_once = False
        last_response: httpx.Response | None = None

        for attempt in range(attempts):
            response = await super().send(request, **kwargs)  # type: ignore[arg-type]
            last_response = response

            provider = self._token_provider
            can_refresh = provider is not None and not refreshed_once
            if response.status_code == 401 and can_refresh:
                assert provider is not None  # narrowed by can_refresh
                refreshed_once = True
                await response.aclose()
                await provider.invalidate()
                # Event hooks re-run on the next send() → fresh token injected.
                continue

            if response.status_code in _RETRYABLE_STATUS and attempt < attempts - 1:
                delay = self._backoff(attempt, response)
                await response.aclose()
                await asyncio.sleep(delay)
                continue

            return response

        assert last_response is not None  # attempts >= 1
        return last_response

    def _backoff(self, attempt: int, response: httpx.Response) -> float:
        retry_after = response.headers.get("retry-after")
        if retry_after is not None:
            try:
                return min(float(retry_after), _BACKOFF_CAP_S)
            except ValueError:
                pass  # HTTP-date form not handled here; fall through to backoff
        exp = min(_BACKOFF_BASE_S * (2.0**attempt), _BACKOFF_CAP_S)
        return exp * (0.5 + random.random() / 2.0)  # full-ish jitter


def build_http_client(cfg: FabricConfig, auth: AuthProvider | None) -> FabricAsyncClient:
    """Factory for the shared client (§2.3)."""
    return FabricAsyncClient(cfg, auth)
