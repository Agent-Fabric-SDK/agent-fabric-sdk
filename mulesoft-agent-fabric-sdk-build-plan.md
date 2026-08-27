# MuleSoft Agent Fabric SDK — Build Plan & Implementation Spec

**Audience:** an engineering agent (Claude Opus 4.8 / Sonnet 5) implementing the SDK, plus the human tech lead reviewing scope.
**Status:** design spec, pre-implementation.
**Date of research:** August 2026. All third-party framework APIs cited here were verified around this date and **must be re-verified before coding** (see §0.3).

---

## 0. Read this before writing any code

### 0.1 What this SDK is

A Python and TypeScript SDK that lets an agent developer, working in their own IDE and their own agent framework, consume three MuleSoft platform capabilities without adopting Mule:

1. **Governed model access** — the Omni Gateway LLM Proxy as a drop-in model provider for seven agent frameworks.
2. **Governed tool access** — Anypoint Exchange as a live registry, resolving to ready-to-bind MCP toolsets.
3. **Provisioning as code** — declarative MCP Bridge instances and policy bindings, applied from CI with plan/diff/apply semantics.

### 0.2 What this SDK is explicitly NOT

Do not build these. Each was considered and rejected for a stated reason.

| Not building | Why |
|---|---|
| A Python/TS runtime for Agent Broker orchestration | Agent networks compile to Mule apps on CloudHub 2.0; brokers are A2A servers. Reimplementing the guided-determinism graph engine is a competing product, not an SDK. |
| Authoring of gateway policy *logic* | Omni Gateway policies are Rust→WASM on Envoy via the PDK. Cannot be expressed in Python or TS. |
| An agent-network YAML/Agent Script generator | Schema is new and moving (Agent Network 2.0 / `.agent` files). The Anypoint CLI plugin and DX MCP Server already cover it. Wrap the CLI later if demanded. |
| A wrapper abstraction over the seven frameworks | Adapters return **native** framework objects. See §3.1. |
| Runtime policy application from application code | Inverts the platform-team ownership model. Provisioning is a CI-time concern. See §5.4. |

### 0.3 Mandatory verification step (do this first, before M0)

Several APIs referenced below are recent or move fast. **Do not code against my descriptions. Verify each, record the verified signature in `docs/verified-apis.md` with a date and source URL, and only then implement.**

Verify:

- **Anypoint OAuth token endpoint** — exact path, region host variants (US/EU/Canada/Japan Hyperforce), connected-app scope names needed for Exchange read, API Manager write, and policy management. Some operations require an *admin* connected app with user context rather than pure client credentials.
- **LLM Proxy endpoint shape** — base URL format, whether `/v1` is included, auth header name (bearer vs. custom), whether an SLA/consumer credential pair or a single API key is used, streaming support, and which OpenAI request fields pass through vs. get stripped.
- **Token attribution headers** — the exact header names the gateway reads for business-group and client-application attribution. These are the single most important unknown; without them the SDK's core value proposition (cost attribution per agent) does not work.
- **Policy rejection response shapes** — status codes and bodies returned when token rate limiting, prompt-injection protection, content safety, or PII detection blocks a request. Capture real responses as fixtures (§6.2).
- **MCP Bridge provisioning API** — whether API Manager exposes a documented REST endpoint for creating MCP Bridge instances, or whether it is UI/wizard-only with an internal endpoint. **This determines whether §5 is viable at all.** If UI-only, fall back to wrapping the Terraform provider (§5.5).
- **Terraform provider coverage** — `mulesoft/anypoint` v1.x reportedly covers MCP servers and AI agent resources. Enumerate exactly what it already does before duplicating it.
- **Framework APIs** — every constructor in §3.3. `agent-framework` (Python) in particular changed its top-level class name recently; the August 2026 docs show `from agent_framework import Agent` with a `client=` kwarg, not `ChatAgent`.

If any verification fails, **stop and report** rather than inventing an endpoint. A fabricated endpoint that returns 404 in a customer's sandbox destroys trust in the whole package.

### 0.4 Naming and legal

`MuleSoft`, `Anypoint`, `Omni Gateway`, and `Agent Fabric` are Salesforce trademarks. **"Agent Fabric" is a specific MuleSoft product name, not a generic term**, so the project name "MuleSoft Agent Fabric SDK" reads as a first-party SDK for that product. That is fine — desirable, even — if this ships with MuleSoft's endorsement or as a MuleSoft-owned project. If it does not, the name will be read as an official-status claim, which is a real trademark exposure and will also confuse users about who supports it.

Two workable paths:

1. **Endorsed.** Confirm with MuleSoft (see the week-1 conversation in §8) and use the name as-is.
2. **Unaffiliated.** Keep the descriptive form in the docs — "an SDK for MuleSoft Agent Fabric" — but ship under a distinct, org-scoped project name so the package itself does not read as first-party.

Working names in this document — `mulesoft-agent-fabric` (import `agent_fabric`) / `@yourorg/agent-fabric`, CLI `agent-fabric` — assume path 1. Under path 2, rename the distributions and keep the import name. Either way, put a support statement in the README stating exactly who maintains the project and what the support expectations are.

---

## 1. Architecture

### 1.1 Layer diagram

