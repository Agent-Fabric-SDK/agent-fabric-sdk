# Changelog

All notable changes to `donkey-kit` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Per-call and per-run correlation IDs via `donkey.run()`** (#195). Group one
  logical agent run under a shared correlation id:

  ```python
  async with donkey.run(id=ticket.id):
      await triage_agent.run(ticket)
  ```

  `donkey.run(id=…)` returns a **dual sync/async** context manager, so plain
  `with donkey.run(...)` works too. It binds **two ids** on every request in the
  block:
  - a **run id** → the `X-Correlation-Id` request header → the span's
    `donkey.correlation_id` → `DonkeyError.correlation_id`. Shared by every call
    in the block — the client↔gateway join key.
  - a fresh **per-call id** → the `X-Donkey-Request-Id` request header → the new
    `DonkeyError.call_id`. Unique per logical request and **stable across that
    request's retries**, so one call can be pinpointed within a run; it exists
    even when a request fails before any response.

  Propagation is contextvar-based: it reaches framework-spawned `asyncio` tasks
  (e.g. every LangGraph node) with no threading through state, does not leak
  across concurrent runs, and works with or without OpenTelemetry installed.
  Nested `donkey.run()` blocks rebind then restore; omitting `id` binds a
  generated "run of one". `run_context()` is retained as a back-compat alias.
  `DonkeyError` now also carries `.call_id` alongside `.correlation_id` and the
  gateway's own `.request_id`, and `classify(response)` derives both client-sent
  ids from the response's request so bridging an `openai` error needs no extra
  wiring. Cost-attribution fields (enduser/team/project/env) layer onto
  `donkey.run()` in #196 without a breaking change.

  The two request-header **names** (`X-Correlation-Id`, `X-Donkey-Request-Id`)
  are UNVERIFIED placeholders (§0.3): overridable via `correlation_header` /
  `call_id_header` config (or `DONKEY_CORRELATION_HEADER` /
  `DONKEY_CALL_ID_HEADER`). `x-correlation-id` is verified only as a
  gateway **response** echo — see `docs/verified-apis.md` §3.
- **OpenTelemetry GenAI instrumentation** (#192). Every governed model call now
  opens a single span (`donkey.llm.chat`) that carries **two namespaces at once**:
  the OpenTelemetry `gen_ai.*` semantic-convention attributes and the stable
  DDK `donkey.*` attributes. Emitted keys: `gen_ai.system`,
  `gen_ai.request.model`, `gen_ai.usage.input_tokens`,
  `gen_ai.usage.output_tokens`, `donkey.correlation_id`, `donkey.policy.decision`,
  `donkey.policy.type`, and `donkey.budget.remaining`. Telemetry is an optional
  dependency (`pip install "donkey-kit[otel]"`) and is an inert no-op when
  OpenTelemetry is not installed.
- **Pinned GenAI semantic-convention version.** The convention version is pinned
  to **`1.30.0`** in a single constant
  (`donkey_kit.core.telemetry.GEN_AI_SEMCONV_VERSION`). The `gen_ai.*` keys are
  transcribed literals rather than re-exported from the installed
  `opentelemetry.semconv` package, so upgrading that package never silently
  changes what is emitted.
- **Span lifecycle for refusals, exceptions, and streaming** (#193). A classified
  policy refusal now sets the span's OTel status to `ERROR` (in addition to
  `donkey.policy.decision = refuse`), and a transport error/cancellation marks the
  span `ERROR` and closes it. A streaming (SSE) response produces exactly one span
  that stays open until the stream finishes and closes exactly once — on full
  drain, mid-iteration abandonment, or an exception during iteration — with
  `gen_ai.usage.*` populated from the terminal `usage` event (present only when the
  stream carries one, e.g. Chat Completions `stream_options={"include_usage": true}`).

### Notes for contributors

- Bumping `GEN_AI_SEMCONV_VERSION` is a deliberate, single-file change and **must**
  be accompanied by a new entry in this changelog under the version being released.
- The `donkey.*` attribute keys are **public API**: renaming one is a breaking
  change and requires a major/minor bump plus a `Changed` entry here.

[Unreleased]: https://github.com/Donkey-Development-Kit/donkey-development-kit/commits/develop
