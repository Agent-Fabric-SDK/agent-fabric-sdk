---
name: afdk-release
description: Use when tagging an agent-fabric-sdk release, cutting a GitHub Release, writing release notes, or bumping the package version. Owns the PEP 440 milestone-driven tag convention, the pre-release ladder (.devN → aN/bN/rcN → final), where the version string is bumped, the `gh release create` recipe, and the hotfix-tag case. Triggers when about to run `git tag`, `gh release create`, or when someone says "cut a release", "tag the release", "write release notes", or "bump the version". This is the tagging half that [[afdk-merge-strategy]] deliberately leaves out.
---

# AFDK Release

## Overview

`agent-fabric-sdk` releases are **git tags plus GitHub Releases on `main`**.
This skill owns everything from "the promotion merge has landed on `main`"
onward: the version string, the tag, the GitHub Release, and its notes.

It is the sibling of [[afdk-merge-strategy]], and the split is deliberate:

- [[afdk-merge-strategy]] gets the release **content** onto `main` (the
  `develop → main` no-ff promotion merge) and closes the milestone. It states
  outright that **tagging is out of scope** and defers here.
- **This skill turns that promotion into a named, tagged, released version.**

So the full release lifecycle is: promote (`afdk-merge-strategy`) → **tag +
release (this skill)**. Never tag a commit that isn't already the tip of `main`
after a promotion merge — a tag is a claim about `main`, not about `develop`.

## Version scheme: PEP 440, milestone-driven

This is a Python package. **Version strings are PEP 440**, not raw SemVer, so
they normalize cleanly on PyPI. The version is **not invented per release** —
it is the version of the **milestone being shipped**. The milestone titles are
the ground truth (`gh` resolves `--milestone` by exact string):

| Milestone (exact title) | Ships version |
| --- | --- |
| `Phase 1 — Build the MVP (0.1.0)` | `0.1.0` |
| `Phase 2 — Differentiate, go beyond (0.2.0)` | `0.2.0` |
| `Phase 3 — Platform capabilities (0.3.0)` | `0.3.0` |
| `Phase 4 — Enterprise readiness (0.4.0)` | `0.4.0` |
| `Phase 5 — Complete rollout (1.0.0)` | `1.0.0` |

`Verification` and `Upstream gaps` have **no version and never ship** — they are
standing milestones (§0.3), not releases. Do not tag against them.

### The pre-release ladder (before a milestone is complete)

A milestone is **release-ready only at 0 open issues** (the signal defined in
[[afdk-merge-strategy]]). Before then, promotions still happen — docs, spec,
and scaffolding land on `main` ahead of the feature work — and those get
**pre-release** tags on the ladder toward the milestone's final version.

PEP 440 pre-release segments sort in this order (each strictly less than the
final version), so tag names sort correctly and PyPI orders them correctly:

```
0.1.0.dev0  <  0.1.0.dev1  <  …  <  0.1.0a1  <  0.1.0b1  <  0.1.0rc1  <  0.1.0
   dev0            devN            alpha 1       beta 1      rc 1        final
```

- **`.devN`** — pre-MVP groundwork: docs, spec, scaffolding, plumbing. No
  usable feature surface yet. (Today's `main` is here.)
- **`aN` / `bN`** — alpha/beta: real feature surface exists, still unstable.
- **`rcN`** — release candidate: milestone all-but-complete, final validation.
- **final** (`0.1.0`) — the milestone hit **0 open issues** and promoted.

Write the tag with the normalized PEP 440 spelling — `0.1.0a1`, **not**
`0.1.0-alpha.1`. Every tag below the final version is flagged **pre-release**
on GitHub (`--prerelease`).

### Single source of version truth — bump in lockstep

The version string lives in **two files**, which MUST always agree:

- `python/pyproject.toml` → `version = "…"`
- `python/src/agent_fabric/__init__.py` → `__version__ = "…"`

**Bump both on `develop`, in the PR that finishes a version's work, BEFORE the
promotion PR** — so the code on `main` already reads the version its tag will
carry. The tag is created *after* the merge, and it must match the string in
those two files at that commit. A tag whose version disagrees with
`__version__` is a bug.

## Release procedure

Run this **after** the `develop → main` promotion merge from
[[afdk-merge-strategy]] has landed (and, for a final release, after that skill
has closed the milestone).

### Approval gate

Tagging and publishing a GitHub Release are **outward-facing, `main`-touching**
actions. Confirm with the user before running, every time — the same standard
[[afdk-merge-strategy]] applies to promotion. Discussion is not approval;
confirm at the moment of tagging. Before tagging, verify:

1. The commit you're tagging **is the current tip of `main`** (a promotion
   merge commit), and CI is green on it.
2. The version in `pyproject.toml` and `__init__.py` at that commit **matches**
   the tag you're about to create.
