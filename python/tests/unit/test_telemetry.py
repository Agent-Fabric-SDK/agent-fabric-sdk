"""GenAI span contract (#192, BG §1.6): a pinned OTel gen_ai.* namespace and a
stable fabric.* namespace, dual-emitted on ONE span.

The acceptance bar this module encodes:

- The semantic-convention version is pinned in a single constant, and the keys
  are transcribed literals — not re-exported from the installed
  ``opentelemetry.semconv`` package — so upgrading that package never silently
  changes what we emit (AC #1/#2). Every gen_ai.* and fabric.* key has a test
  asserting the exact string (AC #3); the fabric.* keys are public API, so a
  rename breaks these tests loudly (AC #4).
- ``build_genai_attributes`` is the pure assembler both namespaces flow through;
  it omits any field left ``None`` so an unobserved value is absent, never a
  placeholder.
- ``genai_span`` puts both namespaces on the *same* span named
  :data:`SPAN_LLM_CHAT` (AC #5), and is an inert no-op when telemetry is off or
  OpenTelemetry is not installed — telemetry is never a hard dependency.

The dual-namespace span assertion needs the OTel SDK; it ``importorskip``s so
the base-only install skips it while the ``otel`` extra runs it in CI.
"""

from __future__ import annotations

import pytest

from agent_fabric.core import telemetry
from agent_fabric.core.errors import (
    AuthError,
    ContentSafetyBlocked,
    FabricError,
    PIIDetected,
    PolicyViolation,
    PromptInjectionBlocked,
    TokenBudgetExceeded,
    UpstreamModelError,
    UpstreamRequestError,
)

# --- the pinned semconv version + the literal keys (AC #1-#4) ---------------


def test_semconv_version_is_pinned_in_one_constant() -> None:
    # Bumping this is the deliberate single-file change AC #2 requires. If this
    # value changes, a CHANGELOG entry must accompany it.
    assert telemetry.GEN_AI_SEMCONV_VERSION == "1.30.0"


def test_gen_ai_keys_are_the_pinned_literal_strings() -> None:
    # Transcribed literals at the pinned version — NOT imported from
    # opentelemetry.semconv, so the installed package's default can drift without
    # changing what we emit (AC #1).
    assert telemetry.GEN_AI_SYSTEM == "gen_ai.system"
    assert telemetry.GEN_AI_REQUEST_MODEL == "gen_ai.request.model"
    assert telemetry.GEN_AI_USAGE_INPUT_TOKENS == "gen_ai.usage.input_tokens"
    assert telemetry.GEN_AI_USAGE_OUTPUT_TOKENS == "gen_ai.usage.output_tokens"


def test_fabric_keys_are_the_stable_public_literal_strings() -> None:
    # These are PUBLIC API (AC #4): renaming one is a breaking change, and this
    # test is the tripwire that makes that break loud.
    assert telemetry.FABRIC_CORRELATION_ID == "fabric.correlation_id"
    assert telemetry.FABRIC_POLICY_DECISION == "fabric.policy.decision"
    assert telemetry.FABRIC_POLICY_TYPE == "fabric.policy.type"
    assert telemetry.FABRIC_BUDGET_REMAINING == "fabric.budget.remaining"
    assert telemetry.FABRIC_COST_TEAM == "fabric.cost.team"


def test_policy_decision_values_are_the_documented_literals() -> None:
    assert telemetry.POLICY_DECISION_ALLOW == "allow"
    assert telemetry.POLICY_DECISION_REFUSE == "refuse"


# --- build_genai_attributes: the pure dual-namespace assembler --------------


def test_build_genai_attributes_emits_every_key_when_all_present() -> None:
    attrs = telemetry.build_genai_attributes(
        system="openai",
        request_model="gpt-4o",
        input_tokens=1420,
        output_tokens=310,
        decision=telemetry.POLICY_DECISION_ALLOW,
        policy_type="pii_detected",
        budget_remaining=18450,
        cost_team="support",
        correlation_id="run-7f3a",
    )
    assert attrs == {
        "gen_ai.system": "openai",
        "gen_ai.request.model": "gpt-4o",
        "gen_ai.usage.input_tokens": 1420,
        "gen_ai.usage.output_tokens": 310,
        "fabric.policy.decision": "allow",
        "fabric.policy.type": "pii_detected",
        "fabric.budget.remaining": 18450,
        "fabric.cost.team": "support",
        "fabric.correlation_id": "run-7f3a",
    }


