---
name: afdk-testing
description: Use when writing, reviewing, or expanding tests in agent-fabric-sdk — picks the right pytest surface (unit / conformance / fixture-driven / sandbox / local_gateway), enforces the "never a silent skip" conformance rule, and prevents per-PR drift in mocking and verification discipline.
---

# AFDK Testing

## Overview

This repo has five distinct test surfaces, each with its own job and its own
gate in CI. Getting the surface wrong either weakens a real gate (a framework
test slipped into `tests/unit`) or produces a false negative (a skipped
conformance scenario nobody reviews). This skill is the routing table plus the
mandatory assertions per surface. For architecture/layering rules that tests
must respect, see [[afdk-coding-conventions]]. For the "never invent an
endpoint/header/class name" discipline the fixture-driven tests exist to
enforce, see [[afdk-verification-discipline]].

All commands below run from `python/` (the CI `working-directory`).

## When to use

- About to add or change a test anywhere under `python/tests/`.
- About to add a new framework adapter under `integrations/` (conformance kit
  applies — see below).
- About to add or change error classification (`core/errors.classify`) or the
  transport layer (`core/transport`).
- About to touch `docs/verified-apis.md` status or add a `_verify.blocked(...)`
  guard — the fixture-driven tests are the other half of that discipline.
- Reviewing a PR that adds or changes tests.

## The first decision: which surface

```
Is it framework-free logic (core/, registry/, errors, config, transport)
  and uses only httpx + pydantic + fixtures?          -> tests/unit (base-only CI job)
Is it exercising an adapter's behavior against a
  fixed set of scenarios (any of the 8 frameworks)?    -> tests/conformance/suite.py
Is it pinning behavior to a REAL captured Anypoint
  request/response (proxy or control-plane)?           -> fixture-driven test under
                                                           tests/unit/ or tests/conformance/,
                                                           reading tests/fixtures/anypoint/**
Does it need a running local Omni Gateway (docker)?     -> @pytest.mark.local_gateway (off by default)
Does it need a real Anypoint sandbox?                   -> @pytest.mark.sandbox (off by default,
                                                            gated by FABRIC_SANDBOX_TESTS=1)
Is it a framework's constructor signature/kwarg shape?  -> scripts/verify_frameworks.py, not pytest
None of the above                                       -> STOP. Ask; don't invent a 6th surface.
```

## Surface 1 — `tests/unit/` (the base-only CI job)

This is the framework-free gate: CI's `base-only` job installs **only**
`.[dev]` (no `llm`, no framework extras) and runs `pytest -q tests/unit` after
importing `agent_fabric` — see `.github/workflows/ci.yml`. Anything here must
work with zero optional dependencies installed. Never add a top-level
framework import to a file under `tests/unit/`; that is exactly the drift this
job exists to catch.

What lives here today (read before adding a sibling):
- `test_errors.py` — `core/errors.classify()` taxonomy off synthetic
  `httpx.Response` objects (no fixtures needed for the generic branches).
- `test_llm_proxy_contract.py` — the SAME `classify()`, but pinned to LIVE
  captured fixtures (see Surface 3 below) — this file straddles "unit" and
  "fixture-driven".
- `test_transport.py` — header injection, retry policy, auth headers, via
  `httpx.MockTransport` (no real network, no respx needed for simple
  request/response stubbing).
- `test_config.py`, `test_pure_logic.py`, `test_registry_shapes.py`,
  `test_governed_state_shapes.py`, `test_fabric_surface.py`,
  `test_adapter_ergonomics.py`.

### Mandatory assertions for `core/errors.classify()` changes

Mirror `test_errors.py` and `test_llm_proxy_contract.py`. Every classify()
change must show:
- The 401 -> `AuthError`, 429 -> `TokenBudgetExceeded` (with `retry_after`
  parsed from whatever header the fixture actually has — `retry-after` OR
  `x-token-reset`/1000, never assume one exists), 5xx -> `UpstreamModelError`
  branches still hold.
