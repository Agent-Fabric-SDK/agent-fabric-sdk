"""Exception taxonomy (§2.4).

Mapping gateway policy rejections to catchable, actionable exceptions is the
SDK's clearest value over raw HTTP.

Two design points that matter:

1. :class:`PolicyViolation` must be distinguishable from a transient error at
   the framework boundary so host frameworks do not silently retry a refusal.
   It is NEVER retried by our transport.
2. ``remediation`` is a required, human-readable next step — worth more than a
   stack trace.

The concrete HTTP-response → exception mapping lives in :func:`classify`, which
is driven by a table that MUST be populated from real captured fixtures (§8.2),
not hand-written guesses. Until fixtures exist, :func:`classify` maps only the
status-code families it can defensibly infer and otherwise returns a generic
:class:`FabricError`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx


class FabricError(Exception):
    """Base for all SDK errors. Carries correlation/request IDs and the raw
    response so callers can inspect what actually happened."""

    def __init__(
        self,
        message: str,
        *,
        correlation_id: str | None = None,
        request_id: str | None = None,
        response: httpx.Response | None = None,
    ) -> None:
        super().__init__(message)
        self.correlation_id = correlation_id
        self.request_id = request_id
        self.response = response


class ConfigError(FabricError):
    """Configuration is missing or invalid. Reports ALL problems at once (§2.1)."""


class AuthError(FabricError):
    """401/403 on the control plane."""


class PolicyViolation(FabricError):
    """Base for gateway-enforced refusals. NEVER retried.

    ``remediation`` is required: it names the concrete next step, e.g.
    "Token budget exceeded for business group `finance`; limit resets in 42m;
    request an increase in API Manager".
    """

    policy: str = "unknown"

    def __init__(
        self,
        message: str,
        *,
        remediation: str,
        policy: str | None = None,
        **kw: Any,
    ) -> None:
        super().__init__(message, **kw)
        self.remediation = remediation
        if policy is not None:
            self.policy = policy


class TokenBudgetExceeded(PolicyViolation):
    policy = "token-rate-limit"

    def __init__(self, message: str, *, retry_after: float | None = None, **kw: Any) -> None:
        super().__init__(message, **kw)
        self.retry_after = retry_after


class PromptInjectionBlocked(PolicyViolation):
    policy = "prompt-injection-protection"


class ContentSafetyBlocked(PolicyViolation):
    policy = "content-safety"


class PIIDetected(PolicyViolation):
    policy = "pii-detection"

    def __init__(self, message: str, *, entities: list[str] | None = None, **kw: Any) -> None:
        super().__init__(message, **kw)
        self.entities = entities or []


class UpstreamModelError(FabricError):
    """Provider-side failure (5xx). Retryable."""


class UpstreamRequestError(FabricError):
    """The upstream provider rejected the request (4xx), passed through the
    gateway verbatim (e.g. OpenAI ``model_not_found``). This is a client-side
    mistake, NOT a gateway policy refusal and NOT a provider outage, so it is
    terminal (never retried) but distinct from :class:`PolicyViolation`.

    Carries the provider's own ``code``/``type``/``param`` when present so the
    caller can act (fix the model, the params, etc.)."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        error_type: str | None = None,
        param: str | None = None,
        **kw: Any,
    ) -> None:
        super().__init__(message, **kw)
        self.code = code
        self.error_type = error_type
        self.param = param


class ToolInvocationError(FabricError):
    """An MCP tool call failed."""


class RegistryError(FabricError):
    """Exchange discovery / resolution failed."""


class ProvisioningError(FabricError):
    """plan/apply/drift failed."""


class GovernanceDrift(FabricError):
    """resolve(): a declared policy is not actually applied on the gateway (§6.3)."""


class PublicationDrift(FabricError):
    """verify(): the live server no longer matches the Exchange descriptor (§7.4)."""


