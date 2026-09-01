"""errors.classify behaviour (§2.4). Policy rejections must be terminal."""

from __future__ import annotations

import httpx

from agent_fabric.core.errors import (
    AuthError,
    PolicyViolation,
    TokenBudgetExceeded,
    UpstreamModelError,
    classify,
)


def _resp(status: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, headers=headers or {}, request=httpx.Request("POST", "https://x"))


def test_401_is_auth_error() -> None:
    assert isinstance(classify(_resp(401)), AuthError)


def test_generic_4xx_is_terminal_policy_violation() -> None:
    err = classify(_resp(400))
    assert isinstance(err, PolicyViolation)
    assert err.remediation  # required, non-empty (§2.4)


def test_429_is_token_budget_with_retry_after() -> None:
    err = classify(_resp(429, {"retry-after": "42"}))
    assert isinstance(err, TokenBudgetExceeded)
    assert err.retry_after == 42.0


def test_5xx_is_retryable_upstream() -> None:
    assert isinstance(classify(_resp(503)), UpstreamModelError)


def test_policy_violation_is_not_a_retryable_type() -> None:
    # A PolicyViolation must never be an UpstreamModelError (which the transport
    # would retry). Distinct branches of the taxonomy (§2.4).
    assert not issubclass(PolicyViolation, UpstreamModelError)
