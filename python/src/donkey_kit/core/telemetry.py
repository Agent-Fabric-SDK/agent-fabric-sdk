"""Telemetry (§2.5) and the run-scoped correlation ID (§2.3).

OpenTelemetry is an optional dependency, off by default in the library and on by
default in the CLI. The correlation ID lives in a ``contextvar`` so a single
agent run's fan-out of model calls and tool calls shares one trace ID end to
end — letting a developer correlate their local trace with what the platform
team sees in Omni Gateway's observability view (a headline feature, §2.5).
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Any

from .errors import (
    ContentSafetyBlocked,
    DonkeyError,
    PIIDetected,
    PolicyViolation,
    PromptInjectionBlocked,
    TokenBudgetExceeded,
)

_correlation_id: ContextVar[str | None] = ContextVar("donkey_correlation_id", default=None)

# Span name constants (§2.5).
SPAN_LLM_CHAT = "donkey.llm.chat"
SPAN_REGISTRY_RESOLVE = "donkey.registry.resolve"
SPAN_TOOL_CALL = "donkey.tool.call"
SPAN_PROVISION_APPLY = "donkey.provision.apply"

# --- GenAI span attribute contract (#192, BG §1.6) --------------------------
# Two namespaces on one span (see :func:`genai_span`):
#
#   gen_ai.*  — the OpenTelemetry GenAI semantic conventions, PINNED to the
#     version below. The keys are transcribed literals, deliberately NOT imported
#     from ``opentelemetry.semconv``: the installed package tracks the latest
#     schema (its default drifts release to release), so re-exporting from it
#     would silently change what we emit. Pinning here means what lands on a span
#     is decided in this file, at this version — and bumping the pin is one
#     reviewable, changelog-worthy edit (AC #1/#2).
#
#   donkey.*  — the stable Donkey namespace. These keys are PUBLIC API:
#     renaming one is a breaking change (AC #4), independent of any gen_ai.* bump.
#
# The OTel GenAI conventions are still evolving upstream (they live under
# ``_incubating``); pinning is exactly what insulates us from that churn.
GEN_AI_SEMCONV_VERSION = "1.30.0"

# gen_ai.* — pinned to GEN_AI_SEMCONV_VERSION.
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

# donkey.* — stable public API (renaming a value here is a breaking change).
DONKEY_CORRELATION_ID = "donkey.correlation_id"
DONKEY_POLICY_DECISION = "donkey.policy.decision"
DONKEY_POLICY_TYPE = "donkey.policy.type"
DONKEY_BUDGET_REMAINING = "donkey.budget.remaining"
DONKEY_COST_TEAM = "donkey.cost.team"

# donkey.policy.decision values.
POLICY_DECISION_ALLOW = "allow"
POLICY_DECISION_REFUSE = "refuse"


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def new_call_id() -> str:
    """A fresh per-request **call id** (§2.3, #195).

    Unlike the run/correlation id — which is contextvar-bound and shared across
    every request in a :func:`run_context` / ``donkey.run()`` block — this is
    generated anew for each logical request, so one call can be pinpointed within
    a run. It is client-generated, so it exists even when a request fails before
    any response (a transport error carries no gateway ``x-request-id``)."""
    return uuid.uuid4().hex


def current_correlation_id() -> str | None:
    return _correlation_id.get()


@contextlib.contextmanager
def run_context(run_id: str | None = None) -> Iterator[str]:
    """Bind a correlation ID for the duration of a logical agent run.

    ``with donkey.run_context(run_id=...)`` lets callers supply their own ID;
    otherwise one is generated. Nested calls restore the previous value on exit.
    """

    rid = run_id or new_correlation_id()
    token = _correlation_id.set(rid)
    try:
        yield rid
    finally:
        _correlation_id.reset(token)


class RunScope:
    """A **dual sync/async** context manager that binds the run correlation id
    to :data:`_correlation_id` for the block (§2.3, #195).

    This is what ``donkey.run(id=...)`` returns, so the same object works under
    both ``with donkey.run(...)`` and ``async with donkey.run(...)`` — binding a
    contextvar needs no ``await``, so both entry paths share one implementation.
    The bound id reaches every model call made inside the block (including calls
    on framework-spawned ``asyncio`` tasks, which copy the current context at
    creation), so a run id set here propagates without threading it through any
    framework state.

    Nested scopes rebind and restore via the contextvar token, so an inner run
    id shadows an outer one for its block and the outer id is restored on exit.
    Enter and exit happen in the same task/context for both protocols, so the
    ``reset(token)`` is always valid.

    The ``id`` keyword is deliberately the only field today; #196 extends
    ``donkey.run()`` with cost-attribution fields (enduser/team/project/env)
    without a breaking change — they layer on as additional bound state, leaving
    this correlation binding intact.
    """

    __slots__ = ("_run_id", "_token")

    def __init__(self, run_id: str | None = None) -> None:
        self._run_id = run_id
        self._token: Any = None

    def _bind(self) -> str:
        rid = self._run_id or new_correlation_id()
        self._token = _correlation_id.set(rid)
        return rid

    def _unbind(self) -> None:
        if self._token is not None:
            _correlation_id.reset(self._token)
            self._token = None

    def __enter__(self) -> str:
        return self._bind()

    def __exit__(self, *exc: Any) -> None:
        self._unbind()

    async def __aenter__(self) -> str:
        return self._bind()

    async def __aexit__(self, *exc: Any) -> None:
        self._unbind()


def run_scope(run_id: str | None = None) -> RunScope:
    """Build a :class:`RunScope` — the dual sync/async run correlation binding
    behind ``donkey.run(id=...)`` (§2.3, #195)."""
    return RunScope(run_id)


def ensure_correlation_id() -> str:
    """Return the current correlation ID, creating (and binding) one if absent."""
    rid = _correlation_id.get()
    if rid is None:
        rid = new_correlation_id()
        _correlation_id.set(rid)
    return rid


def request_correlation_id() -> str:
    """The bound run's correlation ID, or a fresh one that is deliberately *not*
    bound.

    For blocking callers. :func:`ensure_correlation_id` binds on first use, which
    is right under ``asyncio.run`` — that runs in its own ``Context``, so the
    binding dies with the run and one run shares one ID. A synchronous call has
    no such boundary: binding there would pin the very first request's ID to the
    ambient context for the rest of the process, so every later unrelated call
    would report the same run. Grouping stays opt-in via :func:`run_context`.
    """
    return _correlation_id.get() or new_correlation_id()


# --- Optional OpenTelemetry span helper -------------------------------------
def _tracer() -> Any | None:
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    return trace.get_tracer("donkey_kit")


@contextlib.contextmanager
def span(name: str, *, enabled: bool, **attributes: Any) -> Iterator[None]:
    """Start an OTel span if telemetry is enabled and OTel is installed.

    Always attaches the correlation ID. A no-op (and never an error) when
    telemetry is off or OTel is not installed — telemetry must never be a hard
    dependency of the library.
    """

    if not enabled:
        yield
        return
    tracer = _tracer()
    if tracer is None:
        yield
        return
    with tracer.start_as_current_span(name) as sp:  # pragma: no cover - needs otel
        sp.set_attribute(DONKEY_CORRELATION_ID, ensure_correlation_id())
        for key, value in attributes.items():
            if value is not None:
                sp.set_attribute(key, value)
        yield


# --- GenAI chat span (#192, BG §1.6) ----------------------------------------
def policy_type_slug(error: DonkeyError) -> str | None:
    """The :data:`DONKEY_POLICY_TYPE` value for a classified refusal, or ``None``
    for a non-policy error (auth / upstream / transport) that carries no
    governance allow-or-refuse decision.

    Ordered most-specific-subclass first so a :class:`PIIDetected` (which *is* a
    :class:`PolicyViolation`) reports ``"pii_detected"``, not the generic slug.
    """
    if isinstance(error, TokenBudgetExceeded):
        return "token_budget"
    if isinstance(error, PIIDetected):
        return "pii_detected"
    if isinstance(error, PromptInjectionBlocked):
        return "injection"
    if isinstance(error, ContentSafetyBlocked):
        return "content_safety"
    if isinstance(error, PolicyViolation):
        return "policy_violation"
    return None


def build_genai_attributes(
    *,
    system: str | None = None,
    request_model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    decision: str | None = None,
    policy_type: str | None = None,
    budget_remaining: int | None = None,
    cost_team: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Assemble the dual-namespace GenAI span attributes, omitting any field left
    ``None``.

    Both the pinned ``gen_ai.*`` keys and the stable ``donkey.*`` keys are built
    here and land on ONE span (:func:`genai_span`, AC #5). A ``None`` field is
    an unobserved value: it is dropped, never emitted as a null or a placeholder,
    so a caller can record what it knows as it learns it (request model first,
    response fields once the response settles).
    """
    attrs: dict[str, Any] = {}
    if system is not None:
        attrs[GEN_AI_SYSTEM] = system
    if request_model is not None:
        attrs[GEN_AI_REQUEST_MODEL] = request_model
    if input_tokens is not None:
        attrs[GEN_AI_USAGE_INPUT_TOKENS] = input_tokens
    if output_tokens is not None:
        attrs[GEN_AI_USAGE_OUTPUT_TOKENS] = output_tokens
    if decision is not None:
        attrs[DONKEY_POLICY_DECISION] = decision
    if policy_type is not None:
        attrs[DONKEY_POLICY_TYPE] = policy_type
    if budget_remaining is not None:
        attrs[DONKEY_BUDGET_REMAINING] = budget_remaining
    if cost_team is not None:
        attrs[DONKEY_COST_TEAM] = cost_team
    if correlation_id is not None:
        attrs[DONKEY_CORRELATION_ID] = correlation_id
    return attrs


class GenAiSpan:
    """Handle to the in-flight GenAI span.

    :meth:`record` maps keyword fields through :func:`build_genai_attributes` and
    sets each resulting attribute on the span. When there is no live span
    (telemetry off, or OpenTelemetry not installed) it wraps ``None`` and every
    call is a no-op — telemetry must never be a hard dependency or an error path.
    """

    __slots__ = ("_span",)

    def __init__(self, span: Any | None) -> None:
        self._span = span

    def record(self, **fields: Any) -> None:
        """Set the (non-``None``) attributes named by ``fields`` on the span.

        Idempotent-friendly: call it repeatedly as values become known; each key
        is set to its latest observed value and unobserved fields are skipped.
        """
        if self._span is None:
            return
        for key, value in build_genai_attributes(**fields).items():
            self._span.set_attribute(key, value)

    def set_error(self) -> None:
        """Mark the span's OTel status as ERROR — a refusal or an exception is a
        failed operation, not a successful-looking span (#193, AC #1/#4). A no-op
        without a live span, so telemetry-off / OTel-absent never crashes. The
        ``opentelemetry`` import is lazy and only reached when a real span
        exists, keeping the framework-free-core base install clean."""
        if self._span is None:
            return
        from opentelemetry.trace import Status, StatusCode

        self._span.set_status(Status(StatusCode.ERROR))

    def end(self) -> None:
        """End a DETACHED span (one from :func:`start_genai_span`). A no-op
        without a live span. Not to be called for a span owned by the
        :func:`genai_span` context manager — that ends it on block exit."""
        if self._span is None:
            return
        self._span.end()


@contextlib.contextmanager
def genai_span(*, enabled: bool) -> Iterator[GenAiSpan]:
    """The GenAI chat span (:data:`SPAN_LLM_CHAT`) for one governed model call.

    Yields a :class:`GenAiSpan` the caller records onto. Both the pinned
    ``gen_ai.*`` attributes and the stable ``donkey.*`` attributes go on this one
    span (AC #5). A no-op (yielding an inert handle, never raising) when
    telemetry is off or OpenTelemetry is not installed.

    The span is opened as a context manager so it closes on the way out even when
    the wrapped call raises before a response exists — a transport error escapes
    the transport's ``_finish`` hook, so the span lifecycle cannot rely on it
    (see ``core.transport.DonkeyAsyncClient._finish``, #179/#192).
    """
    if not enabled:
        yield GenAiSpan(None)
        return
    tracer = _tracer()
    if tracer is None:
        yield GenAiSpan(None)
        return
    with tracer.start_as_current_span(SPAN_LLM_CHAT) as sp:
        yield GenAiSpan(sp)


def start_genai_span(*, enabled: bool) -> GenAiSpan:
    """A DETACHED :data:`SPAN_LLM_CHAT` span the caller must :meth:`GenAiSpan.end`.

    Unlike :func:`genai_span` (a context manager that ends the span on block
    exit), this returns a live span whose lifetime is *not* bound to a ``with``
    block. That is what the streaming path needs: the span must outlive
    ``send()`` so the stream wrapper can fill ``gen_ai.usage.*`` from the terminal
    SSE event and end the span when the stream closes — on drain, abandonment, or
    exception (#193). Inert (an end-safe no-op handle, never raising) when
    telemetry is off or OpenTelemetry is not installed.

    The span is deliberately NOT made the current context: a streamed response is
    consumed long after ``send()`` returns, so there is no live scope to nest
    under. It records attributes and closes correctly, which is the whole of the
    span contract #193 requires."""
    if not enabled:
        return GenAiSpan(None)
    tracer = _tracer()
    if tracer is None:
        return GenAiSpan(None)
    return GenAiSpan(tracer.start_span(SPAN_LLM_CHAT))
