# Agent Fabric SDK — documentation site

A [Nextra](https://nextra.site) (Next.js + MDX) documentation site for the
MuleSoft Agent Fabric SDK. Content lives in `pages/**/*.mdx`; navigation is
declared in the `_meta.js` files next to the pages.

## Local development

```bash
cd docs-site
npm install
npm run dev          # http://localhost:3000
```

Build a production bundle:

```bash
npm run build
npm run start        # serves the built site
```

## Deploy

This is a standard Next.js app, so it deploys to Vercel or Railway without
special configuration — the only thing to set is the **project root**, because
the site lives in the `docs-site/` subdirectory of the repo.

### Vercel

1. Import the repo.
2. Set **Root Directory** to `docs-site`.
3. Framework preset auto-detects as **Next.js**. Build command `next build`,
   output handled automatically. Deploy.

(Optionally add a `vercel.json` at the repo root with
`{ "buildCommand": "cd docs-site && npm install && npm run build" }` if you
prefer configuring from the repo root instead of the dashboard.)

### Railway

1. New project → Deploy from the repo.
2. Set the service **Root Directory** to `docs-site` (or a `RAILWAY_DOCKERFILE`
   / Nixpacks root).
3. Nixpacks detects Next.js: build `npm run build`, start `npm run start`.
   `npm run start` binds to `$PORT` (Railway sets it) via the `start` script.

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
