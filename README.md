# MuleSoft Agent Fabric SDK

An SDK for consuming **MuleSoft Agent Fabric** capabilities — governed model
access, governed tool access, and provisioning-as-code — from your own agent
framework, in your own IDE, without adopting Mule.

> **Project status — alpha, pre-release.** This is `v0.1.0.dev0`
> (`Development Status :: 3 - Alpha`). The **LLM data plane is live-verified**;
> most other surfaces are verification-gated — see
> [Status](#status-llm-data-plane-is-live-verified) below.
> **Not yet published to PyPI** — [install from source](#install).
> **Unofficial:** an independent project, **not** affiliated with or endorsed by
> Salesforce or MuleSoft.

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

## Status: LLM data plane is live-verified

This repository contains the **M0 scaffold + M1 foundation**:

- `core/` — config, auth, the single shared transport/header-injection client,
  the error taxonomy, telemetry, and a TTL cache. **Framework-free** (enforced
  by import-linter in CI).
- `llm/` — the framework-free OpenAI-compatible proxy client + model catalog.
- `integrations/` — native-object adapters for the eight frameworks.
- Structural modules for `registry/`, `tools/`, `provisioning/`, plus the
  `Governance` and `Publication` objects.

> **What is verified.** The **LLM data plane** (governed model access through the
> Omni Gateway proxy) is live-verified against a real Anypoint sandbox: the base
> URL shape (`https://<ingress>/<instance>/`, no `/v1`), the
> `client_id` + `client_secret` consumer-auth header pair, the attribution
> headers, and the four rejection shapes the proxy returns
> (auth `401`, PII `403`, token-budget `429`, upstream passthrough) — see
> [`docs/verified-apis.md`](docs/verified-apis.md) §2–§4. Both the framework-free
> client and the eight adapters are wired to that verified contract.
>
> **What is still blocked.** Per §0.3 / working-instruction #2, code paths that
> need an *unverified* endpoint, header, or framework class name raise
> `NotImplementedError("blocked on verification: …")` or a `ConfigError` rather
> than guessing. That currently includes the Exchange→MCP tool discovery join
> (`fabric.tools.discover`), the provisioning control-plane APIs, and the exact
> framework adapter class names / kwargs (§8). The worklist is
> [`docs/verified-apis.md`](docs/verified-apis.md).

## Install

> **Not yet published to PyPI.** Until the first release is cut, install from
> source:

```bash
git clone https://github.com/Agent-Fabric-SDK/agent-fabric-sdk.git
cd agent-fabric-sdk/python
pip install -e ".[llm,langgraph]"   # base + raw client + one framework
```

Once released, it will be installable directly (the line below is **planned —
not yet on PyPI**):

```bash
pip install "mulesoft-agent-fabric[llm,langgraph]"   # base + raw client + one framework
```

Optional extras (one per framework): `langgraph`, `adk`, `strands`,
`agent_framework`, `openai`, `anthropic`, `crewai`, `llamaindex`; plus `mcp`,
`a2a`, `otel`, `cli`, `local`, `all`.

## Configure

Governed model access needs three values, resolved from kwargs → env vars →
`.agent-fabric.toml` → default (§2.1). The proxy authenticates on a
`client_id` / `client_secret` **header pair** (consumer auth), *not* a bearer
token — this is separate from any Anypoint control-plane credential.

```bash
export MULESOFT_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # note: no /v1
export MULESOFT_LLM_PROXY_CLIENT_ID="<consumer client id>"
export MULESOFT_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"

# Optional attribution, surfaced on telemetry (§3)
export MULESOFT_APP_NAME="checkout-agent"
export MULESOFT_BUSINESS_GROUP="payments"
```

`Fabric.from_env()` reads these. Missing fields are reported **all at once** with
the env var names, not one-per-run (§2.1).

## What #1 gives you

Deliverable #1 wired the *live-verified* proxy contract into config, the shared
transport, the framework-free client, and all eight adapters. Concretely, you
can now point **any** of these at your governed Omni Gateway proxy and have the
SDK inject the verified `client_id`/`client_secret` headers, attribution, and the
retry policy for you:

### 1. Framework-free client (`fabric.llm.client()`) — verified

Returns a native `AsyncOpenAI` aimed at the proxy. Use the OpenAI SDK exactly as
you normally would; the SDK adds the governance headers.

```python
import asyncio
from agent_fabric import Fabric

async def main():
    async with Fabric.from_env() as fabric:
        client = fabric.llm.client()               # AsyncOpenAI at the proxy

        # Chat Completions
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Say hi in three words."}],
        )
        print(resp.choices[0].message.content)

        # …or the Responses API, streaming
        stream = await client.responses.create(
            model="gpt-4o", input="Stream a haiku.", stream=True,
        )
        async for event in stream:
            print(event)

asyncio.run(main())
```

Pass `sync=True` for the blocking `openai.OpenAI` instead. It is governed on
identical terms — same base URL, same verified header pair, same correlation ID
and retry policy — and needs no event loop:

```python
from agent_fabric import Fabric

with Fabric.from_env() as fabric:
    client = fabric.llm.client(sync=True)      # openai.OpenAI at the proxy
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Say hi in three words."}],
    )
    print(resp.choices[0].message.content)
```

The two forms are typed overloads, so the call site narrows to `OpenAI` or
`AsyncOpenAI` rather than a union and editors keep completing on the result. The
blocking transport takes no `AuthProvider` — that protocol is `async def` — which
costs nothing on the proxy (it authenticates on the header pair, not a fetched
token) but does keep the control-plane surfaces `registry` and `tools` async-only.

### 2. Native framework objects (§3.1) — one call per framework

Each adapter returns the **framework's own object**, not a wrapper, already
pointed at the proxy. Accessing an adapter whose extra is not installed raises
`ImportError` with the exact `pip install` command.

```python
async with Fabric.from_env() as fabric:
    # Tier 1
    fabric.langgraph.chat_model("gpt-4o", temperature=0.2)   # -> ChatOpenAI
    fabric.adk.model("gpt-4o")                               # -> google.adk LiteLlm
    fabric.strands.model("gpt-4o")                           # -> strands OpenAIModel
    fabric.agent_framework.chat_client("gpt-4o")             # -> Agent Framework chat client
    fabric.openai.model("gpt-4o")                            # -> OpenAI Agents SDK OpenAIChatCompletionsModel
    fabric.anthropic.client()                                # -> anthropic AsyncAnthropic
    fabric.crewai.llm("gpt-4o")                              # -> crewai LLM (LiteLLM-backed)

    # Tier 2
    fabric.llamaindex.llm("gpt-4o")                          # -> OpenAILike (is_chat_model=True)
```

Then hand that object to your framework as usual, e.g. LangGraph:

```python
from langgraph.prebuilt import create_react_agent

async with Fabric.from_env() as fabric:
    model = fabric.langgraph.chat_model("gpt-4o", temperature=0)
    agent = create_react_agent(model, tools=[])
    result = await agent.ainvoke({"messages": [("user", "hello")]})
```

> The proxy *contract* the adapters target is verified; the exact framework class
> names/kwargs are still being confirmed against installed versions (§8). Tier 1
> adapters raise a clear "blocked on verification" error rather than guess if a
> name cannot be resolved.

**Two more ways to get the same governed object**, if the `fabric.<framework>`
factory call isn't the shape you want. The factory returns a native object
already; these just move where the construction happens:

```python
# (a) Governed-kwargs accessor — you build the native object yourself. Same
#     values the factory uses; one source of truth for the proxy connection.
from langchain_openai import ChatOpenAI
model = ChatOpenAI(model="gpt-4o", temperature=0.2,
                   **fabric.langgraph.connection_kwargs())

# (b) Module-level factory — no `fabric.` prefix; a cached default Fabric is
#     built from the environment under the hood.
from agent_fabric.integrations.langgraph import chat_model
model = chat_model("gpt-4o", temperature=0.2)
```

Every adapter has both: `connection_kwargs()` returns that framework's governed
constructor kwargs (`base_url`/`api_base`/`client_args`/`async_client` as
appropriate), and each module exposes its primary factory at module level
(`adk.model`, `strands.model`, `llamaindex.llm`, `openai_agents.model`,
`anthropic.client`, `crewai.llm`, `agent_framework.chat_client`). Prefer the
`fabric.` factory when you want shared-client reuse and explicit lifecycle
(`async with Fabric(...)`); reach for these when you want full control of the
constructor or a shorter call site.

### 3. Governed error taxonomy — the proxy's rejections become typed exceptions

`classify()` maps the four live rejection shapes (§4) to typed exceptions so you
branch on governance outcomes instead of parsing bodies. The **raw**
`fabric.llm.client()` is the OpenAI SDK, so it raises `openai.APIStatusError` on
HTTP failures — apply `classify()` to `error.response` to bridge into the
taxonomy:

```python
import openai
from agent_fabric import PIIDetected, TokenBudgetExceeded, AuthError
from agent_fabric.core.errors import classify

try:
    resp = await client.chat.completions.create(model="gpt-4o", messages=msgs)
except openai.APIStatusError as e:
    governed = classify(e.response)          # -> a FabricError subclass
    if isinstance(governed, PIIDetected):
        print("blocked, entities:", governed.entities)
    elif isinstance(governed, TokenBudgetExceeded):
        print("slow down; retry after", governed.retry_after, "s")
    elif isinstance(governed, AuthError):
        print("bad credentials:", governed)
    else:                                    # policy / upstream / provider errors
        print(f"{type(governed).__name__}: {governed}")
```

The full taxonomy — `AuthError` (401), `PIIDetected` (403), `TokenBudgetExceeded`
(429), `PolicyViolation` (base for every governance rejection), and `FabricError`
(base of the whole tree) — is importable from `agent_fabric`.

### 4. Model handles without a `/models` endpoint

The governed proxy has **no** catalog endpoint (`GET /models` → `404`, verified
§2). Use `resolve()` for a heuristic capability handle from a known id:

```python
handle = fabric.llm.resolve("gpt-4o")
print(handle.capabilities)          # function_calling / vision / json_output
# fabric.llm.list_models(live=True) intentionally raises ConfigError explaining
# the proxy exposes no catalog — the SDK never fabricates a /models path.
```

## Language parity (§1.3)

Python ships for all eight frameworks. TypeScript is planned for four
(LangGraph.js, ADK TS, LlamaIndex.TS, Strands TS) plus the Vercel AI SDK and
OpenAI Agents SDK. **TS CrewAI / Anthropic SDK / Microsoft Agent Framework
are not promised** — those frameworks have no TS distribution.

## Framework tiers (§1.4)

- **Tier 1** (full, conformance-gated, blocking CI): LangGraph, Google ADK,
  Strands, Microsoft Agent Framework, OpenAI Agents SDK, Anthropic SDK, CrewAI.
- **Tier 2** (supported, non-blocking CI): LlamaIndex.

## Known adapter limitations

Published from the conformance kit's `KNOWN_LIMITATIONS` table (§8.1) — e.g. the
ADK adapter cannot propagate a per-run correlation ID because LiteLLM owns the
transport. Limitations are credibility, not embarrassment.

## Development

```bash
cd python
pip install -e ".[dev,llm,cli]"
pytest -q
mypy
lint-imports    # enforces the framework-free core rule (§1.1)
```
