---
name: afdk-git-workflow
description: Use for this repo's branch lifecycle — finding/filing the issue, cutting the branch, worktrees, committing, and pushing. Triggers when the user says "work an issue", "work on #N", "start issue N", "tackle issue N", "pick up issue N", "let's do issue N", or is about to edit code, run `git checkout -b`/`git worktree add`, commit, or push. PR creation/merge is handled by [[afdk-pr-workflow]] / [[afdk-merge-strategy]].
---

# AFDK Git Workflow

## Overview

Every code change in `agent-fabric-sdk` starts with a GitHub issue and happens
on a dedicated branch named after that issue. No exceptions for "small"
changes — small changes are exactly where this discipline gets skipped and
history gets muddied. This is a Python SDK with a build-plan-as-spec
(`mulesoft-agent-fabric-sdk-build-plan.md`) and a `§N.N`-cited codebase; commit
messages should cite the relevant section when a change is implementing or
touching spec-governed behavior.

## IRON LAW

**No code change without an issue and a matching branch.**

Before editing a single file:

1. There **must** be a GitHub issue describing the change.
2. You **must** be on a branch named `<type>/<issue#>-<slug>`, cut from
   `develop`.

If either is missing, stop and fix it before touching code.

### Acceptable exception: `.claude/skills` edits on `develop`

Updates scoped **entirely** to `.claude/skills/**` (skill content,
descriptions, frontmatter) may be committed and pushed directly to `develop`
without a dedicated issue/branch/PR. Skills are agent tooling, not SDK code or
the build-plan spec — round-tripping every wording tweak through an issue +
PR adds friction with no review value.

This exception applies **only** when:

- The diff touches nothing outside `.claude/skills/**`.
- It's a content edit to existing skills or a new skill — not a change to
  repo policy, CI, `python/`, `docs-site/`, or the build plan itself.

Anything else (even `.claude/README.md`, `.claude/settings*.json`,
`.claude/hooks/`, `mulesoft-agent-fabric-sdk-build-plan.md`, or a mixed diff
that touches skills plus anything else) follows the normal issue + branch + PR
flow.

**Before committing direct to `develop`**, present the user with:

1. A **recap of changes** — `git status` + a short bulleted summary of what
   each touched skill file changed (one line per file).
2. The **drafted commit message** (subject + body) you intend to use.

Wait for explicit user approval, then commit and push. This replaces the PR
review gate that direct commits skip — the user gets one chance to redirect
before the change lands on `develop`.

## The rule, in steps

1. **Find or file the issue.** Search first:
   ```bash
   gh issue list --repo Agent-Fabric-SDK/agent-fabric-sdk --search "<keywords>"
   ```
   If nothing matches, file one using the [[afdk-filing-issues]] skill — that
   skill owns issue creation; do not bypass it.
2. **Cut the branch from `develop`.**
   ```bash
   git fetch origin
   git checkout develop && git pull --ff-only
   git checkout -b <type>/<issue#>-<slug>
   ```
3. **Brainstorm the approach before coding**, especially for anything that
   touches the layered architecture (§1.1), a verification-gated surface
   (§0.3), or an adapter (§8–§10). If [[superpowers:brainstorming]] is
   available, invoke it now to align on intent and design before touching
   code. Capture the outcome in the GitHub issue (edit the body or add a
   comment) — the issue is the plan; don't create local `plans/*.md` files.
   Skip brainstorming only for trivially-scoped changes (typo fix, dependency
   bump, single-line config tweak) where intent is already obvious from the
   issue.

   **Re-confirm the layer and verification boundaries before writing code.**
   Check whether the change:
   - Stays inside the layering `integrations → tools → registry → llm → core`
     (§1.1) — a lower layer must never import a higher one; `lint-imports`
     enforces this in CI, but catch it before you write the import.
   - Touches anything in `core/` — it must stay framework-free (httpx +
     pydantic only); any framework import belongs in an adapter, imported
     lazily inside a method.
   - Depends on an endpoint, header, or class name that isn't in
     `docs/verified-apis.md` as VERIFIED — if so, this is a
     [[afdk-verification-discipline]] question, not a place to guess. Use
     `_verify.blocked("…")` or an `Unverified(...)` placeholder rather than
     inventing a value.
4. **Make the change, commit, push, open a PR targeting `develop`.**
   Reference the issue in the PR body with `Closes #<issue#>`. Commit
   messages should cite `§N.N` when the change implements or modifies
   build-plan-governed behavior, e.g. `fix(llm): correct proxy base URL
   handling (§2.1)`. PR creation and the smoke test are owned by
   [[afdk-pr-workflow]]; merge strategy (squash vs. merge, `develop` →
   `main` promotion) is owned by [[afdk-merge-strategy]].