```
┌────────────────────────────────────────────────────────────────┐
│ integrations/  (one optional extra per framework)              │
│  langgraph · adk · autogen · agent_framework · semantic_kernel │
│  llamaindex · strands                                          │
│  — each returns NATIVE framework objects, never wrappers       │
└───────────────┬────────────────────────────────────────────────┘
                │
┌───────────────▼───────────────┬────────────────┬───────────────┐
│ llm/                          │ registry/      │ tools/        │
│ OpenAI-compatible client      │ Exchange       │ MCP session   │
│ factory + model catalog       │ discovery,     │ mgmt, tool    │
│                               │ typed assets   │ filtering     │
└───────────────┴───────────────┴────────────────┴───────────────┘
┌────────────────────────────────────────────────────────────────┐
│ core/  config · auth · transport · errors · telemetry · region  │
│        ZERO framework dependencies. httpx / fetch only.         │
└────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────┐
│ provisioning/ (separate entry point, CI-oriented)               │
│  declarative specs · plan/diff/apply · governance lint · CLI    │
└────────────────────────────────────────────────────────────────┘
```

**Hard rule:** `core` has no dependency on any agent framework. `integrations/*` may depend on exactly one framework each. Nothing in `integrations/` may be imported by `core`, `llm`, `registry`, or `tools`. Enforce with an import-linter rule in CI.

### 1.2 Repository layout

Monorepo, two publishable trees.

```
mulesoft-agent-fabric-sdk/
├── python/
│   ├── pyproject.toml                 # hatchling; optional extras per framework
│   ├── src/agent_fabric/
│   │   ├── __init__.py                # Fabric, FabricConfig, exceptions
│   │   ├── core/
│   │   │   ├── config.py              # FabricConfig, env resolution, regions
│   │   │   ├── auth.py                # AuthProvider protocol + AnypointConnectedApp
│   │   │   ├── transport.py           # shared httpx.AsyncClient factory, hooks
│   │   │   ├── errors.py              # exception taxonomy (§2.4)
│   │   │   ├── telemetry.py           # OTel spans, correlation IDs
│   │   │   └── cache.py               # TTL cache for tokens + registry lookups
│   │   ├── llm/
│   │   │   ├── client.py              # raw AsyncOpenAI-compatible client
│   │   │   └── catalog.py             # ModelHandle, list/resolve models
│   │   ├── registry/
│   │   │   ├── exchange.py            # search, get asset, resolve
│   │   │   └── models.py              # AssetRef, McpServerHandle, AgentHandle
│   │   ├── tools/
│   │   │   ├── session.py             # MCP streamable-HTTP session mgmt
│   │   │   └── filter.py             # allow/deny, tag + domain filtering
│   │   ├── integrations/
│   │   │   ├── langgraph.py
│   │   │   ├── adk.py
│   │   │   ├── autogen.py
│   │   │   ├── agent_framework.py
│   │   │   ├── semantic_kernel.py
│   │   │   ├── llamaindex.py
│   │   │   └── strands.py
│   │   └── provisioning/
│   │       ├── spec.py                # pydantic models for the YAML spec
│   │       ├── planner.py             # desired vs. actual → Plan
│   │       ├── applier.py
│   │       ├── lint.py                # governance ruleset preflight
│   │       └── cli.py                 # `agent-fabric` typer CLI
│   └── tests/
│       ├── unit/
│       ├── contract/                  # respx fixtures from real responses
│       ├── conformance/               # SAME suite run against every adapter
│       └── integration/               # docker-compose local-mode gateway
├── typescript/
│   ├── package.json                   # pnpm workspace root
│   └── packages/
│       ├── core/                      # @yourorg/agent-fabric-core
│       ├── langgraph/
│       ├── adk/
│       ├── llamaindex/
│       ├── strands/
│       └── cli/
├── examples/                          # one runnable example per framework
├── docs/
│   ├── verified-apis.md               # OUTPUT OF §0.3 — keep current
│   └── unsupported-boundary.md        # §7.3
└── .github/workflows/
```

### 1.3 Language parity — be honest about this

Of the seven requested frameworks, TypeScript equivalents exist for only some:

| Framework | Python | TypeScript |
|---|---|---|
| LangGraph | yes | yes (LangGraph.js) |
| Google ADK | yes | yes (`@google/adk`) |
| LlamaIndex | yes | yes (LlamaIndex.TS) |
| Strands | yes | yes (`@strands-agents/sdk`) |
| AutoGen | yes | no |
| Microsoft Agent Framework | yes | no (.NET, Python, Go) |
| Semantic Kernel | yes | no (.NET, Python, Java) |

**Ship Python for all seven. Ship TypeScript for four**, and add the Vercel AI SDK and OpenAI Agents SDK (JS) as the two TS-native targets that fill the gap. Do not promise TS AutoGen/SK/MAF in any README.

### 1.4 Framework tiering — also be honest

Microsoft's own documentation positions Agent Framework as the direct successor to both Semantic Kernel and AutoGen, built by the same teams, merging AutoGen's abstractions with Semantic Kernel's enterprise features. Three of the seven targets are Microsoft, and two of those are on a declared sunset path.

Plan accordingly:

