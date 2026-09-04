# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An SDK for consuming **Agent Fabric** capabilities from Python agent code,
without adopting Mule. The LLM data plane is live-verified; most control-plane
and tool surfaces are still verification-gated (see below).

The product thesis, which determines what gets built: **the wrapper is the
skeleton.** It is not sold as a way to reach the Omni Gateway — a stock OpenAI
client with a `base_url` and two headers does that. It is the single point in
the process where every request enters and every response leaves, so it is the
only place where budget headers, error classification, correlation IDs, cost
tags, OTel spans, simulation, and refusal handlers can all attach without the
developer wiring each one. **The skeleton is worth exactly the sum of what
hangs on it** — which is why the *six-piece minimum* (typed refusals, budget
object + pacing, local gateway simulator, `simulate()` + conformance plugin,
OTel GenAI instrumentation, correlation IDs + cost tags) is one milestone
rather than spread across the roadmap.

## The build plan is the spec

Two documents in `spec/` are authoritative, with one job each:

- **`spec/agent-fabric-sdk-build-plan.md`** — phases, milestones, label
  taxonomy, implementation order, and the standing invariants. Cite it by
  phase (`Phase 1`) or section name.
- **`spec/agent-fabric-sdk-build-guide.md`** — feature-by-feature scope: what
  each capability is, the scenario that justifies it, and its acceptance bar.
  **Cite it as `BG §1.1` … `BG §3.5`** — always with the `BG` prefix.

Per-issue detail lives in **neither**. It lives in the GitHub issue, because
the issue is the plan.

### Citation convention — read this before adding a `§` reference

`spec/archive/agent-fabric-sdk-build-plan-v1.md` is the **archived** v1 plan.
Its three-pillar model, provisioning control plane, and eight-adapter
conformance roster are cut, so it is not the authority for what to build. It
is retained for exactly one reason: ~500 bare `§N.N` citations across ~70
files in `python/` and `docs/` point into its numbering.

The two schemes collide — v1 `§1.1` is the layered-architecture rule, build
guide `1.1` is the LLM client — so they are kept textually distinct:

| Form | Means | Use it? |
| --- | --- | --- |
| `BG §1.1` | A build guide section | **Yes** — for all new feature-scope references |
| bare `§1.1` | A section of the archived v1 plan | No new ones; existing ones still resolve |
| `Phase 1` | A milestone in the build plan | Yes — named, never `§`-numbered |

When a docstring says "blocked on verification (§6.7)" or "floors, never
ceilings (§8.4)", that is a v1 anchor: read it **in the archive** before
changing the behavior. The constraints are deliberate, not accidental. Do not
remove a `§`-cited guard without reading its section.

## Verification discipline (§0.3 — the most important rule)

Working instruction #2: **never invent an endpoint, header name, or class name.**
A fabricated endpoint that 404s in a customer sandbox destroys trust in the whole
package. Two mechanisms in `core/_verify.py` enforce this:

- `_verify.blocked("…")` returns `NotImplementedError("blocked on verification: …")`.
  Used where there is no defensible placeholder at all (e.g. `fabric.tools.discover`,
  the provisioning control-plane APIs). **Do not replace these with guesses.**
- `Unverified(...)` placeholder constants emit a one-time `UnverifiedValueWarning`
  when read and are fully overridable via config/env. A value flips to
  `verified=True` only after it is confirmed against a real Anypoint sandbox.

`docs/verified-apis.md` is the single source of truth for what is verified and
the worklist of what is blocked. When you confirm a value against a sandbox:
flip its row there **and** set `verified=True` in `_verify.py`. What is verified
today: the LLM proxy data plane (base URL shape with **no `/v1`**, the
`client_id`/`client_secret` header pair, streaming, the four rejection shapes),
the OAuth2 token path, and the CLI-plugin REST contract (§12, from static
analysis). Still blocked: Exchange→MCP tool discovery, the provisioning
control-plane, and the exact framework adapter class names/kwargs (§8–§10).

The **`Verification` milestone** is the live worklist, and it is deliberately
unversioned and cross-phase — it never "completes". Each row blocks specific
feature work, so a question started when the phase that needs it starts will
block that phase; started early, it resolves in time. The `Upstream gaps`
milestone is its sibling for asks that only the Omni Gateway team can close.

## Layered architecture (§1.1 — enforced by CI)

`import-linter` (`lint-imports`) enforces this at build time; violating it fails
CI. Lower layers must never import higher ones:

```
integrations  (top — per-framework native-object adapters)
    ↓
tools         (MCP discovery/binding — resolves registry handles)
    ↓
registry      (Exchange/governed-state)
    ↓
llm           (framework-free OpenAI-compatible proxy client + catalog)
    ↓
core          (config, auth, transport, errors, telemetry, cache — FRAMEWORK-FREE)
```

**`core/` has zero agent-framework dependencies — httpx + pydantic only.** The
`base-only` CI job installs *only* the base package and imports `agent_fabric`
to catch accidental top-level framework imports. Adapters import their framework
**lazily inside methods**, never at module top level.

The adapter cut (below) makes this gate *more* important, not less: with one
conformance-gated adapter and seven `connection_kwargs()`-only frameworks,
nothing but the linter stops a framework import from drifting into `core`.

### How the pieces connect

- `Fabric` (`fabric.py`) is the public surface and orchestrator. It owns one
  shared `FabricAsyncClient` (an `httpx.AsyncClient` subclass that injects
  governance/attribution headers) and hands it to the LLM client, registry, and
  every adapter, so there is one transport and one header-injection point.
- **`FabricAsyncClient` is the skeleton, and the four transport lifecycle hooks
  are its attachment points** (`BG §1.1`). Budget parsing, OTel spans,
  classification, and `simulate()` all hang off the same hooks — which is why
  the hooks land before the features that use them (#179). Building any of
  those features first means building it twice.
- Per-framework adapters are **lazy attributes** resolved by `Fabric.__getattr__`
  via the `ADAPTERS` registry in `integrations/__init__.py`. Accessing an adapter
  whose extra is not installed raises `ImportError` with the exact `pip install`
  command — never a bare `ModuleNotFoundError`. Each adapter returns the
  **framework's own native object** (e.g. `ChatOpenAI`), not a wrapper.
- Config resolves kwargs → env vars → `.agent-fabric.toml` → default (§2.1);
  missing fields are reported all at once. `Fabric.from_env()` is the entry point.
- `core/errors.classify()` maps the proxy's live rejection shapes to typed
  exceptions. The discriminator is the error **`type`** plus specific headers, not
  the status code alone (a PII block is a 403 but is not an auth error). See §4 of
  `docs/verified-apis.md` and `test_llm_proxy_contract.py`.

## Adapters: one deep, seven shallow (`BG §1.8`)

The eight-adapter roster is **cut**. The plan keeps:

- **LangGraph** — the one deep, conformance-gated adapter (#198).
- **The raw client** — `fabric.llm.client()`, for the no-framework case.
- **Seven frameworks at `connection_kwargs()` only** — ADK, Strands, MS Agent
  Framework, OpenAI Agents SDK, Anthropic, CrewAI, LlamaIndex. Verified at the
  `connection_kwargs()` level, not the constructor level.

This is why `connection_kwargs()` becomes *more* load-bearing after the cut,
not less: it is the entire supported surface for seven of the eight. Adapters
return the **framework's own native object**, never a wrapper. Bringing a
framework back to the full bar is demand-driven, one at a time — #223 picks the
second deep adapter from Phase 1 demand evidence (do not guess it), and #244
handles the remainder in Phase 5. The demotion itself is tracked in #197, and
deepening LangGraph in #198; until #197 lands, the eight-adapter matrix is
still in blocking CI.

## Conformance kit (§8.1)

`python/tests/conformance/suite.py` defines ONE suite run identically against
every supported adapter. A framework is "supported" only when it passes all
scenarios or records an **asserted exemption** in `KNOWN_LIMITATIONS` — never a
silent skip. Exemptions are published in the README as credibility (e.g.
ADK/CrewAI cannot propagate a per-run correlation ID because LiteLLM owns the
transport).

**The centre of gravity moves** (`BG §1.5`): from an internal eight-adapter
matrix to the **customer-facing pytest plugin** users run against their own
agent (#191). The internal matrix shrinks to LangGraph; the public plugin is
the deliverable. The old Tier 1 / Tier 2 split retires with the roster cut.

## Commands

All Python work happens in `python/`.

```bash
cd python
pip install -e ".[dev,llm,cli]"   # what CI installs; add other extras as needed

pytest -q                          # full suite
pytest -q tests/unit               # unit only (what base-only CI runs)
pytest -q tests/unit/test_errors.py::test_pii_detected   # single test
mypy                               # mypy --strict, BLOCKING in CI (files=src/agent_fabric)
ruff check .
lint-imports                       # enforce the framework-free core rule (§1.1)
```

Live/sandbox tests are **off by default** and gated by markers/env:
`local_gateway` (needs a local Omni Gateway via docker, §6.5) and `sandbox`
(needs `FABRIC_SANDBOX_TESTS=1` + a real Anypoint sandbox).

Verify framework constructor signatures against installed packages (executable
form of the §8 verification step; also the nightly-matrix CI gate):

```bash
python scripts/verify_frameworks.py            # offline signature check, all installed
python scripts/verify_frameworks.py --live     # + one real proxy round-trip
python scripts/verify_frameworks.py --emit-verified   # print §8 markdown rows to paste
```

The docs site (`website/`, Nextra/Next.js): `cd website && npm install && npm run dev`.

## Conventions

- **Python floor is 3.10**; `tomllib` is backfilled with `tomli`, and
  `typing-extensions` is pulled in under 3.12. Keep 3.10 compatibility.
- **Extras are floors, never ceilings (§8.4)** — no upper pins in
  `pyproject.toml`. A fresh resolve always takes the newest release so the
  nightly matrix finds breakage early. Known incompatibilities (e.g. `openai>=3`
  retyping the http client) are documented in `docs/verified-apis.md §8.1` as
  local dev constraints, **not** encoded as pins.
- Every governed surface has three ergonomic forms: the `fabric.<framework>`
  factory, a `connection_kwargs()` accessor, and a module-level factory. Keep all
  three when adding an adapter (see README §2).
- Never commit secrets: `.agent-fabric.local.toml`, `fabric.lock.local`, and
  `.env` are gitignored. The LLM proxy authenticates on a `client_id`/`client_secret`
  header pair (consumer auth) — separate from any Anypoint control-plane credential.
- **Docs cite a symbol, not path:line.** Line numbers drift as soon as
  anything above them changes; reference the file plus the symbol name instead
  (function, class, config key). Applies to `docs/verified-apis.md`, both
  `spec/` documents, and every page under `website/`.
- **Cross-surface lockstep.** A capability that lives on more than one surface
  (Python SDK / TypeScript once Phase 5 ships / `website/` /
  `docs/verified-apis.md` / README exemptions) changes on all of them together,
  or the divergence is a recorded, intentional decision — never a silent
  omission on one surface.
- **The issue is the plan.** Plan content for a change lives in the GitHub
  issue/PR, not in committed `plans/*.md` scratch files — this complements
  "the build plan is the spec" above. No code change happens without an issue
  and a matching branch (see [[afdk-git-workflow]]).
- **Refusals are not backlog.** The build plan's *Do not build, at any phase*
  list is binding: no client-side policy enforcement, no client-side semantic
  caching, no provisioning control plane competing with API Manager/Terraform,
  no re-implementation of Agent Scanners / Kill Switch / Trusted Agent
  Identity, no approval UI or queue, no eval framework, no gateway in the agent
  process, and no home-grown A2A protocol implementation (wrap the official
  `a2a-sdk`). At each of these boundaries the SDK's job is to make the
  platform's own capability reachable and typed, not to reproduce it.

## Claude Code skills

Skills under `.claude/skills/` are prefixed `afdk-` (Agent Fabric SDK) and are
the trigger-based path into this file's rules — the matcher loads the right
skill when your phrasing matches its description. The full index, with a
"when it fires" column for every skill and the sub-agent skill-loading rule,
is [`.claude/skills/README.md`](.claude/skills/README.md).

One line per skill:

- **`afdk-coding-conventions`** — writing/reviewing Python under `python/src/agent_fabric/**`.
- **`afdk-testing`** — writing or expanding tests; which pytest surface to use.
- **`afdk-pr-review`** — reviewing a PR against this repo's invariants.
- **`afdk-git-workflow`** — issue → branch → commit lifecycle.
- **`afdk-pr-workflow`** — pre-PR gate, opening the PR, post-merge checks.
- **`afdk-merge-strategy`** — merging into `develop`, promoting to `main`.
- **`afdk-filing-issues`** — filing a new GitHub issue.
- **`afdk-issue-relationships`** — linking issues that already exist.
- **`afdk-docs-authoring`** — writing/rewriting a `website/pages/**.mdx` page.
- **`afdk-docs-sync`** — deciding whether a code change needs a matching website update.
- **`afdk-verification-discipline`** — touching any Anypoint endpoint, header, class name, or kwarg.

If a phrasing slips past the matcher, invoke the skill (or read its doc)
explicitly rather than proceeding without it — e.g. "working an issue" should
still mean "invoke `afdk-git-workflow` before edits" even if the trigger
didn't fire. Dispatching sub-agents has its own hard rule: see the
"Parallel sub-agent work" section of `.claude/skills/README.md`.

**Skill-editing exception:** edits scoped entirely to `.claude/skills/**` may
go straight to `develop` after an approved recap + commit message — they skip
the issue+branch+PR ceremony (see [[afdk-git-workflow]]).
