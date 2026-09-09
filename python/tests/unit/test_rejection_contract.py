"""The six documented rejection shapes (#181), asserted from the shared
``tests/fixtures/rejections/`` index so the local gateway simulator (#187) can
replay the identical files and any contract drift fails both at once (AC #4).

Rows 1/2/5 alias the live captures under ``anypoint/llm_proxy/`` (referenced, not
moved); rows 3/4/6 (injection, content-moderation, upstream-5xx) live in
``rejections/`` with zero-byte bodies — their shapes are unverified/under-
documented and blocked on #253 (see ``rejections/README.md`` and docs §4). The
discriminator is the error ``type`` + specific headers, NEVER the status code
alone.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from agent_fabric.core.errors import (
    PIIDetected,
    PolicyViolation,
    PromptInjectionBlocked,
    TokenBudgetExceeded,
    UpstreamModelError,
    UpstreamRequestError,
    classify,
)
from agent_fabric.simulator.fixtures import parse_headers

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REJECTIONS = _FIXTURES / "rejections"
LIVE = _FIXTURES / "anypoint" / "llm_proxy"


def _headers(path: Path) -> dict[str, str]:
    """Delegate to the simulator's shared loader so the classify() contract and
    the #187 replay parse the identical files with the identical rule — BG §1.4's
    "same files, both fail together" holds by construction, not convention."""
    return parse_headers(path.read_text())


def _response(base: Path, slug: str, status: int) -> httpx.Response:
    """Build an httpx.Response from a ``reject.<slug>`` fixture pair. An empty
    body is a real captured shape (``.body.empty``), never a guessed body."""
    headers = _headers(base / f"reject.{slug}.headers.txt")
    body_json = base / f"reject.{slug}.body.json"
    if body_json.exists():
        return httpx.Response(status, headers=headers, json=json.loads(body_json.read_text()))
    return httpx.Response(status, headers=headers)  # .body.empty → no body


def test_row1_token_rate_limit_is_token_budget() -> None:
    err = classify(_response(LIVE, "token-rate-limit", 429))
    assert isinstance(err, TokenBudgetExceeded)
    assert err.policy == "token-rate-limit"


def test_row2_pii_detection_is_pii_not_auth() -> None:
    err = classify(_response(LIVE, "pii-detected", 403))
    assert isinstance(err, PIIDetected)
    assert err.policy == "pii-detection"


def test_row3_injection_protection_is_prompt_injection_blocked() -> None:
    err = classify(_response(REJECTIONS, "injection-protection", 400))
    assert isinstance(err, PromptInjectionBlocked)
    assert err.policy == "prompt-injection-protection"
    assert err.remediation  # required, non-empty


def test_row4_content_moderation_falls_through_to_generic_policy_violation() -> None:
    # Under-documented shape: a plain 4xx with no nested error and no injection
    # header must stay a generic PolicyViolation — not be misrouted to
    # PromptInjectionBlocked or UpstreamRequestError (ordering guard).
    err = classify(_response(REJECTIONS, "content-moderation", 400))
    assert type(err) is PolicyViolation
    assert err.policy == "unknown"


def test_row5_upstream_4xx_is_upstream_request_error() -> None:
    body = json.loads((LIVE / "reject.model-not-found.body.json").read_text())
    err = classify(httpx.Response(400, json=body))
    assert isinstance(err, UpstreamRequestError)
    assert not isinstance(err, PolicyViolation)


def test_row6_upstream_5xx_is_retryable_upstream_model_error() -> None:
    err = classify(_response(REJECTIONS, "upstream-5xx", 503))
    assert isinstance(err, UpstreamModelError)