- `PolicyViolation` is proven **not** a subclass of `UpstreamModelError` — a
  policy rejection is terminal, not retryable (§2.4). Don't let a refactor
  quietly merge these branches.
- Every `PolicyViolation` has a non-empty `remediation` — assert it directly,
  don't just assert `isinstance`.
- If you add a new rejection shape (a new policy, a new error envelope), add
  its capture to `tests/fixtures/anypoint/llm_proxy/` (see Surface 3) rather
  than hand-writing a synthetic body — this repo's error taxonomy is
  fixture-derived (§8.2), not assumption-derived.
- If two error families are distinguishable only by a subtle discriminator
  (flat-string `error` vs. nested `error` object; presence/absence of
  `www-authenticate`), write the discriminator test explicitly — see
  `test_two_error_envelope_families_are_distinguishable` — don't just test the
  happy path of the new branch.

## Surface 2 — `tests/conformance/suite.py` (the adapter conformance kit)

One suite, defined once (§8.1), run against **every** framework adapter. A
framework counts as "supported" only if it passes every scenario in
`CONFORMANCE_SCENARIOS`, or the scenario is a documented, **asserted**
exemption recorded in `KNOWN_LIMITATIONS[<framework>][<scenario>]` with a
non-empty reason string. There is no `pytest.mark.skip` escape hatch here —
a silent skip is exactly the failure mode this kit exists to prevent.

Current scenario list (18 scenarios spanning completion, tool-calling,
governance, attribution, and publication/descriptor drift) and the one
existing exemption (`adk` and `crewai` both route through LiteLLM and cannot
inject the httpx client, so `correlation_id_propagated` is exempted with a
documented reason) are both fixed in `suite.py` — read the module docstring
and `KNOWN_LIMITATIONS` before adding a ninth framework or a 19th scenario.

When adding or deepening an adapter. Note the roster is cut to **one deep,
conformance-gated adapter (LangGraph) plus seven frameworks supported at
`connection_kwargs()` only** (`BG §1.8`), and the old Tier 1 / Tier 2 split is
retired. A shallow framework is verified at the `connection_kwargs()` level,
not the constructor level:
1. Wire every scenario in `CONFORMANCE_SCENARIOS` against that adapter.
2. If a scenario genuinely cannot pass for a structural reason (not a bug you
   should fix), add an entry to `KNOWN_LIMITATIONS` with a specific,
   falsifiable reason — not "not supported yet".
3. Never add a framework-specific scenario to this file; if the new adapter
   needs a new invariant tested, that invariant must apply to all frameworks
   (extend `CONFORMANCE_SCENARIOS`) or it doesn't belong in the shared suite.
4. Nightly-matrix DoD (§8.4) for a deep, conformance-gated adapter requires: listed in
   `nightly-matrix.yml`'s framework matrix, has `scripts/verify_frameworks.py`
   entry, has `examples/<fw>/main.py` that exits 0 with no creds, and passes
   the conformance kit.

## Surface 3 — fixture-driven tests against captured Anypoint contracts

`tests/fixtures/anypoint/` holds REAL captures (not hand-written JSON) from a
real sandbox org, taken via `anypoint-cli-v4` and direct proxy calls. Read
`tests/fixtures/anypoint/README.md` and `tests/fixtures/anypoint/llm_proxy/README.md`
before adding a fixture — they record exactly which CLI command / HTTP call
produced each file, and which quirks matter (e.g. the token-rate-limit
rejection has an **empty body**, `retry-after` is absent and the budget is
header-only in ms; the PII rejection is a 403 with **no** `www-authenticate`,
which is the discriminator against the client-id-enforcement 401).

Rules for this surface:
- A fixture is a capture, not a fixture-of-convenience. If you need a new
  response shape, capture it for real (or get a maintainer to) and document
  the provenance in the relevant README the same way the existing entries do
  — org id, environment, CLI/proxy version, what was applied to produce the
  rejection, and confirmation nothing sensitive (API keys, tokens) survived.
