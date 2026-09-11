# Tool access

  **Phase 2 — designed, not yet shipped.** This documents governed tool access as designed in the build guide. The platform contracts it depends on are being live-verified; until then, unverified paths raise `NotImplementedError("blocked on verification: …")` rather than guess. See [Verification policy](https://donkey-development-kit.github.io/donkey-development-kit/concepts/verification.md).

Governed tool access is the differentiating feature: discover the MCP tools your
organisation has published and governed, filter them down to what an agent
actually needs, and bind them into any of the eight frameworks as that
framework's **native tool objects** — the same "no wrapper" rule as
[model access](https://donkey-development-kit.github.io/donkey-development-kit/frameworks.md).

## The target developer experience

Two lines take you from "our enterprise has a governed tool catalog" to "my
LangGraph agent can use it":

```python
tools = await donkey.tools.discover(domain="hr", tags=["approved"])
agent = create_react_agent(donkey.langgraph.chat_model("gpt-4o"), tools.langgraph())
```

Everything else in this section — search filters, session management,
per-framework binding, pinning, and A2A tool handles — exists to make those
two lines hold up in production.

## What discovery returns

`donkey.tools.discover(...)` is also the filter and search entry point. The
same call narrows the catalog by name/description glob, governance, domain,
tags, and asset type, so an agent binds only the tools it needs instead of the
whole catalog:

```python
tools = await donkey.tools.discover(
    search="*accounts*",     # glob over asset name + description
    governed_only=True,      # default criteria, or a GovernanceCriteria
    domain="hr",
    tags=["approved"],
    asset_types=["mcp"],
    environment="Production",
    limit=50,
)
```

`governed_only` and the `GovernanceCriteria` vocabulary are covered on the
[Discovery, search & filter](https://donkey-development-kit.github.io/donkey-development-kit/tool-access/discovery.md) page — "governed" is a
computed predicate, not a flag Exchange exposes directly. See also the
[environments and governance object](https://donkey-development-kit.github.io/donkey-development-kit/concepts/environments.md) page for how
governance is scoped per environment.

## In this section

  
    Narrow the catalog by name, governance, domain, tags, and asset type.
  
  
    Turn a `ToolSet` into each framework's own native tool objects.
  
  
    Pin resolved versions and digests so a run is reproducible.
  
  
    Treat a governed agent-to-agent endpoint as another bindable tool.
  

**Status: planned — not yet shipped.**