## Branch naming

Format: `<type>/<issue#>-<short-kebab-slug>`

| `<type>` | When to use |
| --- | --- |
| `feat` | New user-visible capability or API surface |
| `fix` | Bug fix — something that was supposed to work and didn't |
| `docs` | README, CLAUDE.md, build-plan updates, docs-site content, comments |
| `chore` | Tooling, deps, refactors, build/CI config |

Slug rules:
- 2–5 words, kebab-case, lowercase, no punctuation.
- Describes *what* changes, not *how* — `fix/42-proxy-url-trailing-slash`,
  not `fix/42-strip-string`.
- Issue number is mandatory. A branch without the issue number is wrong even
  if everything else is right.

Examples:
- ✅ `fix/42-proxy-url-trailing-slash`
- ✅ `feat/57-crewai-connection-kwargs`
- ✅ `docs/13-verified-apis-update`
- ❌ `fix/proxy-url` (no issue #)
- ❌ `feat/57` (no slug)
- ❌ `42-fix-proxy` (no type prefix)
- ❌ `fix-42-proxy` (wrong separator — must be `/`)

## Use a git worktree per issue

If another Claude session, terminal, or IDE window is already working on a
different issue in this repo, **do not share the working tree**. Switching
branches in-place mid-session corrupts the other session's view (uncommitted
edits land on the wrong branch, `python/` build artifacts and installed
extras get reused across branches, file watchers thrash).

**Rule:** one issue = one branch = one worktree. Cut a worktree instead of
`git checkout -b` whenever there's any chance of a parallel session.

```bash
git fetch origin
git worktree add ../agent-fabric-sdk-fix-42-proxy-url -b fix/42-proxy-url-trailing-slash origin/develop
cd ../agent-fabric-sdk-fix-42-proxy-url
```

A fresh worktree has no installed virtualenv/extras. From the worktree's
`python/` directory: `pip install -e ".[dev,llm,cli]"` before running tests,
mypy, ruff, or `lint-imports`.

When done (PR merged or abandoned), tear down the worktree **and**
fast-forward the primary checkout's `develop` so it picks up the merge
commit:

```bash
git worktree remove ../agent-fabric-sdk-fix-42-proxy-url
git branch -d fix/42-proxy-url-trailing-slash   # or -D if abandoned

# In the primary checkout (the one tracking `develop`), pull the merge commit.
git -C <primary-checkout> checkout develop
git -C <primary-checkout> pull --ff-only
```

Run the `pull --ff-only` even if `gh pr merge` reported success — the merge
happens on the remote, your local `develop` only learns about it when you
fetch + fast-forward.

**When a worktree is mandatory:**

- Another Claude session is open on this repo (even just reading).
- A long-running process (dev server, `pytest --looponfail`, a running docs
  build) holds files in the working tree on another branch.
- You'd otherwise need to `git stash` to switch issues.

**When `git checkout -b` in place is fine:**

- You're certain no other session is touching the repo.
- No long-running process holds files in the working tree.

For deeper worktree mechanics (pruning, listing, recovering), see
[[superpowers:using-git-worktrees]].

**No workarounds for prerequisite changes.** If, while working in a worktree
on issue #N, you discover the work needs an out-of-scope change first (a
missing `core/` primitive, a change to the layering boundary, a
verification unblock that hasn't happened yet), **stop and surface it**. Do
not patch around it locally, do not silently expand the scope of #N, do not
guess at the unverified value "just to keep moving." Tell the user what's
blocking and offer to file a new issue for the prerequisite via
[[afdk-filing-issues]] (see also [[afdk-issue-relationships]] for how to link
it). The user decides whether to: (a) pause #N until the prerequisite lands,
(b) expand #N's scope explicitly, or (c) take a different approach. One
issue = one branch is only meaningful if scope stays honest.

## Base branch

**Always `develop`.** Never branch from `main`, never PR into `main`. `main`
is release-only and moves only when `develop` is promoted (see
[[afdk-merge-strategy]]). If you're on `main` when starting work, that's a
red flag — `git checkout develop` first.

## Forbidden rationalizations