def test_build_genai_attributes_omits_none_fields() -> None:
    # An unobserved value is absent, never emitted as a null/placeholder — a
    # request-only span (before the response) carries just the request model.
    attrs = telemetry.build_genai_attributes(request_model="gpt-4o")
    assert attrs == {"gen_ai.request.model": "gpt-4o"}


def test_build_genai_attributes_empty_when_nothing_observed() -> None:
    assert telemetry.build_genai_attributes() == {}


def test_build_genai_attributes_keeps_zero_token_counts() -> None:
    # 0 tokens is a real observation (an empty completion), distinct from None.
    attrs = telemetry.build_genai_attributes(input_tokens=0, output_tokens=0)
    assert attrs["gen_ai.usage.input_tokens"] == 0
    assert attrs["gen_ai.usage.output_tokens"] == 0


# --- policy_type_slug: classified refusal -> fabric.policy.type -------------


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TokenBudgetExceeded("x", remediation="r"), "token_budget"),
        (PIIDetected("x", remediation="r"), "pii_detected"),
        (PromptInjectionBlocked("x", remediation="r"), "injection"),
        (ContentSafetyBlocked("x", remediation="r"), "content_safety"),
        (PolicyViolation("x", remediation="r"), "policy_violation"),
    ],
)
def test_policy_type_slug_maps_each_policy_violation(error: FabricError, expected: str) -> None:
    assert telemetry.policy_type_slug(error) == expected


@pytest.mark.parametrize(
    "error",
    [
        AuthError("x"),
        UpstreamRequestError("x"),
        UpstreamModelError("x"),
        FabricError("x"),
    ],
)
def test_policy_type_slug_is_none_for_non_policy_errors(error: FabricError) -> None:
    # Auth / upstream / transport failures carry no governance allow-or-refuse
    # decision, so they map to None — the transport omits the decision rather
    # than misreporting one.
    assert telemetry.policy_type_slug(error) is None


def test_policy_type_slug_prefers_the_most_specific_subclass() -> None:
    # PIIDetected is a PolicyViolation; the specific slug must win over the base.
    assert telemetry.policy_type_slug(PIIDetected("x", remediation="r")) == "pii_detected"


# --- genai_span: inert unless telemetry is on AND OTel is installed ----------


def test_genai_span_disabled_yields_an_inert_handle() -> None:
    with telemetry.genai_span(enabled=False) as gspan:
        # record() must be a safe no-op — no span, no crash.
        gspan.record(system="openai", request_model="gpt-4o", input_tokens=5)


def test_genai_span_without_otel_is_inert(monkeypatch: pytest.MonkeyPatch) -> None:
    # Enabled, but OTel absent (tracer is None): still a no-op, never an error.
    monkeypatch.setattr(telemetry, "_tracer", lambda: None)
    with telemetry.genai_span(enabled=True) as gspan:
        gspan.record(system="openai", input_tokens=5)


# --- genai_span: both namespaces on ONE span (AC #5) ------------------------


def _in_memory_tracer():
    """A real OTel tracer wired to an in-memory exporter, or skip if the SDK
    (the ``otel`` extra) is not installed."""
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("agent_fabric.test"), exporter


