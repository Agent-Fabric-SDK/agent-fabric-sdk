"""Budget: the first-class object parsed from the LLM proxy's ``x-token-*``
headers (§1.3 / BG §1.3, #185). No network is touched — headers are attached to
constructed ``httpx.Response`` objects, and the transport wiring is exercised via
``httpx.MockTransport``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from donkey_kit import Budget, Donkey
from donkey_kit.core.budget import Budget as CoreBudget
from donkey_kit.core.config import DonkeyConfig
from donkey_kit.core.transport import DonkeyAsyncClient, DonkeyClient

_FIXED_NOW = datetime(2026, 9, 8, 14, 0, 0, tzinfo=timezone.utc)


def _resp(status: int = 200, **headers: str) -> httpx.Response:
    return httpx.Response(status, headers=headers)


# --- the object in isolation ----------------------------------------------


def test_budget_starts_unobserved() -> None:
    b = Budget()
    assert b.limit is None
    assert b.remaining is None
    assert b.reset_at is None
    assert b.observed_at is None
    assert b.fraction_used is None  # unobserved, not zero — nothing seen yet


def test_reset_ms_converts_to_reset_at_to_the_second() -> None:
    """AC: x-token-reset is milliseconds *to* reset (a delta, docs §4), so
    reset_at = observed_at + that delta. Injected clock makes it exact."""
    b = Budget()
    b.observe(
        _resp(**{"x-token-limit": "1000", "x-token-remaining": "250", "x-token-reset": "60000"}),
        now=_FIXED_NOW,
    )
    assert b.limit == 1000
    assert b.remaining == 250
    assert b.observed_at == _FIXED_NOW
    assert b.reset_at == _FIXED_NOW + timedelta(seconds=60)


def test_fraction_used_math() -> None:
    b = Budget()
    b.observe(_resp(**{"x-token-limit": "1000", "x-token-remaining": "250"}), now=_FIXED_NOW)
    assert b.fraction_used == 0.75


def test_fraction_used_guards_zero_limit() -> None:
    b = Budget()
    b.observe(_resp(**{"x-token-limit": "0", "x-token-remaining": "0"}), now=_FIXED_NOW)
    assert b.fraction_used is None  # no division by zero


def test_fraction_used_clamped_to_unit_interval() -> None:
    b = Budget()
    # remaining above limit (a window that reset between calls) must not go negative
    b.observe(_resp(**{"x-token-limit": "100", "x-token-remaining": "150"}), now=_FIXED_NOW)
    assert b.fraction_used == 0.0


def test_missing_headers_leave_object_unobserved_and_do_not_raise() -> None:
    """AC: a response with no x-token-* headers is a defined no-op — observed_at
    stays None so nobody mistakes 'never seen' for 'seen, empty'."""
    b = Budget()
    b.observe(_resp(200), now=_FIXED_NOW)  # a happy-path response without budget headers
    assert b.limit is None
    assert b.remaining is None
    assert b.reset_at is None
    assert b.observed_at is None
    assert b.fraction_used is None


def test_partial_headers_update_only_what_is_present() -> None:
    b = Budget()
    b.observe(
        _resp(**{"x-token-limit": "1000", "x-token-remaining": "800", "x-token-reset": "30000"}),
        now=_FIXED_NOW,
    )
    later = _FIXED_NOW + timedelta(seconds=5)
    # A later response carrying only remaining: limit/reset_at persist, observed_at moves.
    b.observe(_resp(**{"x-token-remaining": "600"}), now=later)
    assert b.limit == 1000  # persisted
    assert b.remaining == 600  # updated
    assert b.reset_at == _FIXED_NOW + timedelta(seconds=30)  # persisted
    assert b.observed_at == later  # freshness moved


def test_non_numeric_headers_are_ignored_not_fatal() -> None:
    b = Budget()
    b.observe(_resp(**{"x-token-limit": "lots", "x-token-remaining": "500"}), now=_FIXED_NOW)
    assert b.limit is None  # garbage ignored
    assert b.remaining == 500  # the parseable one still landed
    assert b.observed_at == _FIXED_NOW


def test_top_level_export_is_the_core_object() -> None:
    assert Budget is CoreBudget


# --- transport wiring: _on_response feeds the budget -----------------------


async def test_async_client_updates_attached_budget_on_response() -> None:
    b = Budget()

    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(
            **{"x-token-limit": "1000", "x-token-remaining": "900", "x-token-reset": "1000"}
        )

    client = DonkeyAsyncClient(
        DonkeyConfig(), None, budget=b, transport=httpx.MockTransport(handler)
    )
    async with client:
        await client.get("https://x")
    assert b.limit == 1000
    assert b.remaining == 900
    assert b.observed_at is not None  # stamped by the real clock in the hook


async def test_async_client_without_budget_is_a_noop_seam() -> None:
    """No budget attached → the hook stays byte-identical to a hookless client."""
    client = DonkeyAsyncClient(
        DonkeyConfig(), None, transport=httpx.MockTransport(lambda r: _resp(200))
    )
    async with client:
        resp = await client.get("https://x")
    assert resp.status_code == 200  # nothing raised, nothing to observe


def test_sync_client_updates_attached_budget_on_response() -> None:
    b = Budget()

    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(**{"x-token-limit": "500", "x-token-remaining": "100"})

    client = DonkeyClient(DonkeyConfig(), budget=b, transport=httpx.MockTransport(handler))
    with client:
        client.get("https://x")
    assert b.limit == 500
    assert b.remaining == 100
    assert b.fraction_used == 0.8


# --- Donkey-level: budget is per-instance ----------------------------------


def test_donkey_exposes_a_budget() -> None:
    donkey = Donkey(DonkeyConfig())
    assert isinstance(donkey.budget, Budget)
    assert donkey.budget.observed_at is None  # unobserved until the first call returns
    assert donkey._http._budget is donkey.budget  # the shared client feeds this object


def test_two_donkeys_never_share_budget_state() -> None:
    """AC: per-Donkey, not global. Two instances with different credentials must
    not share budget state."""
    f1 = Donkey(DonkeyConfig(llm_proxy_client_id="a"))
    f2 = Donkey(DonkeyConfig(llm_proxy_client_id="b"))
    assert f1.budget is not f2.budget
    f1.budget.observe(_resp(**{"x-token-limit": "1000", "x-token-remaining": "1"}), now=_FIXED_NOW)
    assert f2.budget.remaining is None  # untouched


async def test_donkey_budget_updates_through_the_shared_client() -> None:
    donkey = Donkey(DonkeyConfig())
    donkey._http._swap_transport(
        httpx.MockTransport(
            lambda r: _resp(**{"x-token-limit": "2000", "x-token-remaining": "1500"})
        )
    )
    async with donkey._http as client:
        await client.get("https://proxy/chat/completions")
    assert donkey.budget.limit == 2000
    assert donkey.budget.remaining == 1500
    assert donkey.budget.fraction_used == 0.25