| Excuse | Reality |
| --- | --- |
| "It's a one-line typo, no issue needed" | Trivial-exception thinking is the #1 way history gets unanchored. File the issue. It takes 30 seconds. |
| "I'll file the issue after, while the PR is open" | Then the branch name has no number to embed. File first, branch second. |
| "I'm just exploring, I won't commit" | Then don't be on `develop` either. Cut a `chore/<#>-spike` branch or use a worktree. |
| "The issue exists but the number isn't in the branch name" | Rename the branch (`git branch -m <new>`) before the first commit. The number is mandatory. |
| "The user told me to fix it, that's authorization enough" | The user authorized the change, not the workflow shortcut. Issue + branch still required. |
| "I'll branch from `main` because `develop` is behind" | `develop` being behind is a separate problem. Fix it (`git pull --ff-only`) — don't reroute around it. |
| "There's already a branch open for something similar, I'll reuse it" | One issue = one branch. Reusing branches mixes scopes and breaks `Closes #<n>`. |
| "I'll just `git checkout` the other branch quickly" | If another session is in this repo, that other session sees your checkout. Use a worktree. |
| "Worktrees are overkill for a small fix" | The cost is one command. The cost of a corrupted parallel session is a debugging detour. |
| "It's unverified but close enough, I'll just fill it in" | That's exactly what §0.3 forbids. Use `_verify.blocked(...)` or `Unverified(...)` and route through [[afdk-verification-discipline]]. |

## Red flags — STOP

If any of these are true, you're about to violate the rule:

- About to run `Edit`/`Write` and `git branch --show-current` returns
  `develop` or `main` (and the diff is not confined to `.claude/skills/**`).
- About to run `git checkout -b` with no issue number in the name.
- About to file an issue *after* having already made changes locally.
- About to commit with a message that describes work but cites no issue.
- Telling yourself "this one's small enough to skip the issue."
- About to `git checkout` an existing branch while another session/dev
  server might be using the current tree.
- About to fill in an unverified endpoint/header/class name to "just make it
  work."

**All of these mean: stop, file/find the issue, cut the right branch, then
resume.**

## Recovery — if you already started on the wrong branch

You edited files on `develop` (or an unnumbered branch) before reading this.
Don't panic, don't `reset --hard`, don't lose work.

```bash
# 1. Make sure changes are saved (committed or stashed) on the wrong branch.
git stash push -u -m "wip before rebranching"

# 2. Find or file the issue, then cut the proper branch from develop.
git checkout develop && git pull --ff-only
git checkout -b fix/<issue#>-<slug>

# 3. Reapply the work.
git stash pop
```

If you already committed on `develop` locally (not pushed):

```bash
git checkout -b fix/<issue#>-<slug>   # carries the commits with you
git checkout develop
git reset --hard origin/develop       # ONLY safe because you didn't push develop
```

If you already pushed to `develop`: stop and ask the user before doing
anything else. Rewriting shared history is a destructive op.

## Autonomy on the issue branch

Once you're on a correctly-named `<type>/<#>-<slug>` branch (cut from
`develop`, with the right issue number), commit and push autonomously. Don't
pause to ask before each `git commit` or `git push` — the branch itself is
the isolation boundary, and per-step confirmation just adds friction.

**Confirm before:**

- Force-push (`--force`, `--force-with-lease`).
- History rewrites: `rebase -i`, `commit --amend` after a push, `git reset
  --hard` of pushed commits.
- `--no-verify` / skipping hooks.
- Deleting the branch.
- Any operation that touches `develop` or `main`.

After pushing, surface the branch name so the user can follow along. **Once
the branch is ready for review, hand off to [[afdk-pr-workflow]]** — that
skill owns the smoke test (`pytest -q`, `mypy`, `ruff check .`,
`lint-imports`), PR creation gate, and post-merge verification.

## Quick reference (branch lifecycle)

```bash
# Start a change
gh issue list --repo Agent-Fabric-SDK/agent-fabric-sdk --search "<keywords>"
# (file a new issue via the afdk-filing-issues skill if no match)
git fetch origin
git checkout develop && git pull --ff-only
git checkout -b fix/<issue#>-<slug>

# Push when ready for review
git push -u origin fix/<issue#>-<slug>
# → continue with [[afdk-pr-workflow]] for smoke test + PR creation

# After the PR is merged (worktree workflow): tear down + fast-forward develop.
git worktree remove ../agent-fabric-sdk-<slug>
git branch -d fix/<issue#>-<slug>
git checkout develop && git pull --ff-only   # picks up the merge commit
```

## Common mistakes

| Mistake | Fix |
| --- | --- |
| Branched off `main` | `git rebase --onto develop $(git merge-base main <branch>) <branch>` then push. Only works cleanly when the branch's commits sit directly on top of `main` with no intervening merges. |
| Branch name missing issue # | `git branch -m <type>/<#>-<slug>` before first push |
| Committed on `develop` directly (and it wasn't a skills-only diff) | See Recovery section above |
| PR opened against `main` | Edit PR base to `develop` (`gh pr edit --base develop`) |
| One branch covering two issues | Split: cherry-pick the second issue's commits onto a new branch |
| Commit message with no `§` cite for a spec-governed change | Amend before pushing (or a follow-up commit if already pushed) to add the section reference |