- Load fixtures by path, off `Path(__file__).resolve().parents[N] / "fixtures" / "anypoint" / ...`
  — follow the existing pattern in `test_llm_proxy_contract.py` /
  `test_governed_state_shapes.py`, don't reinvent the fixture root.
- `respx` is a declared dev dependency (`pyproject.toml` `[dev]` extra,
  `respx>=0.21`) for mocking `httpx` calls against these captured contracts. It
  is not yet used anywhere in the tree — the raw-`httpx.MockTransport` pattern
  in `test_transport.py` is today's baseline for simple stubbing. Reach for
  `respx` specifically when a test needs to assert on the *request* that was
  sent (URL, headers, body) while replaying a captured fixture response, since
  that's the ergonomic gap `httpx.MockTransport` handlers don't close cleanly.
  Don't introduce a second, competing httpx-mocking convention without reading
  both files first.
- Cite the fixture's §-section (e.g. §2/§3/§4 for the LLM proxy contract, §6/§7
  for governed-state) in the test docstring, matching the existing style —
  this repo's tests are commentary-heavy on purpose; a fixture-driven test
  with no docstring pointing at the build-plan section is a red flag in
  review.

## Surface 4 — `sandbox` / `local_gateway` markers (off by default)

Declared in `python/pyproject.toml` `[tool.pytest.ini_options]`:
- `local_gateway` — requires a local Omni Gateway via docker (§6.5).
- `sandbox` — requires a real Anypoint sandbox, gated by
  `FABRIC_SANDBOX_TESTS=1` (off by default).