- **Tier 1 (full support, conformance-gated, blocking CI):** LangGraph, Google ADK, Strands, Microsoft Agent Framework.
- **Tier 2 (supported, conformance-gated, non-blocking CI):** LlamaIndex.
- **Tier 3 (maintenance only, examples + smoke test, documented as legacy):** AutoGen, Semantic Kernel. Point users at the Microsoft migration guides in the docstrings.

This is a scope decision, not a technical one — raise it with the human lead before M1.

---

## 2. `core` — the foundation

### 2.1 Configuration

```python
# src/agent_fabric/core/config.py
from dataclasses import dataclass
from typing import Literal

Region = Literal["us", "eu", "ca", "jp"]

@dataclass(frozen=True)
class FabricConfig:
    # --- Anypoint control plane (registry + provisioning) ---
    client_id: str | None = None          # env: ANYPOINT_CLIENT_ID
    client_secret: str | None = None      # env: ANYPOINT_CLIENT_SECRET
    org_id: str | None = None             # env: ANYPOINT_ORG_ID
    environment: str = "Sandbox"          # env: ANYPOINT_ENV
    region: Region = "us"                 # env: ANYPOINT_REGION
    base_url: str | None = None           # override; else derived from region

    # --- LLM proxy (data plane) ---
    llm_proxy_url: str | None = None      # env: MULESOFT_LLM_PROXY_URL
    llm_proxy_key: str | None = None      # env: MULESOFT_LLM_PROXY_KEY

    # --- Attribution (see §0.3 for real header names) ---
    application_name: str | None = None   # env: MULESOFT_APP_NAME
    business_group: str | None = None     # env: MULESOFT_BUSINESS_GROUP

    # --- Behaviour ---
    timeout_s: float = 60.0
    max_retries: int = 3
    registry_cache_ttl_s: int = 300
    telemetry: bool = True

    @classmethod
    def from_env(cls) -> "FabricConfig": ...
    def validated(self) -> "FabricConfig":
        """Raise ConfigError listing every missing field at once, not one at a time."""
```

Resolution order: explicit kwarg → env var → `.agent-fabric.toml` in cwd or `$XDG_CONFIG_HOME` → default. Never read `.env` implicitly; document that the user calls `load_dotenv()` themselves.

`validated()` must report **all** missing fields in one error. A config error that surfaces one missing variable per run is the most common source of first-five-minutes abandonment.

### 2.2 Auth

```python
class AuthProvider(Protocol):
    async def token(self) -> str: ...
    async def invalidate(self) -> None: ...

class AnypointConnectedApp(AuthProvider):
    """OAuth2 client_credentials against the Anypoint token endpoint.

    Caches the token in memory with a 60s safety margin before expiry.
    On 401 from any downstream call, invalidate() then retry exactly once.
    """
```

Also implement `StaticToken` (for CI where a token is injected) and `ChainedAuth`. Keep the interface small so a customer can plug in their own vault.

**Verify (§0.3):** the token endpoint path, and which operations require an admin connected app with user context. Document per-operation scope requirements in a table in `docs/`.

The LLM proxy credential is **separate** from the control-plane credential and must not be conflated. A developer may legitimately have proxy access and no Exchange access.

### 2.3 Transport — the single place headers get injected

This is the most important piece of engineering in the SDK. Every framework has a different mechanism for setting request headers, and several have none. The solution is one shared HTTP client.

```python
def build_http_client(cfg: FabricConfig, auth: AuthProvider | None) -> httpx.AsyncClient:
    """Returns an httpx.AsyncClient with:
      - request event hook injecting:
          * correlation ID (uuid4 per logical agent run, propagated via contextvar)
          * attribution headers (application, business group)  [names: see §0.3]
          * bearer token, refreshed lazily
      - retry on 429/502/503/504 with exponential backoff + jitter,
        honouring Retry-After when present
      - NO retry on 4xx policy rejections (see §2.4) — those are terminal
      - timeout from config
    """
```

Every framework adapter that accepts a custom HTTP client **must** be given this one. For frameworks that only accept a `default_headers` dict, pass a snapshot and accept that the correlation ID will be per-client rather than per-run — document the degradation explicitly per adapter in §3.3.

Correlation ID lives in a `contextvar` so a single agent run's fan-out of model calls and tool calls share one trace ID end to end. Expose `with fabric.run_context(run_id=...)` for callers who want to supply their own.

### 2.4 Error taxonomy

Mapping gateway policy rejections to catchable, actionable exceptions is the SDK's clearest value over raw HTTP. Get the shape right even before the real status codes are verified.

```python
class FabricError(Exception):
    """Base. Carries correlation_id, request_id, raw response."""

class ConfigError(FabricError): ...
class AuthError(FabricError): ...            # 401/403 on control plane

class PolicyViolation(FabricError):
    """Base for gateway-enforced refusals. NEVER retried."""
    policy: str          # e.g. "token-rate-limit"
    remediation: str     # human-readable next step

class TokenBudgetExceeded(PolicyViolation): ...   # retry_after: float | None
class PromptInjectionBlocked(PolicyViolation): ...
class ContentSafetyBlocked(PolicyViolation): ...
class PIIDetected(PolicyViolation):
    entities: list[str]                            # if the gateway reports them

class UpstreamModelError(FabricError): ...   # provider-side failure, retryable
class ToolInvocationError(FabricError): ...
class RegistryError(FabricError): ...
class ProvisioningError(FabricError): ...
```

