# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An SDK for consuming **Agent Fabric** capabilities — governed model
access, governed tool access, and provisioning-as-code — from any of eight
agent frameworks, without adopting Mule. Python ships today (`python/`);
TypeScript is planned (§1.3). The current state is the **M0 scaffold + M1
foundation**: the LLM data plane is live-verified; most control-plane and tool
surfaces are still verification-gated (see below).

## The build plan is the spec

`agent-fabric-sdk-build-plan.md` (156KB, at repo root) is the
authoritative specification. **Every `§N.N` reference in code, docstrings,
tests, and commit messages points into it.** When a docstring says something is
"blocked on verification (§6.7)" or "floors, never ceilings (§8.4)", read that
section of the build plan before changing the behavior — the constraints are
deliberate, not accidental. Do not remove a `§`-cited guard without reading its
section.

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

### How the pieces connect

- `Fabric` (`fabric.py`) is the public surface and orchestrator. It owns one
  shared `FabricAsyncClient` (an `httpx.AsyncClient` subclass that injects
  governance/attribution headers) and hands it to the LLM client, registry, and
  every adapter, so there is one transport and one header-injection point.
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

## Adapter conformance kit (§8.1)

`python/tests/conformance/suite.py` defines ONE suite run identically against
every adapter. A framework is "supported" only when it passes all scenarios or
records an **asserted exemption** in `KNOWN_LIMITATIONS` — never a silent skip.
Exemptions are published in the README as credibility (e.g. ADK/CrewAI cannot
propagate a per-run correlation ID because LiteLLM owns the transport). Tier 1
frameworks are conformance-gated in blocking CI; Tier 2 (LlamaIndex) is
non-blocking.

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
- "Agent Fabric", "Anypoint", "Omni Gateway", "MuleSoft" are Salesforce
  trademarks; the package name is descriptive, not first-party (§0.4).
- **Docs cite a symbol, not path:line.** Line numbers drift as soon as
  anything above them changes; reference the file plus the symbol name instead
  (function, class, config key). Applies to `docs/verified-apis.md`, the build
  plan's `§`-anchors, and every page under `website/`.
- **Cross-surface lockstep.** A capability that lives on more than one surface
  (Python SDK / planned TypeScript / `website/` / `docs/verified-apis.md` /
  README exemptions) changes on all of them together, or the divergence is a
  recorded, intentional decision — never a silent omission on one surface.
- **The issue is the plan.** Plan content for a change lives in the GitHub
  issue/PR, not in committed `plans/*.md` scratch files — this complements
  "the build plan is the spec" above. No code change happens without an issue
  and a matching branch (see [[afdk-git-workflow]]).

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
