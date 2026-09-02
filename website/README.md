# Agent Fabric SDK — documentation site

A [Nextra](https://nextra.site) (Next.js + MDX) documentation site for the
Agent Fabric SDK. Content lives in `pages/**/*.mdx`; navigation is
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
npx serve out        # preview the exported site at the root
```

To preview exactly as GitHub Pages serves it — under the project sub-path:

```bash
DOCS_BASE_PATH=/agent-fabric-sdk npm run build
npx serve out        # assets resolve under /agent-fabric-sdk/
```

## Deploy — GitHub Pages

The site is published by [`.github/workflows/docs.yml`](../.github/workflows/docs.yml)
on every push to `main` that touches `website/**` (and on manual
`workflow_dispatch`). The workflow builds the static export with
`DOCS_BASE_PATH=/agent-fabric-sdk`, adds `.nojekyll`, and deploys the `out/`
artifact to Pages. The published site lives at
`https://agent-fabric-sdk.github.io/agent-fabric-sdk/`.

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