Two design points that matter:

1. **`PolicyViolation` must be distinguishable from a transient error at the framework boundary.** Most agent frameworks will retry or loop on an exception. A prompt-injection block that gets retried three times is three policy violations in the audit log and a confused developer. Every adapter must surface `PolicyViolation` in a way the host framework will not silently retry — for frameworks with middleware/hooks, install a hook that converts it to a terminal agent state.
2. **`remediation` is a required field.** "Token budget exceeded for business group `finance`; limit resets in 42m; request an increase in API Manager" is worth more than a stack trace.

The concrete mapping from HTTP response → exception class lives in one function, `errors.classify(response)`, driven by a table populated from real captured fixtures (§6.2). Do not hand-write guesses into the table.

### 2.5 Telemetry

OpenTelemetry, optional dependency, off by default in libraries and on by default in the CLI.

Spans: `fabric.llm.chat`, `fabric.registry.resolve`, `fabric.tool.call`, `fabric.provision.apply`. Attributes: model, proxy route, business group, application, token counts if the gateway returns them, policy decisions.

The point is that a developer can correlate their local trace with what the platform team sees in Omni Gateway's observability view via the shared correlation ID. Say so in the docs — it is a headline feature.

---

## 3. Pillar 1 — governed model access

### 3.1 The one design rule

**Adapters return native framework objects.**

```python
model = fabric.langgraph.chat_model("gpt-4o")   # -> a real ChatOpenAI instance
```

Not a `FabricChatModel` implementing `BaseChatModel`. Reasons:

- Zero surface area to maintain when the framework adds features.
- Users keep every existing framework capability (structured output, streaming, caching, callbacks) with no gaps.
- Reviewers can read the returned object and know exactly what it does.
- If the SDK is later abandoned, users' code degrades to three lines of manual configuration, not a rewrite.

The cost: no cross-framework portability of agent code. Accept it. Portability was never the ask.

### 3.2 Public surface

```python
from agent_fabric import Fabric

fabric = Fabric.from_env()                      # or Fabric(config=FabricConfig(...))

# Raw, framework-free
client = fabric.llm.client()                    # AsyncOpenAI pointed at the proxy
models = await fabric.llm.list_models()         # [ModelHandle(id, provider, ...)]

# Per framework (each an optional extra)
fabric.langgraph.chat_model("gpt-4o", temperature=0.2)
fabric.adk.model("gpt-4o")
fabric.autogen.model_client("gpt-4o")
fabric.agent_framework.chat_client("gpt-4o")
fabric.semantic_kernel.chat_completion("gpt-4o")
fabric.llamaindex.llm("gpt-4o")
fabric.strands.model("gpt-4o")
```

Accessing an adapter whose extra is not installed raises `ImportError` with the exact install command:
`pip install "mulesoft-agent-fabric[langgraph]"`. Implement via `__getattr__` on `Fabric` with a lazy import and a curated message. Do not let a bare `ModuleNotFoundError` escape.

Every adapter accepts `**kwargs` forwarded verbatim to the underlying constructor, so users are never blocked by the SDK lagging a framework feature.

### 3.3 Per-framework integration points

Verified around August 2026. **Re-verify each before implementing (§0.3)** and record in `docs/verified-apis.md`.

#### LangGraph / LangChain (Python + TS)

```python
from langchain_openai import ChatOpenAI

def chat_model(self, model: str, **kw) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        base_url=self._cfg.llm_proxy_url,
        api_key=self._cfg.llm_proxy_key,
        default_headers=self._attribution_headers(),
        http_async_client=self._http_client(),      # our client, our hooks
        max_retries=0,                              # we retry in transport
        **kw,
    )
```

Header injection: full (`default_headers` + custom http client). Best-case adapter.

#### Google ADK (Python + TS)

ADK is Gemini-first and reaches other providers through the `LiteLlm` wrapper (`google.adk.models.lite_llm.LiteLlm`), which takes LiteLLM-format model strings.

```python
from google.adk.models.lite_llm import LiteLlm

def model(self, model: str, **kw) -> LiteLlm:
    return LiteLlm(
        model=f"openai/{model}",          # LiteLLM's OpenAI-compatible route
        api_base=self._cfg.llm_proxy_url,
        api_key=self._cfg.llm_proxy_key,
        extra_headers=self._attribution_headers(),
        **kw,
    )
```

Header injection: via LiteLLM's `extra_headers`. **Cannot inject our httpx client** — LiteLLM owns the transport. Consequence: retries and correlation-ID-per-run degrade. Document this. Consider a LiteLLM custom logger callback to recover trace correlation.

ADK requires `litellm>=1.84`. Pin a floor, not a ceiling.

#### AutoGen (Python only; Tier 3)

```python
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.models import ModelInfo

def model_client(self, model: str, model_info: ModelInfo | None = None, **kw):
    return OpenAIChatCompletionClient(
        model=model,
        base_url=self._cfg.llm_proxy_url,
        api_key=self._cfg.llm_proxy_key,
        default_headers=self._attribution_headers(),
        model_info=model_info or self._infer_model_info(model),
        **kw,
    )
```

