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

_correlation_id: ContextVar[str | None] = ContextVar("fabric_correlation_id", default=None)

# Span name constants (§2.5).
SPAN_LLM_CHAT = "fabric.llm.chat"
SPAN_REGISTRY_RESOLVE = "fabric.registry.resolve"
SPAN_TOOL_CALL = "fabric.tool.call"
SPAN_PROVISION_APPLY = "fabric.provision.apply"


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def current_correlation_id() -> str | None:
    return _correlation_id.get()


@contextlib.contextmanager
def run_context(run_id: str | None = None) -> Iterator[str]:
    """Bind a correlation ID for the duration of a logical agent run.

    ``with fabric.run_context(run_id=...)`` lets callers supply their own ID;
    otherwise one is generated. Nested calls restore the previous value on exit.
    """

    rid = run_id or new_correlation_id()
    token = _correlation_id.set(rid)
    try:
        yield rid
    finally:
        _correlation_id.reset(token)


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
    return trace.get_tracer("agent_fabric")


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
        sp.set_attribute("fabric.correlation_id", ensure_correlation_id())
        for key, value in attributes.items():
            if value is not None:
                sp.set_attribute(key, value)
        yield
