---
name: afdk-docs-authoring
description: Use when writing or editing pages under website/pages/**.mdx (the Nextra docs site) — owns the pages layout, _meta.js ordering, the SDK-developer audience contract, the VERIFICATION-STATUS framing, the trademark/support boundary (§0.4), and the "cite a symbol, not path:line" rule. Read before adding a page or substantially rewriting one.
---

# AFDK Docs Authoring

## Overview

`website/` is a Nextra 3 site (`next` + `nextra-theme-docs`) documenting the
`agent-fabric` Python SDK for people who consume it, not people who
build it. It ships from `website/pages/**.mdx`, ordered by `_meta.js` files,
themed by `website/theme.config.tsx`. This skill is the authoring runbook —
what to read and obey *before* you write or rewrite a page. [[afdk-docs-sync]]
owns the complementary PR-time gate: when a code change under `python/src/`
should trigger a doc update, and what happens if the docs lag.

## When this skill activates

- Creating a new page under `website/pages/`.
- Substantially rewriting an existing page (more than a typo or one-line fix).
- Editing any `_meta.js` to add, reorder, or relabel entries.
- Reviewing a PR that touches `website/pages/**.mdx` or `_meta.js`.
- The user says "add a docs page for X", "document the new adapter", "update
  the quickstart", etc.

## Audience contract

The reader is a developer integrating `agent-fabric` into their own
agent code. They have:

- Python and pip, and are willing to run `pip install "agent-fabric[...]"`.
- No access to this repo's private planning doc
  (`agent-fabric-sdk-build-plan.md`) or its issue tracker.
- No need to know internal test layout, CI job names, or which milestone
  something shipped in.

Therefore rendered prose **must not**:

- Cite `path:line` into this repo's source (line numbers drift the moment
  someone edits the file above the cited line — see "Cite a symbol, not
  path:line" below).
- Reference internal-only concepts by their planning-doc shorthand without
  translating them: it is fine, even expected, to cite a `§N.N` section number
  from `agent-fabric-sdk-build-plan.md` as **authority** (e.g. "See
  Verification policy (§0.3)" — the site does this deliberately, see
  `website/pages/concepts/verification.mdx`), but don't assume the reader has
  or needs the document itself to understand the page.
- Claim something is verified, live, or supported when it is not — see
  VERIFICATION-STATUS framing below. This is the contract violation with the
  highest blast radius in this repo: a customer who trusts a fabricated
  endpoint or header name and hits a `404` in their own sandbox stops trusting
  the whole package (§0.3).
- Overclaim MuleSoft affiliation — see the trademark/support boundary below.

## File layout

```
website/
├── pages/
│   ├── _meta.js                # top-level nav: Introduction, Quickstart,
│   │                           #   feature-overview, pillars (frameworks,
│   │                           #   tool-access, provisioning, publishing),
│   │                           #   concepts, errors, reference — via
│   │                           #   `type: 'separator'` section headers
│   ├── index.mdx                # landing page
│   ├── quickstart.mdx
│   ├── feature-overview.mdx
│   ├── errors.mdx               # error taxonomy
│   ├── publishing.mdx
│   ├── concepts/
│   │   ├── _meta.js             # verification, governance, environments, attribution
│   │   ├── verification.mdx     # §0.3 — the VERIFICATION-STATUS page, read this first
│   │   ├── governance.mdx
│   │   ├── environments.mdx
│   │   └── attribution.mdx
│   ├── frameworks/               # Pillar 1: one page per framework adapter
│   │   ├── _meta.js              # index, langgraph, adk, strands,
│   │   │                         #   agent-framework, openai, anthropic,
│   │   │                         #   crewai, llamaindex
│   │   ├── index.mdx
│   │   └── <framework>.mdx       # one per Tier 1/2 integration
│   ├── tool-access/               # Pillar 2
│   │   ├── _meta.js               # index, discovery, binding, a2a, lockfile
│   │   └── *.mdx
│   ├── provisioning/              # Pillar 3
│   │   ├── _meta.js               # index, spec, plan-apply, governance-lint
│   │   └── *.mdx
│   └── reference/
│       ├── _meta.js               # configuration, unsupported-boundary
│       └── *.mdx
├── theme.config.tsx              # site chrome, trademark footer, docsRepositoryBase
└── package.json                  # npm install / dev / build / start
```

Add a page inside the pillar or concept group it belongs to; don't invent a
new top-level group for one page — the existing separators (Pillars, Concepts,
Reference) already cover the domain, and `frameworks/`, `tool-access/`, and
`provisioning/` each map to one of the three pillars in the build plan.

## `_meta.js` conventions

Each directory's `_meta.js` is a plain JS object exporting `{ slug: label }`
(or a `{ type: 'separator', title }` entry to visually group siblings). It
controls **order and label**, not existence — a page not listed still renders,
just without a nice label, usually last. Observed conventions in this repo:

- Top-level `pages/_meta.js` uses `'-- <name>': { type: 'separator', title:
  '<Title>' }` entries to break the sidebar into Pillars / Concepts /
  Reference. Follow that pattern for any new grouping rather than nesting deeper.
- Section labels can carry a `§N.N` citation right in the label string, e.g.
  `verification: 'Verification policy (§0.3)'` in `concepts/_meta.js` — do this
  when the section number is genuinely load-bearing for the reader (verification
  status, governance), not decoratively.
- `frameworks/_meta.js`, `tool-access/_meta.js`, and `provisioning/_meta.js`
  each start with `index: 'Overview'` (or equivalent) followed by the concrete
  pages in the order you want them read, not alphabetical — quickstart-shaped
  reading order beats alphabetical.

When adding a page: add its slug to the directory's `_meta.js` in the position
where a first-time reader should encounter it. A page missing from `_meta.js`
is a page that got orphaned — check for it after every new-page PR.

## VERIFICATION-STATUS framing (§0.3) — the load-bearing rule

This is the single most important discipline on this site, because the SDK's
credibility rests on it. `website/pages/concepts/verification.mdx` is the
canonical page; every other page that claims a fact about the Anypoint
control plane, the LLM proxy, or a framework's constructor signature must be
consistent with it and with `docs/verified-apis.md` (the engineering source of
truth, `NOT` shipped to the docs site, but you should read it before writing).

Rules for any page that states a platform fact:

1. **Never invent an endpoint, header, or class name.** If you don't have a
   verified value, don't write a plausible-looking one — write that it's
   blocked on verification, or omit the claim.
2. **Use the same status vocabulary the codebase uses**, don't paraphrase it
   into something softer: `VERIFIED (LIVE)`, `VERIFIED (CLI)`, `VERIFIED
   (plugin)`, `VERIFIED (build)`, `VERIFIED-SHAPE-ONLY`, `UNVERIFIED`. A page
   that says "supported" about something `docs/verified-apis.md` marks
   `UNVERIFIED` is a documentation bug, not a simplification.
3. **When a code path is guarded**, say so in the reader's terms: the
   behavior is a `NotImplementedError("blocked on verification: …")` raised
   at call time, not a silent no-op and not a guess. `errors.mdx` models this
   well for the "not-yet-captured shapes" case (prompt-injection /
   content-safety bodies fall through to `PolicyViolation` rather than
   inventing a discriminator).
4. **Point to the verification mechanism, not just the claim.** For framework
   adapters that's `python scripts/verify_frameworks.py [--live]
   [--emit-verified]` and the nightly matrix (`nightly-matrix.yml`) — cite
   them so a skeptical reader can reproduce the check themselves, the same
   way `concepts/verification.mdx` does.
5. **Prefer "blocked on verification" framing over silence.** If a pillar or
   feature is unverified, say what's blocked and why, rather than omitting
   the page — omission reads as "not started," while a "blocked on
   verification" callout reads as "known, deliberate, and tracked."

If you are unsure whether a fact is currently verified, read
`docs/verified-apis.md`'s status table for that row before writing the
sentence. Don't infer status from how confident the sentence sounds elsewhere
in the codebase.

## Trademark / support boundary (§0.4)

`MuleSoft`, `Anypoint`, `Omni Gateway`, and `Agent Fabric` are Salesforce
trademarks; "Agent Fabric" names a specific MuleSoft product, not a generic
term. This SDK is **descriptive, not first-party** — it is "an SDK *for*
Agent Fabric," not a MuleSoft-branded product. `theme.config.tsx`
encodes this in the footer:

> Agent Fabric SDK — an SDK *for* Agent Fabric. "Agent Fabric",
> "Anypoint", and "Omni Gateway" are Salesforce trademarks; this project is
> descriptive (§0.4).

When writing or reviewing prose:

- Never imply MuleSoft/Salesforce endorsement, authorship, or official
  support unless that has actually been confirmed (§0.4 describes two
  workable paths — endorsed vs. unaffiliated — and this project currently
  reads as the unaffiliated path).
- Keep the descriptive phrasing ("an SDK for Agent Fabric") rather
  than letting a page drift into first-party voice ("Agent Fabric's SDK",
  "our platform").
- Don't add a support promise ("we'll fix this within X days") that isn't
  backed by an actual maintainer commitment; the trademark footer's job is
  precisely to keep the "who supports this" question honest.
- `theme.config.tsx`'s `project.link` and `docsRepositoryBase` currently point
  at a placeholder (`your-org/agent-fabric`) with a `TODO` — flag
  this if you're doing a pre-publish pass, but don't silently "fix" it to a
  guessed URL; the real slug is `Agent-Fabric-SDK/agent-fabric-sdk` per repo
  facts, confirm with a maintainer before changing site chrome that affects
  trademark posture.

## Cite a symbol, not path:line

Never write `python/src/agent_fabric/core/errors.py:142` in rendered prose.
Line numbers drift the moment anyone edits above that line, and the citation
silently goes stale with no build failure to catch it. Instead:

- Cite the **importable symbol**: `agent_fabric.PIIDetected`,
  `agent_fabric.core.errors.classify()`, `fabric.llm.client(sync=True)`. This
  is how `errors.mdx` and `quickstart.mdx` already do it — every code sample
  cites a class or function name a reader can `import` and check, never a
  line number.
- Cite a **module path without a line number** when you need to point at a
  file rather than a symbol, e.g. "the placeholder constants live in
  `core/_verify.py`" (from `concepts/verification.mdx`) — a path survives
  refactors inside the file; a line number does not.
- Cite a **`§N.N` build-plan section** for design authority
  (`agent-fabric-sdk-build-plan.md`), not a line range in that
  document either — sections are stable identifiers, line numbers aren't.
- Cite a **command** the reader can run to reproduce a claim
  (`python scripts/verify_frameworks.py --live`) rather than describing what
  running it once showed at some line in some log.

If you catch yourself about to write a colon followed by a number after a
file path, stop and find the symbol or section name instead.

## Page conventions observed in this repo

- **Nextra components**: pages import from `'nextra/components'` —
  `Callout`, `Steps`, `Tabs` are used today (`quickstart.mdx` uses all three;
  `errors.mdx` uses `Callout`). Use `<Callout type="info">` for framing notes,
  `<Callout type="warning">` where a subtlety could bite (e.g. `errors.mdx`'s
  warning that `fabric.llm.client()` raises `openai.APIStatusError`, not a
  `FabricError`, until bridged with `classify()`), `<Callout type="error">`
  only for the highest-severity warnings (verification.mdx uses it exactly
  once, for "never invent an endpoint, header name, or class name").
- **`<Steps>`** for install/configure/run sequences (see `quickstart.mdx`).
- **`<Tabs>`** when the same task has multiple equally-valid entry points —
  `quickstart.mdx` uses it for Python async / Python sync / TypeScript /
  cURL, all hitting the same governed proxy contract.
- **Cross-links use root-relative paths** (`/errors`, `/concepts/verification`,
  `/frameworks`), matching Nextra's routing off `pages/`, not relative `./`
  paths and not full URLs.
- **A page ends with a "Where to go next" section** linking forward to
  logical next reads (see the bottom of `quickstart.mdx`) — not mandatory on
  every page, but the pattern to reach for when a page is an entry point.
- **Voice**: second person, present tense, developer-to-developer. Tables are
  used liberally for anything with a discriminator (see the rejection-shape
  table in `errors.mdx`) — prefer a table over prose when there are 3+ items
  each with the same 2-3 attributes.

## Adding a new page — checklist

1. Decide which pillar/concept group it belongs to (`frameworks/`,
   `tool-access/`, `provisioning/`, `concepts/`, `reference/`, or top-level).
2. Write the `.mdx` following the conventions above; cross-check every
   platform-fact sentence against `docs/verified-apis.md`'s status column.
3. Cite symbols/commands/§-sections, never `path:line`.
4. Add the slug to the group's `_meta.js` in reading order (and to the parent
   `pages/_meta.js` if it's a new top-level entry).
5. Smoke-test locally:
   ```bash
   cd website
   npm install
   npm run dev     # or: npm run build && npm run start
   ```
   Confirm the page renders, the sidebar position and label are right, and
   every cross-link resolves.
6. If the page states anything [[afdk-docs-sync]] would consider a
   code-surface claim (e.g. a new adapter's exact factory signature), make
   sure that skill's mapping is updated too — this skill owns *how* to write
   the page, not *whether* a given code change obligates one.

## Editing an existing page — checklist

1. Make the edit.
2. Re-read the whole page as a developer who has never seen this repo's
   internal planning doc. Would any sentence read as an official-support or
   verified-fact claim that isn't backed by `docs/verified-apis.md` today?
3. Check every code sample still names real, importable symbols
   (`agent_fabric.PIIDetected`, `fabric.langgraph.chat_model`, etc.) —
   renamed exports are the most common source of silent doc drift.
4. Re-check `_meta.js` if the edit changed the page's role (e.g. it's no
   longer an entry point, or it now belongs in a different group).

## Forbidden rationalizations

| Excuse | Reality |
| --- | --- |
| "I'll cite the exact line, it's more precise" | Line numbers drift on the next unrelated edit; the citation goes stale with no build failure. Cite the symbol or `§N.N` section instead. |
| "It's probably verified by now, I'll just say it's supported" | If `docs/verified-apis.md` still says `UNVERIFIED`, the page must say so too. "Probably" is exactly the guess §0.3 forbids. |
| "This endpoint/header name is a reasonable guess" | A fabricated endpoint that 404s in a customer sandbox is worse than admitting it's unknown (§0.3). Write "blocked on verification" instead. |
| "I'll drop the descriptive phrasing, 'Agent Fabric's SDK' reads cleaner" | That phrasing implies first-party MuleSoft authorship. Trademark exposure (§0.4) outranks prose elegance. |
| "One extra top-level nav group won't hurt" | The existing three separators (Pillars/Concepts/Reference) map onto the build plan's own structure. A stray fourth group signals the page doesn't actually belong anywhere yet — find its real home instead. |
| "The page doesn't need `_meta.js` updated, Nextra will just append it" | True but it lands in the wrong reading position with no label — always place it deliberately. |

## Quick reference

```bash
# Smoke-test the docs site
cd website
npm install
npm run dev              # http://localhost:3000
npm run build && npm run start   # production build check

# Find the verification status of a claim before writing it
grep -n "VERIFIED\|UNVERIFIED" docs/verified-apis.md | less

# Find every place a fact is guarded pending verification
rg "blocked on verification" python/src/agent_fabric

# Reproduce the framework-adapter verification claims yourself
cd python
python scripts/verify_frameworks.py            # signature check, offline
python scripts/verify_frameworks.py --live     # + real proxy round-trip
```

See [[afdk-verification-discipline]] for the engineering-side rules that
produce `docs/verified-apis.md` in the first place, and [[afdk-docs-sync]]
for when a `python/src/` change obligates a doc update at all.