def test_genai_span_puts_both_namespaces_on_one_span(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer, exporter = _in_memory_tracer()
    monkeypatch.setattr(telemetry, "_tracer", lambda: tracer)

    with telemetry.genai_span(enabled=True) as gspan:
        gspan.record(request_model="gpt-4o")  # recorded at span start
        gspan.record(  # recorded after the response settles
            system="openai",
            input_tokens=1420,
            output_tokens=310,
            decision=telemetry.POLICY_DECISION_ALLOW,
            budget_remaining=18450,
            correlation_id="run-7f3a",
        )

    spans = exporter.get_finished_spans()
    assert len(spans) == 1  # AC #5: ONE span, never two
    span = spans[0]
    assert span.name == telemetry.SPAN_LLM_CHAT
    attrs = dict(span.attributes)
    # gen_ai.* (pinned) and fabric.* (stable) coexist on the same span.
    assert attrs["gen_ai.system"] == "openai"
    assert attrs["gen_ai.request.model"] == "gpt-4o"
    assert attrs["gen_ai.usage.input_tokens"] == 1420
    assert attrs["gen_ai.usage.output_tokens"] == 310
    assert attrs["fabric.policy.decision"] == "allow"
    assert attrs["fabric.budget.remaining"] == 18450
    assert attrs["fabric.correlation_id"] == "run-7f3a"


def test_genai_span_records_a_refusal_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer, exporter = _in_memory_tracer()
    monkeypatch.setattr(telemetry, "_tracer", lambda: tracer)

    with telemetry.genai_span(enabled=True) as gspan:
        gspan.record(
            decision=telemetry.POLICY_DECISION_REFUSE,
            policy_type="token_budget",
        )

    (span,) = exporter.get_finished_spans()
    attrs = dict(span.attributes)
    assert attrs["fabric.policy.decision"] == "refuse"
    assert attrs["fabric.policy.type"] == "token_budget"


# --- set_error: refusals/exceptions mark the span ERROR (#193, AC #1/#4) -----


def test_genai_span_set_error_is_inert_without_a_span() -> None:
    # Off / OTel absent → GenAiSpan(None): set_error() and end() are safe no-ops,
    # never a crash and never a hard OTel import.
    gspan = telemetry.GenAiSpan(None)
    gspan.set_error()
    gspan.end()


def test_genai_span_set_error_sets_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    from opentelemetry.trace import StatusCode

    tracer, exporter = _in_memory_tracer()
    monkeypatch.setattr(telemetry, "_tracer", lambda: tracer)

    with telemetry.genai_span(enabled=True) as gspan:
        gspan.record(decision=telemetry.POLICY_DECISION_REFUSE, policy_type="pii_detected")
        gspan.set_error()

    (span,) = exporter.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR


# --- start_genai_span: a detached span the caller ends itself (#193) ---------
# Streaming needs the span to outlive send(): usage lands in the terminal SSE
# event, which the caller reads after send() has returned. So the streaming
# path opens a DETACHED span (not the auto-closing genai_span context manager)
# and hands it to the stream wrapper, which ends it when the stream closes.


def test_start_genai_span_disabled_is_inert() -> None:
    gspan = telemetry.start_genai_span(enabled=False)
    gspan.record(request_model="gpt-4o")
    gspan.set_error()
    gspan.end()  # no span, no crash


def test_start_genai_span_without_otel_is_inert(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telemetry, "_tracer", lambda: None)
    gspan = telemetry.start_genai_span(enabled=True)
    gspan.record(request_model="gpt-4o")
    gspan.end()


def test_start_genai_span_is_detached_and_ends_only_when_told(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer, exporter = _in_memory_tracer()
    monkeypatch.setattr(telemetry, "_tracer", lambda: tracer)

    gspan = telemetry.start_genai_span(enabled=True)
    gspan.record(request_model="gpt-4o", system="openai")
    # Detached: the span is live but NOT yet finished — nothing has ended it.
    assert exporter.get_finished_spans() == ()

    gspan.record(input_tokens=11, output_tokens=3)
    gspan.end()

    (span,) = exporter.get_finished_spans()  # ends exactly once, when the caller says
    assert span.name == telemetry.SPAN_LLM_CHAT
    attrs = dict(span.attributes)
    assert attrs["gen_ai.request.model"] == "gpt-4o"
    assert attrs["gen_ai.usage.input_tokens"] == 11
    assert attrs["gen_ai.usage.output_tokens"] == 3
