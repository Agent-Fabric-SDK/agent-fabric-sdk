"""The conformance harness + suite, driven against toy agents (#191, BG §1.5).

The plugin is the shipped surface, but the logic lives in
:func:`donkey_kit.conformance.harness.run_conformance`: build a fresh
``Donkey`` per scenario, arm the gateway with a captured fixture, drive
``agent.run(...)`` and observe. These tests exercise that logic directly against
in-repo toy agents — a well-behaved one that passes every scenario, and four
deliberately-broken ones that each break *exactly one* thing — so every test
can assert both that the target scenario fails and that the other three still
pass. A regression in any scenario's verdict is caught without a real gateway.

The toy agents call ``donkey.openai()``, so this module needs ``openai`` (the
plugin itself does not — see ``test_conformance_base_only``). Under ``[dev]``
alone the whole module skips.
"""

from __future__ import annotations

import logging

import pytest

pytest.importorskip("openai")

import openai  # noqa: E402 — after importorskip

from donkey_kit.conformance import run_conformance, validate_known_limitations  # noqa: E402
from donkey_kit.conformance.harness import (  # noqa: E402
    ConformanceUsageError,
    _build_agent,
    _offline_config,
)
from donkey_kit.conformance.suite import SCENARIOS  # noqa: E402
from donkey_kit.core.errors import classify  # noqa: E402
from donkey_kit.core.telemetry import current_correlation_id  # noqa: E402
from donkey_kit.donkey import Donkey  # noqa: E402

_LOG = logging.getLogger("donkey_kit.tests.toy_agent")

_MODEL = "gpt-5.1"


def _statuses(results: list) -> dict[str, str]:
    return {r.scenario: r.status for r in results}


def _detail(results: list, scenario: str) -> str:
    return next(r.detail for r in results if r.scenario == scenario)


def _expect_only_failure(results: list, failing: str) -> None:
    """Assert exactly ``failing`` failed and every other scenario passed — the
    heart of these tests: each broken agent trips its own scenario and no other."""
    expected = {s.name: ("fail" if s.name == failing else "pass") for s in SCENARIOS}
    assert _statuses(results) == expected


# --- toy agents --------------------------------------------------------------
# GoodAgent does everything right and passes all four scenarios. Each broken
# agent inherits it and overrides run() to break exactly one behaviour, so its
# test can assert the other three scenarios still pass.


class GoodAgent:
    """Bridges refusals with classify(), never retries a refusal, logs the
    correlation id, and tolerates an absent budget."""

    def __init__(self, donkey: Donkey) -> None:
        self._client = donkey.openai()
        self._budget = donkey.budget

    async def run(self, prompt: str) -> str:
        try:
            resp = await self._client.responses.create(model=_MODEL, input=prompt)
        except openai.APIStatusError as exc:
            # Bridge the raw HTTP refusal to the typed taxonomy — do NOT retry.
            raise classify(exc.response) from exc
        _LOG.info("run complete correlation_id=%s", current_correlation_id())
        # Only reason about the budget when it was actually observed.
        if self._budget.remaining is not None and self._budget.remaining < 0:
            raise RuntimeError("over budget")
        return resp.output_text


class RetriesBudgetAgent(GoodAgent):
    """The headline bug: retries a terminal budget refusal (429) in a loop.
    Every other refusal is still bridged, and success still logs the id — so
    only the retry scenario fails."""

    async def run(self, prompt: str) -> str:
        for attempt in range(3):
            try:
                resp = await self._client.responses.create(model=_MODEL, input=prompt)
            except openai.RateLimitError as exc:  # a 429 budget refusal — retried!
                if attempt == 2:
                    raise classify(exc.response) from exc
                continue
            except openai.APIStatusError as exc:
                raise classify(exc.response) from exc
            _LOG.info("run complete correlation_id=%s", current_correlation_id())
            return resp.output_text
        raise AssertionError("unreachable")


class SwallowsPiiAgent(GoodAgent):
    """Catches the refusal and re-raises a generic RuntimeError, losing the typed
    PIIDetected. Does not retry, so only the PII scenario fails."""

    async def run(self, prompt: str) -> str:
        try:
            resp = await self._client.responses.create(model=_MODEL, input=prompt)
        except openai.APIStatusError as exc:  # swallows the typed refusal
            raise RuntimeError(f"agent failed: {exc}") from exc
        _LOG.info("run complete correlation_id=%s", current_correlation_id())
        return resp.output_text


class DropsCorrelationAgent(GoodAgent):
    """Completes fine and bridges refusals, but never carries the correlation id
    into its logs — so only the correlation scenario fails."""

    async def run(self, prompt: str) -> str:
        try:
            resp = await self._client.responses.create(model=_MODEL, input=prompt)
        except openai.APIStatusError as exc:
            raise classify(exc.response) from exc
        _LOG.info("run complete")  # no correlation id
        return resp.output_text


class CrashesWithoutBudgetAgent(GoodAgent):
    """Assumes budget headers are always present and does arithmetic on
    ``remaining``. It logs the id before crashing (so correlation still passes)
    and only trips over an unobserved budget — so only that scenario fails."""

    async def run(self, prompt: str) -> str:
        try:
            resp = await self._client.responses.create(model=_MODEL, input=prompt)
        except openai.APIStatusError as exc:
            raise classify(exc.response) from exc
        _LOG.info("run complete correlation_id=%s", current_correlation_id())
        # TypeError when remaining is None (no x-token-* headers on the response).
        if self._budget.remaining < 100:  # type: ignore[operator]
            _LOG.warning("low budget")
        return resp.output_text


