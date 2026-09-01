import React from 'react'
import type { DocsThemeConfig } from 'nextra-theme-docs'

const config: DocsThemeConfig = {
  logo: (
    <span style={{ fontWeight: 700, letterSpacing: '-0.01em' }}>
      🧵 Agent Fabric SDK
    </span>
  ),
  project: {
    // TODO: point at the real repository before publishing (§0.4).
    link: 'https://github.com/your-org/mulesoft-agent-fabric',
  },
  docsRepositoryBase:
    'https://github.com/your-org/mulesoft-agent-fabric/tree/main/docs-site',
  // Violet accent, close to the reference docs look.
  color: {
    hue: 262,
    saturation: 90,
  },
  head: (
    <>
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <meta
        name="description"
        content="An SDK for MuleSoft Agent Fabric — governed model access, governed tool access, and provisioning-as-code, from your own agent framework."
      />
      <meta property="og:title" content="Agent Fabric SDK" />
      <meta
        property="og:description"
        content="Governed model access, tool access, and provisioning-as-code for MuleSoft Agent Fabric."
      />
    </>
  ),
  footer: {
    content: (
      <span>
        Agent Fabric SDK — an SDK <em>for</em> MuleSoft Agent Fabric. “Agent
        Fabric”, “Anypoint”, and “Omni Gateway” are Salesforce trademarks; this
        project is descriptive (§0.4).
      </span>
    ),
  },
  sidebar: {
    defaultMenuCollapseLevel: 1,
    toggleButton: true,
  },
  toc: {
    backToTop: true,
  },
}

export default config