3. Whether this is a **pre-release** (below the milestone's final version) or a
   **final** release (milestone at 0 open, just promoted) — this decides
   `--prerelease`.

### Steps

```bash
REPO=Agent-Fabric-SDK/agent-fabric-sdk

# 1. Confirm main's tip and the version string agree with the tag.
git fetch origin --tags
git log --oneline origin/main -1
git show origin/main:python/pyproject.toml | rg '^version'          # must equal the tag
git show origin/main:python/src/agent_fabric/__init__.py | rg '__version__'

# 2. Annotated tag on main's tip, v-prefixed. One tag per promotion.
git tag -a v<VERSION> <main-tip-sha> -m "v<VERSION> — <one-line summary>"
git push origin v<VERSION>

# 3. GitHub Release. --prerelease for anything below the milestone's final version.
gh release create v<VERSION> --repo "$REPO" \
  --title "v<VERSION> — <short title>" \
  --prerelease \           # OMIT this line only for a final X.Y.Z release
  --notes "$(cat <<'EOF'
<curated notes — see "Release notes" below>
EOF
)"
```

Notes:

- **Annotated tags only** (`-a`), never lightweight — a release tag carries a
  message and author. Prefix with `v`.
- **`--prerelease` for every tag below the milestone's final version**
  (`.devN`, `aN`, `bN`, `rcN`). Drop it *only* for `X.Y.Z` finals.
- Tag `main` **only**. Never tag `develop` or a feature branch.
- Publishing to **PyPI is a separate, not-yet-wired step** — do not invent a
  publish workflow or `twine`/trusted-publisher config here. The tag + GitHub
  Release is the deliverable this skill owns; if/when PyPI publishing is added,
  it hangs off the tag, and its exact mechanism gets verified first (§0.3).

## Release notes — GitHub Releases only

**There is no `CHANGELOG.md`.** The GitHub Release *is* the changelog. Do not
add a committed changelog file — that would be a new cross-surface lockstep
target with no reader the Release page doesn't already serve.

Build the notes in two passes:

1. **Raw list.** For any tag after the first, let GitHub draft the PR list
   between the previous tag and this one:
   ```bash
   gh release create v<VERSION> --repo "$REPO" --generate-notes --draft …
   ```
   `--generate-notes` needs a previous tag to diff against; the **first ever
   release is hand-written** (there's nothing to diff from).
2. **Curate.** Rewrite the auto-list into a short human summary. The Release
   body MUST call out — mirroring the promotion PR body
   [[afdk-merge-strategy]] already requires:
   - **Breaking changes** (and the migration).
   - **Verification-status changes (§0.3)** — any surface that flipped
     `blocked → verified` or vice-versa; link the `docs/verified-apis.md` row.
   - **Extras changes (§8.4)** — new/removed extras, floor bumps (never upper
     pins).
   - For a **pre-release**, one plain line stating what is *not* yet real —
     e.g. "pre-MVP: docs and scaffolding only; the LLM data plane is the sole
     live-verified surface." Do not let a `.devN` tag read like a usable SDK.

Cite **symbols, not `path:line`** in notes (repo convention) and keep the
trademark/support wording per §0.4 — a Release page is public.

## Hotfix tags

When [[afdk-merge-strategy]]'s hotfix path lands a fix straight on `main`
(squash PR into `main`, then cherry-pick to `develop`), it produces a new
`main` tip that needs its own tag:

- Bump the **patch** component: a hotfix on `v0.1.0` ships `v0.1.1`. Bump the
  version string in both files as part of the hotfix PR, so `main` matches the
  tag.
- Tag and release exactly as above. A hotfix on a final release is itself
  final (no `--prerelease`); a hotfix on a pre-release keeps climbing the
  ladder.

## Red flags — STOP

- About to `git tag` a commit that is **not** the current tip of `main`.
- About to tag with a version that **disagrees** with `__version__` /
  `pyproject.toml` at that commit.
- About to create a Release for a below-final version **without**
  `--prerelease`.
- About to spell a pre-release SemVer-style (`0.1.0-alpha.1`) instead of PEP
  440 (`0.1.0a1`).
- About to add a `CHANGELOG.md` — the GitHub Release is the changelog.
- About to invent a PyPI-publish workflow — it's a separate, verification-gated
  step, not part of this skill.
- About to tag without explicit user approval at tag time.

## Forbidden rationalizations

| Excuse | Reality |
| --- | --- |
| "Main is pre-MVP but calling it 0.1.0 is close enough" | `0.1.0` means the Phase 1 milestone completed (0 open). Below that, it's `0.1.0.devN` / `aN` / `bN` / `rcN`, flagged pre-release. |
| "SemVer `-alpha.1` is clearer than `a1`" | PyPI normalizes it to `a1` anyway; carry the normalized spelling in the tag so tag and package version match. |
| "A CHANGELOG.md is more durable" | It's another lockstep surface to drift. The Release page is the durable, public record here. |
| "I'll tag develop's tip, it's the same content" | It isn't — `main` has the promotion merge commit. Tags are claims about `main`. |
| "The release was agreed yesterday, I'll skip the approval" | Tagging publishes outward. Confirm at tag time, every time. |

## Quick reference

```bash
REPO=Agent-Fabric-SDK/agent-fabric-sdk

# Version = the shipping milestone (Phase N → 0.N.0, Phase 5 → 1.0.0).
# Below final → pre-release ladder: 0.N.0.devK < …a1 < …b1 < …rc1 < 0.N.0
# Bump BOTH files on develop before the promotion PR:
#   python/pyproject.toml            version = "<VERSION>"
#   python/src/agent_fabric/__init__.py   __version__ = "<VERSION>"

# After the develop→main promotion merge lands (afdk-merge-strategy), with approval:
git fetch origin --tags
git tag -a v<VERSION> <main-tip-sha> -m "v<VERSION> — <summary>"
git push origin v<VERSION>
gh release create v<VERSION> --repo "$REPO" \
  --title "v<VERSION> — <title>" \
  --prerelease \                 # omit ONLY for a final X.Y.Z
  --generate-notes               # first release only: hand-write instead
# Then curate: breaking changes, §0.3 verification flips, §8.4 extras,
# and (pre-release) a line on what is not yet real.
```
