---
name: afdk-pr-workflow
description: Use for the agent-fabric-sdk PR lifecycle — the local pre-PR gate that mirrors CI, drafting and creating the PR, post-merge issue close verification, and worktree teardown. Triggers when about to run `gh pr create`, approve/merge a PR, or after a merge lands.
---

# AFDK PR Workflow

## Overview

This skill picks up where [[afdk-git-workflow]] leaves off: the branch is
pushed and you're ready to open the PR. It covers the local pre-PR gate, the
approval gates, post-merge issue-close verification, and worktree teardown.

For branch-side work (issue → branch → commits) see [[afdk-git-workflow]]. For
review-time invariants (layering, verification discipline, framework-free
core) see [[afdk-pr-review]]. For merge method see [[afdk-merge-strategy]].
For the docs gate that must also pass before merge see [[afdk-docs-sync]].

## Target repo

```
Agent-Fabric-SDK/agent-fabric-sdk
```

PRs target `develop` (integration branch), never `main` (release branch).

## Approval gates — explicit user approval, no exceptions

- **Creating a PR** (`gh pr create`). Draft a title + body, show it to the
  user, wait for "go ahead" before invoking.
- **Approving a PR** (`gh pr review --approve`).
- **Merging a PR** (`gh pr merge`). Merge method is fixed by
  [[afdk-merge-strategy]] — don't pick per PR.

**Also confirm before:**

- Force-push (`--force`, `--force-with-lease`).
- History rewrites: `rebase -i`, `commit --amend` after a push, `git reset --hard`
  of pushed commits.
- `--no-verify` / skipping hooks.
- Deleting the branch.
- Editing the base branch of an open PR.
- Any operation that touches `develop` or `main`.

## Before opening the PR — run the local pre-PR gate

There is no Makefile in this repo — every command is run directly, from
`python/`. Run the exact set of checks CI runs (`.github/workflows/ci.yml`,
jobs `base-only`, `typecheck-and-lint`, `test`) **before** drafting the PR:

```bash
cd python
pytest -q                # mirrors the `test` job (matrix 3.10/3.11/3.12 in CI;
                          # you run whatever interpreter is active locally)
mypy                      # mypy --strict, BLOCKING in CI (files=src/agent_fabric)
ruff check .              # line-length 100; E,F,I,UP,B
lint-imports              # import-linter: enforces the §1.1 layered,
                          # framework-free-core architecture
```

If the diff touches an adapter under `integrations/` or anything in
`extras`/framework wiring, also run the framework-signature check (this is
the executable form of the §8 verification step and the nightly-matrix gate
in `.github/workflows/nightly-matrix.yml`):

```bash
python scripts/verify_frameworks.py            # offline signature check, all installed
# python scripts/verify_frameworks.py --live    # + one real proxy round-trip (needs sandbox creds; ask before running)
```

Any non-zero exit means **stop** — fix it before drafting the PR. CI also runs
a `base-only` job that installs *only* `[dev]` and imports `agent_fabric` to
catch accidental top-level framework imports; if you added or touched an
adapter, sanity-check that a bare `pip install -e ".[dev]"` + `python -c
"import agent_fabric"` still succeeds (no top-level framework import leaked
into `core`/`llm`/`registry`/`tools`).

**Skipping this gate is a red flag.** Don't open the PR on a branch that
hasn't passed locally. The only acceptable bypass is when the gate itself is
broken (infra glitch unrelated to the diff) — surface it to the user, don't
silently skip.

## Docs gate

If the diff changes anything documented in `docs/verified-apis.md`, README
ergonomics (§2), or adapter surfaces, the docs-sync checks in
[[afdk-docs-sync]] must also pass before the PR is drafted — a code change
that flips a value from `UNVERIFIED` to `VERIFIED` (or adds an adapter) with
no matching `docs/verified-apis.md` row is an incomplete PR, not a
follow-up.

## Drafting and creating the PR

Once the local gate (and docs gate, if applicable) is green:

1. Build a title (imperative, ≤70 chars, no trailing period) and a body that
   includes `Closes #<issue#>` when a tracked issue exists.
2. Cite the relevant `§N.N` build-plan section(s) in the summary when the
   change implements or modifies spec-governed behavior — reviewers will look
   it up.
3. Show the rendered draft (title + body) to the user and wait for explicit
   confirmation.
4. Then run, **always with an explicit `--head` flag and from the worktree's
   directory**:

```bash
gh pr create --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --base develop --head <branch-name> \
  --title "<imperative title>" \
  --body "$(cat <<'EOF'
Closes #<issue#>

## Summary
<1-3 bullets — what changed and why, with §N.N references where relevant>

## Test plan
- [ ] <observable behavior, e.g. specific pytest/mypy/ruff/lint-imports output>

## Post-deploy steps
<mandatory section — see below; write "None." if genuinely nothing follow-up>
EOF
)"
```

**Why `--head` is mandatory:** without it, `gh pr create` infers the head
branch from the current working directory's checkout — if you're in the
primary checkout (tracking `develop` or an unrelated branch), `gh` will
silently attach your title/body to the wrong diff. Always pass
`--head <branch-name>` and run from the worktree where that branch lives.

5. **Verify the PR's head matches the branch you intended** before declaring
   success:

```bash
gh pr view <pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --json headRefName,baseRefName,number --jq '.'
gh pr diff <pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk --name-only | head
```

If `headRefName` doesn't match `<branch-name>`, close the PR
(`gh pr close <pr#>`) and re-file from the correct worktree before doing
anything else.

### Mandatory "## Post-deploy steps" section

