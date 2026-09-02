# Agent Fabric SDK

An SDK for consuming **Agent Fabric** capabilities — governed model access,
governed tool access, and provisioning-as-code — from your own agent framework,
in your own IDE, without adopting Mule.

> **Project status — alpha, pre-release.** This is `v0.1.0.dev0`
> (`Development Status :: 3 - Alpha`). The **LLM data plane is live-verified**;
> most other surfaces are verification-gated (see
> [What's verified](#whats-verified-03) below). **Not yet published to PyPI** —
> [install from source](#install). **Unofficial:** an independent project,
> **not** affiliated with or endorsed by Salesforce or MuleSoft.

> ### Support & trademark statement (please read — §0.4)
>
> **"Agent Fabric" is a MuleSoft (Salesforce) product name, not a generic
> term.** `MuleSoft`, `Anypoint`, `Omni Gateway`, and `Agent Fabric` are
> Salesforce trademarks.
>
> **Maintainer & support.** This is an **independent, community-maintained**
> project, published under the org-scoped `Agent-Fabric-SDK` name — it is **not**
> affiliated with, endorsed by, or supported by Salesforce or MuleSoft. It is
> provided **as-is, without warranty of any kind**; the maintainers triage issues
> and pull requests on a **best-effort basis, with no SLA**. Because it ships
> under a distinct, org-scoped name, only the descriptive form ("an SDK for
> MuleSoft Agent Fabric") appears in prose — the package does not represent itself
> as a first-party, official-status SDK.
>
> Licensed under [Apache-2.0](LICENSE). See
> [`docs/unsupported-boundary.md`](docs/unsupported-boundary.md) for exactly
> which platform APIs this SDK calls and their support classification.

## Documentation

Two audiences, two doc sets:

- **Use the SDK** → the documentation site:
  **<https://agent-fabric-sdk.github.io/agent-fabric-sdk/>**. Install and
  configure, per-framework model access, the governed error taxonomy, and what
  to trust today — everything you need to point your agent at a governed proxy.
- **Understand or contribute to the repo:**
  - [`ARCHITECTURE.md`](ARCHITECTURE.md) — how the SDK is built: the layered
    stack, the framework-free core, verification discipline, the error taxonomy,
    and framework tiering.
  - [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to work in the repo: the
    branch/PR/release workflow, the testing strategy, coding conventions, and
    the docs-sync rule.
  - [`docs/verified-apis.md`](docs/verified-apis.md) — the verification ledger:
    the single source of truth for what is confirmed against a real sandbox and
    what is still blocked.

## Install

> **Not yet published to PyPI.** Until the first release is cut, install from
> source:

```bash
git clone https://github.com/Agent-Fabric-SDK/agent-fabric-sdk.git
cd agent-fabric-sdk/python
pip install -e ".[llm,langgraph]"   # base + raw client + one framework
```

Extras are one per framework (`langgraph`, `adk`, `strands`, `agent_framework`,
`openai`, `anthropic`, `crewai`, `llamaindex`) plus `mcp`, `a2a`, `otel`, `cli`,
`local`, and `all`. Configuration and first-agent walkthroughs live on the
[documentation site](https://agent-fabric-sdk.github.io/agent-fabric-sdk/).

## What's verified (§0.3)

The **LLM data plane** — governed model access through the Omni Gateway proxy —
is live-verified against a real Anypoint sandbox, and both the framework-free
client and the eight framework adapters are wired to that verified contract.
Everything still gated raises `NotImplementedError("blocked on verification: …")`
rather than guessing at an unverified endpoint, header, or class name — that
currently includes Exchange→MCP tool discovery, the provisioning control-plane,
and the exact framework adapter class names/kwargs.

The discipline behind this is documented in
[`ARCHITECTURE.md` → Verification discipline](ARCHITECTURE.md#verification-discipline-03);
the row-by-row worklist is [`docs/verified-apis.md`](docs/verified-apis.md).
