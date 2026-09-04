---
name: afdk-coding-conventions
description: Use when authoring or reviewing any Python code in the agent-fabric SDK (python/src/agent_fabric/**) — typing under mypy --strict, ruff rules, the import-linter layering + framework-free core rule, lazy framework imports in adapters, the §N.N build-plan citation habit, the "floors never ceilings" extras rule, the 3.10 floor, and trademark-descriptive language. This is the read-the-doc backstop for the trigger-based matcher.
---

# AFDK Coding Conventions

## Overview

`agent-fabric` (import package `agent_fabric`) is a Python SDK for
consuming **Agent Fabric** from any of eight agent frameworks. The
authoritative contract for *what the code must look like* is split across two
sources you should keep open:

- **`CLAUDE.md`** (repo root) — the short version of every rule below.
- **`spec/agent-fabric-sdk-build-plan.md`** — phases, invariants, the
  do-not-build list. **`spec/agent-fabric-sdk-build-guide.md`** — feature
  scope, cited as `BG §N.N`. A **bare** `§N.N` points into the archived v1
  plan at `spec/archive/agent-fabric-sdk-build-plan-v1.md`, where most
  existing citations in the tree still resolve.
  When a docstring says "blocked on verification (§6.7)" or "floors, never
  ceilings (§8.4)", read that section before changing the behavior — the
  constraints are deliberate.

**Read those, then come back for the checklist below.** This skill exists
because those pointers are easy to skip past on a "small" code touch.

All Python work happens in `python/`. There is no Makefile — commands run
directly.

## When this skill activates

Trigger this skill when about to:

- Add or edit anything under `python/src/agent_fabric/**` — especially `core/`
  (the framework-free layer) or `integrations/**` (the adapters).
- Add or edit a framework adapter (LangGraph, ADK, Strands, Microsoft Agent
  Framework, OpenAI Agents SDK, Anthropic, CrewAI, LlamaIndex).
- Touch `pyproject.toml` extras, mypy, ruff, or the import-linter contracts.
- Review a PR diff that touches any of the above (see [[afdk-pr-review]]).

If the change is docs-only (`website/**`, `docs/**`, `*.md`), see
[[afdk-docs-authoring]] instead. If the change invents or confirms an endpoint,
header, or class name, [[afdk-verification-discipline]] is the more specific
rulebook.

## Pre-write checklist

Walk this against the build plan before writing code:

- [ ] **Typing under `mypy --strict`** — the whole `src/agent_fabric` tree is
      strict-checked and CI blocks on it. Annotate every public signature; no
      untyped defs, no implicit `Any`. Prefer `X | None` over `Optional[X]`
      (ruff `UP` will rewrite the old form). Use `from __future__ import
      annotations` at the top of every module (it is the house style — every
      file in the tree has it).
- [ ] **`TYPE_CHECKING` for framework types** — import a framework's *types*
      only under `if TYPE_CHECKING:` (see `integrations/langgraph.py`: `from
      langchain_openai import ChatOpenAI` lives in the guard; the runtime import
      is inside the method). This keeps `core/` and module top levels
      framework-free while still giving `mypy` and editors the real type.
- [ ] **Lazy framework import inside methods** — adapters import their framework
      *inside the method that uses it*, never at module top level. Pattern from
      `langgraph.py`:
      ```python
      def chat_model(self, model: str, **kw: Any) -> ChatOpenAI:
          from langchain_openai import ChatOpenAI  # lazy, inside the method
          return ChatOpenAI(model=model, **self.connection_kwargs(), **kw)
      ```
      This is what lets `import agent_fabric` succeed with no framework
      installed. The `base-only` CI job enforces it (installs only `[dev]`,
      imports `agent_fabric`, runs `tests/unit`).
- [ ] **Layering (§1.1)** — `integrations → tools → registry → llm → core`.
      Lower layers never import higher ones, and nothing below `integrations`
      may import `integrations`. Enforced by `lint-imports` (import-linter),
      blocking in CI. `core/` depends on **httpx + pydantic only** — no agent
      framework, ever.
- [ ] **pydantic v2 models** — config/state models are pydantic v2
      (`pydantic>=2.6`); the `pydantic.mypy` plugin is on. Use v2 idioms
      (`model_validate`, `Field`, `model_config`), not v1.
- [ ] **Citation habit** — when code encodes a spec decision, cite the section
      in the docstring/comment. Use **`BG §N.N`** for build-guide scope (e.g.
      `# budget parsed at the response hook (BG §1.3)`); a bare `§N.N` (e.g.
      `"""…(§2.3)"""`) points into the archived v1 plan and should not be added
      fresh. Reviewers and future-you rely on these to find
      the rationale.
- [ ] **Verification guards (§0.3)** — never invent an endpoint, header, or
      class name. Use `core/_verify.py`: `_verify.blocked("…")` returns
      `NotImplementedError("blocked on verification: …")` for surfaces with no
      defensible placeholder; `Unverified(...)` constants emit a one-time
      `UnverifiedValueWarning` and are config/env-overridable. Flip
      `verified=True` **and** the row in `docs/verified-apis.md` together, never
      one without the other. Full rules in [[afdk-verification-discipline]].
- [ ] **Extras are floors, never ceilings (§8.4)** — no upper version pins in
      `pyproject.toml`. Add `foo>=X`, never `foo<Y`. Known incompatibilities go
      in `docs/verified-apis.md §8.1` as documented dev constraints, not as
      pins. The nightly matrix (`scripts/verify_frameworks.py`) exists to catch
      breakage from newest releases early.
- [ ] **3.10 floor** — `requires-python = ">=3.10"`; CI matrix is 3.10/3.11/3.12.
      `tomllib` is stdlib only on 3.11+, so `tomli` is backfilled below 3.11;
      `typing-extensions` is pulled in below 3.12. Keep 3.10 compatibility — do
      not use 3.11+ syntax/stdlib without a backfill.
- [ ] **`py.typed`** — the package ships `src/agent_fabric/py.typed` (PEP 561).
      New subpackages inherit it; keep public API fully annotated so downstream
      users get types.
- [ ] **Three ergonomic forms per governed surface** — each adapter keeps the
      `fabric.<framework>` factory, a `connection_kwargs()` accessor, and a
      module-level factory (see `langgraph.py`). Keep all three when adding an
      adapter.
- [ ] **Trademark-descriptive language (§0.4)** — "Agent Fabric", "Anypoint",
      "Omni Gateway", "MuleSoft" are Salesforce trademarks. Write the package as
      a descriptive third-party SDK ("an SDK for consuming Agent
      Fabric"), never as a first-party / official Salesforce product.

## Post-write self-review

Run the same gate CI runs, from `python/`:

```bash
cd python
pip install -e ".[dev,llm,cli]"    # what CI installs
mypy                               # mypy --strict, BLOCKING (files=src/agent_fabric)
ruff check .                       # E,F,I,UP,B; line-length 100
lint-imports                       # §1.1 layering + framework-free core
pytest -q tests/unit               # the base-only unit job
pytest -q                          # full suite when you have the extras installed
```

If you touched framework adapters or their kwargs, also run the §8 signature
check (also the nightly-matrix gate):

```bash
python scripts/verify_frameworks.py            # offline signature check
python scripts/verify_frameworks.py --live     # + one real proxy round-trip
python scripts/verify_frameworks.py --emit-verified   # print §8 markdown rows
```

Then grep the diff for red flags:

```bash
# Framework imports leaked to a module top level (should be lazy / TYPE_CHECKING)
git diff origin/develop...HEAD -- 'python/src/agent_fabric/integrations/**' \
  | grep -nE "^\+(import|from) (langchain|langgraph|google|agents|anthropic|crewai|llama_index|strands|litellm|agent_framework)"
# → each hit must be inside a method body or under `if TYPE_CHECKING:`

# core/ reaching up into a framework or a higher layer
git diff origin/develop...HEAD -- 'python/src/agent_fabric/core/**' \
  | grep -nE "^\+(import|from) agent_fabric\.(integrations|tools|registry|llm)"

# Upper version pins sneaking into extras (§8.4 forbids them)
git diff origin/develop...HEAD -- 'python/pyproject.toml' | grep -nE '<[0-9]|<='

# A verification guard being replaced with a guess (§0.3)
git diff origin/develop...HEAD -- 'python/src/agent_fabric/**' \
  | grep -nE "^-.*(_verify\.blocked|Unverified\()"
# → confirm the value was actually verified + docs/verified-apis.md flipped
```

## Formatter + linter mechanics

- **ruff** owns both formatting-adjacent lint and code quality. Config in
  `[tool.ruff]`: `line-length = 100`, `target-version = "py310"`, selected rule
  families `E, F, I, UP, B`. `I` sorts imports; `UP` pushes modern syntax
  (`X | None`, `list[...]`); `B` is flake8-bugbear. One documented per-file
  ignore: `provisioning/cli.py` waives `B008` because Typer's API requires
  `typer.Option(...)` in argument defaults.
- **mypy** is `strict = true`, `python_version = "3.10"`, `files =
  ["src/agent_fabric"]`, with the `pydantic.mypy` plugin. Optional/absent deps
  are handled by a single `[[tool.mypy.overrides]]` block with
  `ignore_missing_imports = true` — do **not** scatter inline `# type: ignore`
  for a framework that becomes typed once its extra is installed (the block
  keeps those from going stale).
- **import-linter** (`lint-imports`) enforces two contracts in
  `[tool.importlinter]`: a `forbidden` contract (nothing in `core/llm/registry/
  tools` may import `integrations`) and a `layers` contract (the §1.1 stack).

## When to deviate

Encode the rule, not a law of nature. A principled deviation gets a leading
comment explaining *why*, with the section it trades against, so the next
reviewer does not re-flag it. If the deviation is general enough to recur,
update the relevant `spec/` document (or `docs/verified-apis.md` for a
verification change) in the **same** PR.

## Forbidden rationalizations

| Excuse | Reality |
| --- | --- |
| "I'll import the framework at the top, it's cleaner" | Then `import agent_fabric` breaks for anyone without that extra, and the `base-only` CI job fails. Import lazily inside the method; put the *type* under `TYPE_CHECKING`. |
| "`Any` here, I'll tighten the type later" | `mypy --strict` blocks CI and later doesn't come. Annotate it now; use `object`/`unknown`-style narrowing if the shape is genuinely open. |
| "It's just a small helper in `core/`, one framework import is fine" | `core/` is httpx + pydantic only (§1.1). `lint-imports` fails the build. There is no small exception. |
| "I'll pin `openai<3` so it stops breaking" | §8.4 forbids upper pins. Document the incompatibility in `docs/verified-apis.md §8.1`; let the nightly matrix surface it. |
| "I'll just fill in the real endpoint I think it is" | §0.3: never invent an endpoint/header/class name. Use `_verify.blocked(...)` or an `Unverified(...)` placeholder until it's confirmed against a sandbox. See [[afdk-verification-discipline]]. |
| "3.11 has `tomllib` built in, I'll use it directly" | The floor is 3.10. Use the `tomli` backfill path already in the code. |
| "I'll skip the local gate, CI will tell me" | mypy + ruff + lint-imports run in seconds locally; CI tells you minutes later on a branch reviewers are already looking at. |
| "The package is basically MuleSoft's, I'll word it that way" | §0.4: these are Salesforce trademarks. Keep the language descriptive/third-party unless the project ships with MuleSoft's endorsement. |

## Linkage to other rules

- **Verification (§0.3)** — [[afdk-verification-discipline]] is the specific
  rulebook for `_verify.py`, `docs/verified-apis.md`, and the status legend.
- **Tests + conformance kit (§8.1)** — [[afdk-testing]].
- **PR review of these conventions** — [[afdk-pr-review]]; the local gate above
  is the pre-PR smoke step consumed by [[afdk-pr-workflow]].
- **Branch/commit hygiene (`§N.N` in commit messages)** — [[afdk-git-workflow]].