**Gotcha:** AutoGen requires an explicit `model_info` (vision/function-calling/JSON-output capability flags) for any model name it does not recognise. Since the proxy may expose arbitrary logical model names, `_infer_model_info` must derive capabilities from the registry's model catalog, with a conservative fallback (`function_calling=True, vision=False, json_output=False`) and a warning. Without this, AutoGen throws on construction and the adapter looks broken.

#### Microsoft Agent Framework (Python; .NET and Go out of scope for v1)

Current Python surface is `from agent_framework import Agent` with `Agent(client=<ChatClient>, name=..., instructions=...)`. The OpenAI-compatible chat client class name and its base-URL kwarg **must be verified** — this package is young and renamed classes recently.

```python
def chat_client(self, model: str, **kw):
    from agent_framework.openai import OpenAIChatClient   # VERIFY name/path
    return OpenAIChatClient(
        model_id=model,                                    # VERIFY kwarg
        base_url=self._cfg.llm_proxy_url,
        api_key=self._cfg.llm_proxy_key,
        default_headers=self._attribution_headers(),
        **kw,
    )
```

Agent Framework has first-class **middleware** for intercepting agent actions. Use it: ship `fabric.agent_framework.policy_middleware()` that catches `PolicyViolation` and terminates the run cleanly rather than letting the agent loop retry. This is the best policy-integration story of any of the seven — make it the flagship example.

#### Semantic Kernel (Python; Tier 3)

```python
from openai import AsyncOpenAI
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

def chat_completion(self, model: str, service_id: str = "mulesoft", **kw):
    return OpenAIChatCompletion(
        ai_model_id=model,
        service_id=service_id,
        async_client=AsyncOpenAI(
            base_url=self._cfg.llm_proxy_url,
            api_key=self._cfg.llm_proxy_key,
            default_headers=self._attribution_headers(),
            http_client=self._http_client(),
        ),
        **kw,
    )
```

Header injection: full, because we construct the `AsyncOpenAI` client ourselves. Prefer this pattern anywhere a framework accepts a pre-built OpenAI client.

#### LlamaIndex (Python + TS)

```python
from llama_index.llms.openai_like import OpenAILike

def llm(self, model: str, **kw) -> OpenAILike:
    return OpenAILike(
        model=model,
        api_base=self._cfg.llm_proxy_url,
        api_key=self._cfg.llm_proxy_key,
        is_chat_model=True,
        is_function_calling_model=True,
        default_headers=self._attribution_headers(),
        **kw,
    )
```

**Gotcha:** `OpenAILike` defaults `is_chat_model=False`, which silently routes to the completions endpoint and fails against a chat-only proxy. Always set it. This is the single most common LlamaIndex-with-a-gateway bug.

#### Strands Agents (Python + TS)

```python
from strands.models.openai import OpenAIModel

def model(self, model: str, **kw) -> OpenAIModel:
    return OpenAIModel(
        client_args={
            "base_url": self._cfg.llm_proxy_url,
            "api_key": self._cfg.llm_proxy_key,
            "default_headers": self._attribution_headers(),
            "http_client": self._http_client(),
        },
        model_id=model,
        **kw,
    )
```

`client_args` is forwarded to the underlying OpenAI client, so header and transport injection are both available. Strands also has lifecycle **hooks** (`BeforeToolCallEvent` and friends) — use them for the same policy-termination pattern as Agent Framework.

### 3.4 Model catalog

`fabric.llm.list_models()` returns logical model names the proxy exposes, not raw provider names. Prefer the proxy's own `/models` endpoint if it has one; fall back to the registry. Cache with the configured TTL.

`ModelHandle` should carry enough capability metadata to feed AutoGen's `model_info` and to let a developer branch on function-calling support. If the platform does not expose capability metadata, ship a small bundled JSON capability table keyed by well-known model IDs, clearly marked as a heuristic, and let users override it.

---

## 4. Pillar 2 — governed tool access (the differentiating feature)

This is the feature that makes someone install the package. Prioritise it accordingly.

### 4.1 Target developer experience

```python
tools = await fabric.tools.discover(domain="hr", tags=["approved"])
agent = create_react_agent(fabric.langgraph.chat_model("gpt-4o"), tools.langgraph())
```

Two lines from "our enterprise has a governed tool catalog" to "my LangGraph agent can use it." Everything in this section exists to make those two lines work.

### 4.2 Registry discovery

```python
class ExchangeRegistry:
    async def search(
        self, *, query: str | None = None, asset_types: list[AssetType] | None = None,
        tags: list[str] | None = None, domain: str | None = None,
        environment: str | None = None, limit: int = 50,
    ) -> list[AssetRef]: ...

    async def resolve_mcp(self, ref: AssetRef | str) -> McpServerHandle: ...
    async def resolve_agent(self, ref: AssetRef | str) -> AgentHandle: ...
```

`AssetRef` is `group_id/asset_id/version` plus name, type, tags, description, and the Exchange URL. Accept a shorthand string form (`"com.acme/vendor-shipment-mcp/1.0.0"`) everywhere a ref is taken.

`McpServerHandle` carries the consumer endpoint URL, transport type, auth requirements, and the tool descriptors if the registry exposes them without a live connection.

Caching: registry lookups are cached with `registry_cache_ttl_s`. Provide `fabric.registry.refresh()` and honour a `FABRIC_NO_CACHE=1` escape hatch.

