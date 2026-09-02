# agent-fabric-sdk project skills

Project-local runbooks loaded on demand. Each skill under `afdk-*/SKILL.md`
encodes a piece of this repo's discipline — the build plan as spec, the
layered/framework-free core, the verification contract, the branch/issue
lifecycle — so it can be pulled into context exactly when it's relevant instead
of living only in a human's head or a scroll-past section of `CLAUDE.md`.

## Index

| Skill | When it fires |
|---|---|
| [`afdk-coding-conventions`](afdk-coding-conventions/SKILL.md) | Authoring or reviewing any Python code under `python/src/agent_fabric/**` — mypy --strict, ruff, the import-linter layering + framework-free-core rule, lazy framework imports in adapters, `§N.N` citation habit, floors-never-ceilings, the 3.10 floor, trademark wording. |
| [`afdk-testing`](afdk-testing/SKILL.md) | Writing, reviewing, or expanding tests — routes to the right pytest surface (unit / conformance / fixture-driven / sandbox / local_gateway) and enforces the "never a silent skip" conformance rule. |
| [`afdk-pr-review`](afdk-pr-review/SKILL.md) | Reviewing an agent-fabric-sdk PR — checks the architectural invariants (layering, verification discipline, error-taxonomy correctness, floors-never-ceilings, §N.N hygiene, py.typed/mypy --strict, trademark wording) before `gh pr review`. |
| [`afdk-git-workflow`](afdk-git-workflow/SKILL.md) | Starting or continuing work on an issue — finding/filing it, cutting the branch, worktrees, committing, pushing. Triggers on "work an issue" / "work on #N" phrasing or before any edit/commit/push. |
| [`afdk-pr-workflow`](afdk-pr-workflow/SKILL.md) | Once a branch is pushed and ready for a PR — local pre-PR gate mirroring CI, drafting/creating the PR, post-merge issue-close verification, worktree teardown. |
| [`afdk-merge-strategy`](afdk-merge-strategy/SKILL.md) | Merging a PR into `develop` or promoting `develop` to `main` — merge method per direction, approval gates, hotfix handling, revert recipes. |
| [`afdk-filing-issues`](afdk-filing-issues/SKILL.md) | Filing, opening, or reporting a new GitHub issue (bug or enhancement) against this repo. |
| [`afdk-issue-relationships`](afdk-issue-relationships/SKILL.md) | Linking issues that already exist — sub-issues, blocked-by/blocking, cross-link "related" comments. Runs after filing, not as part of it. |
| [`afdk-docs-authoring`](afdk-docs-authoring/SKILL.md) | Writing or substantially rewriting a page under `docs-site/pages/**.mdx` — layout, `_meta.js` ordering, the SDK-developer audience contract, VERIFICATION-STATUS framing, trademark/support boundary, "cite a symbol, not path:line". |
| [`afdk-docs-sync`](afdk-docs-sync/SKILL.md) | A PR touches a load-bearing surface (`core/errors.py`, `provisioning/*`, `tools/*`, `registry/*`, `integrations/*`, `docs/verified-apis.md`, `README.md`) that the docs site describes — forces a matching docs-site update in the same PR or a documentation-labeled follow-up issue. |
| [`afdk-verification-discipline`](afdk-verification-discipline/SKILL.md) | Touching any Anypoint endpoint, header, class name, or kwarg — before adding/removing a `_verify.blocked` guard or `Unverified` placeholder, flipping a `docs/verified-apis.md` row, or reviewing a claim that a surface is "verified". Enforces §0.3, "never invent an endpoint, header, or class name." |

## How they fit together

The lifecycle of a change runs roughly:

1. **`afdk-filing-issues`** (+ **`afdk-issue-relationships`** if it links to
   other work) creates the issue that authorizes the change — "the issue is
   the plan."
2. **`afdk-git-workflow`** cuts the branch and governs commits. While editing,
   **`afdk-coding-conventions`** governs the code itself and
   **`afdk-verification-discipline`** governs any claim about a MuleSoft
   endpoint/header/class name. **`afdk-testing`** governs what you write to
   prove it. **`afdk-docs-sync`** (paired with **`afdk-docs-authoring`` for the
   actual prose) governs whether docs-site must move in lockstep.
3. **`afdk-pr-workflow`** opens the PR once the branch is ready;
   **`afdk-pr-review`** is the checklist a reviewer (human or agent) runs
   against it, re-checking the same invariants from the outside.
4. **`afdk-merge-strategy`** governs how the approved PR lands on `develop`
   and how `develop` is later promoted to `main`.

Every stage re-touches the same three invariants from a different angle:
verification discipline (never invent an endpoint/header/class name), the
layered framework-free-core import rule, and the conformance-exemption
"never a silent skip" rule. That repetition is intentional — each skill
enforces its slice at the point in the lifecycle where it's cheapest to catch
a violation.

## Parallel sub-agent work

**Every dispatched sub-agent MUST be loaded with all afdk-* skills relevant to
its task — no exceptions on the relevant ones.** A sub-agent has no future
turn in which to notice a missing skill and go fetch it; whatever invariant
isn't loaded at dispatch time is an invariant that gets silently skipped in
that sub-agent's output. This repo's invariants — the verification discipline
(§0.3, never invent an endpoint/header/class name), the layered
framework-free-core import rule (§1.1), and the conformance-exemption "never
a silent skip" rule (§8.1) — are exactly the kind of thing a sub-agent will
violate quietly and confidently if it never saw the skill that states them.

If the dispatch mechanism you're using cannot accept the full relevant set of
skills for a sub-agent's task, **stop and surface that limitation to the
user** rather than dispatching with a reduced set. A partial load is worse
than no load, because it looks like coverage.

## Updating skills

Edits scoped entirely to `.claude/skills/**` are exempt from the usual
issue+branch+PR ceremony — see [[afdk-git-workflow]] for the exception and
what "scoped entirely" means in practice.
