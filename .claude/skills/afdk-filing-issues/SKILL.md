---
name: afdk-filing-issues
description: Use when the user asks to file, open, create, or report a GitHub issue (bug or enhancement) against this Agent Fabric SDK repo
---

# Filing Agent Fabric SDK GitHub Issues

## Overview

Issues are filed against `Agent-Fabric-SDK/agent-fabric-sdk` — the user does not
maintain a fork. Always pass `--repo Agent-Fabric-SDK/agent-fabric-sdk`
explicitly to `gh` so the issue lands on the right repo regardless of the
working directory or which of `develop`/`main` is checked out.

## IRON LAW — Confirmation before creation

**Never run `gh issue create` until the user has explicitly confirmed the final
draft.** No exceptions.

Workflow — every single time, even when the user's request looks complete:

1. Gather title, type, area(s), body content.
2. **Show the full draft** to the user (title, labels, full rendered body) and
   ask for explicit approval.
3. Only after the user replies with confirmation (e.g. "yes", "file it", "go
   ahead") do you invoke `gh issue create`.

**Forbidden rationalizations:**

| Excuse | Reality |
| --- | --- |
| "The user already gave me everything" | They gave inputs, not approval to publish. Confirm. |
| "It's just a small typo fix issue" | Issues are visible to others; reversibility is partial. Confirm. |
| "User said 'open an issue for X'" | That's the request, not sign-off on the wording. Show draft, confirm. |
| "I already confirmed once this session" | Confirmation is per-issue, not per-session. |

A user saying "file an issue about the proxy header bug" is a **request**, not
a **confirmation**. Draft → show → wait → file.

## Target repo

```
Agent-Fabric-SDK/agent-fabric-sdk
```

Always pass `--repo Agent-Fabric-SDK/agent-fabric-sdk` to `gh issue create` and
`gh issue list`. Branch model is `develop` (integration) → `main` (release);
which branch is checked out locally is irrelevant to where the issue is filed.

## Before filing — gather these

1. **Type** — bug, enhancement, or docs.
2. **Title** — imperative mood, ≤ 70 chars, no trailing period.
3. **Area(s)** — which layer(s)/surface(s) of the architecture (see Labels).
4. **Body content** for the right template (see Templates).

If anything is ambiguous, ask once rather than guessing.

**Order of operations** (each step is a hard gate — do not proceed past a
failure):

1. Brainstorm scope (next section) — only if [[superpowers:brainstorming]] is
   available.
2. Codebase verification.
3. Cross-surface impact evaluation (SDK layers → docs → CLI → verified-apis.md).
4. Duplicate check.
5. Draft, citing `BG §N.N` build-guide sections where relevant (see the
   citation convention in `CLAUDE.md` — `BG §` for the build guide, bare `§`
   only for the archived v1 plan).
6. Show draft to user.
7. Wait for explicit confirmation.
8. Assign the milestone — pick the one matching milestone (see Milestone); ask
   the user once if the mapping is genuinely ambiguous.
9. Create any missing labels (`gh label create … || true`).
10. `gh issue create`.

## Brainstorm scope before drafting

If [[superpowers:brainstorming]] is available in this session, invoke it
**before** codebase verification to align with the user on the issue's intent,
scope, and shape. The output becomes the raw material for the issue body —
title, problem statement, proposal, out-of-scope.

Skip brainstorming only when:

- The skill is not available in the session.
- The request is trivially scoped (typo, broken link, one-line docstring) and
  the title/body are obvious from the user's message.

Do not create local `plans/` or scratch `.md` files for this — the GitHub issue
body is the artifact. Brainstorm in the conversation; conclusions land in the
issue.

## Codebase verification — mandatory

Before drafting the issue body, **verify the user's claim against the actual
code**, per §0.3 (never invent an endpoint, header, or class name — the same
discipline applies to what you claim in an issue). This applies to both bugs
and enhancements:

- **Bug**: confirm the broken path exists in code, find the actual error site,
  capture `file:line`.
- **Enhancement**: confirm the gap is real — check `docs/verified-apis.md` and
  `core/_verify.py` first; a feature that looks "missing" may already be a
  deliberate `_verify.blocked("…")` guard with an existing `Verification`
  milestone row, in which case the "issue" is really "unblock that row", not a
  new gap.

Workflow:

1. Use `Grep`/`Read` (or an Explore agent for broad searches) to locate the
   relevant module. Start from the layer map in `CLAUDE.md` (`core` → `llm` →
   `registry` → `tools` → `integrations`, plus `provisioning/`).
2. Read enough of the code to confirm or refute the claim.
3. Capture specific `path:line` references for a `## Current behavior
   (verified)` section, and cite the relevant `BG §N.N` build-guide section if
   one governs the area.

**If the claim is wrong or already implemented:** stop and tell the user, with
file:line citations. Do not file an issue for a non-issue.

**If the claim is partially right:** narrow title/scope to what's actually
missing/broken; note what already works.

**If fully confirmed:** draft with `## Current behavior (verified)` citing
exact locations.

Forbidden rationalizations:

| Excuse | Reality |
| --- | --- |
| "User clearly knows the codebase" | Even the author misremembers which layer owns what. Verify. |
| "It's a feature request, nothing to verify" | It may already be a tracked `_verify.blocked(...)` guard. Verify the gap first. |
| "Verifying takes too long" | One Grep + one Read is ~10 seconds; a wrong-headed issue costs hours of triage. |

## Cross-surface impact evaluation — mandatory

This SDK exposes the **same capability through multiple layered/parallel
surfaces**. A change framed as "a core fix" almost always has siblings in
adapters, docs, or the CLI. Filing an issue that names only the surface the
user mentioned produces partial work. Before drafting the body, walk every
surface below and record an explicit verdict in a `## Cross-surface impact`
section.

| Surface | Where it lives | Ask yourself |
| --- | --- | --- |
| **`core/`** | `python/src/agent_fabric/core/` — config, auth, transport, errors, telemetry, cache | Framework-free by contract (§1.1). Does this change a shared header, error classification (`core/errors.classify()`), or a `_verify.py` guard/placeholder? |
| **`llm/`** | `python/src/agent_fabric/llm/` — OpenAI-compatible proxy client + catalog | Does the LLM data-plane contract (base URL, `client_id`/`client_secret` headers, streaming, rejection shapes, §2–§4) change? |
| **`registry/`** | `python/src/agent_fabric/registry/` — Exchange/governed-state | Does Exchange lookup or governed-state shape change? |
| **`tools/`** | `python/src/agent_fabric/tools/` — MCP discovery/binding | Does `fabric.tools.discover` or any MCP-bridge binding logic change (currently blocked on verification, §6.7)? |
| **`integrations/`** | `python/src/agent_fabric/integrations/` — LangGraph (the one deep, conformance-gated adapter) plus seven frameworks supported at `connection_kwargs()` only | Does the deep adapter change, or the shared `connection_kwargs()` contract? A shared-contract change (e.g. header injection) puts every framework in scope at once — the conformance kit (`python/tests/conformance/suite.py`) exists precisely to catch that drift. See `BG §1.8`. |
| **TypeScript parity (Phase 5, `BG §3.5`)** | not yet in code | Would a Python-side fix need a matching TS-side note/follow-up once TS ships? Flag it even though there's no TS code yet, so the parity gap is tracked. |
| **Provisioning CLI** | `python/src/agent_fabric/provisioning/cli.py` (`agent-fabric` command: `validate`, `plan`, `apply`, `drift`, `lint`, `generate`, `status`, `init`, `publish`, `verify`) | Does a CLI command's behavior, output, or `_blocked(...)` message change? |
| **Nextra docs site** | `website/pages/` (`index.mdx`, `quickstart.mdx`, `feature-overview.mdx`, `errors.mdx`, `publishing.mdx`, plus `concepts/`, `frameworks/`, `provisioning/`, `reference/`, `tool-access/`) | Does a documented flow, code sample, or reference page describe the behavior being changed? |
| **`docs/verified-apis.md`** | repo root `docs/verified-apis.md` + guards in `core/_verify.py` | Does this issue flip a row's status (UNVERIFIED → VERIFIED-*), add a new row, or touch a `_verify.blocked(...)` / `Unverified(...)` guard? Say which row. |

How to apply the verdict:

- **In scope, this issue:** name the concrete module(s)/file(s) in the
  Proposal and add the matching `area:*` label.
- **In scope, but deliberately deferred:** say so in `## Out of scope` and file
  (or note the need for) a linked follow-up via [[afdk-issue-relationships]].
  Never silently drop a surface.
- **Genuinely not affected:** state that explicitly (e.g. "TypeScript parity:
  not affected, no TS code exists yet"). A one-line "not affected" is the proof
  you checked, not noise.

The guiding rule: **a capability that exists on more than one surface must
change on all of them in lockstep (respecting the layering — lower layers never
import higher ones), or the divergence must be a recorded, intentional
decision.**

Forbidden rationalizations:

| Excuse | Reality |
| --- | --- |
| "User only asked about core" | The user named the symptom surface. Map the full blast radius across layers. |
| "The adapter fix is obvious, the implementer will notice" | Implementers scope to the issue; an unmentioned adapter is an unfixed adapter. |
| "Docs can be updated later" | "Later" is how docs rot. Either in this issue or a linked follow-up — [[afdk-docs-sync]]. |
| "TypeScript doesn't exist yet" | Then the issue is where the future parity gap gets recorded. Flag it now. |
| "Listing unaffected surfaces is noise" | An explicit "not affected" is the audit trail proving you evaluated it. |

## Duplicate check — mandatory

Before showing the draft to the user, search existing issues for likely
duplicates:

```bash
gh issue list \
  --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --state all --limit 20 \
  --search "<2-3 distinctive keywords from the title or symptom>"
```

Pick keywords that would appear in a duplicate's title/body — class names,
`§N.N` references, error type strings — not generic words like "bug" or
"error".

**If you find a plausible match:** surface it with the issue number/URL and
ask whether to (a) comment on the existing issue instead, (b) file a new one
with a back-reference, or (c) drop it. Do not silently skip filing.

**If nothing matches:** proceed to draft + confirmation, and note that you
checked ("No matching open or closed issues for `<keywords>`").

## Labels

The repo does not ship a pre-defined label taxonomy — create labels on first
use with `gh label create ... || true` (idempotent) before `gh issue create`,
since a missing label hard-errors the create call. Triage runs on **milestone +
labels** together (see Milestone); there is no GitHub Projects v2 board.

**Type label (apply exactly one):**

| User intent | Label |
| --- | --- |
| Something is broken | `bug` |
| New capability / improvement | `enhancement` |
| Docs-only (README, `website/`, `docs/verified-apis.md`, docstrings) | `documentation` |
| Build/tooling/refactor with no user-facing behavior change | `chore` |

**Priority label (apply exactly one):**

| Label | Meaning | When to use |
| --- | --- | --- |
| `priority/p0` | Critical | Breaks the LLM data-plane contract, is a security issue, blocks the current phase, or blocks CI on `main`. |
| `priority/p1` | Must-have | Blocks a real adapter/framework from working, or breaks `lint-imports`/`mypy --strict`. |
| `priority/p2` | Ship soon | Meaningful improvement; a workaround exists. **Default when unsure.** |
| `priority/p3` | Nice-to-have | Cosmetic, docs polish, or future-facing (e.g. TS parity notes). |

**Size label (apply exactly one):**

| Label | Effort | Typical shape |
| --- | --- | --- |
| `size/xs` | <1h | Docstring/docs tweak, single-line fix. |
| `size/s` | ~½ day | One file or a small contained change; maybe one new test. |
| `size/m` | 1-2 days | Multiple files, a new adapter method, or a focused refactor. |
| `size/l` | 3+ days | New adapter, cross-layer change, or anything touching `docs/verified-apis.md` sign-off plus code. |

Signals that push an issue up a size bucket:

- Spans more than one architecture layer (`core`/`llm`/`registry`/`tools`/`integrations`).
- Flips a `docs/verified-apis.md` row from `UNVERIFIED` (needs a real sandbox
  round-trip, not just a code change).
- Touches the shared `connection_kwargs()` contract, so every framework is in
  scope at once (conformance-kit-wide change).
- Adds a new framework integration or a new CLI command.

If the issue feels larger than `size/l`, decompose into sub-issues via
[[afdk-issue-relationships]] rather than filing one oversized issue.

**Area label (apply one *per area the issue touches*).** These use a **colon**
(`area:skeleton`), not a slash. The old `area/*` slash labels are **retired** —
using one will not fail the create call, it will silently re-create a dead
label, which is worse. Each area maps to a build guide section, so the label
tells a reader which part of the guide is that issue's spec:

| Label | Covers | `BG §` |
| --- | --- | --- |
| `area:skeleton` | `FabricAsyncClient`, config, transport hooks, the `Fabric` facade | `1.1` |
| `area:refusals` | `classify()`, the typed error taxonomy, refusal handlers | `1.2`, `2.1`, `2.2` |
| `area:budget` | `Budget` object, pacing, rate-limit awareness | `1.3` |
| `area:simulator` | `fabric mock` — the local gateway simulator | `1.4` |
| `area:testing` | `simulate()`, the public pytest plugin, conformance kit | `1.5` |
| `area:telemetry` | OTel GenAI spans, correlation IDs, cost tags | `1.6`, `1.7` |
| `area:adapters` | Framework adapters and `connection_kwargs()` | `1.8`, `2.8` |
| `area:cli` | The `fabric` CLI and the decorators | `1.9` |
| `area:docs` | Docs site, README, `llms.txt`, examples | `1.10` |
| `area:hitl` | Human-in-the-loop normalisation, approval routing | `2.3` |
| `area:identity` | On-behalf-of, RFC 8693 token exchange | `2.4` |
| `area:scanner` | `fabric scan` / `publish` and the GitHub Action | `2.5` |
| `area:tools` | MCP tool discovery and governed tool consumption | `2.7` |
| `area:a2a` | A2A `serve` / `expose` / `dev` | `2.9` |
| `area:policies` | Policy handshake and to-the-code push | `3.2`, `3.3` |
| `area:release` | Packaging, PyPI, semver, changelog, CI | — |
| `area:typescript` | The TypeScript port | `3.5` |

**Status labels (apply if they fit):**

| Label | Meaning |
| --- | --- |
| `blocked-on-verification` | Cannot be closed by writing code — needs a `§0.3` answer first |
| `upstream-gap` | A product ask to the Omni Gateway team, not SDK code |
| `epic` | Tracking issue spanning several child issues |
| `six-piece-minimum` | Part of the minimum set that justifies installing the SDK |

When in doubt, scan the Proposal section line-by-line and add a label for each
area it names.

Before applying an area label for the first time, create it — run all needed
`gh label create` calls in one step, even if the labels probably already
exist:

```bash
R="--repo Agent-Fabric-SDK/agent-fabric-sdk"

# area (colon, not slash)
gh label create area:skeleton           $R --color 5319e7 --description "FabricAsyncClient, config, transport hooks, Fabric facade (1.1)" 2>/dev/null || true
gh label create area:refusals           $R --color e11d21 --description "classify(), the typed error taxonomy, handlers (1.2, 2.1, 2.2)" 2>/dev/null || true
gh label create area:budget             $R --color d93f0b --description "Budget object, pacing, rate-limit awareness (1.3)" 2>/dev/null || true
gh label create area:simulator          $R --color 0e8a16 --description "fabric mock — the local gateway simulator (1.4)" 2>/dev/null || true
gh label create area:testing            $R --color bfd4f2 --description "simulate(), the pytest plugin, conformance kit (1.5)" 2>/dev/null || true
gh label create area:telemetry          $R --color 1d76db --description "OTel GenAI spans, correlation IDs, cost tags (1.6, 1.7)" 2>/dev/null || true
gh label create area:adapters           $R --color fbca04 --description "Framework adapters and connection_kwargs() (1.8, 2.8)" 2>/dev/null || true
gh label create area:cli                $R --color b60205 --description "The fabric CLI and decorators (1.9)" 2>/dev/null || true
gh label create area:docs               $R --color c2e0c6 --description "Docs site, README, llms.txt, examples (1.10)" 2>/dev/null || true
gh label create area:hitl               $R --color f9d0c4 --description "Human-in-the-loop normalisation and approval routing (2.3)" 2>/dev/null || true
gh label create area:identity           $R --color 006b75 --description "On-behalf-of, RFC 8693 token exchange (2.4)" 2>/dev/null || true
gh label create area:scanner            $R --color c5def5 --description "fabric scan / publish and the GitHub Action (2.5)" 2>/dev/null || true
gh label create area:tools              $R --color 0052cc --description "MCP tool discovery and governed tool consumption (2.7)" 2>/dev/null || true
gh label create area:a2a                $R --color 5319e7 --description "A2A serve / expose / dev (2.9)" 2>/dev/null || true
gh label create area:policies           $R --color bfdadc --description "Policy handshake and to-the-code push (3.2, 3.3)" 2>/dev/null || true
gh label create area:release            $R --color fef2c0 --description "Packaging, PyPI, semver, changelog, CI" 2>/dev/null || true
gh label create area:typescript         $R --color 2b7489 --description "TypeScript port (3.5)" 2>/dev/null || true

# status
gh label create blocked-on-verification $R --color e11d21 --description "Cannot be closed by writing code (§0.3)" 2>/dev/null || true
gh label create upstream-gap            $R --color 000000 --description "A product ask to the Omni Gateway team, not SDK code" 2>/dev/null || true
gh label create epic                    $R --color 3e4b9e --description "Tracking issue spanning several child issues" 2>/dev/null || true
gh label create six-piece-minimum       $R --color ff8c00 --description "Part of the minimum set that justifies installing the SDK" 2>/dev/null || true

# priority / size / type
gh label create priority/p0             $R --color b60205 --description "Critical: blocks the phase" 2>/dev/null || true
gh label create priority/p1             $R --color d93f0b --description "Must-have for the milestone" 2>/dev/null || true
gh label create priority/p2             $R --color fbca04 --description "Meaningful improvement, ship soon" 2>/dev/null || true
gh label create priority/p3             $R --color 0e8a16 --description "Nice-to-have, not blocking" 2>/dev/null || true
gh label create size/xs                 $R --color c5def5 --description "Trivial: <1h" 2>/dev/null || true
gh label create size/s                  $R --color 9ecbe8 --description "~half day, one file" 2>/dev/null || true
gh label create size/m                  $R --color 76b8da --description "1-2 days, multiple files" 2>/dev/null || true
gh label create size/l                  $R --color 4a90c2 --description "3+ days, cross-layer" 2>/dev/null || true
gh label create size/xl                 $R --color 2c5f8a --description "Multi-week, its own workstream" 2>/dev/null || true
gh label create chore                   $R --color fef2c0 --description "Build/tooling/refactor, no user-facing behavior change" 2>/dev/null || true
```

The `2>/dev/null || true` makes re-runs idempotent. There is no GitHub Projects
v2 board to add the issue to after filing — milestone + labels drive triage.

## Milestone

**Every new issue MUST be assigned to exactly ONE milestone.** Milestones are
the only roadmap axis this repo has (there is no Projects v2 board), so an issue
without one is invisible to release planning. `gh` resolves `--milestone` by the
exact title string, so **quote the title verbatim — never invent, reword, or
renumber it** (§0.3 discipline applies with extra force to the skill that
enforces it).

The milestones, with the scope each owns. Five are sequential product phases
carrying a semver target; two are standing and unversioned:

| Milestone title (verbatim) | Scope |
| --- | --- |
| `Phase 1 — Build the MVP (0.1.0)` | Skeleton + the six-piece minimum (typed refusals, budget, simulator, `simulate()`+conformance, OTel GenAI, correlation/cost tags), one deep LangGraph adapter, decorators + CLI, docs, PyPI. `BG §1.1`–`1.10`. |
| `Phase 2 — Differentiate, go beyond (0.2.0)` | Refusal handlers, classification registry, HITL, identity helpers, in-repo scanner + Action, kill-switch, MCP discovery, second adapter, A2A `serve`/`expose`/`dev`. `BG §2.1`–`2.9`. |
| `Phase 3 — Platform capabilities (0.3.0)` | Policy handshake, to-the-code push, structured output + eval hooks. Largely gated on `Upstream gaps`. `BG §3.2`–`3.4`. |
| `Phase 4 — Enterprise readiness (0.4.0)` | Security review, performance budget, error-message pass, migration and deprecation policy, compliance evidence, log shipping, residency, workload identity, support model. |
| `Phase 5 — Complete rollout (1.0.0)` | TypeScript port, remaining adapters by demand, go-to-market, 1.0 stability guarantees. `BG §3.5`, gated on Python product-market fit. |
| `Verification` | The `§0.3` worklist: never invent an endpoint, header, class name or kwarg. Cross-phase and unversioned — each row blocks specific feature work. |
| `Upstream gaps` | Product asks to the Omni Gateway team. Filed in Phase 1, landing whenever the gateway ships them. `BG §3.1`. |

Note the em-dash (`—`) in every phase title, and that `Verification` and
`Upstream gaps` have no version and never complete.

**Picking heuristic** — key off the issue's `BG §N.N` and its primary
area/surface:

| Issue is about… | Milestone |
| --- | --- |
| verification / `_verify.py` guards / flipping a `docs/verified-apis.md` row | `Verification` |
| a product ask only the gateway team can close (no SDK code will fix it) | `Upstream gaps` |
| the skeleton, transport hooks, config, or the `Fabric` facade | `Phase 1 — Build the MVP (0.1.0)` |
| any of the six-piece minimum: refusals, budget, simulator, `simulate()`/conformance, OTel GenAI, correlation/cost tags | `Phase 1 — Build the MVP (0.1.0)` |
| the LangGraph deep adapter, `connection_kwargs()`, decorators, the `fabric` CLI, quickstart/docs, PyPI release | `Phase 1 — Build the MVP (0.1.0)` |
| refusal handlers, classification registry, HITL, identity/OBO, scanner + Action, kill-switch, MCP tool discovery, A2A, the second adapter | `Phase 2 — Differentiate, go beyond (0.2.0)` |
| policy handshake, to-the-code push, structured output, eval hooks | `Phase 3 — Platform capabilities (0.3.0)` |
| security review, perf budget, deprecation policy, compliance evidence, support model | `Phase 4 — Enterprise readiness (0.4.0)` |
| TypeScript, remaining adapters by demand, go-to-market, 1.0 guarantees | `Phase 5 — Complete rollout (1.0.0)` |

If an issue is **blocked on a verification answer but is itself feature work**,
file it in its feature phase and add `blocked-on-verification` — do not park
feature work in the `Verification` milestone. `Verification` holds the
questions, not the features that wait on them.

If the mapping is **genuinely ambiguous** (e.g. an issue that spans two
milestones' scope with no clear primary), **ask the user once** which milestone
to use rather than guessing — the same "ask once rather than guessing" rule the
rest of this skill follows.

Pass the milestone on the create call: `gh issue create --milestone "<exact
title>"`. To set or change it on an already-filed issue: `gh issue edit <#>
--milestone "<exact title>"`. To read an issue's milestone back:

```bash
gh api repos/Agent-Fabric-SDK/agent-fabric-sdk/issues/<#> --jq '.milestone.title'
```

## Title conventions

- Imperative, present tense: "Classify PII rejection before token-budget
  rejection" (not "Classified" or "Classifying").
- Bugs lead with the symptom, not the fix: "`fabric.llm.client()` omits
  `client_secret` header on retry" not "Add header to retry logic".
- No issue numbers, no `[BUG]` prefixes — labels cover that.

## Templates

### Bug

```markdown
## Summary
<one paragraph: what's broken and the user-visible impact>

## Reproduction
1. <step>
2. <step>
3. <step>

## Expected
<what should happen — cite the BG §N.N build-guide section if one governs it>

## Actual
<what happens — paste error messages / stack traces in fenced blocks>

## Current behavior (verified)
<file:line references confirming the bug in this codebase>

## Cross-surface impact
- **core/llm/registry/tools/integrations:** <which layer(s), or "not affected">
- **TypeScript parity (planned):** <note, or "not affected">
- **Provisioning CLI:** <command affected, or "not affected">
- **Nextra docs site:** <page, or "not affected">
- **docs/verified-apis.md:** <row affected, or "not affected">

## Environment
- Branch / commit: <git rev-parse --short HEAD>
- Python version: <3.10 / 3.11 / 3.12>
- Extras installed: <e.g. dev,llm,cli>
```

### Enhancement

```markdown
## Summary
<one paragraph: what should exist and why>

## Motivation
<user problem this unblocks — link the relevant BG §N.N build-guide section>

## Proposal
<concrete shape of the change — which module(s), which layer, any new
Unverified(...) placeholder or _verify.blocked(...) guard to add/remove>

## Cross-surface impact
- **core/llm/registry/tools/integrations:** <which layer(s), or "not affected">
- **TypeScript parity (planned):** <note, or "not affected">
- **Provisioning CLI:** <command affected, or "not affected">
- **Nextra docs site:** <page(s), or "not affected">
- **docs/verified-apis.md:** <new/changed row, or "not affected">

## Out of scope
<what this issue intentionally does NOT cover — name any in-scope surface
deliberately deferred to a follow-up>

## Acceptance criteria
- [ ] <observable behavior>
- [ ] <observable behavior>
```

### Docs

```markdown
## Summary
<what's missing/wrong in docs>

## Where
<file path(s) — README.md, CLAUDE.md, website/pages/..., docs/verified-apis.md>

## Suggested change
<bullet points or a draft>
```

## Assignee on filing

**File new issues unassigned.** Assignee marks who is *actively working* on an
issue, not who triages it. The assignee is set later, when someone picks the
issue up — see [[afdk-git-workflow]]. Do not pass `--assignee` on `gh issue
create` unless the user explicitly names one.

## Filing command

Use a heredoc for the body so multi-line markdown survives intact:

```bash
gh issue create \
  --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --title "Classify PII rejection before token-budget rejection" \
  --milestone "Phase 1 — Build the MVP (0.1.0)" \
  --label bug --label area:refusals --label priority/p1 --label size/s \
  --body "$(cat <<'EOF'
## Summary
...

## Reproduction
...
EOF
)"
```

Multiple labels: repeat `--label`. Do not use `--label "a,b"` (interpreted as
one label name).

## Issue relationships

If this issue depends on, blocks, or relates to another issue, add a `##
Depends on` or `## Related` section to the body before filing:

```markdown
## Depends on
- #13 — <one-line reason>

## Related
- #11 — <one-line reason>
```

The structural wiring (sub-issue / blocked-by / cross-link comment) happens
**after** the issue is filed, via [[afdk-issue-relationships]]. Don't use
closing keywords (`Closes #X`, `Fixes #X`) issue → issue; those only work in PR
descriptions.

## Verifying after filing

After `gh issue create` returns the URL:

1. Print the URL to the user.
2. Do not auto-comment, auto-assign, or auto-close. Issue management beyond
   creation needs explicit user instruction.

## Red flags — STOP and ask for confirmation

If you find yourself about to run `gh issue create` and any of these are true,
**stop**:

- You have not shown the user the rendered title + body in this turn.
- The user's last message described the problem but did not say "file it" /
  "create it" / "go ahead" / equivalent.
- You're filing a second issue in the same turn after one confirmation (each
  issue needs its own confirmation).
- You haven't run `gh issue list --search` for likely duplicates this turn.
- You haven't grepped/read the relevant code (or `docs/verified-apis.md`) to
  verify the claim and capture `file:line` references.
- The body has no `## Cross-surface impact` section, or that section omits any
  surface (layers, TypeScript parity, provisioning CLI, docs site,
  verified-apis.md). Every surface gets a verdict — "not affected" counts;
  silence does not.
- You concluded a surface is in scope but neither added its `area:*` label nor
  recorded the deferral in `## Out of scope` + a linked follow-up.
- The issue has no `priority/*`, `size/*`, or type (`bug`/`enhancement`/
  `documentation`/`chore`) label.
- The issue has no milestone assigned.
- The issue touches more than one architecture layer but has only one
  `area:*` label.
- The issue depends on another open issue, but the body has no `## Depends
  on` section (wiring the structural link is [[afdk-issue-relationships]]'s
  job, but the markdown section must be in the body at filing time).
- The Proposal claims a gap that is actually a known, already-tracked
  `_verify.blocked("…")` guard — the issue should say which `Verification`
  row it unblocks, not describe it as a fresh bug.

## Common mistakes

| Mistake | Fix |
| --- | --- |
| Filing against a fork or `tbolis/...` | User has no fork. Always `--repo Agent-Fabric-SDK/agent-fabric-sdk`. |
| `--label "bug,area:refusals"` (one combined string) | Use repeated `--label` flags. |
| Pasting body via `--body "$(printf ...)"` with unescaped backticks | Use a quoted heredoc (`<<'EOF'`) — single-quoted EOF disables shell expansion. |
| Skipping an area label because it doesn't exist | Create it first with `gh label create ... || true`, then file. |
| Title in past tense or with `[BUG]` prefix | Imperative present tense; rely on the `bug` label. |
| Filing a "bug" for a `_verify.blocked(...)` code path | That's tracked-as-designed per §0.3; file it against the `Verification` milestone as unblock work, not a defect. |

## Quick reference

```bash
# Smallest valid invocation
gh issue create \
  --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --title "<imperative title>" \
  --milestone "Phase 1 — Build the MVP (0.1.0)" \
  --label <type> --label <area>... --label <priority> --label <size> \
  --body "$(cat <<'EOF'
<template-filled body>
EOF
)"
```

## Related skills

- [[afdk-issue-relationships]] — wiring dependency/blocking links after filing,
  and decomposing oversized issues into sub-issues.
- [[afdk-git-workflow]] — picking up a filed issue, branching, and assignee
  handling.
- [[afdk-docs-sync]] — keeping `website/` and `docs/verified-apis.md` in sync
  with code changes described in an issue's Proposal.
