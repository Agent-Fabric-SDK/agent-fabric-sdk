---
name: afdk-issue-relationships
description: Use when linking GitHub issues for agent-fabric-sdk — sub-issues (parent/child), blocked-by/blocking dependencies, or cross-link "related" comments. Run after an issue is filed, not as part of filing it.
---

# Agent Fabric SDK Issue Relationships

## Overview

Plain `#NN` mentions in an issue body create a backlink in the timeline but are not structural — they don't show in a "Blocked by" panel and don't auto-update. Pick the right tool per relationship type.

This skill is for **linking issues that already exist**. For drafting and filing the issue itself, use [[afdk-filing-issues]] first; come here once both issues exist and you need to wire the relationship.

## Target repo

```
Agent-Fabric-SDK/agent-fabric-sdk
```

Always pass `--repo Agent-Fabric-SDK/agent-fabric-sdk` to `gh` calls.

## Pick the right tool

| Relationship | Tool |
| --- | --- |
| B is a sub-task / breakdown of A | sub-issue (B → A) |
| A is a parallel feature that needs B first | issue dependency (A blocked-by B) |
| "related to / could reuse / follow-up" | cross-link comments |

## Hard dependency — sub-issues (parent / child)

When issue A *cannot ship until* issue B ships AND B is a breakdown of A's scope, make B a **sub-issue** of A. The parent's UI then shows a Sub-issues panel with completion progress, and the child shows its parent.

```bash
# Get the child's internal id (NOT the issue number).
gh api repos/Agent-Fabric-SDK/agent-fabric-sdk/issues/<child-number> --jq '.id'

# Link it. NOTE: use -F (typed integer), not -f (string) — the API rejects strings.
gh api -X POST repos/Agent-Fabric-SDK/agent-fabric-sdk/issues/<parent-number>/sub_issues \
  -F sub_issue_id=<child-id>
```

When you link a sub-issue, also add a `## Depends on` line to the parent's body (see "Body sections" below) so a reader scanning the markdown sees it without opening the Sub-issues panel.

## Hard dependency without containment — issue dependencies (blocked-by / blocking)

When issue A *cannot ship until* B ships but A is **not** a sub-task of B (they're parallel features, just sequenced — e.g. one framework adapter's conformance work blocking another's), use GitHub's issue-dependencies API instead of sub-issues. This adds a "Blocked by" panel on A and a "Blocking" panel on B without implying hierarchy.

```bash
# Get the blocker's internal id (NOT the issue number).
gh api repos/Agent-Fabric-SDK/agent-fabric-sdk/issues/<blocker-number> --jq '.id'

# Mark <blocked-number> as blocked-by <blocker-id>. Use -F (typed integer).
gh api -X POST repos/Agent-Fabric-SDK/agent-fabric-sdk/issues/<blocked-number>/dependencies/blocked_by \
  -F issue_id=<blocker-id>
```

The response will include `issue_dependencies_summary: { blocked_by: N, blocking: M }` — verify N incremented before reporting success.

## Soft relationship — cross-link comments

For "related to" / "could reuse" / "follow-up of" relationships that are not blocking (e.g. an adapter bug that also affects the conformance suite's KNOWN_LIMITATIONS list, without blocking it), drop a brief comment on **both** issues so the timelines link both ways. Keep it one or two sentences and explain *the nature* of the relationship — "Related: #X" alone is noise.

```bash
gh issue comment <issue> --repo Agent-Fabric-SDK/agent-fabric-sdk \
  --body "Related: #<other> — <one-sentence reason>"
```

Run both directions in the same step (parallel `&` calls + `wait`).

## Body sections: `## Depends on` / `## Related`

When an issue has hard or soft dependencies, add one or both sections to the body — the markdown is part of the contract, the GitHub link is the structural backup.

If the issue is already filed, edit its body with `gh issue edit <#> --body-file -` (heredoc) rather than re-filing. If you're filing a fresh issue, add these sections **before** filing per [[afdk-filing-issues]].

```markdown
## Depends on
- #42 — core/_verify.py must lift the `_verify.blocked("§6.9 custom policies")` guard before this issue's PolicyPlugin adapter can be implemented against the real shape.

## Related
- #37 — the LangGraph adapter hit the same UNVERIFIED gap in docs/verified-apis.md; worth reconciling the two VERIFIED-SHAPE-ONLY entries together.
```

Reference the relevant build-plan §N.N when it clarifies *why* the dependency exists — e.g. "blocked by #N per §6.10 PolicyPlugin interface" is more useful to a future reader than the bare relationship.

## What NOT to do

- Don't use **closing keywords** (`Closes #X`, `Fixes #X`) issue → issue. They only work in PR descriptions, where the linked issue auto-closes on merge. In an issue body they're misleading.
- Don't skip the body section on the assumption that the GitHub link is enough — issue bodies are read in many contexts (email digests, search snippets) where the structural link is invisible.
- Don't link an issue to itself or create circular dependency chains. The API will accept some of these silently and they wedge the UI.
- Don't mark an issue "blocked by" a framework's UNVERIFIED status as a substitute for filing the verification work itself — link to the actual tracking issue, not the docs/verified-apis.md entry.

## Verifying the link

```bash
# Sub-issues on a parent
gh api repos/Agent-Fabric-SDK/agent-fabric-sdk/issues/<parent-number>/sub_issues --jq '.[].number'

# Dependency summary on an issue
gh api repos/Agent-Fabric-SDK/agent-fabric-sdk/issues/<#> \
  --jq '.issue_dependencies_summary'
```
