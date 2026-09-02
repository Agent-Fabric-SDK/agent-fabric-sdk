---
name: afdk-merge-strategy
description: Use when merging an agent-fabric-sdk PR into `develop` or promoting `develop` to `main`. Defines the merge method for each direction (squash for branch→develop, no-ff merge commit for develop→main), the approval gates, hotfix handling, and revert recipes. Triggers when about to run `gh pr merge`, cut a release, or touch `main`.
---

# AFDK Merge Strategy

## Overview

This repo uses two branches with **different merge methods** because they serve
different purposes:

- `develop` is the integration branch — its log should read as an **issue log**
  (one commit per closed issue/PR).
- `main` is the release branch — its log should read as a **release log** (one
  merge commit per promotion). CI (`.github/workflows/ci.yml`) runs on every
  `pull_request` and on `push` to `main`, so `main`'s tip is always the thing
  that was last validated end-to-end (`base-only`, `typecheck-and-lint`, the
  `test` matrix across Python 3.10/3.11/3.12).

Picking the right method per direction keeps both logs useful and `git revert`
clean. This skill covers the merge *method* and gates only — for branch
naming/setup see [[afdk-git-workflow]], for the PR lifecycle see
[[afdk-pr-workflow]]. Release **tagging** is intentionally out of scope here.

## The rule

| Direction | Method | Why |
| --- | --- | --- |
| `<type>/<#>-<slug>` → `develop` | **Squash merge** | One commit on `develop` per issue/PR. `Closes #N` still fires. `git revert <sha>` backs out the whole issue cleanly. WIP commits ("fix mypy", "address review") collapse away. |
| `develop` → `main` | **Merge commit (no fast-forward)** | Each release is one identifiable merge commit on `main`. Easy to identify and revert a whole release. A fast-forward would silently advance `main` and erase the release boundary. |

**Never:**

- Rebase-merge into `develop` — branch commits are usually unpolished WIP;
  rebasing pollutes `develop`'s log with them.
- Squash `develop` into `main` — that throws away the per-issue commits
  preserved on `develop`. Strictly worse than the merge commit.
- Fast-forward `develop` into `main` — invisible release, can't point at or
  revert "the whole release" as a unit.
- Merge `main` back into `develop`. If `main` ever carries a hotfix that
  bypassed `develop`, cherry-pick it onto `develop` instead.

## Direction 1: `<branch>` → `develop` (squash)

This is the default lifecycle covered by [[afdk-git-workflow]] +
[[afdk-pr-workflow]]. The only thing this skill adds is the **merge method**.

### Approval gate

Same as the rest of [[afdk-pr-workflow]]: explicit user "go ahead" before
`gh pr merge`. No autonomy at the merge step, even for a well-formed,
CI-green PR. Before merging, confirm CI is green on the PR (`base-only`,
`typecheck-and-lint` — including `mypy --strict` and `lint-imports` — and the
`test` matrix), since these jobs are blocking gates for this repo.

### Command

```bash
gh pr merge <pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --squash \
  --delete-branch \
  --subject "<imperative subject> (#<pr#>)" \
  --body "Closes #<issue#>"
```

Notes:

- `--squash` is mandatory. Do not pass `--merge` or `--rebase` for this
  direction.
- `--delete-branch` removes the remote branch after merge. Local branch/
  worktree teardown is handled per [[afdk-git-workflow]].
- The squash subject **must** include the PR number as ` (#<pr#>)` — GitHub
  usually inserts this automatically, but pass it explicitly so the squashed
  commit on `develop` is greppable.
- `Closes #<issue#>` in the body keeps the auto-close link working post-squash.
  Verify it fired per [[afdk-pr-workflow]].
- If the change touches a `§N.N`-cited guard (build plan, `core/_verify.py`,
  `docs/verified-apis.md`), make sure the PR body/commit references the
  section per §0.3 — this is a repo convention, not optional polish.

### Post-merge cleanup (mandatory, with user approval)

After a successful squash-merge into `develop`, the local branch/worktree are
stale and should be removed — leaving them around clutters `git worktree list`
and risks accidental commits onto a dead branch.

**Approval gate:** removing a worktree touches the user's filesystem, so
confirm before running.

```bash
# After user approval, from the main repo checkout (not the worktree being removed):
git worktree remove <path-to-issue-worktree>
git branch -D <branch-name>
git worktree list   # verify it's gone
```

If the worktree has uncommitted changes, `git worktree remove` will refuse —
surface that to the user rather than passing `--force`.

## Direction 2: `develop` → `main` (no-ff merge commit)

Promotion to `main` is a deliberate release event, not a routine sync. CI only
runs the full matrix on `pull_request` and on `push` to `main` — so a release
PR from `develop` into `main` is also the point where CI validates the
promotion.

### Approval gate

**Always confirm with the user before promoting.** Promotion is a
`main`-touching operation.

Required confirmations before opening/merging the release PR:

1. The user has explicitly asked for a release (or approved a proposal to
   release).
2. CI is green on `develop`'s tip (`base-only`, `typecheck-and-lint`, `test`
   matrix).
3. There are no open PRs the user expects in this release that haven't merged
   into `develop` yet.
4. Any breaking changes, new blocked/verified surfaces (§0.3), or extras
   changes are called out in the release PR body.

### Command

Promotion uses a PR (`develop` → `main`) so the merge commit is reviewable,
not a local `git merge` pushed straight to `main`.