**Pinning matters.** Resolving `latest` at agent startup means a platform-team asset change silently alters agent behaviour in production. Default to requiring an explicit version; allow `version="latest"` only with a logged warning. Ship `fabric.tools.lock()` which writes a `fabric.lock` file of resolved versions and digests, and `discover(locked=True)` which refuses to resolve anything not in the lockfile. Teams shipping agents to production will need this and nobody else provides it.

### 4.3 MCP session management

MCP servers created by MCP Bridge are gateway endpoints speaking streamable HTTP, protected by gateway policies. The session layer must handle:

- **Auth.** Client-credentials OAuth is the machine-to-machine case. Strands' `MCPClient` already builds streamable HTTP with a `client_credentials` grant internally; other frameworks need headers supplied. Provide `McpServerHandle.auth_headers()` returning a ready dict, refreshed on 401.
- **Connection lifecycle.** MCP clients are stateful and several frameworks connect lazily. Do not open connections in `discover()`. Return handles; connect on first tool use.
- **Multi-server aggregation.** `ToolSet` wraps N `McpServerHandle`s. Tool-name collisions across servers must be resolved by prefixing with the server's short name, and the mapping surfaced in `ToolSet.name_map` so a developer can debug why the model called `hr__get_employee`.
- **Filtering.** `ToolSet.filter(allow=[...], deny=[...], predicate=fn)`. Enterprise MCP servers can expose dozens of tools; handing 60 tool descriptors to a model degrades it and inflates token cost. Make filtering prominent in the docs, and log the descriptor token count at debug level.

### 4.4 Per-framework tool binding

| Framework | Binding |
|---|---|
| LangGraph | `langchain_mcp_adapters.client.MultiServerMCPClient({...}).get_tools()` — build the connection dict from handles, transport `"streamable_http"`, headers injected |
| Google ADK | `McpToolset(connection_params=StreamableHTTPConnectionParams(url=..., headers=...), tool_filter=[...])`; pass the toolset object straight into `LlmAgent(tools=[...])` |
| AutoGen | `autogen_ext.tools.mcp.mcp_server_tools(StreamableHttpServerParams(url=..., headers=...))` — **verify class name** |
| MS Agent Framework | its MCP client/tool class for streamable HTTP — **verify name**; docs reference hosted MCP tools and MCP clients for tool integration |
| Semantic Kernel | `MCPStreamableHttpPlugin` added to the `Kernel` — **verify** |
| LlamaIndex | `llama_index.tools.mcp.BasicMCPClient` + `McpToolSpec(...).to_tool_list_async()` |
| Strands | `MCPClient(lambda: streamablehttp_client(url, headers=...))`; implements `ToolProvider`, so it can be passed directly into `Agent(tools=[...])` with automatic lifecycle management |

Each returns the framework's native tool type. `ToolSet` exposes one method per installed integration:

```python
ts = await fabric.tools.discover(domain="hr")
ts.langgraph()          # -> list[BaseTool]
ts.adk()                # -> list[McpToolset]
ts.strands()            # -> list[MCPClient]
ts.llamaindex()         # -> list[FunctionTool]
# etc.
```

Note the shape difference: ADK and Strands want toolset/provider objects, LangGraph and LlamaIndex want flat tool lists. Do not force a uniform return type; match each framework's idiom and document the difference in the method docstring.

### 4.5 Agent handles (A2A)

Secondary but cheap. Agent Broker is an A2A server, and A2A-compliant agents in the registry can be consumed from Python. Ship `AgentHandle.as_tool()` which wraps a remote A2A agent as a callable tool in each framework, using the community `a2a-sdk` for protocol handling rather than implementing JSON-RPC yourself.

This is what lets a Python agent delegate to an Agent Broker without the developer learning A2A. Keep it in scope for M2 but behind a `[a2a]` extra.

---

## 5. Pillar 3 — provisioning as code

**Gate:** do not start M3 until §0.3 has confirmed a usable MCP Bridge provisioning API. If it is UI-only, jump to §5.5.

### 5.1 Spec format

A single declarative YAML file, versioned in the user's repo, validated by pydantic models.

```yaml
apiVersion: fabric/v1
kind: FabricSpec
metadata:
  name: hr-agent-tools
  environment: Sandbox
  businessGroup: 5a1b...

mcpBridges:
  - name: hr-tools
    gateway: managed-omni-eu-1
    apis:
      - assetId: employee-api
        version: 1.2.0
        upstream: https://internal.acme.com/employees
        tools:
          - name: get_employee
            method: GET
            resource: /employees/{id}
            description: Fetch an employee record by ID.
            inputSchema: auto        # derive from the OAS/RAML spec
          - name: search_employees
            method: GET
            resource: /employees
            description: Search employees by department or title.
            inputSchema:
              type: object
              properties:
                department: {type: string}
              required: [department]
    policies:
      - assetId: rate-limiting-sla-based
        version: 1.2.0
        config:
          rateLimits:
            - maximumRequests: 100
              timePeriodInMilliseconds: 60000
```

Design notes:

