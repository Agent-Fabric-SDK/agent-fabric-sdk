import nextra from 'nextra'

const withNextra = nextra({
  theme: 'nextra-theme-docs',
  themeConfig: './theme.config.tsx',
  defaultShowCopyCode: true,
})

// Project sub-path for GitHub Pages (e.g. "/agent-fabric-sdk"). Left empty for
// `npm run dev` and for a future custom domain, so local/root hosting is
// unaffected; the Pages workflow sets DOCS_BASE_PATH=/agent-fabric-sdk.
const basePath = process.env.DOCS_BASE_PATH ?? ''

export default withNextra({
  reactStrictMode: true,
  output: 'export', // static HTML export — GitHub Pages has no Node server
  images: { unoptimized: true }, // the next/image optimizer can't run on a static host
  basePath,
  assetPrefix: basePath || undefined,
  // Expose the sub-path to component code: next/image's unoptimized loader does
  // NOT apply basePath to /public assets, so <Figure> prefixes them itself.
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
})