def classify(response: httpx.Response, *, correlation_id: str | None = None) -> FabricError:
    """Map an HTTP error response to a specific exception.

    The precise policy discrimination (§2.4, working instruction #4) is driven by
    real rejection captures from a live governed LLM proxy (docs §4,
    ``tests/fixtures/anypoint/llm_proxy/reject.*``), NOT hand-written guesses.
    What the captures established:

    * **PII detection** rejects with **403** and a *nested* error object whose
      ``type`` is ``"pii_detected"`` (and, unlike a genuine auth failure, NO
      ``www-authenticate`` header). So a 403 is NOT automatically an auth error —
      the error ``type`` is checked first.
    * **Token rate limit** rejects with **429** and an **empty body**; the budget
      state is entirely in headers (``x-token-limit`` / ``x-token-remaining`` /
      ``x-token-reset`` in ms). There is NO standard ``retry-after``.
    * **client-id-enforcement** rejects with **401** + a *flat-string* ``error``
      and a ``www-authenticate`` header → auth.
    * **Upstream provider passthrough** (e.g. OpenAI ``model_not_found``) is a
      non-429 4xx with a nested error object carrying ``code``/``type``/``param``.

    Policies still not observed live (prompt-injection, content-safety) fall
    through to a generic :class:`PolicyViolation` whose message says so.
    """

    request_id = response.headers.get("x-request-id")
    status = response.status_code
    kw: dict[str, Any] = {
        "correlation_id": correlation_id,
        "request_id": request_id,
        "response": response,
    }

    # A nested ``{"error": {...}}`` object is emitted by BOTH the upstream
    # provider AND some gateway LLM policies (e.g. PII). The ``type`` field —
    # not the status code or the mere presence of a nested object — is the
    # authoritative discriminator (docs §4).
    error_obj = _provider_error_object(response)
    error_type = _str_or_none(error_obj.get("type")) if error_obj is not None else None

    # Gateway PII policy: 403 + nested object, type == "pii_detected". Checked
    # BEFORE the 401/403 → auth rule because a PII block is not an auth failure.
    if error_type == "pii_detected":
        message = _str_or_none(error_obj.get("message")) if error_obj else None
        return PIIDetected(
            message or f"Request blocked: personally identifiable information detected ({status}).",
            entities=_pii_entities(message),
            remediation=(
                "The PII-detection policy blocked this request because the prompt "
                "(or completion) contained personally identifiable information. "
                "Remove or redact the flagged values, or relax the policy's entity "
                "list / action in API Manager."
            ),
            **kw,
        )

    if status in (401, 403):
        return AuthError(
            f"Authentication/authorization failed ({status}). Check the "
            f"connected-app credentials and their scopes (see docs/verified-apis.md §1).",
            **kw,
        )

    # Token rate limit: 429 with an empty body; budget state is header-only
    # (x-token-limit / x-token-remaining / x-token-reset ms). No retry-after.
    if status == 429:
        return TokenBudgetExceeded(
            "Token rate limit or budget exceeded (429).",
            retry_after=_retry_after(response),
            remediation=(
                "A token-rate-limit policy exhausted the budget window. Wait for it "
                "to reset (see retry_after / x-token-reset) or request an increase in "
                "API Manager."
            ),
            **kw,
        )

    # Other non-429 4xx. If the body is the upstream provider envelope (nested
    # error object with code/type), it is a request mistake passed through the
    # gateway; otherwise it is an as-yet-unclassified gateway policy refusal.
    if 400 <= status < 500:
        if error_obj is not None:
            return UpstreamRequestError(
                f"The upstream model provider rejected the request ({status}): "
                f"{error_obj.get('message') or 'see .response'}",
                code=_str_or_none(error_obj.get("code")),
                error_type=error_type,
                param=_str_or_none(error_obj.get("param")),
                **kw,
            )
        return PolicyViolation(
            f"Request refused by a gateway policy ({status}).",
            policy="unknown",
            remediation=(
                "A gateway policy refused this request. This is terminal and was NOT "
                "retried. Only PII (403) and token-budget (429) rejections are "
                "identified from live captures so far; prompt-injection / "
                "content-safety discrimination is pending capture (§8.2). Inspect "
                ".response for the raw body."
            ),
            **kw,
        )

    if 500 <= status < 600:
        return UpstreamModelError(
            f"Upstream/provider failure ({status}). Retryable.",
            **kw,
        )

    return FabricError(f"Unexpected response ({status}).", **kw)


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds until the caller may retry. Prefers the standard ``retry-after``
    (delta-seconds) header; falls back to the LLM token-rate-limit policy's
    ``x-token-reset`` header, which is captured in **milliseconds** (docs §4)."""
    raw = response.headers.get("retry-after")
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            pass  # HTTP-date form; left for the fixture-driven parser (§8.2)
    reset_ms = response.headers.get("x-token-reset")
    if reset_ms is not None:
        try:
            return float(reset_ms) / 1000.0
        except ValueError:
            return None
    return None


_PII_TYPE_RE = re.compile(r'"pii_type"\s*:\s*"([^"]+)"')


def _pii_entities(message: str | None) -> list[str]:
    """Best-effort extraction of the flagged PII entity types from the PII
    policy's rejection message (a JSON-ish list of ``{"pii_type": "...", ...}``
    objects; docs §4). Returns an empty list if none can be parsed."""
    if not message:
        return []
    return _PII_TYPE_RE.findall(message)


def _provider_error_object(response: httpx.Response) -> dict[str, Any] | None:
    """Return the provider's error object iff the body is the upstream-passthrough
    envelope ``{"error": {..object..}}``. An Anypoint policy rejection uses a flat
    ``{"error": "<string>"}`` and returns ``None`` (see docs §4)."""
    try:
        body = response.json()
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return err
    return None


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None