- **`inputSchema: auto`** derives the schema from the API's published spec in Exchange. This is the highest-leverage feature in the whole provisioning module — it is what makes bulk conversion of 200 APIs tractable. Implement it as a local OAS/RAML → JSON Schema transform so it can run offline in CI and produce a reviewable diff.
- **DataWeave is a hard boundary.** MCP Bridge's HTTP mapping uses DataWeave expressions for non-trivial parameter extraction. The spec must accept a raw `httpMapping.dataweave` string passthrough field and make no attempt to generate or parse DataWeave. Document this clearly as a limitation.
- **No secrets in the spec.** Reference them: `upstreamAuth: ${secret:anypoint-secrets-manager/hr-api-key}`. Resolve at apply time.

### 5.2 Plan / apply

```
$ agent-fabric plan -f fabric.yaml
  + mcpBridge  hr-tools                    (create)
  ~ mcpBridge  finance-tools               (update: +1 tool, ~1 description)
      + tool   list_invoices
      ~ tool   get_invoice   description changed
  - policy     rate-limiting-sla-based     on hr-tools (remove)

3 changes. Run `apply` to proceed.

$ agent-fabric apply -f fabric.yaml --auto-approve
```

Requirements:

- **Read-before-write, always.** Fetch current state, diff, render, then apply. Never blind-PUT.
- **Idempotent.** Re-running `apply` with no spec change produces zero API calls that mutate.
- **`--dry-run` and `--out plan.json`** for CI gating. The GitHub Action posts the plan as a PR comment; `apply` runs only on merge.
- **Partial-failure handling.** Apply resources in dependency order, stop on first failure, report exactly what was applied and what was not. Do not attempt automatic rollback — report state and let the operator re-plan. Silent partial rollback in a control plane is worse than a clear stop.
- **Drift detection.** `agent-fabric drift` compares live state against the spec and exits non-zero. Run it on a schedule; it catches console changes that bypass the pipeline.

### 5.3 Governance lint

Governance rulesets resolve locally with per-rule severities. Wire `agent-fabric lint` to validate API specs against project and centralized rulesets **before** anything is published, and fail the PR on `error` severity.

This is small, cheap, uncontroversial, and the fastest way to get a platform team to say yes to the SDK. Build it in M1 even though the rest of provisioning is M3.

### 5.4 Policy ownership — the political constraint

Applying policies from application code inverts the ownership model platform teams bought Omni Gateway for. Design so that:

- The **spec file lives in the repo** and is reviewable.
- **Apply runs in CI** under a connected app whose scopes the platform team controls.
- The SDK supports an **allow-list catalog**: `fabric.yaml` can reference only policy assets the platform team has approved, enumerated in a separate `policy-catalog.yaml` that the platform team owns in a different repo.

Ship the allow-list mechanism in v1 even if nobody asks for it. Its absence is what gets the SDK banned in a security review.

### 5.5 Fallback if there is no provisioning API

If §0.3 finds MCP Bridge is wizard-only:

1. Cut §5 from v1 entirely. Do not reverse-engineer internal endpoints — they will break, and doing so in an enterprise product is a support liability.
2. Keep §5.3 (lint), which needs no provisioning API.
3. Emit **Terraform** from the same `fabric.yaml` spec (`agent-fabric generate --target terraform`), and let the official provider do the applying. The `inputSchema: auto` derivation is still the valuable part, and it survives this pivot intact.

Option 3 is a genuinely good outcome. Do not treat it as a failure mode.

---

## 6. Testing

### 6.1 The adapter conformance kit — the most important test asset

One suite, defined once, executed identically against every framework adapter. Any new framework is "supported" only when it passes all of it.

```python
# tests/conformance/suite.py
CONFORMANCE_SCENARIOS = [
    "simple_completion",           # one turn, no tools, assert text returned
    "streaming_completion",        # tokens arrive incrementally
    "single_tool_call",            # model calls one MCP tool, result returned
    "multi_tool_multi_server",     # two servers, name collision resolved
    "tool_filtering",              # denied tool is absent from descriptors
    "policy_violation_terminal",   # gateway 4xx -> PolicyViolation, NOT retried
    "attribution_headers_present", # assert headers on every outbound request
    "correlation_id_propagated",   # same ID on model call and tool call
]
```

Parametrise over adapters with pytest. A framework that cannot satisfy `correlation_id_propagated` (likely ADK, via LiteLLM) records a documented, asserted exemption in a `KNOWN_LIMITATIONS` table rather than silently skipping. Publish that table in the README — it is credibility, not embarrassment.

### 6.2 Contract fixtures

Write a `scripts/probe.py` that runs against a real sandbox and records every response shape into `tests/contract/fixtures/`: token issuance, model list, a successful completion, a streaming completion, and one deliberately-triggered instance of each policy rejection. Redact secrets on write.

Unit and contract tests replay these with `respx` (Python) / `msw` (TS). **The `errors.classify` table is generated from these fixtures**, not from guesses. Re-run the probe monthly; a fixture diff is an early warning that the platform changed.

### 6.3 Integration

`docker-compose` bringing up Omni Gateway in Local Mode with declarative config, an upstream mock API, and an MCP Bridge-equivalent config. Not everything is testable locally — LLM Proxy and MCP Bridge are Connected Mode features — so integration coverage is partial by design. Mark clearly which tests need a real sandbox and gate them behind `FABRIC_SANDBOX_TESTS=1` so contributors without an org can still run the suite.

