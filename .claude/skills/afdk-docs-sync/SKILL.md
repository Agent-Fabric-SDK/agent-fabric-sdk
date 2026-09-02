---
name: afdk-docs-sync
description: Use when a PR touches a load-bearing SDK surface (core/errors.py, provisioning/*, tools/*, registry/*, integrations/*, docs/verified-apis.md, README.md) that the docs-site, the in-repo contributor docs (ARCHITECTURE.md, CONTRIBUTING.md), or the python/examples/*/README.md files describe. Forces the contributor to update the matching page (a docs-site/pages/**.mdx page, the contributor doc, or the paired example README) in the same PR or file a documentation-labeled follow-up issue. Companion to [[afdk-docs-authoring]].
---

# AFDK Docs Sync

## Overview

`docs-site/` (Nextra) describes how the SDK behaves from a developer's
perspective — install steps, governed model access, tool discovery/binding,
provisioning, and the verification contract. When code changes what the SDK
does or which platform facts it depends on, the docs must change with it, or
the drift gets discovered by a confused adopter instead of at review time.

This skill is the gate that prevents that drift. It is a PR-time human/agent
check, not a CI script — there is no automated drift detector in this repo, so
the discipline lives entirely in the mapping table below and in whether
reviewers enforce it.

For page structure, the `Callout type="info"` planned-design disclaimer, and
the audience contract, see [[afdk-docs-authoring]]. This skill only adds the
*when-to-update* mapping.

## When this skill activates

```bash
git diff --name-only origin/develop...HEAD
```

or, reviewing a PR you didn't author:

```bash
gh pr diff <pr#> --name-only --repo Agent-Fabric-SDK/agent-fabric-sdk
```

Cross-reference every touched path against the mapping table below. The table
is the ground truth — it was built from the real `python/src/agent_fabric/`
tree and the real `docs-site/pages/` tree, not guessed.

## Surface → docs-page mapping

| Code surface | Docs page(s) | Why |
| --- | --- | --- |
| `python/src/agent_fabric/core/errors.py` | `docs-site/pages/errors.mdx` | The four live-verified rejection shapes and the typed-exception taxonomy documented there come straight from `classify()` and the exception classes here. |
| `python/src/agent_fabric/core/config.py`, `core/auth.py` | `docs-site/pages/reference/configuration.mdx` | `Fabric.from_env()` precedence (kwargs → env vars → `.agent-fabric.toml` → defaults) and the three required LLM-proxy values are documented there. |
| `python/src/agent_fabric/core/_verify.py`, `docs/verified-apis.md` | `docs-site/pages/concepts/verification.mdx` + `docs-site/pages/reference/unsupported-boundary.mdx` | Verification status legend, `_verify.blocked(...)` guards, and the unsupported-boundary list are the public face of §0.3. |
| `python/src/agent_fabric/llm/*` (`catalog.py`, `client.py`) | `docs-site/pages/feature-overview.mdx`, `docs-site/pages/concepts/attribution.mdx` | Model catalog shape, capability flags, and the live-verified attribution headers (Pillar 1). |
| `python/src/agent_fabric/registry/governance.py`, `python/src/agent_fabric/governance.py` | `docs-site/pages/concepts/governance.mdx`, `docs-site/pages/concepts/environments.mdx` | The `Governance` object's three verbs and what each environment can actually enforce. |
| `python/src/agent_fabric/registry/publication.py`, `registry/exchange.py` | `docs-site/pages/publishing.mdx` | Publishing-to-Exchange is documented as symmetric with `Governance` — both objects share code and doc structure by design. |
| `python/src/agent_fabric/registry/introspect.py`, `registry/models.py` | `docs-site/pages/tool-access/discovery.mdx` | `fabric.tools.discover(...)` narrowing (search/governance/domain/tags/asset type/environment) and the `ToolSet` shape. |
| `python/src/agent_fabric/tools/filter.py` | `docs-site/pages/tool-access/discovery.mdx` | Filter semantics documented there must match the actual filter keys/behavior. |
| `python/src/agent_fabric/tools/session.py` | `docs-site/pages/tool-access/binding.mdx` | MCP session management section documents lifecycle for sessions created here. |
| `python/src/agent_fabric/registry/*` (lockfile/version resolution, wherever `version="latest"` pinning lives) | `docs-site/pages/tool-access/lockfile.mdx` | Pinning/lockfile behavior for governed tool catalogs. |
| `python/src/agent_fabric/integrations/*` (`adk.py`, `agent_framework.py`, `anthropic.py`, `crewai.py`, `langgraph.py`, `llamaindex.py`, `openai_agents.py`, `strands.py`, `_base.py`) | `docs-site/pages/frameworks/<same-framework>.mdx` (`adk.mdx`, `agent-framework.mdx`, `anthropic.mdx`, `crewai.mdx`, `langgraph.mdx`, `llamaindex.mdx`, `openai.mdx`, `strands.mdx`) + `docs-site/pages/frameworks/index.mdx` if the eight-framework list or Tier 1/2 status changes | Each adapter file maps 1:1 to a framework doc page; note `integrations/openai_agents.py` → `frameworks/openai.mdx` (name mismatch — verify before assuming a literal filename match). |
| `python/src/agent_fabric/tools/*` binding into an A2A `AgentHandle.as_tool()` path | `docs-site/pages/tool-access/a2a.mdx` | A2A agent-as-tool wrapping semantics. |
| `python/src/agent_fabric/provisioning/spec.py` | `docs-site/pages/provisioning/spec.mdx` | The declarative YAML spec format and its pydantic-validated shape. |
| `python/src/agent_fabric/provisioning/planner.py`, `provisioning/applier.py` | `docs-site/pages/provisioning/plan-apply.mdx` | `agent-fabric plan` / `agent-fabric apply` diff-and-change semantics. |
| `python/src/agent_fabric/provisioning/lint.py` | `docs-site/pages/provisioning/governance-lint.mdx` | `agent-fabric lint` ruleset behavior and CI-failing severities. |
| `python/src/agent_fabric/provisioning/publish.py` | `docs-site/pages/provisioning/index.mdx`, `docs-site/pages/publishing.mdx` | Pillar 3 overview and its publish-symmetry-with-Governance framing. |
| `python/src/agent_fabric/provisioning/cli.py` | `docs-site/pages/provisioning/index.mdx`, `docs-site/pages/quickstart.mdx` if CLI invocation syntax shown there changes | CLI command names/flags shown in provisioning docs and any quickstart CLI snippet. |
| `docs/unsupported-boundary.md` | `docs-site/pages/reference/unsupported-boundary.mdx` | That page explicitly defers to the repo file as the authoritative, maintained list — keep them in lockstep. |
| `docs/verified-apis.md` (status legend, any row flipping status) | `docs-site/pages/concepts/verification.mdx` + `docs-site/pages/reference/unsupported-boundary.mdx` | Both pages assert specific verification claims (live-verified LLM data plane, attribution, rejection shapes) that must track the real status table. |
| `README.md` (install steps, Status section, extras) | `docs-site/pages/quickstart.mdx`, `docs-site/pages/index.mdx` | The README's install/quickstart narrative and the site's landing/quickstart pages must not diverge on install command, extras, or verified-status claims. |
| `spec/agent-fabric-sdk-build-plan.md` (any §N.N a docs page cites) | whichever page cites that §N.N | Pages cite build-plan sections as authority (e.g. `verification.mdx` → §0.3, `errors.mdx` → the rejection-shape sections); if the cited section's content changes meaning, the citing page is now wrong even if no code changed. |

If a PR touches a surface not on this list but you suspect a docs implication
(new public API, new env var, new CLI flag), default to surfacing it — the
cost of asking is one PR comment; the cost of silent drift is an adopter
filing a confused issue against a page that describes a different SDK than
the one they installed.

## Contributor docs are in scope too (ARCHITECTURE.md / CONTRIBUTING.md)

The mapping above targets the consumer-facing `docs-site/`. Two in-repo
contributor docs describe the SDK's *internals and workflow* and drift the same
way when code changes underneath them — treat them as mapped surfaces, not
"just Markdown." Both cite the build plan's `§N.N` sections and link into each
other; a change that invalidates a claim they make must update them in the same
PR (or record the divergence as an intentional decision).

| Code / repo surface | Contributor doc + section | Why |
| --- | --- | --- |
| `core/_verify.py`, `docs/verified-apis.md` (guard mechanism, flip procedure) | `ARCHITECTURE.md` → *Verification discipline (§0.3)* | The narrative of `blocked(...)` vs `Unverified(...)` and how a row flips to `verified=True` lives here; a change to that mechanism dates the section. |
| `core/errors.py` (taxonomy invariants, `classify()`) | `ARCHITECTURE.md` → *Error-taxonomy design (§2.4)* | Documents the two invariants (`PolicyViolation` never retried; every error carries `remediation`) and that `classify()` is fixture-driven. |
| `pyproject.toml` `importlinter` config, or a new layer under `src/agent_fabric/` | `ARCHITECTURE.md` → *Layered architecture (§1.1)* | The 5-layer stack (`integrations → tools → registry → llm → core`) and the framework-free-core rule are described there. |
| `tests/conformance/suite.py` `KNOWN_LIMITATIONS`, Tier-1/Tier-2 status | `ARCHITECTURE.md` → *Framework tiering* | Tier gating (blocking vs non-blocking CI) and its rationale. |
| Branch/PR/release flow, CI gates (`.github/workflows/ci.yml`), pytest surfaces/markers (`pyproject.toml`), coding conventions | `CONTRIBUTING.md` (§1 workflow / §2 testing / §3 conventions) | This file is the human-readable distillation of the `afdk-*` skills; a workflow, CI-gate, test-surface, or convention change must move with it. |

### The deliberate example-README duplication

The **install + env-var Configure block** and each framework's **manual-equivalent
snippet** are intentionally duplicated between the canonical docs page and the
`python/examples/<fw>/README.md` files (and the `demos/README.md`
harness): the docs page is for *reading*, the example README is for *running it
in place* (CONTRIBUTING.md §4). Nothing enforces the correspondence, so it is a
**manual-sync drift risk**.

| Code / doc surface | Canonical (source of truth) | Paired copy to reconcile |
| --- | --- | --- |
| `integrations/<fw>.py` construction snippet | `docs-site/pages/frameworks/<fw>.mdx` | `python/examples/<fw>/README.md` "manual equivalent" |
| install command / env-var names (`core/config.py`, extras in `pyproject.toml`) | `docs-site/pages/quickstart.mdx` (+ `reference/configuration.mdx`) | every `python/examples/<fw>/README.md` "Run" block + `demos/README.md` "Setup" |

When you change an install command, an env-var name, or a framework's
construction snippet, update the canonical docs page **and** the paired example
README(s) in the same PR. When in doubt, the docs-site page wins and the example
README is reconciled to it.

## The gate

For every surface match, the PR author (or reviewing agent) must do one of:

1. **Update the matching page in the same PR.** Re-read the page top to
   bottom against the diff; rewrite the affected section(s). Mention the doc
   edit in the PR body.
2. **File a `documentation`-labeled follow-up issue** referencing the PR (see
   [[afdk-filing-issues]] for the filing flow). Title:
   `docs: update <page>.mdx for <change> (follow-up to #<pr#>)`. Body: what
   changed in the code and what the page needs to reflect. Cross-link the
   issue from the PR description.

**Not allowed:** merging with neither a docs update nor a linked follow-up.

## Deciding between update-now and follow-up

Update in the same PR when:

- The docs delta is mechanical (a new provisioning field, a new rejection
  shape row in `errors.mdx`, a flipped `VERIFIED` status).
- The PR already touches `docs-site/` or `docs/`.
- A developer hitting the merged change without the doc update would be
  actively misled (e.g. a page claims `UNVERIFIED` for something the PR just
  live-verified, or vice versa).

File a follow-up when:

- The docs delta needs content beyond a quick prose fix (e.g. a new framework
  adapter needing a whole new `frameworks/<name>.mdx` page).
- The change is exploratory/behind a guard (`_verify.blocked(...)` still in
  place) and the user-visible behavior isn't real yet.
- The docs delta is large enough to deserve its own review pass.

When in doubt, update in the same PR — follow-ups decay.

## What "re-read the page" means

1. Open the mapped `docs-site/pages/**.mdx` file and the source file(s) that
   changed.
2. Walk the page section by section: "is this still true after my PR merges?"
3. Rewrite any paragraph that is now wrong, respecting the audience contract
   in [[afdk-docs-authoring]] (including the `Callout type="info"` "Planned
   design" disclaimer where the page already carries one — don't silently
   remove it unless the underlying platform contract really is now
   `VERIFIED`).
4. If verification status changed (a row moved from `UNVERIFIED` to
   `VERIFIED (LIVE|CLI|plugin|build)` per docs/verified-apis.md), update the
   corresponding claim in `concepts/verification.mdx` and/or
   `reference/unsupported-boundary.mdx` and the top-of-README status banner
   consistently — don't let one page say "live" while another still says
   "planned design."

## Workflow when authoring a PR

1. Run the surface probe before opening the PR:
   ```bash
   git diff --name-only origin/develop...HEAD
   ```
2. Cross-reference each touched path against the mapping table above.
3. For each match, apply the gate (update now, or file + link a follow-up).
4. Run the repo's normal gates before pushing — `pytest -q`, `mypy`,
   `ruff check .`, `lint-imports` (from `python/`) — docs changes don't bypass
   these; a docs-only change to `docs-site/` can be checked with
   `npm run build` from `docs-site/` if you touched MDX syntax.
5. Mention any docs edit (or the follow-up issue link) explicitly in the PR
   description.

## Workflow when reviewing a PR

1. `gh pr diff <pr#> --name-only --repo Agent-Fabric-SDK/agent-fabric-sdk` and
   grep against the mapping table's left column.
2. For each match, check whether the PR (a) updated the mapped page, (b)
   linked a `documentation`-labeled follow-up issue, or (c) did neither.
3. If (c): block the merge with a review comment listing the surface
   match(es) and the specific page(s) that need one of (a) or (b). See
   [[afdk-pr-review]] for how this fits into the broader review pass.

## Forbidden rationalizations

| Excuse | Reality |
| --- | --- |
| "The page already says something close enough" | Re-read top to bottom before deciding that; "close enough" is how a `VERIFIED (LIVE)` claim outlives the fixture that backed it. |
| "I'll update the docs in a follow-up next PR" | File the issue now if you're not updating in this PR — the filed issue is the visible commitment; "next PR" with no issue is not. |
| "It's just an internal refactor, no behavior changed" | If the public surface (constructor names, error types, CLI flags, YAML spec fields) is unchanged, say so in the PR body and skip the mapped page — but confirm the surface really is unchanged, not just "probably." |
| "docs/verified-apis.md is engineering-internal, not docs-site" | It feeds two live docs-site pages (`concepts/verification.mdx`, `reference/unsupported-boundary.mdx`) plus the README status banner — a status flip there is a docs-site change by another name. |
| "The framework adapter is Tier 2 / experimental" | LlamaIndex (Tier 2) still has a `frameworks/llamaindex.mdx` page; Tier status changes what claims the page can make, not whether it needs updating. |

## Red flags — STOP

- About to merge a PR that touches a mapped surface with neither a docs
  update nor a linked follow-up issue.
- About to claim a page is "still accurate" without actually re-reading it
  against the diff.
- About to add a new load-bearing surface (new module under `core/`,
  `provisioning/`, `tools/`, `registry/`, `integrations/`) without adding a
  row to this table.
- About to change code underneath an `ARCHITECTURE.md` narrative (layering,
  verification discipline, error taxonomy, framework tiering) or a
  `CONTRIBUTING.md` workflow/testing/convention rule without updating the
  contributor doc in lockstep.
- About to change an install command, env-var name, or a framework's
  construction snippet without updating **both** the canonical docs page and
  the paired `python/examples/<fw>/README.md` copy.
- About to change a `docs/verified-apis.md` status without checking whether
  `concepts/verification.mdx`, `reference/unsupported-boundary.mdx`, or the
  README status banner now contradict it.

## Quick reference

```bash
# Probe: which mapped surfaces does this PR touch?
git diff --name-only origin/develop...HEAD | grep -E \
  'core/errors\.py|core/config\.py|core/auth\.py|core/_verify\.py|llm/|registry/|tools/|integrations/|provisioning/|docs/verified-apis\.md|docs/unsupported-boundary\.md|README\.md'

# Reviewing someone else's PR
gh pr diff <pr#> --name-only --repo Agent-Fabric-SDK/agent-fabric-sdk

# Filing a follow-up
gh issue create --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --title "docs: update <page>.mdx for <change> (follow-up to #<pr#>)" \
  --label documentation
```

## Extending the mapping table

When a new module becomes load-bearing for a docs page (new adapter, new
provisioning verb, new registry concept):

1. Add a row here — file pattern on the left, exact `docs-site/pages/**.mdx`
   path on the right, one-line "why."
2. Verify the target `.mdx` file actually exists under `docs-site/pages/`
   before writing the row — do not assume a plausible filename; `ls
   docs-site/pages/<dir>`.
3. If no matching page exists yet, that's a signal the new surface needs a new
   page — coordinate with [[afdk-docs-authoring]] rather than silently
   skipping the row.

See [[afdk-verification-discipline]] for the deeper rule this table is a
special case of: never let a doc page assert something the code (or
`docs/verified-apis.md`) doesn't back up.