class SyncGoodAgent:
    """A well-behaved agent on the blocking client, to exercise sync arming."""

    def __init__(self, donkey: Donkey) -> None:
        self._client = donkey.openai(sync=True)
        self._budget = donkey.budget

    def run(self, prompt: str) -> str:
        try:
            resp = self._client.responses.create(model=_MODEL, input=prompt)
        except openai.APIStatusError as exc:
            raise classify(exc.response) from exc
        _LOG.info("run complete correlation_id=%s", current_correlation_id())
        if self._budget.remaining is not None and self._budget.remaining < 0:
            raise RuntimeError("over budget")
        return resp.output_text


# --- the good agents pass everything -----------------------------------------


async def test_good_agent_passes_every_scenario() -> None:
    results = await run_conformance(GoodAgent)
    assert _statuses(results) == {s.name: "pass" for s in SCENARIOS}


async def test_sync_good_agent_passes_every_scenario() -> None:
    # Same guarantees on the blocking surface: the harness arms both transports.
    results = await run_conformance(SyncGoodAgent)
    assert _statuses(results) == {s.name: "pass" for s in SCENARIOS}


# --- each broken agent trips exactly its scenario ----------------------------


async def test_retrying_agent_fails_only_the_retry_scenario() -> None:
    results = await run_conformance(RetriesBudgetAgent)
    _expect_only_failure(results, "retries_token_budget")
    assert "retried" in _detail(results, "retries_token_budget").lower()


async def test_swallowing_agent_fails_only_the_pii_scenario() -> None:
    results = await run_conformance(SwallowsPiiAgent)
    _expect_only_failure(results, "swallows_pii_as_generic")
    assert "swallowed" in _detail(results, "swallows_pii_as_generic").lower()


async def test_dropping_agent_fails_only_the_correlation_scenario() -> None:
    results = await run_conformance(DropsCorrelationAgent)
    _expect_only_failure(results, "correlation_id_propagated")


async def test_crashing_agent_fails_only_the_budget_headers_scenario() -> None:
    results = await run_conformance(CrashesWithoutBudgetAgent)
    _expect_only_failure(results, "works_without_budget_headers")
    assert "TypeError" in _detail(results, "works_without_budget_headers")


# --- exemptions --------------------------------------------------------------


async def test_exemption_marks_scenario_exempt_and_skips_the_run() -> None:
    # Even though this agent WOULD fail the retry scenario, an asserted exemption
    # records it as exempt (with the reason) and does not run the check.
    reason = "this demo agent has no retry loop to exercise"
    results = await run_conformance(
        RetriesBudgetAgent, known_limitations={"retries_token_budget": reason}
    )
    statuses = _statuses(results)
    assert statuses["retries_token_budget"] == "exempt"
    assert _detail(results, "retries_token_budget") == reason
    # Every other scenario still runs and passes for this agent.
    assert statuses["works_without_budget_headers"] == "pass"


async def test_invalid_exemption_raises_before_running() -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        await run_conformance(GoodAgent, known_limitations={"not_a_scenario": "x"})


# --- validate_known_limitations ---------------------------------------------


def test_validate_known_limitations_none_is_empty() -> None:
    assert validate_known_limitations(None) == {}


def test_validate_known_limitations_rejects_non_dict() -> None:
    with pytest.raises(TypeError):
        validate_known_limitations(["retries_token_budget"])


def test_validate_known_limitations_rejects_unknown_scenario() -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        validate_known_limitations({"nope": "reason"})


@pytest.mark.parametrize("reason", ["", "   ", None, 123])
def test_validate_known_limitations_requires_nonempty_reason(reason: object) -> None:
    with pytest.raises(ValueError, match="non-empty reason"):
        validate_known_limitations({"retries_token_budget": reason})


def test_validate_known_limitations_returns_plain_dict() -> None:
    out = validate_known_limitations({"swallows_pii_as_generic": "handled upstream"})
    assert out == {"swallows_pii_as_generic": "handled upstream"}


# --- factory introspection (_build_agent) ------------------------------------


def _fresh_donkey() -> Donkey:
    return Donkey(_offline_config())


def test_build_agent_passes_donkey_positionally() -> None:
    fab = _fresh_donkey()
    try:
        seen = {}

        def factory(donkey: Donkey) -> str:
            seen["donkey"] = donkey
            return "agent"

        assert _build_agent(factory, fab) == "agent"
        assert seen["donkey"] is fab
    finally:
        fab.close()


def test_build_agent_passes_donkey_keyword_only() -> None:
    fab = _fresh_donkey()
    try:
        seen = {}

        def factory(*, donkey: Donkey) -> str:
            seen["donkey"] = donkey
            return "agent"

        assert _build_agent(factory, fab) == "agent"
        assert seen["donkey"] is fab
    finally:
        fab.close()


def test_build_agent_calls_zero_arg_factory_without_donkey() -> None:
    fab = _fresh_donkey()
    try:
        def factory() -> str:
            return "agent"

        assert _build_agent(factory, fab) == "agent"
    finally:
        fab.close()


# --- agent contract errors ---------------------------------------------------


async def test_agent_without_run_raises_usage_error() -> None:
    class NoRun:
        def __init__(self, donkey: Donkey) -> None:
            pass

    with pytest.raises(ConformanceUsageError, match="run"):
        await run_conformance(NoRun)


async def test_harness_runs_scenarios_in_canonical_order() -> None:
    results = await run_conformance(GoodAgent)
    assert [r.scenario for r in results] == [s.name for s in SCENARIOS]
    assert all(isinstance(r.title, str) and r.title for r in results)