```bash
# 1. Open the release PR.
gh pr create --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --base main --head develop \
  --title "Release: <short description>" \
  --body "$(cat <<'EOF'
Promotion of `develop` → `main`.

## Included
- #<pr1>
- #<pr2>
- ...

## Notes
<one-paragraph summary, breaking changes, verification-status changes (§0.3), extras changes (§8.4)>
EOF
)"

# 2. After user approval, merge with a merge commit (no fast-forward, no squash).
gh pr merge <release-pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --merge \
  --subject "Release: <short description> (#<release-pr#>)"
# (do NOT pass --delete-branch — develop is not disposable)
```

Notes:

- `--merge` is mandatory. `--squash` and `--rebase` are wrong for this
  direction (see the "Never" list above).
- **Do not pass `--delete-branch`.** `develop` is the long-lived integration
  branch.
- Release **tagging** is deliberately not covered by this skill — follow
  whatever tagging convention the user specifies at release time.
- After the merge, `develop` already contains everything now on `main` (it
  was the source), so no fast-forward of `develop` is needed. The merge
  commit lives only on `main`.

### Hotfix exception

If `main` needs a fix that can't wait for the next `develop` promotion
(security, prod-down):

1. Branch from `main`: `hotfix/<#>-<slug>` (issue still mandatory, per
   [[afdk-git-workflow]]).
2. PR into `main` with a **squash** merge (one commit, fast revert):
   ```bash
   gh pr merge <hotfix-pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk \
     --squash --delete-branch \
     --subject "<title> (#<hotfix-pr#>)"
   ```
3. **Cherry-pick** the squashed commit onto `develop` immediately:
   ```bash
   git checkout develop && git pull --ff-only
   git cherry-pick <hotfix-sha-on-main>
   git push origin develop
   ```
4. Never merge `main` back into `develop`. Cherry-pick keeps `develop`'s log
   linear and avoids reintroducing `main`'s release merge commits as noise on
   `develop`.

## Reverting

| Scenario | How |
| --- | --- |
| Back out one issue from `develop` | `git revert <squash-sha-on-develop>`. Open as a normal PR (with an issue) — the revert is itself a change, per [[afdk-pr-workflow]]. |
| Back out a whole release from `main` | `git revert -m 1 <release-merge-sha>`. The `-m 1` picks the first parent (the previous `main` tip) as mainline. Cherry-pick the revert onto `develop` so the two stay aligned. |
| Back out a hotfix from `main` | `git revert <hotfix-sha>`. Then revert the cherry-pick on `develop` too. |

## Forbidden rationalizations

| Excuse | Reality |
| --- | --- |
| "Rebase-merge keeps history cleaner" | Only if branch commits are curated — they aren't, by design. Squash is the right discipline boundary here. |
| "Just FF `main` — it's the same content" | FF erases the release boundary. You lose the ability to point at "the release" or revert it as a unit. |
| "Squashing develop into main is simpler" | It throws away the per-issue commits and `Closes #N` linkage that develop preserved. |
| "Hotfix is small, I'll just push to main" | Issue + branch + PR rule applies to `main` too, and `main` requires blocking CI (mypy --strict, lint-imports, the full matrix) to pass on the PR. |
| "I'll merge main into develop to sync" | Pulls `main`'s release merge commits into `develop`'s log as noise. Cherry-pick instead. |
| "I'll skip the user approval, the release was discussed yesterday" | Discussion ≠ approval-at-merge-time. Confirm at the moment of merge. |

## Red flags — STOP

- About to run `gh pr merge` without `--squash` for a branch → `develop` PR.
- About to run `gh pr merge` with `--squash` or `--rebase` for a `develop` →
  `main` PR.
- About to `git push origin main` from your local machine (promotion goes
  through a PR).
- About to merge `main` into `develop`.
- About to fast-forward `main` to `develop` directly.
- About to merge a release PR without confirming with the user that this is a
  release-now event, or without CI green (`typecheck-and-lint` including
  `mypy --strict` + `lint-imports`, and the full `test` matrix).
- About to walk away from a branch → `develop` squash-merge without prompting
  the user to remove the local branch and worktree — they're stale the moment
  the merge lands.

## Quick reference

```bash
# Branch → develop (squash, after user approval)
gh pr merge <pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --squash --delete-branch \
  --subject "<title> (#<pr#>)" --body "Closes #<issue#>"
# Then, after user approval, remove local branch + worktree:
git worktree remove <path-to-issue-worktree>
git branch -D <branch-name>

# develop → main (release PR, then merge commit)
gh pr create --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --base main --head develop \
  --title "Release: <short description>" --body "<notes>"
gh pr merge <release-pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --merge --subject "Release: <short description> (#<release-pr#>)"

# Hotfix on main (squash), then cherry-pick onto develop
gh pr merge <hotfix-pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --squash --delete-branch --subject "<title> (#<hotfix-pr#>)"
git checkout develop && git pull --ff-only
git cherry-pick <hotfix-sha-on-main> && git push origin develop
```

## Common mistakes

| Mistake | Fix |
| --- | --- |
| Used `--merge` for a branch → `develop` PR | Revert the merge commit on `develop`, reopen the PR (or a fresh one), squash-merge it. |
| Used `--squash` for `develop` → `main` | Revert the squash on `main`, redo the promotion via a `--merge` PR. |
| Forgot to cherry-pick a hotfix onto `develop` | `git cherry-pick <hotfix-sha-on-main>` on `develop`. The next `develop` → `main` promotion would otherwise re-revert the hotfix. |
| Merged `main` into `develop` accidentally | Don't try to undo with another merge. Tell the user — the cleanup depends on whether anything has landed on `develop` since. |
