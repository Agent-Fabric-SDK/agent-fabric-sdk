# Changelog

All notable changes to `agent-fabric` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **OpenTelemetry GenAI instrumentation** (#192). Every governed model call now
  opens a single span (`fabric.llm.chat`) that carries **two namespaces at once**:
  the OpenTelemetry `gen_ai.*` semantic-convention attributes and the stable
  Agent Fabric `fabric.*` attributes. Emitted keys: `gen_ai.system`,
  `gen_ai.request.model`, `gen_ai.usage.input_tokens`,
  `gen_ai.usage.output_tokens`, `fabric.correlation_id`, `fabric.policy.decision`,
  `fabric.policy.type`, and `fabric.budget.remaining`. Telemetry is an optional
  dependency (`pip install "agent-fabric[otel]"`) and is an inert no-op when
  OpenTelemetry is not installed.
- **Pinned GenAI semantic-convention version.** The convention version is pinned
  to **`1.30.0`** in a single constant
  (`agent_fabric.core.telemetry.GEN_AI_SEMCONV_VERSION`). The `gen_ai.*` keys are
  transcribed literals rather than re-exported from the installed
  `opentelemetry.semconv` package, so upgrading that package never silently
  changes what is emitted.

### Notes for contributors

- Bumping `GEN_AI_SEMCONV_VERSION` is a deliberate, single-file change and **must**
  be accompanied by a new entry in this changelog under the version being released.
- The `fabric.*` attribute keys are **public API**: renaming one is a breaking
  change and requires a major/minor bump plus a `Changed` entry here.

[Unreleased]: https://github.com/Agent-Fabric-SDK/agent-fabric-sdk/commits/develop