Neither marker has a test using it yet — they're declared ahead of the tests
that will need them (M1+, per suite.py's own docstring: "the scenario bodies
are wired in M1+ against captured contract fixtures and the local gateway").
When you add the first test using one of these markers:
- Mark it explicitly: `@pytest.mark.sandbox` / `@pytest.mark.local_gateway`.
- The test must degrade to a clean skip (not a failure) when its precondition
  env var/docker service is absent — that's what "off by default" means in
  CI. This is different from the conformance kit's "never skip" rule: these
  markers gate *infra availability*, not *framework support*, so a clean skip
  here is correct and a silent skip in `suite.py` is not.
- Do not run these by default in `pytest -q`; if you need to exercise them
  locally, use `pytest -q -m sandbox` / `-m local_gateway` (or run the file
  directly) with the required env vars / docker service up.

## Surface 5 — `scripts/verify_frameworks.py` (not pytest)

This is the executable form of the §0.3 verification step for the adapters'
native constructor signatures (docs/verified-apis.md §8) — it is deliberately
outside pytest because its subject is "does the exact class we name exist and
accept the exact kwargs we pass" against the framework as actually installed,
which pytest's fixture model doesn't fit well.

- `python scripts/verify_frameworks.py` — signature check (offline, all
  installed frameworks).
- `--live` — also makes one real completion round-trip; needs the 3
  `AGENT_FABRIC_LLM_PROXY_*` env vars.
- `--only <fw> [<fw>...]` — restrict to specific frameworks.
- `--emit-verified` — print §8 markdown rows to paste into
  `docs/verified-apis.md` after maintainer sign-off.
- Exit code is non-zero if any **installed** framework fails signature
  verification — this doubles as a CI gate. `nightly-matrix.yml` runs it per
  framework in the matrix (`langgraph`, `adk`, `strands`, `agent_framework`,
  `llamaindex`, `autogen`, `semantic_kernel`) plus the example smoke test
  (`examples/<fw>/main.py` must exit 0 with no creds) plus `pytest -q`.
- If you rename an adapter's native class or change its factory kwargs,
  `verify_frameworks.py`'s `FRAMEWORKS` tuple list is the other place to
  update (framework key, factory import path, factory fn name, expected
  `module.ClassName`) — a mismatch here shows as `CLASS RENAMED` or
  `SIGNATURE FAIL` in the table, not a pytest failure.
- A `_verify.blocked("…")`-guarded adapter constructor correctly shows as
  `BLOCKED (§0.3)` here, not a failure — don't "fix" the script to make a
  genuinely-blocked adapter pass; fix the blocking guard once the endpoint is
  verified.

## `mypy` as a correctness gate

`mypy` runs `--strict` (per `[tool.mypy]` / the `typecheck-and-lint` CI job)
and is **blocking**, same tier as tests. A test file that silences a type
error with an unexplained `# type: ignore` is hiding a real signature
mismatch — the same class of bug `verify_frameworks.py` exists to catch for
framework constructors. Run `mypy` locally before opening a PR that touches
`core/`, `registry/`, or any adapter:

```bash
mypy
```

## Routing quick-reference: "which surface does my change belong to"

| Change | Surface |
|---|---|
| New branch in `core/errors.classify()` | `tests/unit/test_errors.py` (synthetic) + a new/updated fixture in `tests/fixtures/anypoint/llm_proxy/` if it's a new real rejection shape |
| New header/retry/auth behavior in `core/transport.py` | `tests/unit/test_transport.py`, `httpx.MockTransport` |
| New/changed `registry/` model or governance rule | `tests/unit/test_governed_state_shapes.py` / `test_registry_shapes.py`, fixture-backed where the shape comes from real API Manager data |
| New framework adapter under `integrations/` | `tests/conformance/suite.py` (all scenarios) + `scripts/verify_frameworks.py` entry + `examples/<fw>/main.py` + nightly-matrix.yml row |
| Adapter constructor signature/kwarg change | `scripts/verify_frameworks.py` `FRAMEWORKS` tuple, re-run `--only <fw>` |
| New captured Anypoint contract | new file(s) under `tests/fixtures/anypoint/**` + README entry documenting provenance |
| Anything needing docker/sandbox | `@pytest.mark.local_gateway` / `@pytest.mark.sandbox`, clean-skip by default |

## Commands

```bash
# from python/
pip install -e ".[dev,llm,cli]"                       # dev install, what CI installs
pytest -q                                              # full suite
pytest -q tests/unit                                   # unit only (base-only CI job)
pytest -q tests/unit/test_errors.py::test_401_is_auth_error   # single test
pytest -q -m sandbox                                   # opt-in sandbox tests
pytest -q -m local_gateway                             # opt-in local-gateway tests
mypy                                                    # mypy --strict, blocking
ruff check .                                            # line-length 100; E,F,I,UP,B
lint-imports                                            # layered-architecture gate (§1.1)
python scripts/verify_frameworks.py [--live] [--only <fw>] [--emit-verified]
```

## Red flags — STOP

- A test under `tests/unit/` imports a framework package at module level (not
  lazily inside a method) — that breaks the `base-only` CI job's whole premise.
- A new adapter is called "supported" (docs, example, changelog) but has no
  entry in `tests/conformance/suite.py`'s run and no `KNOWN_LIMITATIONS`
  exemption for a scenario it can't pass.
- A `KNOWN_LIMITATIONS` entry with a vague reason ("not supported", "TODO") —
  it must be a specific, falsifiable structural reason like the existing
  LiteLLM-transport exemption.
- A hand-written JSON fixture under `tests/fixtures/anypoint/` with no README
  entry recording where it came from.
- A new `_verify.blocked(...)` guard added without a corresponding row/status
  change tracked in `docs/verified-apis.md` — see [[afdk-verification-discipline]].
- `# type: ignore` or a broadened `except Exception` added inside a test just
  to make `mypy`/the test pass.
- Loosening `ruff`/`mypy` config, or adding a new `pytest.ini_options` marker
  that isn't `sandbox`/`local_gateway`, to make a test suite green instead of
  fixing the code.

## Related skills

- [[afdk-coding-conventions]] — the layered architecture (`core` is
  framework-free) that Surface 1's `base-only` job protects.
- [[afdk-verification-discipline]] — the §0.3 "never invent an endpoint" rule
  that fixture-driven tests and `verify_frameworks.py` both enforce.
- [[afdk-pr-review]] — review-time checklist; testing gaps are one axis of it.
- [[afdk-git-workflow]] / [[afdk-pr-workflow]] — where these tests live in the
  branch → PR lifecycle.