### 6.4 Nightly framework matrix

Seven frameworks, each releasing independently, several pre-1.0. Run the conformance suite nightly against the **latest** release of each framework in addition to the pinned version. Open an issue automatically on failure. Without this you find out a framework broke when a user reports it.

Pin floors, not ceilings, in `pyproject.toml`. Never `<` pin a framework — it forces users into dependency hell.

---

## 7. Delivery

### 7.1 Milestones

| Milestone | Scope | Est. (2 engineers) |
|---|---|---|
| **M0 — Verify** | §0.3 in full. `docs/verified-apis.md`. `scripts/probe.py` + captured fixtures. Go/no-go on §5. | 2 weeks |
| **M1 — Model access** | `core` complete. `llm` client + catalog. Adapters for Tier 1 (LangGraph, ADK, Strands, Agent Framework). Conformance kit. `lint` command. Docs site skeleton. **First public release, 0.1.0.** | 4 weeks |
| **M2 — Tool access** | `registry` + `tools` + `ToolSet`. Bindings for all seven. Lockfile. A2A agent handles. LlamaIndex, AutoGen, SK adapters. **0.2.0.** | 5 weeks |
| **M3 — TypeScript** | TS core + LangGraph.js, ADK TS, LlamaIndex.TS, Strands TS, Vercel AI SDK. Shared conformance scenarios ported. **0.3.0.** | 4 weeks |
| **M4 — Provisioning** | Spec, plan/apply/drift, `inputSchema: auto`, policy allow-list, GitHub Action. Or the Terraform-generation pivot. **0.4.0.** | 5 weeks |
| **M5 — Hardening** | Perf, telemetry polish, error-message pass, migration guide, examples for all seven, security review. **1.0.0.** | 3 weeks |

Roughly six months for two engineers. Ship M1 publicly rather than waiting — the LLM proxy adapters are useful alone, and early feedback will reorder M2–M4.

### 7.2 Definition of done, per adapter

1. Passes the full conformance kit, or has an asserted documented exemption.
2. A runnable example in `examples/<framework>/` that works against a sandbox with only env vars set.
3. A docs page with the manual equivalent — the three lines of code the adapter replaces. Users must be able to eject.
4. Listed in the nightly matrix.
5. Version floor declared, no ceiling.

### 7.3 The unsupported boundary

Maintain `docs/unsupported-boundary.md` listing every platform API the SDK calls, classified:

- **Documented and public** — safe.
- **Documented but no SLA for third-party use** — will break, we'll fix.
- **Undocumented** — should be empty. If anything lands here, it needs a written justification and an owner.

Link it from the README above the fold. Enterprise buyers will ask; having the answer pre-written converts a two-week procurement stall into a five-minute conversation.

---

## 8. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| MuleSoft ships a first-party Python/TS SDK | Medium-high | Existential | Talk to MuleSoft product in week 1 of M0. Ask for a written answer. Offer to be a design partner. |
| MCP Bridge has no provisioning API | Medium | M4 only | Pivot to Terraform generation (§5.5). M1–M3 unaffected. |
| Attribution header names not exposed | Low-medium | High — kills cost attribution | Surfaced in M0. If unavailable, escalate to MuleSoft; ship with correlation-ID-only telemetry and document the gap. |
| Framework churn breaks adapters | Certain | Medium | Nightly matrix (§6.4). Native-object design (§3.1) minimises blast radius. |
| Agent Framework absorbs SK and AutoGen users | High | Low | Already tiered (§1.4). |
| Anypoint API changes break control-plane calls | Medium | Medium | Contract fixtures + monthly probe re-run (§6.2). |
| Scope creep into agent-network authoring | High | High | It is in §0.2. Point at it in every scope discussion. |
| Security review rejects policy-from-code | Medium | High | Allow-list catalog + CI-only apply, shipped in v1 (§5.4). |

---

## 9. Working instructions for the implementing model

1. **Verify before you build.** §0.3 is not optional and not parallelisable with implementation. If a doc page contradicts this spec, the doc page wins — update this spec and note the change.
2. **Never invent an endpoint, header name, or class name.** If you cannot verify it, write the code path with an explicit `NotImplementedError("blocked on verification: <what>")` and report it. A stub that raises is honest; a guess that 404s is not.
3. **Generate from OpenAPI where a spec exists.** Hand-written HTTP clients drift. If MuleSoft publishes an OpenAPI document for a surface you need, generate the client and commit the generator config.
4. **Write `scripts/probe.py` before `errors.py`.** The error taxonomy must be derived from observed responses.
5. **Build the conformance kit before the second adapter.** Building it after three adapters means retrofitting three adapters.
6. **Keep `core` framework-free.** Add the import-linter CI rule on day one, not at M5.
7. **Every error message names the next action.** No bare exception types reaching users.
8. **Type everything.** `mypy --strict` on Python, `strict: true` on TS, both blocking in CI. This SDK's differentiator over the existing MCP-tool-based workflow is that it is typed and testable. Untyped code forfeits the entire premise.
9. **Optional extras are genuinely optional.** CI must include a job that installs only the base package and runs the base test suite, to catch accidental top-level framework imports.
10. **When a framework's idiom conflicts with SDK consistency, the framework wins.** Users came from the framework, not from us.
