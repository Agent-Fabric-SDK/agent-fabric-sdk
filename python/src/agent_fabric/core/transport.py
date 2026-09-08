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
  * retries transient upstream/gateway failures (502/503/504) with exponential
    backoff + jitter, honouring Retry-After
  * does NOT retry 4xx — gateway policy rejections are terminal (§2.4). This
    includes 429: on this proxy a 429 is a token-budget refusal
    (TokenBudgetExceeded), and retrying it only burns the same exhausted window
    (§2.4, #183). retry_after is still surfaced for wait_for_reset() (#186).
  * refreshes the token and retries exactly once on 401 (§2.2)

For frameworks that only accept a ``default_headers`` dict (not a client), pass
:func:`attribution_headers` — a snapshot — and accept that the correlation ID is
per-client rather than per-run. Document that degradation per adapter (§3.3).
"""

from __future__ import annotations

import asyncio
import random
import time

import httpx

from . import _verify
from .auth import AuthProvider
from .budget import Budget
from .config import FabricConfig
from .telemetry import ensure_correlation_id, request_correlation_id

CORRELATION_HEADER = "X-Correlation-Id"
# The OpenAI-compatible SDKs reject an empty ``api_key``. The governed proxy
# authenticates on the client_id/client_secret headers (client-id-enforcement,
# §2/§3) and ignores the bearer, so we fill the slot with a harmless sentinel
# whenever no explicit key is configured.
PROXY_API_KEY_SENTINEL = "client-id-enforced"
# 429 is deliberately NOT here: on this proxy every 429 is a token-budget
# refusal that classify() maps to TokenBudgetExceeded (a PolicyViolation), and a
# PolicyViolation is terminal — retrying it only burns the same exhausted budget
# window (§2.4, #183). Only genuinely transient upstream/gateway failures retry.
_RETRYABLE_STATUS = frozenset({502, 503, 504})
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


def _apply_base_headers(cfg: FabricConfig, request: httpx.Request, correlation_id: str) -> None:
    """Correlation ID + attribution, i.e. everything both transports inject
    without needing to await anything. The ID is passed in because the two
    transports source it differently — see :func:`request_correlation_id`."""
    request.headers[CORRELATION_HEADER] = correlation_id
    for name, value in attribution_headers(cfg).items():
        request.headers[name] = value


def _retry_delay(attempt: int, response: httpx.Response) -> float:
    retry_after = response.headers.get("retry-after")
    if retry_after is not None:
        try:
            return min(float(retry_after), _BACKOFF_CAP_S)
        except ValueError:
            pass  # HTTP-date form not handled here; fall through to backoff
    exp = min(_BACKOFF_BASE_S * (2.0**attempt), _BACKOFF_CAP_S)
    return exp * (0.5 + random.random() / 2.0)  # full-ish jitter


class FabricAsyncClient(httpx.AsyncClient):
    """An ``httpx.AsyncClient`` that injects attribution/correlation/auth headers
    and applies the SDK's retry policy. Every adapter that accepts a custom HTTP
    client MUST be given one of these."""

    def __init__(
        self,
        cfg: FabricConfig,
        auth: AuthProvider | None,
        *,
        budget: Budget | None = None,
        **kw: object,
    ) -> None:
        self._cfg = cfg
        # NB: httpx.AsyncClient uses ``self._auth`` internally, so we must NOT
        # store our token provider there — super().__init__() would clobber it.
        self._token_provider = auth
        # Optional in-band budget collaborator (§1.3, #185). When attached, the
        # response hook feeds it; when None the hook stays a byte-identical no-op,
        # so the control-plane token-fetch client tracks no budget.
        self._budget = budget
        super().__init__(
            timeout=cfg.timeout_s,
            event_hooks={"request": [self._inject_headers]},
            **kw,  # type: ignore[arg-type]
        )

    async def _inject_headers(self, request: httpx.Request) -> None:
        _apply_base_headers(self._cfg, request, ensure_correlation_id())
        if self._token_provider is not None:
            token = await self._token_provider.token()
            # Control plane uses OAuth2 client_credentials → ``Authorization:
            # Bearer`` (VERIFIED §12.1). The LLM proxy (data plane) instead uses
            # client_id/client_secret headers and gets NO token provider, so it
            # never reaches here; ``setdefault`` also yields to the OpenAI SDK's
            # own Authorization if one was set at the call site.
            request.headers.setdefault("Authorization", f"Bearer {token}")

    # --- lifecycle hooks (the skeleton's attachment points, BG §1.1) --------
    # These are the *logical* per-``send()`` seams the Phase 1 six-piece minimum
    # plugs into, distinct from the per-wire ``_inject_headers`` event hook.
    # Internal (underscore-prefixed) extension points for the SDK's own layers,
    # NOT public API. Defaults are no-ops: a hookless client behaves exactly as
    # before. Subclasses/layers override; do not call these directly.

    async def _on_request(self, request: httpx.Request) -> None:
        """Called once, before the retry loop. Attachment point for correlation
        IDs, cost tags and span start (budget/telemetry issues plug in here)."""

    async def _on_response(self, request: httpx.Request, response: httpx.Response) -> None:
        """Called once with the final response returned to the caller (after
        retries and any 401 refresh settle). Attachment point for budget parsing,
        span end and ``classify()``.

        Feeds the attached :class:`Budget` from the response's ``x-token-*``
        headers (#185); a no-op when none is attached. A subclass that overrides
        this hook must call ``super()._on_response(...)`` to keep budget tracking."""
        if self._budget is not None:
            self._budget.observe(response)

    async def _on_refusal(self, violation: object) -> None:
        """Refusal seam for Phase 2 reaction handlers. Defined here so the
        attachment point exists; there is no caller until ``classify()`` (#181)
        produces a typed violation. ``violation`` is typed ``object`` until then."""

    def _swap_transport(self, transport: httpx.AsyncBaseTransport) -> None:
        """Replace the underlying transport on a live client. httpx resolves the
        transport per-send from ``self._transport`` (we mount nothing), so the
        next request uses ``transport`` with no reconstruction. This is the seam
        ``simulate()`` (#190) and ``fabric mock`` (#187) swap a fixture into."""
        self._transport = transport

    async def send(
        self,
        request: httpx.Request,
        **kwargs: object,
    ) -> httpx.Response:
        await self._on_request(request)
        attempts = self._cfg.max_retries + 1
        refreshed_once = False
        last_response: httpx.Response | None = None

        attempt = 0
        while attempt < attempts:
            response = await super().send(request, **kwargs)  # type: ignore[arg-type]
            last_response = response

            provider = self._token_provider
            can_refresh = provider is not None and not refreshed_once
            if response.status_code == 401 and can_refresh:
                assert provider is not None  # narrowed by can_refresh
                refreshed_once = True
                await response.aclose()
                await provider.invalidate()
                # A 401 refresh is an auth re-send, not a rate-limit backoff, so
                # it does NOT consume the retry budget (§2.2: "retry exactly once
                # on 401"): re-send once with the fresh token regardless of
                # `attempt`, so the retry still happens on the final attempt /
                # max_retries=0. Event hooks re-run on send() → fresh token.
                continue

            if response.status_code in _RETRYABLE_STATUS and attempt < attempts - 1:
                delay = _retry_delay(attempt, response)
                await response.aclose()
                await asyncio.sleep(delay)
                attempt += 1
                continue

            return await self._finish(request, response)

        assert last_response is not None  # attempts >= 1
        return await self._finish(request, last_response)

    async def _finish(self, request: httpx.Request, response: httpx.Response) -> httpx.Response:
        """Fire the response hook exactly once, on the final response returned to
        the caller. Retry/refresh ``continue`` branches close their intermediate
        response and loop instead of funnelling through here, so ``_on_response``
        only ever sees the response actually returned — never a closed one.

        A transport-level error escapes ``super().send()`` before we reach here,
        so ``_on_response`` cannot run to mask the underlying HTTP error (AC #4).
        NB: that also means ``_on_request`` has no paired ``_on_response`` on a
        network failure — the future span-lifecycle consumer (#192) must close
        its span in a ``finally`` around the call, not rely on ``_on_response``."""
        await self._on_response(request, response)
        return response


class FabricClient(httpx.Client):
    """The blocking twin of :class:`FabricAsyncClient`, for ``fabric.llm.client(
    sync=True)``.

    It injects the same correlation/attribution headers and applies the same
    retry policy, so a synchronous caller is governed identically to an async
    one. Without it, a sync caller would fall back to whatever bare client the
    framework builds for itself and quietly lose both.

    It takes **no** :class:`AuthProvider`: that protocol is async-only
    (``async def token()``), and there is no correct way to await it from here.
    That costs nothing on the LLM data plane, which authenticates with the
    ``client_id``/``client_secret`` header pair (LIVE-VERIFIED §2/§3) rather than
    a fetched token. It does mean the control-plane surfaces — ``registry`` and
    ``tools`` — stay async-only; see §2.2 for why the two credentials are
    deliberately not conflated.
    """

    def __init__(self, cfg: FabricConfig, *, budget: Budget | None = None, **kw: object) -> None:
        self._cfg = cfg
        self._budget = budget  # see FabricAsyncClient.__init__ (§1.3, #185)
        super().__init__(
            timeout=cfg.timeout_s,
            event_hooks={"request": [self._inject_headers]},
            **kw,  # type: ignore[arg-type]
        )

    def _inject_headers(self, request: httpx.Request) -> None:
        _apply_base_headers(self._cfg, request, request_correlation_id())

    # --- lifecycle hooks (BG §1.1) ------------------------------------------
    # Synchronous twins of the async seams, kept in lockstep so a blocking caller
    # is governed identically. Defaults are no-ops; internal, not public API.

    def _on_request(self, request: httpx.Request) -> None:
        """Called once, before the retry loop (see :meth:`FabricAsyncClient._on_request`)."""

    def _on_response(self, request: httpx.Request, response: httpx.Response) -> None:
        """Called once with the final response returned to the caller. Feeds the
        attached :class:`Budget` (#185); a no-op when none is attached. A subclass
        that overrides this must call ``super()._on_response(...)``."""
        if self._budget is not None:
            self._budget.observe(response)

    def _on_refusal(self, violation: object) -> None:
        """Refusal seam for Phase 2; no caller until ``classify()`` (#181)."""

    def _swap_transport(self, transport: httpx.BaseTransport) -> None:
        """Replace the underlying transport on a live client; the next request
        uses it (see :meth:`FabricAsyncClient._swap_transport`)."""
        self._transport = transport

    def send(self, request: httpx.Request, **kwargs: object) -> httpx.Response:
        self._on_request(request)
        attempts = self._cfg.max_retries + 1
        last_response: httpx.Response | None = None

        for attempt in range(attempts):
            response = super().send(request, **kwargs)  # type: ignore[arg-type]
            last_response = response

            # No 401-refresh branch: with no token provider there is nothing to
            # refresh, so a 401 here is a real credential failure and terminal.
            if response.status_code in _RETRYABLE_STATUS and attempt < attempts - 1:
                delay = _retry_delay(attempt, response)
                response.close()
                time.sleep(delay)
                continue

            return self._finish(request, response)

        assert last_response is not None  # attempts >= 1
        return self._finish(request, last_response)

    def _finish(self, request: httpx.Request, response: httpx.Response) -> httpx.Response:
        """Fire the response hook exactly once, on the response actually returned
        (see :meth:`FabricAsyncClient._finish`)."""
        self._on_response(request, response)
        return response


def build_http_client(
    cfg: FabricConfig,
    auth: AuthProvider | None,
    *,
    budget: Budget | None = None,
) -> FabricAsyncClient:
    """Factory for the shared client (§2.3). Pass ``budget`` to track the in-band
    token window on every response (§1.3, #185); omit it for the control-plane
    token-fetch client, which observes no budget."""
    return FabricAsyncClient(cfg, auth, budget=budget)


def build_sync_http_client(cfg: FabricConfig, *, budget: Budget | None = None) -> FabricClient:
    """Factory for the shared blocking client (§2.3). See :class:`FabricClient`
    for why it takes no :class:`AuthProvider`. Pass ``budget`` to share one budget
    object with the async client (§1.3, #185)."""
    return FabricClient(cfg, budget=budget)
