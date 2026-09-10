---
name: afdk-implementing-features
description: Use when actually writing the code for a feature in agent-fabric-sdk — after the issue + branch exist and before the PR. Triggers on "implement feature X", "build the budget/OTel/simulate feature", "wire this onto the transport hook", "attach to the skeleton", "add an adapter for <framework>", "add a new rejection type", "extend classify()", "add a config setting". Owns the IMPLEMENT stage between [[afdk-git-workflow]] step 3 (brainstorm + boundaries) and step 4 (commit/push/PR). Routes to the right pattern; defers code-quality rules to [[afdk-coding-conventions]] and verification to [[afdk-verification-discipline]].
---

# AFDK Implementing Features

## Overview

This skill covers the **IMPLEMENT** stage — you are on a correctly-named issue
branch ([[afdk-git-workflow]]) and about to write code. It exists because the
lifecycle had a skill for every stage *except* the one where the code gets
written, and because this repo has a specific idea of *where new behaviour
attaches*: **the wrapper is the skeleton** (`CLAUDE.md`, `BG §1.1`). New
capability hangs off the shared transport's lifecycle hooks or the adapter
registry — it is almost never a fresh top-level entry point.

It does **not** restate the code-quality rules (mypy `--strict`, ruff, the
framework-free-core import rule, lazy adapter imports, the 3.10 floor,
floors-never-ceilings, `§N.N` citation habit) — those live in
[[afdk-coding-conventions]] and are assumed here. It does not restate the
verification contract — that is [[afdk-verification-discipline]]. This skill is
the *router*: it names the pattern you're implementing and points at the seam,
the tests, and the surfaces that must move in lockstep.

## The one idea: attach, don't re-wire

Every request enters and every response leaves through one shared
`FabricAsyncClient` (mirrored on the sync `FabricClient`). It exposes four
**internal, no-op-by-default** lifecycle hooks — the attachment points for the
six-piece minimum. **Override the hook; never override `send()`.** Full
contracts live in the `core/transport.py` docstrings and are mapped in
[`ARCHITECTURE.md`](../../../ARCHITECTURE.md) ("How the pieces connect") — read
those rather than trusting a copy here.

