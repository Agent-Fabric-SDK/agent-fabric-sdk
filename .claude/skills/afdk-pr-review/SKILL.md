---
name: afdk-pr-review
description: Use when reviewing an agent-fabric-sdk pull request — checks this repo's architectural invariants (framework-free layered core / lint-imports, verification discipline & _verify guards, error-taxonomy correctness, floors-never-ceilings extras, §N.N citation hygiene, py.typed/mypy --strict, trademark wording) before a gh pr review.
---

# Agent Fabric SDK — PR Review

## Overview

`agent-fabric` (import package `agent_fabric`) rests on a small set of
architectural invariants documented in `CLAUDE.md` and the build plan
(`agent-fabric-sdk-build-plan.md`, the authoritative spec — every `§N.N`
points into it). Most are easy to violate in a way that passes a casual read but
breaks the layered/framework-free-core rule, invents an unverified endpoint, or
misclassifies a gateway rejection. This skill is the review-time checklist for
those invariants.

For the branch-side rules and how a PR is opened, see [[afdk-pr-workflow]] and
[[afdk-git-workflow]]. The two invariants with the most depth have dedicated
skills: [[afdk-verification-discipline]] (§0.3) and [[afdk-coding-conventions]].

## When to use

- About to leave a review on an agent-fabric-sdk PR (`gh pr review` — comment,
  request-changes, or approve).
- The user asks to "review", "look at", or "check" a PR or a diff.
- Before approving someone else's PR, even if CI is green — CI catches
  lint/type/import breaks, not invented endpoints or misfiled §-citations.

## Fetching the diff

```bash
gh pr view <pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --json title,body,files,additions,deletions,baseRefName,headRefName
gh pr diff <pr#>  --repo Agent-Fabric-SDK/agent-fabric-sdk
gh pr checks <pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk
```

