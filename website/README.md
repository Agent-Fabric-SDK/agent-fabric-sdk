# Donkey Development Kit — documentation site

A [Nextra](https://nextra.site) (Next.js + MDX) documentation site for the
Donkey Development Kit. Content lives in `pages/**/*.mdx`; navigation is
declared in the `_meta.js` files next to the pages.

## Local development

```bash
cd website
npm install
npm run dev          # http://localhost:3000
```

Build the static export (what CI ships to Pages) and preview it:

```bash
npm run build        # `output: 'export'` → writes a static site to ./out
npm run preview:pages
```

To preview exactly as GitHub Pages serves it — under the project sub-path:

```bash
DOCS_BASE_PATH=/donkey-development-kit npm run build
npm run preview:pages
# Open http://localhost:4173/donkey-development-kit/
```

The preview command serves the generated static files from `out/`, matching
GitHub Pages more closely than the Next.js development server. The preview
script maps the `/donkey-development-kit` project prefix back to the export root so
pages, stylesheets, fonts, and scripts resolve at the same URLs used after
deployment. GitHub's Jekyll preview instructions do not apply here: this site
is a Nextra/Next.js static export, and the Pages workflow disables Jekyll
before deployment.

## AI-readable docs (`llms.txt`)

The site publishes its docs in the [llms.txt convention](https://llmstxt.org)
so coding assistants can read them (#205, BG §1.10):

- `public/llms.txt` — a link index, grouped by nav section.
- `public/llms-full.txt` — every page inlined into one file.
- `public/<path>.md` — the raw markdown for each page, served beside its HTML.

These are **generated** from the pages by
[`scripts/generate-llms.mjs`](scripts/generate-llms.mjs) — the source of truth
is `_meta.js` (ordering + titles) and each `.mdx` (content + frontmatter);
nothing is hand-maintained. `npm run build` regenerates them first (via the
`prebuild` hook), and the `docs-llms-drift` CI job regenerates and fails on any
diff, so the committed artifacts cannot drift from the pages.

```bash
npm run generate:llms   # regenerate after editing pages; commit the result
```

## Deploy — GitHub Pages

The site is published by [`.github/workflows/docs.yml`](../.github/workflows/docs.yml)
on every push to `main` that touches `website/**` (and on manual
`workflow_dispatch`). The workflow builds the static export with
`DOCS_BASE_PATH=/donkey-development-kit`, adds `.nojekyll`, and deploys the `out/`
artifact to Pages. The published site lives at
`https://donkey-development-kit.github.io/donkey-development-kit/`.

**One-time setup:** in repo **Settings → Pages**, set **Source = "GitHub
Actions"**. The workflow cannot flip that switch; until it is set, the deploy
job has nowhere to publish.

`basePath`/`assetPrefix` are gated on `DOCS_BASE_PATH`, so `npm run dev` and a
future custom domain serve at the root without the sub-path.

## Structure

```
pages/
  index.mdx                 Introduction — what the SDK is
  quickstart.mdx            First governed request
  feature-overview.mdx      The three pillars at a glance
  frameworks/               Model access — one page per framework (Pillar 1)
  tool-access.mdx           Pillar 2 (roadmap)
  provisioning.mdx          Pillar 3 (roadmap)
  concepts/                 Verification policy, governance, attribution
  errors.mdx                Governed error taxonomy
  reference/                Configuration, unsupported boundary
```

## Editing rules (inherited from the SDK — §0.3)

**Never document an endpoint, header, or class name that isn't verified.** Where
a value is unconfirmed, say so on the page (see the "Verification policy" page).
The engineering source of truth for what is verified is
[`../docs/verified-apis.md`](../docs/verified-apis.md).