| Hook | Fires | You attach here for… |
| --- | --- | --- |
| `_on_request` | once, before the retry loop | correlation-ID / cost-tag headers (`BG §1.7`); span **start** (`BG §1.6`) |
| `_on_response` | once, on the final response (`_finish()`) | budget parse (`BG §1.3`); span **end**; classification |
| `_on_refusal` | Phase-2 seam, no caller until `classify()` wires it (#181) | typed-refusal handlers (`BG §1.2`) |
| `_swap_transport` | fixture seam | `simulate()` (#190) / `fabric mock` (#187) (`BG §1.4`/`BG §1.5`) |

Three contracts that break silently if ignored:

1. A subclass overriding `_on_response` **must call `super()._on_response(...)`**
   or budget tracking stops.
2. A transport-level error escapes before `_finish` runs, so a span opened in
   `_on_request` has **no paired `_on_response`** — close spans in a `finally`,
   never rely on the response hook.
3. A 429 budget refusal is **terminal** — never retried (see the taxonomy
   pattern below and #290).

The live budget surface is `fabric.budget.remaining` / `.reset_at` /
`.fraction_used` (`core/budget.py`). Pacing on top of it —
`budget.wait_for_reset()` — is **planned (#186), not shipped**; do not reference
it as if it exists.

## Pattern A — attach a cross-cutting feature to a hook

Budget, OTel spans, correlation IDs, cost tags, classification hand-off,
`simulate()`. Pick the hook from the table, override it on `FabricAsyncClient`
**and** its sync twin `FabricClient` (cross-surface lockstep — the two must not
diverge), obey the three contracts, and leave the default a no-op when the
collaborator isn't attached. Tests: [[afdk-testing]] Surface 1
(`tests/unit/`). If the feature reads a new response header whose name isn't
confirmed, that is a [[afdk-verification-discipline]] question — use
`Unverified(...)`, don't guess the header string.

## Pattern B — add or deepen a framework adapter

The `ADAPTERS`-registry wiring lives in no other skill, so it is spelled out
here. An adapter returns the **framework's own native object**, never a
wrapper, and ships in **three ergonomic forms** that stay in lockstep (README
§2): the `fabric.<framework>` factory, a `connection_kwargs()` accessor, and a
module-level factory. Do this in order:

1. **Write `python/src/agent_fabric/integrations/<framework>.py`.** Import the
   framework **lazily inside methods** (§1.1 — never at module top level).
   Reuse the shared helpers in `integrations/_base.py` (`_http_client()`,
   `_require_proxy()`, `_openai_connection()`, `default_adapter()`) so the one
   transport and header-injection point are preserved. Set `max_retries=0` on
   the framework's client when it has one — retries happen in our transport
   (§2.3), not the framework's.
2. **Register it in `ADAPTERS`** (`integrations/__init__.py`): key, module path,
   class name, pip-extra name, and native-import module. The key is what
   `fabric.<key>` resolves to.
3. **Verify the curated `ImportError`.** `Fabric.__getattr__` must raise an
   `ImportError` carrying the exact `pip install 'agent-fabric[<extra>]'`
   command when the extra is absent — never a bare `ModuleNotFoundError`.
4. **Add the extra** to `pyproject.toml` as a **floor, no upper pin** (§8.4).
5. **Wire the conformance suite** (`python/tests/conformance/suite.py`): the one
   suite runs against every adapter. If a scenario genuinely cannot pass (e.g.
   LiteLLM-owned transport can't propagate a per-run correlation ID), record an
   **asserted exemption in `KNOWN_LIMITATIONS`** — *never* a silent skip
   (§8.1). See [[afdk-testing]] for which surface each scenario belongs to.
6. **Add the `scripts/verify_frameworks.py` entry** so the offline
   signature check and nightly matrix cover it. The exact constructor
   kwargs/class name are §8-verification-gated — if unconfirmed, this is a
   [[afdk-verification-discipline]] step, not a guess.
7. **Add `python/examples/<framework>/`** (the eight existing dirs are the
   template) and the docs page under **`website/pages/frameworks/`** (match the
   existing slug — the naming isn't 1:1 with the registry key, e.g.
   `openai.mdx`, `agent-framework.mdx`). Website work follows
   [[afdk-docs-authoring]]; whether it's required *in this PR* is
   [[afdk-docs-sync]].

**Depth is deliberate.** Only LangGraph is the deep, conformance-gated adapter
(target state, #198); the other seven are supported at `connection_kwargs()`
only. Bringing a framework to full depth is demand-driven and picked one at a
time (#223 / #244) — don't deepen an adapter on your own initiative without an
issue that says to.

## Pattern C — add a rejection type / extend `classify()`

Pointer-only, because the rules already live in dedicated skills. The
discriminator is the error **`type`** plus specific headers, **not the status
code alone** (a PII block is a 403 but not an auth error; a 429 budget refusal
is terminal). New mappings are **fixture-driven, not guessed** — capture the
real shape first. See:

- [[afdk-pr-review]] §3 (Error-taxonomy correctness) — the invariants a
  reviewer checks: never-retry-a-refusal, required `remediation`, discriminate
  on `type`+headers.
- [[afdk-testing]] Surface 1 — the mandatory assertions for any
  `core/errors.classify()` change, and the fixture layout under
  `tests/fixtures/`.
- [[afdk-verification-discipline]] — a rejection shape not yet captured live
  (e.g. the content-moderation body, #253) falls through with a message that
  *says so*; it is not invented.

## Pattern D — add a config setting

Three edits move together in `core/config.py`:

1. Add the field to `FabricConfig`.
2. Resolve it in `from_env()` along the fixed precedence — constructor kwargs →
   env var → `.agent-fabric.toml` → default (§2.1). Missing required fields are
   reported **all at once**, not one failure per run.
3. Gate it in `validated(need=...)` under the right profile — `need="llm"` for
   the data-plane path, `need="control_plane"` for the control-plane path — so a
   field is only required where it's actually used.

Anything that names an Anypoint endpoint/header default routes through
[[afdk-verification-discipline]] (`Unverified(...)` or `_verify.blocked(...)`).

## Cross-cutting, every pattern

- **Three ergonomic forms in lockstep** for any governed surface (factory /
  `connection_kwargs()` / module-level) — README §2.
- **Cross-surface lockstep** — a capability on more than one surface (Python /
  sync twin / `website/` / `docs/verified-apis.md` / README exemptions) moves on
  all of them together, or the divergence is a recorded decision. Use
  [[afdk-docs-sync]] to decide what must move *in this PR*.
- **Refusals are not backlog.** The build plan's *Do not build* list is binding
  — no client-side policy enforcement, no provisioning control plane competing
  with API Manager/Terraform, no home-grown A2A. If the feature drifts toward
  one of those, stop and re-read the issue.
- When you finish the code, hand back to [[afdk-git-workflow]] step 4
  (commit/push) and then [[afdk-pr-workflow]] for the pre-PR gate.

## Forbidden rationalizations

| Excuse | Reality |
| --- | --- |
| "I'll just override `send()` — it's simpler." | The hooks exist so features attach without re-wiring transport. Override the hook; `send()` stays owned by the client. |
| "My `_on_response` override doesn't need `super()`." | Then budget tracking silently dies. Always call `super()._on_response(...)`. |
| "I'll close the span in `_on_response`." | A network error never reaches `_on_response`. Close spans in a `finally`. |
| "429 should retry after the reset window." | A budget refusal is terminal (#290). Retrying a governance refusal is the bug the taxonomy prevents. |
| "I'll use `budget.wait_for_reset()`." | It's planned (#186), not shipped. Use `fabric.budget.reset_at`. |
| "New adapter, I'll register it and skip the conformance wiring for now." | An adapter with no suite entry (or asserted exemption) is an unproven claim of support. Wire the suite or record the exemption. |
| "I'll deepen this adapter past `connection_kwargs()` while I'm here." | Depth is demand-driven and issue-gated (#223/#244). LangGraph is the only deep one until then. |
| "I don't know the exact kwarg, I'll use a sensible default." | That's what §0.3 forbids. `Unverified(...)` / `_verify.blocked(...)` and route through [[afdk-verification-discipline]]. |

## Related skills

- [[afdk-git-workflow]] — the branch you must already be on; steps 3→4 bracket
  this stage.
- [[afdk-coding-conventions]] — the code-quality rules this skill assumes.
- [[afdk-verification-discipline]] — any endpoint/header/class-name/kwarg claim.
- [[afdk-testing]] — which pytest surface proves the change.
- [[afdk-docs-sync]] / [[afdk-docs-authoring]] — whether/how `website/` moves.
- [[afdk-pr-workflow]] — the pre-PR gate once the code is written.