Branch model is `develop` (integration) → `main` (release). If `baseRefName` is
not `develop` (and the PR isn't an explicit release PR into `main`), flag it
first.

## What to check

### 1. The layered, framework-free core (§1.1 — enforced by `lint-imports`)

The import graph is `integrations → tools → registry → llm → core`; **lower
never imports higher**. `core/` is framework-free — **httpx + pydantic only**.
The `[tool.importlinter]` contracts in `python/pyproject.toml` encode this: a
`forbidden` contract (nothing below may import `agent_fabric.integrations`) and a
`layers` contract listing the five layers top-to-bottom.

- Confirm CI's `typecheck-and-lint` job is green — it runs `lint-imports`. If the
  diff touches imports and that job is red, the layering is broken; request
  changes.
- **Adapters import their framework lazily inside methods**, never at module top
  level. A top-level `import langgraph` / `from crewai import …` in an
  `integrations/` module defeats the `base-only` CI job (which installs only
  `[dev]` and imports `agent_fabric`). Grep the diff for framework imports at
  column 0 inside `integrations/`.
- Any new top-level import in `core/`, `llm/`, `registry/`, `tools/` that pulls
  in an agent framework is a hard reject — it belongs in `integrations/`, lazily.
- Accessing an adapter whose extra isn't installed must raise `ImportError` with
  the exact `pip install` command, never a bare `ModuleNotFoundError` (§1.1 /
  CLAUDE.md "How the pieces connect").

If you can't tell from CI, run it locally from `python/`: `lint-imports`.

### 2. Verification discipline (§0.3 — never invent an endpoint, header, or class name)

`docs/verified-apis.md` is the single source of truth; `core/_verify.py` holds
the guards. See [[afdk-verification-discipline]] for the full mechanism. At
review time:

- A new endpoint path, header name, or framework class/kwarg in the diff must
  correspond to a `VERIFIED` row in `docs/verified-apis.md` (legend: `VERIFIED
  (LIVE|CLI|plugin|build)` / `VERIFIED-SHAPE-ONLY` / `UNVERIFIED`). If the value
  is asserted as fact but its row is still `UNVERIFIED`, that's an invented
  endpoint — request changes.
- **`_verify.blocked("…")` guards stay until the row is `VERIFIED`.** A diff that
  removes a `blocked(...)` call (which returns
  `NotImplementedError("blocked on verification: …")`) or flips an
  `Unverified(...)` constant's `verified=` to `True` must be accompanied by the
  matching `docs/verified-apis.md` row flipping to `VERIFIED` **in the same PR**,
  with a Date + Source. One without the other is incomplete. For a `VERIFIED
  (plugin)` row, §12.8 additionally wants one live smoke request before the guard
  comes off.
- New unverified values should be introduced as `Unverified(...)` placeholders
  (which warn once via `UnverifiedValueWarning` and are env/config-overridable),
  not as bare string constants asserted as truth. Real confirmed header names
  (e.g. `LLM_PROXY_CLIENT_ID_HEADER = "client_id"`) are plain constants only
  because their `docs/verified-apis.md §2/§3` rows are `VERIFIED (LIVE)`.

### 3. Error-taxonomy correctness (§2.4 — `core/errors.classify()`)

`classify()` discriminates on the error **`type`** plus specific headers, **not
the status code alone**. This is the single most common place to introduce a
subtle bug. Check any change to `classify()` or the fixtures against
`docs/verified-apis.md §4`:

- A 403 is **not** automatically an auth error. PII detection is a 403 with a
  nested `{"error":{…,"type":"pii_detected"}}` object and **no**
  `www-authenticate` header → `PIIDetected`, and it is checked **before** the
  401/403→`AuthError` rule. Reordering those two branches is a regression.
- Token rate limit is **429 with an empty body**; budget state is header-only
  (`x-token-limit` / `x-token-remaining` / `x-token-reset` in **ms**). There is
  no standard `retry-after`; `_retry_after()` falls back to `x-token-reset`/1000.
  A change that assumes a JSON body on 429, or reads `x-token-reset` as seconds,
  is wrong.
- client-id-enforcement is **401** + flat-string `{"error":"…"}` +
  `www-authenticate: Client-ID-Enforcement` → auth.
- Upstream provider passthrough is a **non-429 4xx** with a nested error object
  carrying `code`/`type`/`param` → `UpstreamRequestError` (terminal, distinct
  from `PolicyViolation`). Distinguished from a flat-string Anypoint refusal by
  `_provider_error_object()` (nested dict vs flat string).
- `PolicyViolation` is **never retried** and `remediation` is required. Any new
  subclass must set `policy` and pass `remediation=`.
- New rejection classifications must be backed by real captured fixtures under
  `tests/fixtures/anypoint/llm_proxy/`, not hand-written guesses (§8.2).
  prompt-injection / content-safety are still `UNVERIFIED` and must fall through
  to the generic `PolicyViolation` — a PR that "identifies" them without a
  capture is inventing a shape.

### 4. Extras are floors, never ceilings (§8.4)

No upper version pins in `python/pyproject.toml`. A diff adding `foo<2` or
`foo==1.4.*` to an extra contradicts the policy — the nightly matrix
(`nightly-matrix.yml`, runs `scripts/verify_frameworks.py` against latest
releases) is meant to catch breakage early against the newest resolve. Known
incompatibilities are **documented in `docs/verified-apis.md §8.1` as local dev
constraints**, not encoded as pins. Keep the Python 3.10 floor
(`tomllib`→`tomli` backfill, `typing-extensions` under 3.12).

### 5. §N.N citation hygiene

Every `§N.N` in code, docstrings, tests, and commit messages points into
`agent-fabric-sdk-build-plan.md`. When the diff adds or moves a citation:

- Spot-check that the cited section actually covers the claim — a `§`-cited guard
  must not be removed without reading its section (CLAUDE.md).
- A new guard, error class, or verification row should cite the section that
  authorizes it (e.g. `blocked(...)` for provisioning cites §0.3/§5).

### 6. Typing: `py.typed` + `mypy --strict`

`mypy` runs `--strict` and is **blocking in CI** (`typecheck-and-lint`,
`files=src/agent_fabric`). If that job is red, request changes — don't approve
around it. Public surfaces are fully annotated; the package ships `py.typed`, so
untyped `Any` leaking into a public signature degrades downstream users. `ruff
check .` (line-length 100; rules E,F,I,UP,B) must also be green.

### 7. Conformance kit (§8.1)

If the diff adds or changes a framework adapter, `tests/conformance/suite.py` is
ONE suite run against every adapter. A framework is "supported" only if it passes
all scenarios **or** records an **asserted exemption in `KNOWN_LIMITATIONS`** —
never a silent `skip`/`xfail`. A new adapter with no conformance coverage, or a
`pytest.skip` used to dodge a failing scenario, is a request-changes. Tier 1
adapters (LangGraph, Google ADK, Strands, Microsoft Agent Framework, OpenAI
Agents SDK, Anthropic SDK, CrewAI) are conformance-gated in blocking CI; Tier 2
(LlamaIndex) is non-blocking.

### 8. Trademark-descriptive wording (§0.4)

"Agent Fabric", "Anypoint", "Omni Gateway", "MuleSoft" are Salesforce
trademarks; the package is **descriptive, not first-party**. Reject README /
docs / docstring wording that implies the SDK is an official MuleSoft/Salesforce
product or endorses it. Keep the "for consuming Agent Fabric" framing.

### 9. Tests

- New `core/`/`llm/` logic lands with unit tests under `tests/unit`
  (the `base-only` job runs `pytest -q tests/unit`).
- `classify()` changes must come with fixture-backed cases (see §3 above).
- Live/sandbox tests stay off by default, gated by markers/env (`local_gateway`,
  `sandbox` + `FABRIC_SANDBOX_TESTS=1`). A diff that un-gates them, or hardcodes a
  sandbox host into a default-run test, is a request-changes.

See [[afdk-testing]] for the full testing conventions.

## Running the checks locally

All Python commands run from `python/`:

```bash
pip install -e ".[dev,llm,cli]"    # what CI installs
pytest -q                          # full suite
pytest -q tests/unit               # unit only (base-only CI job)
mypy                               # --strict, blocking
ruff check .
lint-imports                       # framework-free layered architecture (§1.1)
python scripts/verify_frameworks.py            # offline signature check
python scripts/verify_frameworks.py --emit-verified   # §8 rows to paste
```

## How to leave the review

Per [[afdk-pr-workflow]], `gh pr review --approve` requires explicit user
sign-off. Drafting the review body is automatic; **submitting an approve is
not.**

| Finding | Review type |
| --- | --- |
| Architectural invariant violated (sections 1–3, 7) | `--request-changes`, quoting the rule + `§N.N`. |
| Missing verified-apis.md row for a removed guard (section 2) | `--request-changes`. |
| Extras pin (section 4), silent conformance skip (section 7) | `--request-changes`. |
| §-citation drift, trademark wording nit, refactor/naming | `--comment`. |
| All invariants intact + CI green (`base-only`, `typecheck-and-lint`, `test`) | Draft `--approve`, then **ask the user** before submitting. |

```bash
# Draft review (do NOT submit --approve without user approval)
gh pr review <pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk --comment         --body-file review.md
gh pr review <pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk --request-changes --body-file review.md
# gh pr review <pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk --approve  ← user-approved only
```

Avoid a blanket "looks good" with no evidence. Quote the rule and the `§N.N`.

## Common smells

| Smell | Why it matters |
| --- | --- |
| Top-level `import <framework>` in an `integrations/` module | Breaks the `base-only` CI job and the framework-free-core rule (§1.1). |
| `core/`/`llm/` imports anything beyond httpx + pydantic | Violates the `forbidden` import-linter contract. |
| `_verify.blocked(...)` removed with no `verified-apis.md` row flipped | An invented endpoint shipping unverified (§0.3). |
| `Unverified(...).verified=True` with no VERIFIED row + Date/Source | Same — silences the warning without proof. |
| New endpoint/header/class asserted as fact, row still `UNVERIFIED` | Working instruction #2 violation. |
| 401/403→auth rule moved above the `pii_detected` check | Misclassifies a PII block as an auth error. |
| `classify()` reads a JSON body on 429 | 429 is empty-body; budget is header-only (§4). |
| prompt-injection / content-safety given a concrete shape | Still `UNVERIFIED`; must fall through to generic `PolicyViolation`. |
| Upper version pin added to an extra | Contradicts "floors, never ceilings" (§8.4). |
| `pytest.skip`/`xfail` in the conformance suite instead of `KNOWN_LIMITATIONS` | Silent skip hides an unsupported framework (§8.1). |
| Wording implying first-party MuleSoft/Salesforce product | Trademark misuse (§0.4). |