Every PR body must include a `## Post-deploy steps` section — there is no
deploy pipeline of this SDK's own to configure (it's a published package,
not a hosted service), but the section still has real content in most PRs:

- New/changed extras in `pyproject.toml` → note the `pip install` command
  users need to pick up the change.
- A value flipped from `UNVERIFIED`/`VERIFIED-SHAPE-ONLY` to `VERIFIED` in
  `_verify.py` → note that `docs/verified-apis.md` was updated to match
  (§0.3 — the two must move together).
- A new adapter or conformance exemption → note whether the README's
  supported-framework table / `KNOWN_LIMITATIONS` needs a follow-up PR.
- Nothing applicable → write `None.` explicitly. Do not omit the heading.

If you're not sure what belongs here, ask the user — don't guess or hand-wave.

## CI failures on the PR

If CI fails after `gh pr create`:

1. **Do not request review.** A failing PR wastes reviewer attention.
2. Fetch the failing job's logs (`gh run view <run-id> --log-failed --repo
   Agent-Fabric-SDK/agent-fabric-sdk`) and surface the actual error.
3. Fix on the same branch, push, let CI re-run. Do not open a new PR.
4. Only request review once CI is green.

If the failure is in the nightly-matrix (`nightly-matrix.yml`) rather than
this PR's own CI run, treat it as a separate signal — it runs against latest
framework releases (§8.4, "floors, never ceilings") and can go red
independent of your diff. Surface it, don't assume it's caused by your PR.

## Keeping the branch current with `develop`

If `develop` advances while the PR is open:

- **Default: rebase.** `git fetch origin && git rebase origin/develop`. Keeps
  history linear and `Closes #` references intact. Force-push with
  `--force-with-lease` (a confirm-before operation, above).
- **Use merge instead** only if the rebase would be invasive (large conflict
  surface, reviewers already mid-review with line comments that would be
  invalidated).

Don't mix the two on a single branch.

## After a PR merges — close the linked issue explicitly

**Policy: never rely on GitHub auto-close.** Auto-close on `closingIssuesReferences`
can silently fail (body edits after creation, squash merges where the
keyword only landed in the title, occasional misses). Keep `Closes #N` in the
body for reviewer visibility, but treat the explicit close below as the
source of truth. Do this on every merge with a linked issue:

```bash
PR=<pr#>
ISSUE=<issue#>
REPO=Agent-Fabric-SDK/agent-fabric-sdk

SHA=$(gh pr view $PR --repo $REPO --json mergeCommit --jq '.mergeCommit.oid' | cut -c1-7)
STATE=$(gh issue view $ISSUE --repo $REPO --json state --jq '.state')

if [ "$STATE" = "OPEN" ]; then
  gh issue close $ISSUE --repo $REPO --reason completed \
    --comment "Fixed by #$PR (merged as $SHA)."
else
  gh issue comment $ISSUE --repo $REPO \
    --body "Fixed by #$PR (merged as $SHA)."
fi
```

**One narrow exception — ask the user first:** if the PR is a *partial* fix
(e.g. it moves a value from `UNVERIFIED` to `VERIFIED-SHAPE-ONLY` but full
sandbox verification is still pending), the issue should stay open. If
unsure whether the PR fully resolves the issue, surface the question before
closing.

Forbidden rationalizations:

| Excuse | Reality |
| --- | --- |
| "The PR body has `Closes #N`, GitHub will handle it" | Often doesn't; explicit close is cheaper than "verify, then sometimes close". |
| "Auto-close already fired, closing again is a no-op" | Still write the comment — the merge SHA needs to be on the issue record. |
| "The user only said merge, not close" | On this repo, explicit close is the default behavior implied by merge. |

## After merge — worktree teardown

Once the issue is closed and the PR is merged, tear down the worktree used
for this branch — see [[afdk-git-workflow]] for `git worktree remove …` and
the primary checkout's `pull --ff-only`. If a scratch venv or `pip install -e
".[dev,...]"` was created inside the worktree, it goes away with the
worktree; nothing else in this repo needs process/service teardown (no dev
server, no local DB) unless you separately started the `local_gateway`
docker harness (§6.5) for manual testing — stop that explicitly if so.

## Quick reference

```bash
# Pre-PR gate (from python/, after branch pushed) — must pass before drafting the PR
cd python
pytest -q && mypy && ruff check . && lint-imports
# If adapter/framework code changed:
python scripts/verify_frameworks.py

# Draft → confirm → file (run from the worktree, always pass --head explicitly)
gh pr create --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --base develop --head <branch-name> \
  --title "<title>" \
  --body "Closes #<issue#>"$'\n\n'"<summary>"$'\n\n'"## Post-deploy steps"$'\n'"None."

# Verify the PR points at the right branch:
gh pr view <pr#> --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --json headRefName,baseRefName --jq '.'

# Post-merge: explicit close (default policy, never trust auto-close)
PR=<pr#>; ISSUE=<issue#>; REPO=Agent-Fabric-SDK/agent-fabric-sdk
SHA=$(gh pr view $PR --repo $REPO --json mergeCommit --jq '.mergeCommit.oid' | cut -c1-7)
STATE=$(gh issue view $ISSUE --repo $REPO --json state --jq '.state')
if [ "$STATE" = "OPEN" ]; then
  gh issue close $ISSUE --repo $REPO --reason completed \
    --comment "Fixed by #$PR (merged as $SHA)."
else
  gh issue comment $ISSUE --repo $REPO --body "Fixed by #$PR (merged as $SHA)."
fi

# Teardown
# git worktree remove <path>   (see [[afdk-git-workflow]])
```
