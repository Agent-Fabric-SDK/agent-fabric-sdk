# Agent Fabric SDK — Build Plan & Implementation Spec

**Audience:** an engineering agent (Claude Opus 4.8 / Sonnet 5) implementing the SDK, plus the human tech lead reviewing scope.
**Status:** design spec, pre-implementation.
**Date of research:** August 2026. All third-party framework APIs cited here were verified around this date and **must be re-verified before coding** (see §0.3).

---

## 0. Read this before writing any code

### 0.1 What this SDK is

A Python and TypeScript SDK that lets an agent developer, working in their own IDE and their own agent framework, consume three MuleSoft platform capabilities without adopting Mule:

1. **Governed model access** — the Omni Gateway LLM Proxy as a drop-in model provider for eight agent frameworks.
2. **Governed tool access** — Anypoint Exchange as a live registry, resolving to ready-to-bind MCP toolsets.
3. **Provisioning as code** — declarative MCP Bridge instances and policy bindings, applied from CI with plan/diff/apply semantics.

### 0.2 What this SDK is explicitly NOT

Do not build these. Each was considered and rejected for a stated reason.

| Not building | Why |
|---|---|
| A Python/TS runtime for Agent Broker orchestration | Agent networks compile to Mule apps on CloudHub 2.0; brokers are A2A servers. Reimplementing the guided-determinism graph engine is a competing product, not an SDK. |
| Authoring of gateway policy *logic* | Omni Gateway policies are Rust→WASM on Envoy via the PDK. Cannot be expressed in Python or TS. §6.9 specifies a **contract** with companion custom policies and the SDK's client half of it — the policy logic itself lives in a separate repo, and no `.rs` file belongs in this one. |
| An agent-network YAML/Agent Script generator | Schema is new and moving (Agent Network 2.0 / `.agent` files). The Anypoint CLI plugin and DX MCP Server already cover it. Wrap the CLI later if demanded. |
| A wrapper abstraction over the eight frameworks | Adapters return **native** framework objects. See §3.1. |
| Runtime policy application from application code | Inverts the platform-team ownership model. Provisioning is a CI-time concern. See §5.4. |
| A central scanner that publishes to Exchange directly | Repository scanning **is** in scope (§7.10), but the scanner opens PRs; publication happens in each repo's own CI. A central publisher holding write scopes makes its operator the org's publisher of record. See §7.10.3. |

### 0.3 Mandatory verification step (do this first, before M0)

Several APIs referenced below are recent or move fast. **Do not code against my descriptions. Verify each, record the verified signature in `docs/verified-apis.md` with a date and source URL, and only then implement.**

Verify:

- **Anypoint OAuth token endpoint** — exact path, region host variants (US/EU/Canada/Japan Hyperforce), connected-app scope names needed for Exchange read, API Manager write, and policy management. Some operations require an *admin* connected app with user context rather than pure client credentials.
- **LLM Proxy endpoint shape** — base URL format, whether `/v1` is included, auth header name (bearer vs. custom), whether an SLA/consumer credential pair or a single API key is used, streaming support, and which OpenAI request fields pass through vs. get stripped.
- **Token attribution headers** — the exact header names the gateway reads for business-group and client-application attribution. These are the single most important unknown; without them the SDK's core value proposition (cost attribution per agent) does not work.
- **Policy rejection response shapes** — status codes and bodies returned when token rate limiting, prompt-injection protection, content safety, or PII detection blocks a request. Capture real responses as fixtures (§8.2).
- **MCP Bridge provisioning API** — whether API Manager exposes a documented REST endpoint for creating MCP Bridge instances, or whether it is UI/wizard-only with an internal endpoint. **This determines whether §5 is viable at all.** If UI-only, fall back to wrapping the Terraform provider (§5.5).
- **Terraform provider coverage** — `mulesoft/anypoint` v1.x reportedly covers MCP servers and AI agent resources. Enumerate exactly what it already does before duplicating it.
- **Framework APIs** — every constructor in §3.3. `agent-framework` (Python) in particular changed its top-level class name recently; the August 2026 docs show `from agent_framework import Agent` with a `client=` kwarg, not `ChatAgent`.

**Six further M0 items specific to governance and local mode are listed in §6.7, and six more for publication in §7.9. They gate §6 and §7 entirely — do all of them in the same pass.**

If any verification fails, **stop and report** rather than inventing an endpoint. A fabricated endpoint that returns 404 in a customer's sandbox destroys trust in the whole package.

### 0.4 Naming and legal

`MuleSoft`, `Anypoint`, `Omni Gateway`, and `Agent Fabric` are Salesforce trademarks. **"Agent Fabric" is a specific MuleSoft product name, not a generic term**, so the project name "Agent Fabric SDK" reads as a first-party SDK for that product. That is fine — desirable, even — if this ships with MuleSoft's endorsement or as a MuleSoft-owned project. If it does not, the name will be read as an official-status claim, which is a real trademark exposure and will also confuse users about who supports it.

Two workable paths:

1. **Endorsed.** Confirm with MuleSoft (see the week-1 conversation in §10) and use the name as-is.
2. **Unaffiliated.** Keep the descriptive form in the docs — "an SDK for Agent Fabric" — but ship under a distinct, org-scoped project name so the package itself does not read as first-party.

Working names in this document — `agent-fabric` (import `agent_fabric`) / `@yourorg/agent-fabric`, CLI `agent-fabric` — assume path 1. Under path 2, rename the distributions and keep the import name. Either way, put a support statement in the README stating exactly who maintains the project and what the support expectations are.

---

## 1. Architecture

### 1.1 Layer diagram

```
┌────────────────────────────────────────────────────────────────┐
│ integrations/  (one optional extra per framework)              │
│  langgraph · adk · strands · agent_framework · openai · crewai │
│  anthropic · llamaindex                                        │
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
agent-fabric-sdk/
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
│   │   │   ├── governance.py          # GovernanceCriteria, explain()
│   │   │   ├── publication.py         # Publication, AssetType, descriptors
│   │   │   └── introspect.py          # descriptor='auto' generation
│   │   │   └── models.py              # AssetRef, McpServerHandle, AgentHandle
│   │   ├── policies/                  # §6.10 — NOT core/; import-linter keeps it out
│   │   │   ├── base.py                # PolicyPlugin protocol, PolicyRef, RequestContext
│   │   │   ├── registry.py            # discovery, activation, ordering, collision checks
│   │   │   ├── attestation.py         # §6.9.2 client half: canonical JSON, HMAC, codec
│   │   │   └── builtin/               # plugins for the four §6.9 companion policies
│   │   ├── tools/
│   │   │   ├── session.py             # MCP streamable-HTTP session mgmt
│   │   │   └── filter.py             # allow/deny, tag + domain filtering
│   │   ├── integrations/
│   │   │   ├── langgraph.py
│   │   │   ├── adk.py
│   │   │   ├── strands.py
│   │   │   ├── agent_framework.py
│   │   │   ├── openai_agents.py     # fabric.openai — OpenAI Agents SDK
│   │   │   ├── anthropic.py
│   │   │   ├── crewai.py
│   │   │   └── llamaindex.py
│   │   └── provisioning/
│   │       ├── spec.py                # pydantic models for the YAML spec
│   │       ├── planner.py             # desired vs. actual → Plan
│   │       ├── applier.py
│   │       ├── lint.py                # governance ruleset preflight
│   │       ├── publish.py             # Exchange publication, digest, --if-changed
│   │       ├── policy.py              # `agent-fabric policy new|check` (§6.10.5)
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
│   └── unsupported-boundary.md        # §9.3
└── .github/workflows/
```

### 1.3 Language parity — be honest about this

Of the eight targeted frameworks, TypeScript equivalents exist for only some:

| Framework | Python | TypeScript |
|---|---|---|
| LangGraph | yes | yes (LangGraph.js) |
| Google ADK | yes | yes (`@google/adk`) |
| Strands | yes | yes (`@strands-agents/sdk`) |
| OpenAI Agents SDK | yes | yes (`@openai/agents`) |
| Anthropic SDK | yes | yes (`@anthropic-ai/sdk`) |
| LlamaIndex | yes | yes (LlamaIndex.TS) |
| CrewAI | yes | no |
| Microsoft Agent Framework | yes | no (.NET, Python, Go) |

**Ship Python for all eight. Ship TypeScript for six** — LangGraph, ADK, Strands, OpenAI Agents SDK, Anthropic SDK, LlamaIndex — and add the Vercel AI SDK as one further TS-native target. Do not promise TS CrewAI or Microsoft Agent Framework in any README.

### 1.4 Framework tiering — also be honest

The roster deliberately drops AutoGen and Semantic Kernel: Microsoft's own documentation positions Agent Framework as the direct successor to both — built by the same teams, merging AutoGen's abstractions with Semantic Kernel's enterprise features — so carrying all three would mean shipping two sunset-path adapters. Microsoft Agent Framework covers that lineage; CrewAI, the OpenAI Agents SDK, and the Anthropic SDK take the freed capacity.

Plan accordingly:

- **Tier 1 (full support, conformance-gated, blocking CI):** LangGraph, Google ADK, Strands, Microsoft Agent Framework, OpenAI Agents SDK, Anthropic SDK, CrewAI.
- **Tier 2 (supported, conformance-gated, non-blocking CI):** LlamaIndex.
- **Tier 3:** none. (AutoGen and Semantic Kernel are out of scope — see the note above.)

Two Tier 1 targets carry known constraints, tracked as documented conformance exemptions (§8.1) rather than as a lower tier: CrewAI reaches models through LiteLLM (like ADK), so per-run correlation degrades to per-client; and the Anthropic SDK depends on the proxy exposing an Anthropic-native Messages API route, which is an open M0 verification item (§0.3).

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
    llm_proxy_url: str | None = None      # env: AGENT_FABRIC_LLM_PROXY_URL
    llm_proxy_key: str | None = None      # env: AGENT_FABRIC_LLM_PROXY_KEY

    # --- Attribution (see §0.3 for real header names) ---
    application_name: str | None = None   # env: AGENT_FABRIC_APP_NAME
    business_group: str | None = None     # env: AGENT_FABRIC_BUSINESS_GROUP

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

The concrete mapping from HTTP response → exception class lives in one function, `errors.classify(response)`, driven by a table populated from real captured fixtures (§8.2). Do not hand-write guesses into the table.

`classify()` consults activated policy plugins (§6.10.3) before that table, so a custom policy can map its own rejection shape without an edit to `core/`. A plugin declines by returning `None`; it can never turn a rejection into a success (§6.10.4). With no plugins installed — the default, and a tested configuration — behaviour is exactly the fixture-driven table described above.

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
fabric.strands.model("gpt-4o")
fabric.agent_framework.chat_client("gpt-4o")
fabric.openai.model("gpt-4o")                   # OpenAI Agents SDK
fabric.anthropic.client()                       # AsyncAnthropic; model id is per-call
fabric.crewai.llm("gpt-4o")
fabric.llamaindex.llm("gpt-4o")
```

Accessing an adapter whose extra is not installed raises `ImportError` with the exact install command:
`pip install "agent-fabric[langgraph]"`. Implement via `__getattr__` on `Fabric` with a lazy import and a curated message. Do not let a bare `ModuleNotFoundError` escape.

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

#### CrewAI (Python; Tier 1)

CrewAI reaches models through its own `crewai.LLM` class, which wraps LiteLLM — so, as with ADK, an OpenAI-compatible proxy is addressed with the `openai/` model prefix.

```python
from crewai import LLM

def llm(self, model: str, **kw) -> LLM:
    return LLM(
        model=f"openai/{model}",          # LiteLLM's OpenAI-compatible route
        base_url=self._cfg.llm_proxy_url,
        api_key=self._cfg.llm_proxy_key,
        extra_headers=self._attribution_headers(),
        **kw,
    )
```

Header injection: via LiteLLM's `extra_headers`. **Cannot inject our httpx client** — LiteLLM owns the transport, exactly as with ADK. Consequence: retries and correlation-ID-per-run degrade to per-client. This is a documented, asserted conformance exemption (§8.1 `correlation_id_propagated`), shared with ADK.

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

Agent Framework has first-class **middleware** for intercepting agent actions. Use it: ship `fabric.agent_framework.policy_middleware()` that catches `PolicyViolation` and terminates the run cleanly rather than letting the agent loop retry. This is the best policy-integration story of any of the eight — make it the flagship example.

#### OpenAI Agents SDK (Python + TS; Tier 1)

The OpenAI Agents SDK (pip `openai-agents`, import `agents`) models a provider as an `OpenAIChatCompletionsModel` wrapping an `AsyncOpenAI` client. Because we construct that client ourselves, header AND transport injection are both available.

```python
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel

def model(self, model: str, **kw) -> OpenAIChatCompletionsModel:
    return OpenAIChatCompletionsModel(
        model=model,
        openai_client=AsyncOpenAI(
            base_url=self._cfg.llm_proxy_url,
            api_key=self._cfg.llm_proxy_key,
            default_headers=self._attribution_headers(),
            http_client=self._http_client(),
            max_retries=0,                # we retry in transport (§2.3)
        ),
        **kw,
    )
```

Header injection: full — the preferred pattern anywhere a framework accepts a pre-built OpenAI client. Pass the returned model into `agents.Agent(model=...)` and drive it with `Runner` per the SDK's own docs.

#### Anthropic SDK (Python + TS; Tier 1)

Returns a native `anthropic.AsyncAnthropic` client bound to the proxy. **Divergence, by design (§11.10 — the framework wins):** Anthropic's native surface is a *client*, and the model id is a per-call argument, so this adapter exposes `client()` rather than the `model(...)` factory the OpenAI-compatible adapters use.

```python
from anthropic import AsyncAnthropic

def client(self, **kw) -> AsyncAnthropic:
    return AsyncAnthropic(
        base_url=self._cfg.llm_proxy_url,   # UNVERIFIED route — see note below
        api_key=self._cfg.llm_proxy_key,
        default_headers=self._attribution_headers(),
        http_client=self._http_client(),
        max_retries=0,
        **kw,
    )
```

Header injection: full. **Open M0 dependency (§0.3):** the Omni Gateway LLM proxy is verified OpenAI-compatible; whether it also exposes an **Anthropic-native Messages API route** is unverified. If it does not, this adapter's requests will not reach a working upstream — so the SDK emits a one-time `UnverifiedValueWarning` on first use and keeps `base_url` overridable. Confirm the route in M0 before relying on this adapter.

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

`ModelHandle` should carry enough capability metadata to feed any framework that requires explicit capability flags and to let a developer branch on function-calling support. If the platform does not expose capability metadata, ship a small bundled JSON capability table keyed by well-known model IDs, clearly marked as a heuristic, and let users override it.

---

## 4. Pillar 2 — governed tool access (the differentiating feature)

This is the feature that makes someone install the package. Prioritise it accordingly.

### 4.1 Target developer experience

```python
tools = await fabric.tools.discover(domain="hr", tags=["approved"])
agent = create_react_agent(fabric.langgraph.chat_model("gpt-4o"), tools.langgraph())
```

Two lines from "our enterprise has a governed tool catalog" to "my LangGraph agent can use it." Everything in this section exists to make those two lines work.

Discovery is also the **filter and search** entry point. The same call narrows the catalog by name/description (glob), governance, domain, tags, and asset type, so an agent binds only the tools it needs rather than the entire catalog:

```python
# governed-only + name search: only governed tools whose name/description matches "*accounts*"
tools = await fabric.tools.discover(governed_only=True, search="*accounts*")

# full filter surface
tools = await fabric.tools.discover(
    search="*accounts*",           # glob over asset name + description; None = no text filter
    governed_only=True,            # True = default criteria; or a GovernanceCriteria (§6.1)
    domain="hr",
    tags=["approved"],
    asset_types=["mcp"],
    environment="Production",
    limit=50,
)
```

`fabric.tools.discover(...)` is the high-level facade over `ExchangeRegistry.search()` (§4.2). On the facade, `search` is the text/glob filter (maps to the registry's `query`) and `governed_only` is the governance predicate (maps to the registry's `governed`) — the facade uses the clearer names. **Verify (M0/M2):** whether Exchange supports a server-side wildcard/substring query, or the glob must be applied client-side after a coarse Exchange query — see §4.2.

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

`query` matches against asset **name and description** and must accept a glob (`*accounts*`, `get_*`). Apply it server-side if Exchange exposes a wildcard/substring search parameter; otherwise fetch the coarse candidate set (by `asset_types`/`tags`/`domain`) and filter the glob client-side. **Verify in M0** which path Exchange supports; either way the developer-facing `search=` behaviour is identical.

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
| MS Agent Framework | its MCP client/tool class for streamable HTTP — **verify name**; docs reference hosted MCP tools and MCP clients for tool integration |
| OpenAI Agents SDK | `agents.mcp.MCPServerStreamableHttp(params={"url": ..., "headers": ...})`; pass into `agents.Agent(mcp_servers=[...])` — **verify class name** |
| Anthropic SDK | streamable-HTTP MCP servers supplied via the SDK's `mcp_servers` tool integration — **verify name** |
| CrewAI | `crewai_tools.MCPServerAdapter(server_params)` yielding native CrewAI tools — **verify class name** |
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

A single declarative YAML file, versioned in the user's repo, validated by pydantic models. `Governance.export()` (§6.3) emits fragments of exactly this format — the two features share one schema, and that is deliberate. Do not let them diverge.

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

**A policy plugin (§6.10) is not an approval.** Installing and enabling a plugin teaches the SDK to speak a custom policy's wire contract — emit its headers, type its rejections, validate its config. It grants nothing. A policy absent from `policy-catalog.yaml` is still refused by `agent-fabric apply`, plugin or no plugin. Keep the two mechanisms in separate files with separate owners, and say so in the docs, because the first reviewer to mistake one for the other will conclude the allow-list is bypassable.

### 5.5 Fallback if there is no provisioning API

If §0.3 finds MCP Bridge is wizard-only:

1. Cut §5 from v1 entirely. Do not reverse-engineer internal endpoints — they will break, and doing so in an enterprise product is a support liability.
2. Keep §5.3 (lint), which needs no provisioning API.
3. Emit **Terraform** from the same `fabric.yaml` spec (`agent-fabric generate --target terraform`), and let the official provider do the applying. The `inputSchema: auto` derivation is still the valuable part, and it survives this pivot intact.

Option 3 is a genuinely good outcome. Do not treat it as a failure mode.

---

## 6. Governance profiles and environment targeting

Two requested capabilities live here: **governed-only discovery** (§6.1) and the **governance object** attached to agent and MCP-server construction (§6.2 onward). Both are worth building. The second needs one structural change and one corrected expectation before it is safe to implement — read §6.3 and §6.4 before writing code.

### 6.1 Governed-only discovery

#### 6.1.1 "Governed" is not a flag — it is a computed predicate

Exchange is a catalog. Publication to Exchange says nothing about whether an asset is fronted by a gateway, has policies applied, or passes the org's rulesets. There is no single boolean to query. "Governed" must be computed by joining state across three systems, and the join is environment-scoped: an asset governed in Production may be ungoverned in Sandbox.

```python
# src/agent_fabric/registry/governance.py
from dataclasses import dataclass, field

@dataclass(frozen=True)
class GovernanceCriteria:
    """Definition of 'governed'. Every field is a separate, independently
    checkable condition. Defaults are deliberately moderate; orgs override."""

    require_api_instance: bool = True        # an API Manager instance exists in this env
    require_deployed: bool = True            # the instance is deployed to a gateway, not just configured
    require_any_policy: bool = True          # at least one policy is applied
    required_policies: list[str] = field(default_factory=list)
                                             # asset IDs that MUST be present, e.g.
                                             # ["client-id-enforcement", "rate-limiting-sla-based"]
    forbidden_policies: list[str] = field(default_factory=list)
    require_governance_pass: bool = False    # passes org governance rulesets with no `error` findings
    require_gateways: list[str] = field(default_factory=list)
                                             # only assets behind these named gateways
    require_tags: list[str] = field(default_factory=list)
    require_lifecycle: list[str] = field(default_factory=list)
                                             # e.g. ["published", "approved"] if Exchange exposes lifecycle
    allow_unknown: bool = False              # if a check cannot be evaluated, does the asset pass?

STRICT = GovernanceCriteria(
    require_governance_pass=True,
    required_policies=["client-id-enforcement"],
    allow_unknown=False,
)
```

`allow_unknown` matters more than it looks. If the platform does not expose, say, ruleset results through an API, `require_governance_pass=True` with `allow_unknown=False` silently filters the entire catalog to zero results and the developer has no idea why. Every filtered-out asset must therefore carry a reason.

#### 6.1.2 API surface

```python
tools = await fabric.tools.discover(domain="hr", governed_only=True)               # default criteria
tools = await fabric.tools.discover(domain="hr", governed_only=STRICT)             # explicit criteria
tools = await fabric.tools.discover(search="*accounts*", governed_only=True)       # + name/desc glob
assets = await fabric.registry.search(query="*accounts*", asset_types=["mcp"], governed=True)

# Always available for debugging:
report = await fabric.registry.explain(ref, criteria=STRICT)
# GovernanceReport(governed=False, checks=[
#     Check("api_instance_exists", True,  "instance 19283 in Sandbox"),
#     Check("deployed",            True,  "gateway managed-omni-eu-1"),
#     Check("required_policies",   False, "missing: client-id-enforcement"),
#     Check("governance_pass",     None,  "UNKNOWN: rulesets API returned 403"),
# ])
```

`explain()` is not optional polish. Without it, `governed=True` returning an empty list is indistinguishable from a broken credential, and the SDK gets blamed. Make it a first-class documented method and reference it in the empty-result warning message.

**Default:** `governed_only` on the facade (and `governed` on `registry.search()`) defaults to `None` (no filtering) in v1, with a startup log line stating that discovery is unfiltered. Both accept `True` (default `GovernanceCriteria`) or an explicit `GovernanceCriteria` such as `STRICT`. Flipping the default to `True` is a breaking change for a later major version — consider it, but do not surprise people in a minor release.

#### 6.1.3 Implementation — avoid the N+1

Naive implementation queries API Manager once per Exchange asset. On a 500-asset catalog that is 500 sequential calls and a discovery step that takes minutes.

Correct approach:

1. One call to list **all** API Manager instances for `(org, environment)`. Build an in-memory index keyed by `(groupId, assetId, version)` — and also by `(groupId, assetId)` for version-agnostic matching, since instance version and asset version can diverge.
2. One call per instance-set to fetch applied policies, or a single bulk policies call if one exists. **Verify in M0** whether policies can be fetched in bulk; if not, fetch policies only for the candidate assets that survived steps 1 and the cheap Exchange-side filters.
3. Apply Exchange-side filters (tags, lifecycle, asset type) first, before any API Manager calls, to shrink the candidate set.
4. Cache the whole index under `registry_cache_ttl_s`, keyed by environment.

Expose `fabric.registry.warm(environment=...)` so a long-running agent process can build the index at startup rather than on first discovery.

**Verify in M0:** whether "deployed to a gateway" is readable per instance, and whether governance ruleset results are exposed through an API at all. If ruleset results are UI-only, ship `require_governance_pass` as permanently `UNKNOWN` and say so in the docstring rather than quietly dropping the field.

---

### 6.2 The governance object — what it is

```python
from agent_fabric import Governance, GatewayTarget, PolicyBinding

gov = Governance(
    name="hr-agent",
    gateway=GatewayTarget.from_env(),      # resolves local | sandbox | prod
    policies=[
        PolicyBinding("rate-limiting-sla-based", "1.4.0", config={
            "rateLimits": [{"maximumRequests": 100, "timePeriodInMilliseconds": 60000}],
        }),
        PolicyBinding("openai-token-policy", "1.0.0", config={
            "maxTokensPerMinute": 50_000,
        }),
        PolicyBinding("prompt-injection-protection", "1.0.0"),
    ],
)

model = fabric.langgraph.chat_model("gpt-4o", governance=gov)
tools = await fabric.tools.discover(domain="hr", governed=True, governance=gov)
```

`GatewayTarget` is the environment-varying part:

```python
@dataclass(frozen=True)
class GatewayTarget:
    mode: Literal["local", "managed", "self-managed"]
    base_url: str                    # http://localhost:8081 | https://<managed>.gw... | https://<own-host>
    environment: str | None = None   # None for local
    gateway_name: str | None = None  # control-plane gateway/registration name
    connected: bool = True           # local mode gateways are unconnected

    @classmethod
    def from_env(cls) -> "GatewayTarget":
        """FABRIC_TARGET=local|sandbox|production selects a profile from
        .agent-fabric.toml. Local requires no Anypoint credentials beyond
        whatever registration the local gateway itself needs (§6.4)."""
```

Profiles live in `.agent-fabric.toml`, committed to the repo:

```toml
[targets.local]
mode = "local"
base_url = "http://localhost:8081"

[targets.sandbox]
mode = "managed"
base_url = "https://hr-agent.sandbox.eu1.gw.mulesoft.com"
environment = "Sandbox"
gateway_name = "managed-omni-eu-1"

[targets.production]
mode = "self-managed"
base_url = "https://gw.internal.acme.com"
environment = "Production"
gateway_name = "prod-k8s-omni"
```

`PolicyBinding` takes any policy, stock or custom. When an activated plugin (§6.10) matches the `assetId`, construction additionally runs that plugin's `validate_config`, so a bad config fails on the laptop rather than at `agent-fabric apply`. With no matching plugin the binding is still valid — the SDK does not require a plugin to declare a policy, only to speak its wire contract.

This part of the request is sound and maps cleanly onto a pattern developers already know from Terraform workspaces and Kustomize overlays. Build it as specified.

---

### 6.3 Structural change: one object, three verbs — not one deploy

The request as stated is "set the governance object, then deploying it applies it locally / in sandbox / in prod." That is the right ergonomics and the wrong lifecycle, for the reason already established in §5.4: if application code applies policies to a shared gateway, the app team has taken the platform team's job, and the SDK gets rejected in security review.

The fix keeps the ergonomics. **The same `Governance` object supports three verbs with three different trust levels:**

| Verb | Target | Who runs it | What it does |
|---|---|---|---|
| `simulate()` | local | developer, laptop | Starts an ephemeral local Omni Gateway, applies the config, returns a live `base_url`. Nothing shared is touched. |
| `export()` | sandbox, prod | developer, laptop | Compiles the object into a `fabric.yaml` fragment (§5.1). Writes a file. Touches nothing. |
| `resolve()` | sandbox, prod | agent process, runtime | **Read-only.** Looks up the already-provisioned gateway route, verifies the expected policies are actually applied, returns the `base_url`. Raises `GovernanceDrift` if reality does not match the declaration. |

There is deliberately **no `apply()` on the runtime object.** Applying to sandbox and production goes through `agent-fabric apply` in CI, against the reviewed spec, under platform-controlled credentials, filtered by the allow-list catalog (§5.4). The path is:

```
agent code declares Governance
   → export()  → fabric.yaml   → PR review
   → CI: agent-fabric plan      → posted as PR comment
   → merge: agent-fabric apply  → gateway provisioned
   → runtime: resolve()         → verifies + returns URL
```

`resolve()` is the piece that makes this feel like the user's original request rather than a bureaucratic downgrade. The developer still writes one governance object; at runtime it *checks* rather than *mutates*, and a mismatch fails loudly at startup instead of silently running ungoverned. That verification is a genuinely better property than blind application, and it should be marketed as such.

**Escape hatch:** `Governance.apply(target, i_am_the_platform_team=True)` may exist for platform teams automating their own gateways. Make the kwarg name that explicit, require the connected app to hold write scopes it will not have by default, and log every use at WARNING.

---

### 6.4 Corrected expectation: local is not sandbox with a different URL

The request states the difference between local and sandbox/prod is the URL. **It is not, and building on that assumption will produce a local dev loop that passes and a sandbox deploy that fails.** Three material differences:

**1. Local Mode and Connected Mode are different feature sets.** Local Mode gateways are configured by declarative YAML files on disk and do not talk to the control plane. Anything control-plane-dependent is therefore unavailable locally. Verify the exact list in M0, but expect at minimum:

| Capability | Local Mode | Connected Mode |
|---|---|---|
| Routing, CORS, headers, TLS | yes | yes |
| Basic rate limiting / spike control | yes | yes |
| Custom WASM (PDK) policies | yes | yes |
| SLA-based rate limiting, client-ID enforcement, contracts | **no** (needs API Manager client apps) | yes |
| **LLM Proxy** | **probably not** — verify | yes |
| **MCP Bridge** | **probably not** — delivered as an API Manager guided experience | yes |
| Control-plane analytics, token usage reporting | no | yes |

If LLM Proxy and MCP Bridge are Connected-Mode-only, the local gateway **cannot** be a faithful stand-in for the two capabilities this SDK is mostly about. That is the single most important finding M0 must produce. Plan for it now:

- **If confirmed unavailable locally:** `simulate()` still validates routing, auth, rate limiting, custom policies and request/response shape — real value for the dev loop — but LLM traffic is served by a **local mock proxy** the SDK ships (an OpenAI-compatible stub that replays fixtures and simulates policy rejections from §8.2). Label it unambiguously in logs: `LOCAL SIMULATION — LLM proxy is mocked, not a real gateway`. Never let a developer believe they tested the real thing.
- **If available locally:** great, use it, and drop the mock to a fallback.

**A third option this section originally missed.** "Local Mode" and "runs on my laptop" are **orthogonal axes**, and conflating them is what produced the false dichotomy above. Omni Gateway is Flex Gateway (verified: API type `flexGateway`, v1.13.2), and a Flex Gateway can run **self-managed in Connected Mode anywhere a container runs** — including a developer's laptop and a CI runner — drawing its configuration from API Manager rather than from YAML on disk. In that topology the LLM Proxy policies, `client-id-enforcement`, SLA-based rate limiting and control-plane analytics are all **real**, because it is the same gateway binary and the same control plane as production. It costs an Anypoint org, a dev environment, and a per-run API instance. See §6.8 — it is the highest-fidelity local loop available, and it makes the "LLM Proxy is Connected-Mode-only" finding a cost question rather than a capability ceiling.

**2. Policies are not portable across modes.** Classify every policy in a shipped table:

```python
class PolicyPortability(Enum):
    BOTH = "both"
    CONNECTED_ONLY = "connected_only"
    LOCAL_ONLY = "local_only"
    UNKNOWN = "unknown"
```

`simulate()` must print, before it starts, exactly which declared policies are being skipped and why:

```
Starting local Omni Gateway (target: local)
  applied  cors                            1.0.0
  applied  rate-limiting                   1.3.0
  applied  acme-custom-redaction           0.2.0  (WASM)
  SKIPPED  rate-limiting-sla-based         1.4.0  connected-mode only (needs API Manager client apps)
  SKIPPED  prompt-injection-protection     1.0.0  connected-mode only
  ! 2 of 5 policies are not exercised locally. Local pass does not imply sandbox pass.
```

A silent skip here is the worst possible failure mode for this feature. Make the warning loud, non-suppressible by default, and repeated in the summary at teardown.

**3. Identity and secrets differ.** No connected app, no client credentials, no Secrets Manager locally. Ship a `LocalCredentialShim` that generates throwaway credentials and injects them into both the gateway config and the SDK client, so `${secret:...}` references in the spec resolve to dev values from a gitignored `.agent-fabric.local.toml`.

---

### 6.5 `simulate()` — the local harness

```python
async with gov.simulate() as env:                    # mode="local" by default
    model = fabric.langgraph.chat_model("gpt-4o", gateway=env.gateway)
    tools = await fabric.tools.discover(domain="hr", gateway=env.gateway)
    agent = create_react_agent(model, tools.langgraph())
    result = await agent.ainvoke({"messages": [("user", "…")]})
assert env.policy_events("rate-limiting").count == 1
```

`simulate()` takes a `mode` selecting one of three fidelity rungs — `"mock"`, `"local"`, `"connected"` — described in §6.8. The rest of this section covers the `"local"` rung: a Local Mode gateway from declarative YAML. **`env.fidelity` must always be queryable**, so a test that requires a real LLM proxy can assert it got one rather than silently passing against a mock.

Implementation:

1. Render the `Governance` object to Local Mode declarative YAML into a temp dir.
2. `docker compose up` the Omni Gateway image plus, if needed, the mock LLM proxy and any upstream mocks. Wait for readiness on the health endpoint with a bounded timeout and a clear error if the image cannot be pulled.
3. Yield an `Environment` exposing `gateway` (a `GatewayTarget` pointing at the mapped localhost port), `logs()`, and `policy_events(policy_name)` parsed from gateway logs so tests can assert a policy actually fired.
4. Tear down, unless `FABRIC_KEEP_LOCAL=1`.

Design constraints that matter:

- **Port allocation must be dynamic**, not hardcoded 8081, so parallel test workers do not collide.
- **Prefer config hot-reload over container restart** between test cases. Container startup measured in seconds is fine for a dev loop and unacceptable in a test matrix. Make the fixture session-scoped by default with per-test config reload.
- **Do not run this in unit tests.** Gate behind a pytest marker (`@pytest.mark.local_gateway`) that is off by default.
- **Verify licensing in M0.** Omni Gateway local mode likely requires a registration artifact obtained from the control plane. If so, contributors and CI runners without an Anypoint org cannot run `simulate()` at all — which changes it from "the default dev loop" to "an opt-in dev loop for licensed users," and the mock proxy becomes the primary local experience. This is a gating question for the feature's value, not a detail.

**Docker is a hard dependency for this feature only.** It must remain an optional extra (`[local]`) and the rest of the SDK must work without it.

---

### 6.6 MCP servers written in Python or TypeScript

Worth stating plainly, because the request implies it: if a developer writes an MCP server *in their agent framework* and attaches a governance object, the SDK can put a gateway in front of it locally, and can generate the gateway configuration for sandbox and production. **It cannot deploy the server itself to sandbox or production.** CloudHub 2.0 runs Mule applications; there is no MuleSoft-hosted runtime for a Python or TypeScript process.

So the honest split:

| | Local | Sandbox / Prod |
|---|---|---|
| The MCP server process | SDK runs it in docker-compose | **User's own platform** — K8s, Cloud Run, Lambda, ECS |
| The gateway in front of it | SDK spins up local Omni Gateway | SDK exports config; CI applies it |
| Upstream URL in the config | container DNS name | user-supplied, from their deployment |

To make the gap less painful, `agent-fabric export --with-runtime` may emit a Dockerfile and a plain Kubernetes manifest as a starting point. Frame it as a convenience, never as a deployment platform. Do not build a deployment orchestrator — that is a different product, and §0.2 exists to stop this kind of drift.

---

### 6.7 Verification checklist added to M0

Add to §0.3:

- Can Local Mode run the LLM Proxy? Can it run MCP Bridge? **(gating for §6.4/§6.5)**
- Does Local Mode require a control-plane-issued registration or licence artifact? Can CI run it?
- Which policies are Connected-Mode-only? Produce the portability table in §6.4 from real data, not inference.
- Is "deployed to gateway" readable per API instance via a documented API? **(gating for `require_deployed`)**
- Are governance ruleset results exposed via API? **(gating for `require_governance_pass`)**
- Can applied policies be fetched in bulk for an environment, or only per instance? **(determines whether §6.1.3 is fast or slow)**
- Can a Flex Gateway register in **Connected Mode from a laptop or a CI runner**, and what does the registration artifact contain? **(gating for §6.8 — the highest-fidelity local loop)**
- Can an API instance be created and destroyed per developer or per CI run cheaply, and does it count against a licensed instance quota? **(determines whether §6.8 is per-developer or one shared dev gateway)**

---

### 6.8 Local testing against a self-managed Connected Mode gateway

§6.4 and §6.5 assume a local gateway means a **Local Mode** gateway. That assumption produced a genuine gap, because *how a gateway is configured* and *where it runs* are independent:

| | Configured by local YAML (**Local Mode**) | Configured by the control plane (**Connected Mode**) |
|---|---|---|
| **Runs remotely** — private space, cloud, customer K8s | rare, but possible | `mode="managed"` / `mode="self-managed"` — what §6.2 already models |
| **Runs on a laptop or CI runner** | §6.5 `simulate()` | **this section — nothing covered it** |

The bottom-right cell is the important one. Omni Gateway is Flex Gateway, and a Flex Gateway container registered to the control plane in Connected Mode behaves identically wherever it runs: it fetches its API instances and policies from API Manager. Run that container on a laptop against a dedicated dev environment and the LLM Proxy policies (`llm-proxy-core`, `model-based-routing`, `openai-transcoding-policy`), `client-id-enforcement`, SLA-based rate limiting and token-usage analytics are **all real**.

**This changes the shape of the project's biggest governance risk.** §10 rates "Local Mode cannot run LLM Proxy or MCP Bridge" as Medium-high likelihood, High impact, with the outcome "`simulate()` becomes a mock, not a replica." A connected self-managed local gateway makes that a **cost** question rather than a **capability ceiling** — the capability exists locally; it just requires an org and a dev environment.

#### 6.8.1 The three-rung fidelity ladder

| Rung | Gateway | Config from | LLM Proxy | Connected-only policies | `resolve()` testable | Needs an org | Offline |
|---|---|---|---|---|---|---|---|
| `mock` | none — in-process stub | fixtures (§8.2) | mocked | none | no | no | yes |
| `local` | Flex Gateway container, Local Mode | declarative YAML | probably not — M0 | **no** | **no** — no control plane | no* | yes |
| `connected` | **Flex Gateway container, Connected Mode, self-managed** | **API Manager** | **real** | **real** | **yes** | yes + dev env | no |

\* subject to the §6.7 licence-artifact question.

```python
async with gov.simulate(mode="connected") as env:
    assert env.fidelity == "connected"        # never a silent downgrade
    model = fabric.langgraph.chat_model("gpt-4o", gateway=env.gateway)
    resp = await model.ainvoke("hello")

    # Only reachable on this rung: real policies, real drift detection, real usage.
    await gov.resolve(fabric)                          # exercises GovernanceDrift
    assert env.policy_events("llm-token-rate-limit").count == 0
    assert env.usage().total_tokens > 0                # real attribution data
```

**No new types are needed.** §6.2's `GatewayTarget` already expresses this: `mode="self-managed"`, `connected=True`, `base_url="http://localhost:8081"`. The `connected` flag was introduced to carry exactly this distinction. What is missing is the harness, the lifecycle management and the documentation — not the model.

#### 6.8.2 Two capabilities this unlocks that no other rung can

**`resolve()` becomes locally testable.** In Local Mode there is no control plane, so there are no API Manager instances, no applied-policy list, and `GovernanceDrift` detection (§6.3) cannot be exercised *at all* — not in a dev loop, not in CI, only against a shared sandbox. On the `connected` rung there are real instances with real applied policies, so `governance_resolve_drift` becomes a first-class local test.

**Attribution headers become verifiable.** The business-group attribution header name is the **single highest-priority M0 unknown** (§0.3) and it gates every governed call across all nine adapters. Verifying it requires a real gateway that actually reads the header and real analytics that report the attributed usage. A connected local gateway provides both, on a laptop, against a dev environment — which is a far tighter loop than probing a shared sandbox.

#### 6.8.3 Lifecycle is the hard part, not the container

Starting the container is easy. Not leaving debris in the control plane is not.

**Ephemeral API instances.** Each run needs an API instance in the dev environment. Fifty developers times several runs a day produces orphaned instances indefinitely. So: deterministic naming (`fabric-dev-<user>-<spec-digest>`), create-if-absent rather than create-always, teardown on exit **and on exception**, and a **TTL reaper** (`agent-fabric dev reap`) for instances leaked by a hard kill. Report what was reaped; never silently delete something a developer is using.

**A hard environment fence.** The harness creates and destroys control-plane objects, which is a mutation — legitimate here because it is a dev-loop concern rather than the runtime path (working instruction #11), but it must be fenced. Refuse to run against any environment not explicitly marked as a dev target in config, and refuse outright if the environment name resolves to production. A dev harness that can be pointed at production by a typo in an env var is a defect, not a feature.

**Two supported topologies**, because the right one depends on instance quota:

| | Per-developer gateway | One shared dev gateway |
|---|---|---|
| Control-plane objects | one gateway + instances per dev | one gateway, instances per dev |
| Isolation | full | policies collide; noisy neighbours |
| Registration | one artifact per dev | one shared artifact |
| Default when | quota is comfortable | quota is tight |

Default to per-developer; support shared for orgs where a registered gateway is a licensed, counted resource. The §6.7 quota question decides which is the documented default.

**Registration artifacts are credentials.** `flexctl registration create` produces a file containing secrets that let the holder register a gateway into the org. Treat it as such: gitignored, never logged, never baked into an image, generated per developer, and supplied to CI from secrets. `agent-fabric dev up` must refuse to proceed if it finds a registration artifact tracked by git.

**Real traffic costs real tokens.** Unlike `local` and `mock`, this rung sends real requests through the real proxy to a real model. Apply a token-budget policy in the dev environment **by default** rather than documenting the risk, default the harness to conservative `max_tokens`, and print cumulative spend at teardown. A dev loop that quietly consumes a production LLM budget will be switched off after the first invoice.

#### 6.8.4 Where each rung belongs

| Context | Rung | Why |
|---|---|---|
| Unit tests, OSS contributors, no org | `mock` | offline, no credentials, fast |
| Routing, CORS, custom WASM policies, request shape | `local` | real gateway, no control-plane cost |
| Policy behaviour, `resolve()`, attribution, usage | `connected` | the only rung where these are real |
| Pre-merge CI gate | `connected` | highest fidelity before a shared sandbox |
| Release gating | live sandbox | see §8.3 |

Keep `local` as the default for `simulate()`. `connected` is opt-in, because it requires credentials and spends money — but it should be the rung the docs recommend for anyone with an org, and the one CI uses on the main branch.

#### 6.8.5 Added to the M0 verification checklist

Both items are in §6.7. They decide whether §6.8 is per-developer or shared, and how CI obtains a registration.

### 6.9 Companion custom policies — the SDK-coupled contract

§0.2 excludes authoring gateway policy *logic* from this SDK, and that exclusion stands: Omni Gateway policies are Rust→WASM on Envoy via the PDK and cannot be expressed in Python or TypeScript. This section is not a reversal. It specifies the **contract** between the SDK and a small set of custom policies shipped from a **separate companion repository**, of which this SDK implements only the client half.

The reason to specify it here rather than leave it to the policy repo is that the contract is worth more to the SDK than to the gateway. Every stock policy verified in §4 keys on a single HTTP request — a credential, a body, a header. But an agent run is not one request. It is one model call, then a tool call, then six more model calls, then a delegation to another agent. The gateway sees fifteen unrelated requests from one `client_id` and cannot tell a converged run from a runaway loop, or a declared tool from an injected one.

There are exactly three facts the SDK knows that the gateway structurally cannot:

1. **Run shape.** The correlation-ID contextvar in `core/transport.py` (§2.3) already fans one logical run across every model and tool call. Step index, recursion depth, and the parent run in an A2A delegation chain exist only in the client.
2. **The declared toolset.** `ToolSet.filter(allow=, deny=)` (§4.3) runs in the developer's process. It is advisory. A prompt-injected agent can call any tool its credential reaches, and the gateway will allow it.
3. **Provenance.** Framework and version, SDK version, resolved model, lockfile digest (§4.2).

A custom policy that consumes any of those is, by construction, useless without the SDK — which is the property that makes this workstream worth funding. Nothing below can be reproduced with `curl`.

#### 6.9.1 Ownership boundary — read this before writing any Rust

| Artifact | Repo | Owner |
|---|---|---|
| Policy logic (Rust→WASM, PDK), policy Exchange assets | **companion repo**, e.g. `agent-fabric-policies` | platform / gateway team |
| Header emission, signing, error mapping, conformance scenarios | **this SDK** | SDK team |
| Applying a policy to an API instance | CI, from a reviewed spec (§5.4) | platform team |

Three rules follow, and none of them is negotiable:

- **No Rust in this repository.** If a PR to this repo adds a buildable Rust crate, it is in the wrong repo. The SDK's entire contribution is a signed header on the way out and a typed exception on the way back. The one permitted exception is the inert scaffolding templates behind `agent-fabric policy new` (§6.10.5), which are never compiled here.
- **The wire format is a published spec, not an implementation detail.** Version it in the header value itself (`x-agent-run: v1.…`) so the SDK and the policies release independently. Maintain a compatibility matrix in the companion repo; the SDK must tolerate a gateway running the previous major version.
- **§5.4 and working instruction #11 still apply.** These policies are applied by the platform team in CI. Nothing in the SDK's runtime path applies, mutates, or requests a policy. The SDK emits headers and reads decisions.

**Everything here is UNVERIFIED.** Not one row below has been confirmed against a real gateway, and §6.9.6 lists the PDK capability questions that decide whether the design is buildable at all. Per working instruction #2, no SDK code path ships against this contract until its row in `docs/verified-apis.md` is filled in.

#### 6.9.2 `agent-run-attestation` — the primitive; build this one first

A request-side policy requiring a signed run-context header, without which the request is rejected (or, in `observe` mode, annotated and passed).

```
x-agent-run: v1.<base64url(claims_json)>.<base64url(hmac_sha256)>

claims = {
  "run_id":        "0f9c…",      # the §2.3 correlation ID, verbatim
  "parent_run_id": "a41e…",      # A2A / broker delegation chain; null at the root
  "step":          7,            # 7th governed call in this run
  "depth":         2,            # 2 agents deep
  "agent_id":      "checkout-agent",
  "business_group": "payments",
  "framework":     "langgraph@0.2.74",
  "sdk_version":   "0.1.0",
  "toolset_digest": "sha256:…",  # §6.9.5; null when no tools are bound
  "iat": 1756800000, "exp": 1756800300, "nonce": "…"
}
```

**Sign with the `client_secret` the SDK already holds.** API Manager already knows that secret for the client application — `client-id-enforcement` 1.3.3 is verified live on the `openai-sdk` instance (§4) — so the policy can verify without any new key infrastructure, key rotation story, or JWKS endpoint. This is the single most important design decision in the section, and it is also the least certain: whether a PDK policy can read the contract secret for the authenticated client application is an open capability question (§6.9.6). If it cannot, fall back to a policy-configured shared signing key per business group, and accept the rotation burden.

Configuration surface:

```yaml
mode: observe | enforce          # start at observe, always
maxClockSkewSeconds: 60
maxTokenAgeSeconds: 300
replayWindowSeconds: 300         # nonce cache; see the shared-state question in §6.9.6
requireSignature: true           # false = accept unsigned claims, for the migration window
emitTracingLabels: true          # project run_id / agent_id / depth into tracing (§2.5)
```

What it buys, in order of value:

- **It closes the §3 blocker.** "Business-group attribution header name" has been UNVERIFIED since M0 and is rated High impact in §10 because it kills cost attribution. This makes it moot. Rather than waiting for MuleSoft to expose a header the gateway reads, you define the header, you sign it, and the policy reads it. Attribution becomes a contract you control instead of a platform unknown you are blocked on.
- **It makes every other policy in this section possible.** §6.9.3, §6.9.4 and §6.9.5 are all consumers of these claims. Build them in that order or not at all.
- **It gives `mode: enforce` as a real capability.** An instance with this policy is SDK-only by construction, which is a legitimate thing for a platform team to want and impossible to achieve with the stock policy set.
- **It joins the client trace to the gateway trace.** §2.5 promises a developer can correlate a local OTel trace with what the platform team sees. Today that rests on `X-Correlation-Id` surviving; `emitTracingLabels` makes it structural.

**Ship the free version first.** The stock `llm-token-rate-limit` policy takes a DataWeave `keySelector`, verified in §4 as `#[attributes.headers['client_id']]`. The moment the SDK emits a plain `x-agent-run-id` header, that becomes `#[attributes.headers['x-agent-run-id']]` and stock rate limiting is run-scoped with **zero custom code**. Do that in M1. The custom policy earns its keep only when you need signing, replay protection, and step/depth counting — do not let it block the 80% that is a one-line config change.

SDK side. Note the split: run *state* is core, because the correlation contextvar already is; the attestation *codec* is a plugin (§6.10), because `core/` must not know this policy exists.

- `policies/attestation.py` — canonical JSON serialisation (key order is part of the signature; get this wrong and every request fails verification), HMAC, and the header codec. Exposed as a `PolicyPlugin` whose `contribute_headers` emits `x-agent-run`.
- `core/telemetry.py` — `step` and `depth` counters on the run contextvar, incremented per governed call.
- `core/transport.py` — no policy-specific code at all. The header arrives through the plugin hook in `_apply_base_headers` (§6.10.3), which both `FabricAsyncClient` and `FabricClient` already call.
- `Fabric.run_context(run_id=…)` gains `parent_run_id=` so an A2A delegation continues the chain rather than starting a new one.

The plain `x-agent-run-id` header from the paragraph above is the exception: it is core, unconditional, and needs no plugin, because it is just the existing correlation ID under a second name that a `keySelector` can read.

#### 6.9.3 `agent-run-budget` — the runaway-loop killer

`client_id`-keyed token limiting is the wrong granularity for agents. One ReAct loop that will not converge exhausts the budget for every other agent sharing that credential, and the failure lands on whichever agent asks next — not on the one at fault. Keying on `run_id` from §6.9.2 contains the blast radius to the run that caused it.

```yaml
maxTokensPerRun: 50000
maxSteps: 40
maxDepth: 4                      # delegation depth; the A2A cycle guard
runTtlSeconds: 900
onExceeded: reject | truncate    # truncate = allow the in-flight call, block the next
```

`maxDepth` deserves its own mention: §4.5 wraps a remote A2A agent as a callable tool, so agent-calls-agent is a supported pattern, and there is currently nothing anywhere in the stack that stops A delegating to B delegating back to A. Client-side depth counting is defeated by the first participant that does not use the SDK. Gateway-side is not.

The rejection body is the other half of the value. Verified stock behaviour for a token-limit block is `429` with an **empty body**, no `retry-after`, and budget state smuggled into `x-token-reset` as milliseconds (§4). Against that, this policy returns:

```json
{"error": {"type": "run_budget_exceeded", "policy": "agent-run-budget",
           "run_id": "0f9c…", "consumed": 48213, "limit": 50000,
           "step": 41, "limit_kind": "maxSteps",
           "remediation": "Run exceeded 40 steps — likely a non-converging tool loop. Inspect the run trace before raising the limit."}}
```

`PolicyViolation.remediation` is a required field (§2.4) that the SDK currently has to synthesise, because the gateway says nothing. Here it comes from the policy, which is the only party that knows which limit tripped.

**Two hard parts, stated up front.** Token counts live in the response `usage` block, and on a streaming response they arrive only in the terminal SSE event — so accumulation means inspecting a stream without buffering it. And a cross-request counter needs state shared across gateway workers; if the PDK offers no shared store, per-worker approximation is the fallback and the configured limit becomes a soft ceiling that must be documented as such. Both are §6.9.6 questions. Scope this policy only after they are answered.

#### 6.9.4 `fabric-error-envelope` — normalise the rejection shapes

`errors.classify()` is a heuristic table because the gateway speaks four dialects, and §4 says so explicitly: *neither the status code nor the shape of the `error` value is a sufficient discriminator*. A flat `{"error": "…"}` for auth, a nested provider object passed through verbatim, a nested `{"type": "pii_detected"}` for PII that is a `403` but not an auth failure, and an empty body for `429`. The current implementation disambiguates on `www-authenticate` presence and error `type` strings, which works, and which will break the first time a policy is upgraded.

A response-side policy that rewrites **non-2xx responses only** into one versioned envelope collapses that table into a schema check:

```json
{"error": {"envelope": "fabric/v1", "type": "pii_detected", "policy": "llm-pii-detection-policy@1.0.0",
           "message": "…", "remediation": "…", "retry_after_s": 42,
           "correlation_id": "0f9c…", "run_id": "0f9c…",
           "details": {"entities": [{"pii_type": "Email", "start": 31, "end": 48}]},
           "doc_url": "https://…/errors/pii_detected"}}
```

**Make it content-negotiated.** Rewrite only when the request carried `x-fabric-accept-envelope: v1`. Any existing non-SDK consumer of that instance keeps byte-identical passthrough behaviour, so this can be applied to a live instance without a breaking-change review — and the good error experience is an SDK-exclusive property rather than a migration event for somebody else's integration.

Three constraints on the implementation:

- **Never touch a 2xx**, and never touch `text/event-stream`. Streaming is verified working (§2) and a response-rewriting policy is exactly the sort of thing that breaks it.
- **Preserve the original status code.** The envelope changes the body, not the semantics.
- **`details` is open.** The envelope's contract is the outer keys; per-policy payloads go in `details` so a new policy does not require a new envelope version.

Payoff for the SDK: `classify()` becomes "parse the envelope if present, else fall back to today's heuristic table." The fallback stays forever — the SDK must work against an instance with no companion policies — but it stops being the primary path, and a new gateway policy stops being a fixture-capture exercise.

#### 6.9.5 `toolset-contract` — the one with real differentiation

This policy sits on the **MCP ingress** (`https://…/mcp/<name>/`, verified §6), not the LLM proxy, and it is the strongest of the four because it closes a security gap rather than a DX gap.

Today, tool filtering is client-side and therefore advisory. §4.3 recommends filtering to keep descriptor counts down, which is a token-cost argument, not a security one — and the security consequence is not written down anywhere: a prompt-injected agent can invoke any tool its credential can reach, because the gateway has never been told which tools the agent declared.

The policy takes `toolset_digest` from the signed claims (§6.9.2), resolves it against the manifest published to Exchange, and enforces two things:

1. the invoked tool name is in the declared set, and
2. its arguments validate against the published `inputSchema`.

The digest infrastructure already exists. §7.3 derives descriptors from code, §7.5 computes a content digest for `--if-changed`, and the conformance kit already asserts `descriptor_auto_stable` — two introspections of one server produce an identical digest. This policy is largely a consumer of work the plan has already committed to.

It is unforgeable without the SDK because the SDK is what computes the digest at publication time and signs it at call time. That is the cleanest example in this section of the property being asked for.

**Stretch, and the reason to call any of this a fabric:** have the LLM proxy return a short-lived, run-scoped capability token on a successful completion, and have the MCP ingress require it. Governed tools then become callable only from inside a governed model run — a tool call with a valid credential but no active run is rejected. No hand-rolled client can do this, because it requires carrying state from an LLM response header into an MCP session, which is precisely what `core/transport.py` and `McpServerHandle` already are. Treat it as a design spike, not a deliverable: it couples the two data planes, and if the coupling is wrong it fails closed on every tool call in production.

#### 6.9.6 Cross-cutting rules

**Policy ordering is part of the contract.** Attestation must run before anything reading run claims, and the error envelope must sit outermost so it catches rejections from every policy including attestation itself. Record the required order in the companion repo and assert it in `Governance.resolve()` (§6.3) — a correct set of policies in the wrong order is drift, and `GovernanceDrift` should say so.

**Every policy ships `observe | enforce`, and defaults to `observe`.** Roll out in observe, read the analytics, then enforce. A policy that hard-requires an SDK header on day one breaks whatever is already calling that instance, and the rollback is a control-plane change under someone else's change window.

**Fail closed, but only in the direction that is safe.** A missing or invalid attestation in `enforce` mode is a rejection. A missing *optional* claim is not — `toolset_digest` is null for an agent with no tools bound, and that must stay a normal request rather than a policy incident.

**LiteLLM degrades this, as it degrades everything.** ADK and CrewAI cannot be handed the SDK's httpx client, so their correlation ID is per-client rather than per-run — already a documented, asserted conformance exemption (§8.1 `correlation_id_propagated`, §10). Under attestation, those two adapters still authenticate and still attribute per client application, but `step` and `depth` are not trustworthy, which means §6.9.3's `maxSteps` and `maxDepth` cannot be enforced for them. Decide explicitly whether that is an exemption or a hard blocker for enforcement on an instance those frameworks call. Do not discover it during a rollout.

**This is the rare governance feature that is fully testable locally.** The §6.4 portability table says custom WASM (PDK) policies work in **both** Local and Connected Mode — unlike `client-id-enforcement`, SLA rate limiting, or the LLM proxy itself. So these four are exercisable on the `local` rung of `simulate()` (§6.5, §6.8): a real gateway, real policy enforcement, no control-plane cost, no shared sandbox, no org required. `attribution_headers_present` and `correlation_id_propagated` stop being assertions against a mock and become assertions against a gateway that actually rejects. That is a stronger dev loop than anything else in §6 offers, and it is an argument for building §6.9.2 earlier than its business value alone would justify.

#### 6.9.7 Added to the M0 verification checklist

None of this is buildable until the PDK's actual capabilities are known. Each row gates a specific design decision above; add them to `docs/verified-apis.md` and answer them before any Rust is written.

| Question | Gates | If the answer is no |
|---|---|---|
| Can a PDK policy read the contract `client_secret` for the authenticated client application? | §6.9.2 signing key | Per-BG configured shared key; own the rotation story |
| Does the PDK expose state shared across gateway workers (counters, nonce cache)? | §6.9.2 replay window, §6.9.3 budgets | Per-worker approximation; document limits as soft ceilings |
| Can a policy inspect a streaming (SSE) response body without buffering it? | §6.9.3 token accumulation | Budget enforcement is non-streaming-only; say so loudly |
| Can a policy rewrite a response body conditionally on a request header? | §6.9.4 content negotiation | Envelope becomes instance-wide and therefore a breaking change |
| Can a policy make an outbound call (Exchange manifest lookup), and with what latency budget? | §6.9.5 digest resolution | Ship the manifest in policy config; accept staleness |
| Is policy execution order controllable and readable per API instance? | §6.9.6 ordering, drift detection | Order becomes convention, unassertable by `resolve()` |
| Do custom WASM policies genuinely run in Local Mode as §6.4 claims? | the entire local dev-loop argument | Falls back to the `connected` rung; needs an org |

### 6.10 `PolicyPlugin` — the interface custom policies implement

§6.9 specifies four policies. This section specifies the **interface** they implement, and the reason it exists is that the SDK must not know about those four.

Custom policies already exist in the wild. §6.4's own `simulate()` output shows `acme-custom-redaction 0.2.0 (WASM)` sitting alongside the stock set — a customer policy this project will never see. If the SDK hard-codes §6.9's four into `transport.py` and `errors.py`, then every customer with their own PDK policy is locked out of header emission, typed rejections, drift verification, and local simulation, and the four become a permanent maintenance tax on `core/`. One extension point costs less than four special cases and serves an unbounded set.

#### 6.10.1 The protocol

A plugin teaches the SDK three things about one policy: what to send, how to read its rejection, and how to declare it. Every method is optional — a plugin that only classifies errors is a legitimate plugin.

```python
# src/agent_fabric/policies/base.py — framework-free (§1.1)

@dataclass(frozen=True)
class PolicyRef:
    asset_id: str                       # Exchange assetId, e.g. "agent-run-attestation"
    versions: str                       # range this plugin speaks, e.g. ">=1.0,<2.0"
    group_id: str | None = None         # None = the stock-policy org

Surface = Literal["llm", "mcp", "a2a", "control_plane"]

@dataclass(frozen=True)
class RequestContext:
    cfg: FabricConfig
    run: RunContext                     # run_id, parent_run_id, step, depth (§6.9.2)
    surface: Surface

class PolicyPlugin(Protocol):
    ref: PolicyRef
    surfaces: frozenset[Surface]        # where this policy applies; nothing else calls it
    portability: Literal["both", "connected_only"]   # feeds the §6.4 table

    def contribute_headers(self, ctx: RequestContext) -> Mapping[str, str]:
        """Request headers this policy needs. Called per request, on the hot path —
        keep it pure, synchronous, and allocation-light. MUST NOT do I/O."""

    def classify(self, response: httpx.Response) -> FabricError | None:
        """This policy's rejection -> a typed exception, or None for 'not mine'.
        None is the ONLY way to decline. A plugin cannot turn a rejection into a
        success (§6.10.4)."""

    def validate_config(self, config: Mapping[str, object]) -> None:
        """Raise ConfigError on an invalid PolicyBinding config, at construction
        time rather than at apply time. Also drives `agent-fabric lint` (§5.3)."""

    def export_fragment(self, binding: PolicyBinding) -> Mapping[str, object]:
        """The `policies[]` entry this binding compiles to in fabric.yaml
        (§5.1), used by Governance.export() (§6.3)."""

    def simulate_fragment(self, binding: PolicyBinding) -> Mapping[str, object] | None:
        """Declarative Local Mode config, or None meaning connected-only — which
        is what puts the policy in simulate()'s non-suppressible SKIPPED report
        (§6.4). Returning a fragment for a connected-only policy is a bug that
        makes a developer trust a green local run."""
```

`PolicyBinding` is unchanged from §6.2. What changes is that constructing one now looks for a plugin matching its `assetId` and calls `validate_config`, so a typo in a policy config fails on the developer's laptop instead of in the CI apply step.

#### 6.10.2 Discovery is automatic; activation is not

Plugins are found through the `agent_fabric.policies` entry-point group, so a companion package registers itself by being installed and this SDK never depends on it.

**Discovery does not imply activation.** Auto-loading an installed package that can inject headers into every governed request and intercept error classification is a supply-chain hole, and this plan is already careful about exactly that class of risk in §7.10.3. So a discovered plugin is inert until it is named:

```toml
# .agent-fabric.toml — committed, reviewable
[policies]
enabled = ["agent-run-attestation", "acme-pii-redaction"]
```

Also accept `Fabric(policies=[...])` for programmatic use and tests. Discovered-but-not-enabled plugins are logged once at INFO with the line needed to enable them — discoverable, not silent, not automatic.

Three determinism rules, all enforced at `Fabric` construction and never at request time:

- **Ordering is explicit.** Plugins run in the order listed in `enabled`. Never rely on entry-point iteration order.
- **Header collisions are fatal.** A plugin may not write a header another plugin or the core set (§2.3) already writes. Raise `ConfigError` naming both plugins at startup. Silent last-writer-wins on an attribution header is a bug nobody will find.
- **Version mismatch is fatal.** If a plugin's `ref.versions` does not cover the version `resolve()` reports as applied on the gateway, that is `GovernanceDrift` (§6.3), not a warning. A v1 client signing for a v2 policy fails every request; better to fail at startup with the reason.

#### 6.10.3 Where the SDK calls it

Five hooks, five existing call sites. No new machinery.

| Hook | Call site | Notes |
|---|---|---|
| `contribute_headers` | `_apply_base_headers`, both transports (§2.3) | After core headers; collision-checked at startup, not here |
| `classify` | `errors.classify()` (§2.4) | Plugins first, in order; built-in table is the fallback |
| `validate_config` | `PolicyBinding.__init__`, `agent-fabric lint` (§5.3) | Fails on the laptop, not in CI |
| `export_fragment` | `Governance.export()` (§6.3) | Compiles to the §5.1 spec format |
| `simulate_fragment` | `Governance.simulate()` (§6.5) | `None` → the §6.4 SKIPPED report |

`classify()` inverting to plugins-first is the one behavioural change to shipped code, and it is what §6.9.4 needs: the envelope parser is just a plugin that returns `None` when the response carries no envelope, leaving today's verified heuristic table (§4) untouched as the fallback. Both paths keep working, forever, on an instance with no companion policies at all.

#### 6.10.4 A plugin must not be able to break a governed call

This is the part to get right, because a governance SDK whose extension point can silently disable governance is worse than one with no extension point.

- **A plugin cannot suppress a rejection.** `classify` returning `None` means "not mine" and falls through. There is no return value meaning "treat this 403 as success". If a plugin raises, log it and fall through to the built-in table — never swallow the response.
- **A plugin cannot make a call ungoverned.** `contribute_headers` adds; it cannot remove or overwrite core headers. The core set in §2.3 is written last and wins by construction.
- **No I/O on the request path.** `contribute_headers` is synchronous and pure. A plugin needing remote data fetches it at construction and caches it; the alternative is a policy plugin adding a network round-trip to every model call.
- **Failure is loud and early.** Every validation above happens at `Fabric` construction. Nothing about plugin resolution may fail for the first time on request number four hundred.
- **Zero plugins is a supported, tested configuration.** The base test job (working instruction #9) runs with none installed.

**A plugin is not an approval.** §5.4's allow-list catalog is what says a policy may be applied to a shared gateway, and it is owned by the platform team in a different repo. Installing a plugin only teaches the SDK to *speak* to a policy; if the policy is not in the allow-list, `agent-fabric apply` still refuses. Keep those two mechanisms visibly separate — conflating them hands the app team the platform team's job, which is precisely the failure §5.4 exists to prevent.

#### 6.10.5 `agent-fabric policy` — scaffolding, not authoring

The interface above creates a synchronisation problem: a custom policy now has three artifacts that must agree — the PDK config schema on the gateway, the plugin's `validate_config`, and the `fabric.yaml` fragment. Hand-maintaining three copies of one schema guarantees drift.

```
$ agent-fabric policy new acme-pii-redaction --surface llm
  created  policies/acme-pii-redaction/policy.yaml       # one declaration: config schema + metadata
  created  policies/acme-pii-redaction/plugin.py         # PolicyPlugin stub, schema generated
  created  policies/acme-pii-redaction/test_plugin.py    # the §8.1 plugin scenarios, parametrised
  created  policies/acme-pii-redaction/pdk/              # PDK project skeleton + generated JSON schema
  next     implement the Rust handler in pdk/src/lib.rs — the SDK does not generate policy logic (§0.2)
```

One declaration, three generated artifacts, and the last line of output states the boundary. **This does not author policy logic** — §0.2 stands, the Rust handler body is written by a human. What is generated is the schema in three representations and the client-side plumbing, which is exactly the mechanical part.

The scaffold lands in the **user's** working directory, which is where the §6.9.1 "no Rust in this repository" rule and a generator that emits a `pdk/` skeleton stop contradicting each other: this repo ships the generator and its templates, never a compiled policy. A team may keep the generated `pdk/` beside their plugin or move it to a dedicated policy repo; `policy check` works either way, because it reads the deployed schema from the control plane rather than from the neighbouring directory.

```
$ agent-fabric policy check --target sandbox
  ✓ acme-pii-redaction 0.2.0   plugin schema matches the deployed policy
  ✗ agent-run-attestation 1.1.0  plugin declares maxTokenAgeSeconds; gateway does not
```

`check` is grounded in something already verified: `api-mgr:policy:describe <interface> --policyVersion <v> -o json` returns the policy's `configuration[]` (§4), so the deployed schema is readable and diffable against the plugin's declared one. That turns "the policy was upgraded and nobody told the SDK team" from a production incident into a CI failure. Wire it into `agent-fabric lint` (§5.3) and run it on the schedule that already runs `agent-fabric drift` (§5.2).

#### 6.10.6 Scope

In: the protocol, discovery and activation, the five call sites, the safety rules, `policy new` / `policy check`. Ships with §6.9's four as the first four plugins — in `policies/`, **not** in `core/`, so the import-linter rule (§1.1) keeps them out of the framework-free layer and proves the extension point is real rather than a facade over four hard-coded cases.

Out: policy logic (§0.2), a Python→WASM compiler (§0.2), and any runtime path that applies a policy (§5.4, working instruction #11).

---

## 7. Publication — registering code-first assets into Exchange

Symmetric with §6 by design: one declarative object, the same three-verb lifecycle, the same "declare in code, apply in CI, verify at runtime" discipline. The symmetry holds for two of the three verbs. **It breaks at runtime, and §7.4 explains why — read that before implementing.**

Publication is lower risk than §5, because Exchange has a well-trodden publication mechanism (Exchange API, Anypoint CLI, and the Exchange Maven plugin) rather than a possibly-UI-only wizard. Confidence here is higher than anywhere else in this spec.

### 7.1 Scope: code-first assets only

Publication exists for assets that **originate in the developer's code**:

- an MCP server written in Python or TypeScript,
- an agent written in one of the eight frameworks and exposed over A2A,
- an agent exposed as a tool without an A2A surface.

It does **not** exist for assets the platform already owns. If an MCP server was created by MCP Bridge from an existing API (§5), that capability is already in Exchange. Publishing a second, code-derived descriptor for it creates two catalog entries for one capability, which is exactly the failure a registry is supposed to prevent.

**Implement a collision check.** Before publishing, search Exchange for an existing asset with the same endpoint, name, or derived tool signature. On a probable match, refuse and print the existing asset's coordinates. Override with an explicit `--allow-duplicate` flag that logs at WARNING.

### 7.2 The object

```python
from agent_fabric import Publication, AssetType, Contact

pub = Publication(
    asset_type=AssetType.MCP_SERVER,          # MCP_SERVER | A2A_AGENT | AGENT | API
    group_id="${ANYPOINT_ORG_ID}",
    asset_id="hr-tools-mcp",
    version="1.3.0",                          # semver; see §7.5 on immutability
    name="HR Tools",
    description="Employee lookup and leave-balance tools for HR agents.",

    # Discovery metadata
    tags=["hr", "internal", "agent-tool"],
    categories={"Domain": "People", "Lifecycle": "Production"},
    contact=Contact(team="People Platform", email="people-plat@acme.com"),

    # Type-specific descriptor — exactly one, matching asset_type
    descriptor="auto",                        # introspect the live server (§7.3)

    # Documentation pages, published alongside the asset
    docs=[
        ("home", "docs/exchange/overview.md"),
        ("getting-started", "docs/exchange/quickstart.md"),
    ],

    # Where it actually lives — metadata only, see §7.6
    endpoint="https://hr-tools.internal.acme.com/mcp",
    governance=gov,                           # optional link to the §6 object
)
```

`AssetType` drives which descriptor is required and how it is generated:

| `asset_type` | Descriptor | Generated from |
|---|---|---|
| `MCP_SERVER` | MCP tool manifest — server info, tool names, descriptions, JSON Schema inputs | live `tools/list` against the running server |
| `A2A_AGENT` | A2A Agent Card | declared skills, endpoint, auth schemes, input/output modes |
| `AGENT` | agent descriptor (no A2A surface) | framework-specific introspection, best-effort |
| `API` | OpenAPI / AsyncAPI | user-supplied file; no generation |

**M0 gate:** verify whether Exchange exposes first-class asset types for MCP servers and AI agents. Agent Fabric's Agent Registry is built on Exchange, so this is likely — but if it does not, publication degrades to a generic or custom asset type carrying tags, which weakens discoverability and **breaks `asset_types=["mcp"]` filtering in §6.1**. The two features share this dependency; verify once, record once.

### 7.3 `descriptor="auto"` — deriving the spec from code

Hand-maintained catalog descriptors go stale within one sprint. Generation is the entire value of this object, exactly as `inputSchema: auto` is the value of §5.

#### 7.3.1 The key insight: do not write a type-hint-to-JSON-Schema converter

Every one of the eight frameworks **already derives JSON Schema from function signatures, type hints, and docstrings**, because that is how tool calling works at all. `@tool` in LangChain and Strands, `FunctionTool` in ADK and LlamaIndex, `@function_tool` in the OpenAI Agents SDK, `@mcp.tool()` in the MCP Python SDK — each builds a schema and attaches it to a tool object. ADK's documentation is explicit that the docstring is what the model reads.

The SDK's job is therefore **to ask the framework for the schema it already computed**, not to re-derive it. Re-implementing type-hint inference would produce a second, subtly different schema from the one the model actually sees, which is worse than useless — it means the catalog documents something other than the running behaviour.

Concretely, per framework, read the already-populated fields:

| Framework | Tool object | Name / description / schema |
|---|---|---|
| MCP Python SDK (FastMCP) | registered tool | `.name`, `.description`, `.inputSchema` |
| LangChain / LangGraph | `BaseTool` | `.name`, `.description`, `.args_schema` (pydantic → `.model_json_schema()`) |
| Strands | `@tool` function | tool spec including input schema |
| Google ADK | `FunctionTool` | declaration with parameters |
| LlamaIndex | `FunctionTool` | `.metadata.name`, `.description`, `.fn_schema` |
| OpenAI Agents SDK | `FunctionTool` | `.name`, `.description`, `.params_json_schema` |
| Anthropic SDK | tool param dict | `name`, `description`, `input_schema` |
| CrewAI | `BaseTool` | `.name`, `.description`, `.args_schema` (pydantic → `.model_json_schema()`) |
| MS Agent Framework | tool / `AIFunction` | declaration + JSON schema |

**These are per-framework adapters and they will break on upstream releases.** Some of these attributes are semi-public. Put every one of them in the conformance kit and the nightly matrix (§8.4), same as the model and tool adapters.

#### 7.3.2 Three derivation modes, ranked by fidelity

```python
descriptor="auto"          # object introspection — the default
descriptor="auto:live"     # live protocol introspection — highest fidelity
descriptor="auto:static"   # AST only — lowest fidelity, no code execution
descriptor="auto:check"    # generate, diff against committed file, fail on mismatch
```

**1. `auto:live` — highest fidelity.** Start the server, perform the MCP initialize handshake, call `tools/list` (plus `resources/list` and `prompts/list`). This is exactly what a client sees, so it captures dynamically registered tools and any runtime filtering. Requires the server to actually run, which may need credentials and network.

**2. `auto` (object introspection) — the default, and the answer to "build the spec from the code."** Import the user's module, locate the tool and agent objects, read their already-computed schemas. No server, no network, works in CI. Fidelity is near-identical to `auto:live` because it reads the same objects the server would expose.

Caveat that must be documented prominently: **importing user code executes it.** Module-level side effects — database connections, API calls, config loading — will fire. Mitigate with an explicit entrypoint rather than package-wide scanning:

```toml
[publication.entrypoints]
"hr-tools-mcp" = "acme.hr.server:mcp"        # module:attribute
"hr-agent"     = "acme.hr.agent:build_agent" # a zero-arg factory is also accepted
```

Document the contract in one line: **tool definitions must be import-safe.** Most already are.

**3. `auto:static` — AST parsing, genuinely lower fidelity.** Parse decorators, signatures and docstrings without executing anything. Useful only where importing user code is unacceptable (untrusted CI, a security policy against executing PR code during analysis).

Be honest about what it cannot see, because the gap is not marginal:

- tools registered in a loop, or from a config file or database
- tools registered conditionally behind a feature flag
- tools attached dynamically at startup
- schemas built from imported or generated pydantic models
- any tool whose description is computed rather than literal

A static descriptor that silently lists 4 of 11 tools is worse than no descriptor. So: `auto:static` must emit a **completeness warning** whenever it encounters dynamic registration patterns it cannot resolve, and must never be the default.

**Cross-check mode.** `agent-fabric publish --cross-check` runs `auto` and `auto:live` and diffs them. Disagreement means either dynamic registration the object graph does not reflect, or a broken framework adapter. Worth running in CI for anything important.

#### 7.3.3 The honest ceiling: shape is derivable, meaning is not

Type hints give the **shape**. `department: str` becomes `{"type": "string"}` and says nothing about what a valid department is, which values exist, or when the tool should be used instead of a similar one. Only a human supplies that, and it is precisely the part that determines whether a model calls the tool correctly.

So auto-derivation automates the mechanical 80% and cannot touch the 20% that matters most. Design accordingly:

- **Fail publication on missing or tautological descriptions.** A description equal to the identifier, or a near-match after normalising underscores and case, is a failure, not a warning. `"search_employees"` as the description of `search_employees` makes a useless tool look documented.
- **Report description quality** in `preview()`: which tools have descriptions under N characters, which parameters have none, which enums are untyped `str`. Give the developer a checklist, not a verdict.
- Optionally offer `agent-fabric describe --suggest`, which drafts descriptions with an LLM through the governed proxy and writes them into the **source** as docstrings for human review. Drafts into source, never straight into the catalog. Keep this opt-in and clearly labelled.

#### 7.3.4 A2A agent cards derive less well than MCP manifests

Worth stating plainly, because the asymmetry is easy to miss. An **MCP tool manifest is close to 1:1 with functions**, so derivation works well. An **A2A skill is not a function** — it is a coarser capability with examples, input/output modes, and its own description, and one skill typically spans several functions.

Auto-deriving skills from functions produces a card advertising forty micro-skills, which is a bad agent card. So:

- Derive the **mechanical** card fields automatically: endpoint, transport, auth schemes, capability flags, input/output modes, version.
- Require **explicit skill declaration or grouping**. Provide a decorator (`@skill("leave-management", examples=[...])`) or a config mapping functions to skills, and fail publication if an `A2A_AGENT` has no declared skills rather than inventing them.

Also note the card must be **served** at the agent's well-known path for A2A clients to find it. Ship `pub.agent_card_handler()` returning an ASGI/Express-compatible route and one example per web framework. The developer mounts it; do not auto-mount.

#### 7.3.5 Committed vs generated

Support both, and make the CI-friendly mode obvious. `descriptor="auto:check"` generates, compares against a committed descriptor file, and fails on mismatch. That is what teams will actually run in CI: the descriptor is reviewable in the PR diff, and drift between code and descriptor is caught before publication rather than by `verify()` after it.

### 7.4 Runtime verb: `verify()`, not `publish()`

The request asks for publication to work at runtime the way governance does. **The symmetry does not survive contact with how Exchange works, and implementing runtime publication would be actively harmful.** Four reasons, all concrete:

1. **Exchange versions are immutable.** Publishing the same version twice fails. A process that publishes on startup must therefore bump versions, which means every pod restart mints a new catalog version. A ten-replica deployment races to mint ten.
2. **The catalog would reflect what happens to be running.** A registry's value is that it is a curated, reviewed statement of what exists. Runtime self-registration turns it into a log of process starts. This is the specific outcome enterprises adopt a registry to avoid.
3. **Privilege escalation.** Exchange publication needs write scopes. Granting them to a production agent's runtime credential means any compromise of that agent can rewrite the enterprise catalog.
4. **No review.** Publication is a governance act. It belongs behind a PR, like policy.

So the three verbs are:

| Verb | Runs where | What it does |
|---|---|---|
| `preview()` | developer laptop | Generates the descriptor and renders the Exchange entry as it would appear. Writes nothing. |
| `export()` | developer laptop | Compiles into the `fabric.yaml` spec (§5.1). CI publishes on merge via `agent-fabric apply`. |
| `verify()` | agent process, runtime | **Read-only.** Fetches the published descriptor from Exchange, introspects the live server, and compares. Raises `PublicationDrift` on mismatch. |

`verify()` is the genuine mirror of `resolve()`, and it is more useful than runtime publishing would have been. It catches the single most common way an agent registry rots: **a team ships a new tool and the catalog still describes the old surface.** A `verify()` call at startup, or a scheduled `agent-fabric verify` in CI, turns catalog staleness from an invisible slow decay into a failing check with a diff:

```
PublicationDrift: com.acme/hr-tools-mcp/1.3.0
  live server exposes 7 tools, Exchange descriptor lists 5
  + get_leave_balance   (live, not in Exchange)
  + approve_leave       (live, not in Exchange)
  ~ search_employees    input schema changed: +department (required)
  Run `agent-fabric publish --bump minor` to update the catalog.
```

Default `verify()` to warn-and-continue, configurable to raise. A drifted catalog should not take down production traffic, but it must be loud.

### 7.5 Versioning and idempotency

The predictable failure mode is CI publishing a new version on every merge until the catalog holds four hundred patch versions of one asset. Prevent it structurally:

- **Content digest.** Compute a stable hash over the canonical descriptor plus metadata. Store it as an Exchange field or tag on publish.
- **`--if-changed` is the CI default.** Compare the digest against the latest published version; if identical, skip and exit zero.
- **Version strategy is explicit config**, one of: `pinned` (from the object), `from-package` (read the Python/npm package version), or `semantic-auto` (patch for metadata-only changes, minor for added tools, **major for removed or narrowed tools** — a removed tool is a breaking change for every consuming agent). Default to `pinned`, since implicit version bumps in a shared catalog are the kind of magic that erodes trust.
- **Never delete or overwrite.** Deprecation is a metadata change on the existing version, not a delete. If Exchange supports lifecycle states, use them.

### 7.6 Publication ≠ deployment ≠ governance

Three independent facts that this object handles exactly one of:

| Fact | Meaning | Owned by |
|---|---|---|
| Published in Exchange | discoverable | §7 |
| Deployed and reachable | someone can call it | the user's own platform (§6.6) |
| Fronted by a gateway with policies | governed | §6 |

An asset published by §7 alone **will not pass `governed=True` filtering in §6.1**, and that is correct behaviour, not a bug. Publication plus Governance together produce a fully registered, governed asset; either alone is a half-state.

Make this visible rather than leaving developers to discover it. `agent-fabric status` should render all three facts per asset:

```
com.acme/hr-tools-mcp/1.3.0
  published   yes   Exchange, 2026-08-14
  reachable   yes   https://hr-tools.internal.acme.com/mcp (200, 7 tools)
  governed    NO    no API Manager instance in Production
              -> `agent-fabric apply -f fabric.yaml --target production`
```

### 7.7 Catalog ownership

The same political constraint as §5.4. In most orgs, publishing into the shared Exchange organisation requires approval, and an SDK that makes it a one-liner will be seen as a threat to the catalog rather than a contribution to it.

Defaults that keep the SDK welcome:

- Publish to the **developer's own business group** by default. Publishing to the root or a shared org requires explicit `group_id` config plus a `--target shared` flag.
- Support an **allow-list of publishable asset types and target groups**, owned by the platform team in a separate repo, mirroring the policy catalog in §5.4.
- CI-only publication under a connected app whose Exchange write scopes the platform team controls. The developer's own credential should not have them.

### 7.8 Asset auto-detection and `agent-fabric init`

Asset type detection is reliable, because the framework objects are unambiguous. Scan the entrypoint or project and classify:

| Detected | Inferred type |
|---|---|
| A FastMCP / MCP server instance with registered tools | `MCP_SERVER` |
| An A2A server app, or an agent with declared skills and an A2A route | `A2A_AGENT` |
| A framework agent object (LangGraph compiled graph, ADK `LlmAgent`, Strands `Agent`, `agent_framework.Agent`, `agents.Agent` (OpenAI Agents SDK), CrewAI `Agent`/`Crew`, LlamaIndex `FunctionAgent`) with no A2A surface | `AGENT` |
| An OpenAPI / AsyncAPI file with no agent or server object | `API` |

Two things this must get right:

**One project can produce several assets.** A single repo commonly exposes an MCP server *and* an A2A agent, or several agents. Detection returns a **list** of candidate publications, not one. Model it that way from the start; retrofitting multi-asset support later is painful because the CLI, config, and digest layout all assume cardinality.

**Never silently pick a type.** Exchange versions are immutable (§7.5), so an asset published under the wrong type is a catalog error you cannot cleanly delete. Detection proposes; the developer confirms once; the answer is written to config and never re-inferred.

```
$ agent-fabric init
Scanning acme/hr/ …

  Found 2 publishable assets:

  1. MCP_SERVER   acme.hr.server:mcp
     7 tools  ·  all have descriptions  ·  2 params undocumented
  2. A2A_AGENT    acme.hr.agent:build_agent
     LangGraph agent with an A2A route
     ! no skills declared — an agent card needs explicit skills (§7.3.4)

  Write these to .agent-fabric.toml? [Y/n]
```

`init` should also run the §7.3.3 quality report and the §7.1 collision check at this point, so the developer sees every problem before their first publish rather than one per attempt.

Ambiguous or unrecognised projects exit with a clear message naming the entrypoint config to set manually. Detection failing is fine; detection guessing wrong is not.

### 7.9 Added to the M0 verification checklist

- Does Exchange have first-class asset types for MCP servers and AI agents, or must they be published as generic/custom types? **(gates §7.2 and, jointly, `asset_types` filtering in §6.1)**
- Which publication mechanism is supported for non-Mule assets: Exchange REST API, Anypoint CLI, or the Maven plugin? Pick one and note whether it requires a JVM at publish time — a Maven-only path makes the Python and TS CI story materially worse.
- Can arbitrary metadata or tags be attached for the content digest (§7.5)?
- Are asset lifecycle states (draft / published / deprecated) exposed via API? **(gates `require_lifecycle` in §6.1.1 and deprecation in §7.5)**
- Can documentation pages be published programmatically, and in what markup?
- Does Exchange accept an MCP tool manifest and an A2A agent card as native descriptor formats, or must they be attached as files? **(shapes §7.3 output)**
- Can an asset be published in a **draft / unlisted / staged** state, and can provenance be recorded on it? **(gates the `stage` tier in §7.10.2)**

### 7.10 Repository and organisation-wide scanning

Everything above §7.10 assumes one repo, one developer, one interactive command. That answers "help me publish my asset." It does not answer **"we have two hundred repos and an empty catalog,"** which is the harder and more common problem: bootstrapping is a one-time org-wide cost that no individual developer is motivated to pay, and a registry that stays empty for six months never recovers its credibility.

So: scanning is in scope. Fully automatic publication of everything it finds is not, and the reasons are structural rather than cautious.

#### 7.10.1 What is already derivable, restated precisely

| Surface | Derivable without hand-authoring? | Where |
|---|---|---|
| MCP tool names, descriptions, input schemas | **Yes, fully.** Read the schema the framework already computed. | §7.3.1 |
| Asset type (`MCP_SERVER` / `A2A_AGENT` / `AGENT` / `API`) | **Yes.** Framework objects are unambiguous. | §7.8 |
| A2A card mechanical fields — endpoint, transport, auth schemes, I/O modes | **Yes.** | §7.3.4 |
| **A2A skills** | **No, and deliberately so.** Deriving one skill per function produces a card advertising forty micro-skills. | §7.3.4 |
| **Tool *meaning*** — which values are valid, when to call this tool over a similar one | **No.** Shape is derivable; meaning is not. | §7.3.3 |

An MCP server can therefore be scanned to a complete, publishable descriptor with no human input. An A2A agent cannot, and a scanner must not pretend otherwise. That asymmetry drives §7.10.8.

#### 7.10.2 The autonomy ladder — four tiers, default `propose`

| Tier | What it writes | Who reviews | Default for |
|---|---|---|---|
| `report` | nothing, anywhere | nobody | always, on first run |
| `propose` | **a PR in each target repo** adding `.agent-fabric.toml`, a committed descriptor, and the publish workflow | that repo's own owners, via normal PR review | **the default** |
| `stage` | publishes into a separate **discovery** business group, tagged as scanner-derived, never the shared catalog | a catalog curator, out of band | opt-in per org |
| `auto` | publishes to the repo's own business group on merge to the default branch | nobody — CI only | opt-in **per repo** |

One rule makes this safe, and it is not negotiable: **a tier above `propose` can only be enabled by a file committed in the target repo.** Never by a flag on the scanner. If a scanner operator can raise the tier centrally, then one person with a token becomes the org's publisher of record and §7.7 is void — which is the exact outcome that gets the SDK banned in a platform review.

```toml
# .agent-fabric.toml, committed in the TARGET repo — the only place this can be raised
[scan]
tier = "auto"                  # report | propose | stage | auto
assets = ["hr-tools-mcp"]      # explicit; `auto` never applies to newly detected assets
```

A newly detected asset always starts at `propose`, even in a repo set to `auto`. Otherwise adding a file to an `auto` repo silently publishes a new catalog entry, and Exchange versions are immutable (§7.5) — there is no clean undo.

#### 7.10.3 Static-first, because scanning is executing

§7.3.2's caveat — importing user code runs it — is per-repo advice at single-repo scale. At fleet scale it is a security boundary. A central scanner that imports code from two hundred unreviewed repos is arbitrary code execution across the organisation, in one process, with an Anypoint write credential in its environment. Nobody should accept that, and no amount of documentation makes it acceptable.

Therefore:

- **Fleet scanning defaults to `auto:static`** (AST, no execution) and cannot be switched to `auto` for repos it does not own.
- **Escalation to `auto` happens inside the target repo's own CI**, where the repo already trusts its own code, never in the central scanner.
- Consequently, fleet-scan descriptors carry the §7.3.2 completeness caveat and are **proposals, not publications**.

Which yields the invariant that shapes the whole feature:

> **The central scanner never publishes. It opens pull requests. Every publication happens from the target repo's CI, from a reviewed descriptor, under credentials the platform team controls.**

This is not a compromise imposed on the feature — it is strictly better than central publication. The completeness warning lands in a PR where the owning team can see it and fix it by moving to `auto` in their own CI, rather than silently producing a catalog entry listing 4 of 11 tools.

#### 7.10.4 The `propose` PR

```
$ agent-fabric scan fleet --config scan-fleet.yaml --tier propose

Scanning 214 repositories (github.com/acme) …
  208 scanned · 6 skipped (no supported framework detected)

  Detected 47 candidate assets in 31 repositories:
    38  MCP_SERVER    complete descriptor derived
     6  A2A_AGENT     mechanical fields only — skills required (§7.3.4)
     3  AGENT         no A2A surface

  Quality gate (§7.3.3)
    31 pass · 7 have missing or tautological descriptions · 9 have undocumented params

  Cross-repo dedupe (§7.10.6)
    2 clusters where >1 repo exposes the same capability — issues opened, no PRs

  Opening 29 PRs (2 clusters held back) … done
    acme/hr-service#412        1 asset   MCP_SERVER  ready
    acme/finance-tools#89      2 assets  MCP_SERVER  1 quality failure
    …
```

Each PR adds only reviewable files, and never a credential:

```
+ .agent-fabric.toml                        entrypoints + asset types, from detection
+ descriptors/hr-tools-mcp.json             the derived descriptor, reviewable in the diff
+ .github/workflows/fabric-publish.yml      auto:check on PR, publish --if-changed on merge
```

The PR body states what was derived, what could not be, and what the reviewer must supply — the seven-line version of §7.3.3's quality report. A PR that says "3 tools need descriptions, here is the file and the line" converts catalog bootstrapping into ordinary code review, which is the only process that scales to two hundred repos.

#### 7.10.5 Fleet configuration and ownership

```yaml
# scan-fleet.yaml — owned by the platform team
apiVersion: fabric/v1
kind: ScanFleet
hosts:
  - provider: github
    org: acme
    include_topics: ["agent", "mcp"]      # opt-in by repo topic
    exclude: ["acme/archived-*", "acme/*-sandbox"]
    default_branch_only: true
ownership:
  from: CODEOWNERS                        # -> Publication.contact
  fallback_team: "Platform Engineering"
publication:
  group_id: per_repo_business_group        # never the shared catalog from a scan
  tier: propose                            # ceiling; a repo may only lower it
quality:
  block_proposal_below: warning            # do not PR an asset that cannot pass review
```

`ownership.from: CODEOWNERS` is worth more than it looks. §7.1's `Contact` is the field most likely to be left blank, and an uncontactable catalog entry is nearly as bad as a missing one. CODEOWNERS is already maintained, already accurate, and already reviewed.

#### 7.10.6 Cross-repo dedupe is where fleet scanning beats per-repo `init`

§7.1's collision check compares one candidate against Exchange. A fleet scanner sees **all candidates simultaneously**, which catches the duplicate class that per-repo publishing structurally cannot: three teams that each wrapped the same upstream API.

Group candidates by tool-signature digest and endpoint. For any cluster of more than one, **do not open PRs.** Open a single issue naming every repo in the cluster and asking which one owns the capability. A scanner that resolves this by picking the first repo alphabetically produces exactly the duplicate catalog §7.1 exists to prevent, only faster and at scale.

#### 7.10.7 Ship the coverage report first

The read-only, bidirectional inventory needs **no write scopes at all**:

```
$ agent-fabric scan report --config scan-fleet.yaml

In code, not in the catalog        38 assets across 27 repos
In the catalog, no live code        6 assets   -> deprecation candidates (§7.5)
In both, descriptor drifted        11 assets   -> `publish --bump minor` (§7.4)
In both, current                   52 assets

Catalog coverage: 52 of 90 detected capabilities (58%)
```

This is the §5.3 pattern applied to publication: small, cheap, uncontroversial, requires no verification of a write path, and it is the fastest way to get a platform team to say yes to the rest. It is also the artifact that makes the case for funding the bootstrap at all, since "our catalog covers 58% of what we actually run" is a number an engineering director can act on.

Build it before the PR machinery.

#### 7.10.8 Guardrails that survive contact with two hundred repos

- **The quality gate is not downgradable by the scanner.** An asset failing §7.3.3 is never staged or auto-published — at most proposed, with the failures in the PR body. Bulk scanning multiplies §10's "auto-generated descriptions make useless tools look documented" risk by the size of the fleet.
- **A2A agents are `propose`-only, permanently.** Skills cannot be derived (§7.3.4), so no tier auto-publishes an `A2A_AGENT`. The PR asks for `@skill(...)` declarations.
- **Every scanner-derived asset records its provenance** — scanner version, commit SHA, derivation mode, date — so a curator can tell a reviewed entry from a bootstrapped one, and can re-run the bootstrap later without re-litigating which is which.
- **Digest-gated re-scan.** Re-scanning uses §7.5's content digest, so an unchanged repo produces no PR, no issue and no write. Without this, a scheduled fleet scan is a PR spam generator and will be turned off within a week.
- **One PR and one issue per repo, updated in place.** Same discipline as the nightly matrix (§8.4).
- **Rate limits and concurrency are a design constraint, not an afterthought.** Two hundred shallow clones plus Exchange lookups will hit both the Git host's and Anypoint's limits. Bounded concurrency, sparse checkout, and a persistent cache keyed on commit SHA.

#### 7.10.9 What scanning is not

| Not building | Why |
|---|---|
| Zero-touch publication of everything found, with no review | Exchange versions are immutable (§7.5) and catalog ownership is a political constraint (§7.7). The closest offered is `auto`, per-repo opt-in, still quality-gated. |
| A central scanner holding Exchange write scopes | Would make the scanner operator the org's publisher of record. Publication happens in the target repo's CI (§7.10.3). |
| Importing untrusted repo code centrally | Arbitrary code execution across the org. Static-first, escalate only inside the owning repo's CI. |
| A secret scanner, SAST, or code-quality tool | Different products. The scanner detects publishable agent assets and nothing else. |
| Deployment or reachability discovery | The SDK does not deploy anything (§6.6). `reachable` stays a probe in `status`, not an inference. |

#### 7.10.10 Added to the M0 verification checklist

- Can an asset be published in a **draft / unlisted / staged** state? **(gates the `stage` tier — without it, `stage` collapses into `propose`)**
- Can **provenance metadata** be attached to a published asset? Shares the §7.9 metadata/tags verification.
- Is there an Exchange API to list **all** assets in an org efficiently enough for a bidirectional coverage report over a large catalog, or must it be paginated per business group?

---

## 8. Testing

### 8.1 The adapter conformance kit — the most important test asset

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
    "governed_filter_excludes",    # ungoverned asset absent when governed=True
    "governance_resolve_drift",    # declared policy missing on gateway -> GovernanceDrift
    "governance_target_switch",    # same code, FABRIC_TARGET=local|sandbox, correct base_url
    "descriptor_auto_stable",      # two introspections of one server -> identical digest
    "publication_verify_drift",    # added tool on live server -> PublicationDrift
    "publication_idempotent",      # --if-changed with no change -> zero writes, exit 0
    "descriptor_matches_framework",# derived schema == the schema the model receives
    "fidelity_never_downgrades",   # simulate(mode="connected") fails rather than falling back
    "connected_local_real_policy", # connected-mode local gateway enforces a connected-only policy
    "dev_instance_cleaned_up",     # ephemeral API instance destroyed on exit AND on exception
    "scan_never_publishes",        # fleet scan issues ZERO writes to Exchange
    "scan_tier_needs_repo_optin",  # tier > propose ignored unless committed in target repo
    "scan_static_completeness",    # loop-registered tools -> completeness warning in the PR body
    "scan_fleet_dedupe",           # same capability in 2 repos -> 1 issue, 0 PRs
    "auto_vs_live_agree",          # object and live introspection produce one digest
    "dynamic_tools_detected",      # loop-registered tools present in `auto`, warned in `auto:static`
    "asset_type_detection",        # fixture projects per framework classify correctly
    "attestation_header_signed",   # §6.9.2 header present, canonical, signature verifies
    "attestation_step_increments", # step/depth advance across a run's model + tool calls
    "attestation_chain_preserved", # A2A delegation continues parent_run_id, no new root
    "error_envelope_preferred",    # §6.9.4 envelope parsed when present, heuristic when not
    "no_plugins_is_supported",     # §6.10.4 zero plugins installed -> full base behaviour
    "plugin_cannot_suppress",      # a plugin returning None/raising still yields PolicyViolation
    "plugin_header_collision",     # two plugins claiming one header -> ConfigError at startup
    "plugin_version_drift",        # plugin range excludes the applied version -> GovernanceDrift
]
```

Parametrise over adapters with pytest. A framework that cannot satisfy `correlation_id_propagated` (likely ADK, via LiteLLM) records a documented, asserted exemption in a `KNOWN_LIMITATIONS` table rather than silently skipping. Publish that table in the README — it is credibility, not embarrassment.

### 8.2 Contract fixtures

Write a `scripts/probe.py` that runs against a real sandbox and records every response shape into `tests/contract/fixtures/`: token issuance, model list, a successful completion, a streaming completion, and one deliberately-triggered instance of each policy rejection. Redact secrets on write.

Unit and contract tests replay these with `respx` (Python) / `msw` (TS). **The `errors.classify` table is generated from these fixtures**, not from guesses. Re-run the probe monthly; a fixture diff is an early warning that the platform changed.

### 8.3 Integration

Three tiers, matching the §6.8 fidelity ladder. The distinction that matters: LLM Proxy and MCP Bridge are **Connected Mode** features, which is not the same as "not testable locally" — a self-managed Connected Mode gateway runs on a laptop or a CI runner and has both for real (§6.8).

| Tier | Marker | What it runs | Needs an org |
|---|---|---|---|
| `mock` | default, always on | in-process stub replaying §8.2 fixtures | no |
| `local` | `@pytest.mark.local_gateway` | `docker-compose`: Flex Gateway in Local Mode, declarative config, upstream mock | no* |
| `connected` | `@pytest.mark.connected_gateway` | Flex Gateway container in **Connected Mode**, registered to a dev environment | **yes** |
| live sandbox | `FABRIC_SANDBOX_TESTS=1` | the shared sandbox, for release gating | yes |

\* subject to the §6.7 licence-artifact question.

Coverage on the `local` tier is partial by design — connected-only policies are skipped and loudly reported (§6.4). The `connected` tier closes that gap and is the pre-merge gate on the main branch. Keep every org-requiring tier off by default so contributors without an Anypoint org can still run the full `mock` suite.

### 8.4 Nightly framework matrix

Eight frameworks, each releasing independently, several pre-1.0. Run the conformance suite nightly against the **latest** release of each framework in addition to the pinned version. Open an issue automatically on failure. Without this you find out a framework broke when a user reports it.

Pin floors, not ceilings, in `pyproject.toml`. Never `<` pin a framework — it forces users into dependency hell.

---

## 9. Delivery

### 9.1 Milestones

| Milestone | Scope | Est. (2 engineers) |
|---|---|---|
| **M0 — Verify** | §0.3 in full. `docs/verified-apis.md`. `scripts/probe.py` + captured fixtures. Go/no-go on §5. | 2 weeks |
| **M1 — Model access** | `core` complete. `llm` client + catalog. Adapters for Tier 1 (LangGraph, ADK, Strands, Agent Framework, OpenAI Agents SDK, Anthropic SDK, CrewAI). Conformance kit. `lint` command. Docs site skeleton. **First public release, 0.1.0.** | 4 weeks |
| **M2 — Tool access** | `registry` + `tools` + `ToolSet`. Bindings for all eight. Lockfile. A2A agent handles. LlamaIndex (Tier 2) adapter. Governed-only discovery, name/glob `search` + filters, and `explain()` (§6.1). **0.2.0.** | 6 weeks |
| **M2.5 — Governance object** | `Governance`, `GatewayTarget`, target profiles, `resolve()` with drift detection, policy portability table, `simulate()` across all three fidelity rungs incl. the self-managed Connected Mode local gateway and its dev-instance lifecycle (§6.2–§6.6, §6.8). **0.3.0.** | 5 weeks |
| **M2.6 — Policy interface** | `policies/`: the `PolicyPlugin` protocol, discovery + activation, the five call sites, plugin-first `classify()`, `agent-fabric policy new\|check` (§6.10). Then the client half of §6.9: canonical JSON + HMAC codec, header emission in both transports, step/depth counters, `parent_run_id` on `run_context()`, and the four §6.9 policies as the first four plugins. **0.3.2.** | 3 weeks |
| **M2.7 — Publication** | `Publication`, `preview()`, `verify()` with drift diff, digest + `--if-changed`, collision check, `agent-fabric status` (§7). **0.3.5.** | 3 weeks |
| **M2.8 — Derivation** | Per-framework descriptor adapters (§7.3.1), `auto` / `auto:live` / `auto:static` / `auto:check`, cross-check, quality report, asset detection + `agent-fabric init` (§7.8). **0.3.8.** | 4 weeks |
| **M2.9 — Fleet scanning** | `agent-fabric scan` (single repo, non-interactive), coverage report, fleet enumeration, autonomy tiers, `propose` PRs, cross-repo dedupe, scheduled re-scan (§7.10). **0.3.9.** | 3 weeks |
| **M3 — TypeScript** | TS core + LangGraph.js, ADK TS, Strands TS, OpenAI Agents (JS), Anthropic SDK (TS), LlamaIndex.TS, Vercel AI SDK. Shared conformance scenarios ported. **0.4.0.** | 4 weeks |
| **M4 — Provisioning** | Spec, plan/apply/drift, `inputSchema: auto`, policy allow-list, GitHub Action. Plus `Governance.export()` and `Publication.export()`. Or the Terraform-generation pivot. **0.5.0.** | 5 weeks |
| **M5 — Hardening** | Perf, telemetry polish, error-message pass, migration guide, examples for all eight, security review. **1.0.0.** | 3 weeks |

`export()` — for both the governance and publication objects — lands with M4, since it emits the M4 spec format. Ship M2.5 and M2.7 with their local and runtime verbs only, and document `export()` as coming.

**M2.6 splits into two halves with very different dependencies, and only one of them is fenced.** The `PolicyPlugin` interface (§6.10) depends on nothing outside this repo, is worth building for customers who already have their own PDK policies — §6.4's `acme-custom-redaction` is not hypothetical — and is the thing that keeps `core/` from accreting special cases. Build it. The four builtin plugins are the SDK's half of the §6.9 contract: they depend on the companion policy repo existing and on §6.9.7 being answered, so they are excluded from the total below. A deliverable that blocks on a different team's Rust has no business on this plan's critical path.

What is fenced off from both is the one-line version: emit a plain `x-agent-run-id` header in M1 so a platform team can point the stock `llm-token-rate-limit` `keySelector` at it and get run-scoped budgets with no custom policy and no plugin at all (§6.9.2). Do that in M1 regardless of whether the rest of M2.6 is ever funded.

Roughly ten to eleven months for two engineers, up from six. M2.9 depends entirely on M2.8 — a scanner is only as good as the derivation underneath it — but its coverage report (§7.10.7) is read-only and needs no write path, so that one piece can ship alongside M2.7 as a platform-team on-ramp. M2.8 is the single highest-leverage block in the plan after M1 — it is what makes the catalog self-maintaining instead of self-rotting — but it is also the block most exposed to upstream framework churn, so it needs the nightly matrix in place before it starts. Ship M1 publicly rather than waiting — the LLM proxy adapters are useful alone, and early feedback will reorder M2–M4.

### 9.2 Definition of done, per adapter

1. Passes the full conformance kit, or has an asserted documented exemption.
2. A runnable example in `examples/<framework>/` that works against a sandbox with only env vars set.
3. A docs page with the manual equivalent — the three lines of code the adapter replaces. Users must be able to eject.
4. Listed in the nightly matrix.
5. Version floor declared, no ceiling.

### 9.3 The unsupported boundary

Maintain `docs/unsupported-boundary.md` listing every platform API the SDK calls, classified:

- **Documented and public** — safe.
- **Documented but no SLA for third-party use** — will break, we'll fix.
- **Undocumented** — should be empty. If anything lands here, it needs a written justification and an owner.

Link it from the README above the fold. Enterprise buyers will ask; having the answer pre-written converts a two-week procurement stall into a five-minute conversation.

---

## 10. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| MuleSoft ships a first-party Python/TS SDK | Medium-high | Existential | Talk to MuleSoft product in week 1 of M0. Ask for a written answer. Offer to be a design partner. |
| MCP Bridge has no provisioning API | Medium | M4 only | Pivot to Terraform generation (§5.5). M1–M3 unaffected. |
| Attribution header names not exposed | Low-medium | High — kills cost attribution | Surfaced in M0. If unavailable, escalate to MuleSoft; ship with correlation-ID-only telemetry and document the gap. **§6.9.2 makes this moot if built** — a signed, self-defined attestation header the companion policy reads replaces the platform header the SDK is waiting on. |
| Client-side tool filtering mistaken for tool authorization | **High** | **High — a prompt-injected agent calls any tool its credential reaches** | Document `ToolSet.filter` as advisory in §4.3, not a security control. Gateway-enforced fix is §6.9.5, and it needs the attestation primitive first. |
| Runaway agent loop exhausts a shared credential's token budget | High | Medium — the failure lands on an innocent agent | Run-scoped keying: `keySelector` on the SDK's run-id header (free, M1), then §6.9.3 for step/depth limits. |
| A2A delegation cycle (A→B→A) with no depth guard | Medium | Medium — unbounded spend, no client-side fix | Client-side depth counting is defeated by the first non-SDK participant. `maxDepth` in §6.9.3 is the only real guard. |
| Companion policy contract drifts from the SDK's emitted header | Medium | High — every governed call rejects at once | Versioned wire format (`v1.…`), compat matrix in the companion repo, SDK tolerates the previous major, `observe` mode default (§6.9.1, §6.9.6). |
| Custom policies do not actually run in Local Mode as §6.4 claims | Medium | Medium — kills the §6.9.6 local dev-loop argument | M0 gate (§6.9.7). Falls back to the `connected` rung, which needs an org. |
| **A third-party policy plugin weakens governance** — suppresses a rejection, overwrites an attribution header | Medium | **High — the extension point disables the product** | `classify` can only decline, never succeed; core headers written last and win; collisions fatal at startup; conformance `plugin_cannot_suppress` (§6.10.4). |
| Auto-loaded plugin becomes a supply-chain vector | Medium | High — installed code injecting headers into every governed call | Discovery is automatic, **activation is not**: inert until named in a committed `.agent-fabric.toml` (§6.10.2). |
| Policy plugin mistaken for policy approval | Medium | High — reviewer concludes the §5.4 allow-list is bypassable | Separate files, separate owners, stated in §5.4 and §6.10.4; `apply` refuses a non-allow-listed policy regardless of plugins. |
| Policy config schema drifts from the plugin after a gateway upgrade | High over time | Medium — every apply fails, cause non-obvious | `agent-fabric policy check` diffs the plugin schema against `api-mgr:policy:describe` output; wired into `lint` and the scheduled drift run (§6.10.5). |
| The plugin interface is a facade over four hard-coded policies | Medium | Medium — customers with their own PDK policies stay locked out | The four §6.9 policies ship **as plugins in `policies/`**, under the same import-linter rule as any third party (§6.10.6). |
| Framework churn breaks adapters | Certain | Medium | Nightly matrix (§8.4). Native-object design (§3.1) minimises blast radius. |
| Anthropic-native proxy route unavailable | Medium | Medium — Anthropic adapter cannot reach a working upstream | M0 gate (§3.3). One-time `UnverifiedValueWarning`; `base_url` overridable; the seven other adapters are unaffected. |
| CrewAI/ADK LiteLLM transport blocks per-run correlation | Certain | Low | Documented, asserted conformance exemption (§8.1); LiteLLM logger callback may recover it later. |
| Anypoint API changes break control-plane calls | Medium | Medium | Contract fixtures + monthly probe re-run (§8.2). |
| Scope creep into agent-network authoring | High | High | It is in §0.2. Point at it in every scope discussion. |
| **Local Mode cannot run LLM Proxy or MCP Bridge** | **Medium-high** | **Medium — was High before §6.8** | M0 gate (§6.7). Ship the mock proxy either way; label simulation loudly (§6.4). **A self-managed Connected Mode gateway running locally has both for real (§6.8)**, so this became a cost question rather than a capability ceiling. |
| Local Mode needs a control-plane licence artifact | Medium | Medium — blocks OSS contributors and CI | M0 gate. Fall back to mock-proxy-only local loop; `connected` rung for anyone with an org. |
| **Orphaned dev API instances accumulate in the control plane** | **High if unguarded** | **Medium — quota exhaustion and a mess nobody owns** | Deterministic naming, create-if-absent, teardown on exception, `agent-fabric dev reap` TTL reaper (§6.8.3). |
| Dev harness pointed at a production environment by a stray env var | Low-medium | **High** | Hard environment fence: refuse any environment not explicitly marked a dev target, and refuse outright on production (§6.8.3). |
| Gateway registration artifact leaked or committed | Medium | High — lets the holder register a gateway into the org | Treated as a credential: gitignored, never logged, per-developer; `dev up` refuses if git tracks it (§6.8.3). |
| Connected local dev loop silently spends LLM budget | Medium-high | Medium — feature switched off after the first invoice | Token-budget policy applied in the dev environment by default, conservative `max_tokens`, cumulative spend printed at teardown (§6.8.3). |
| A test expecting `connected` silently runs on `mock` | Medium | High — a false pass on the policy behaviour that matters most | `env.fidelity` queryable; `simulate(mode=...)` fails rather than downgrading; conformance `fidelity_never_downgrades` (§6.8.1). |
| Developers trust a green `simulate()` run | High | High — ungoverned code reaches prod | Non-suppressible skipped-policy warning (§6.4). `resolve()` drift check at startup as the real gate. |
| `governed=True` silently returns empty | High | Medium — SDK gets blamed | `explain()` (§6.1.2) plus a reason attached to every exclusion. |
| Governed-discovery join is slow on large catalogs | Medium | Medium | Bulk index + Exchange-side prefilter (§6.1.3). `warm()` at startup. |
| Governance object read as app-team policy authorship | Medium | High — security review rejection | Three-verb split, no runtime `apply()` (§6.3). |
| Exchange lacks first-class MCP/agent asset types | Medium | High — weakens both §7 and `governed` filtering in §6.1 | Single M0 gate serving both features (§7.9). Fall back to tagged custom types. |
| Catalog spam from per-merge publishing | High if unguarded | Medium — erodes registry trust | Content digest + `--if-changed` as CI default + `pinned` version strategy (§7.5). |
| Auto-generated descriptions make useless tools look documented | High | Medium | Fail publication on missing or tautological descriptions (§7.3.3). |
| Framework tool-object internals change, breaking descriptor derivation | High | Medium | Conformance scenario `descriptor_matches_framework` + nightly matrix (§8.4). |
| Importing user code for introspection triggers side effects | Medium | Medium | Explicit entrypoints, documented import-safety contract, `auto:static` fallback (§7.3.2). |
| `auto:static` silently under-reports tools | Medium | High — incomplete catalog looks complete | Completeness warning on unresolved dynamic registration; never the default (§7.3.2). |
| Auto-derived A2A cards advertise dozens of micro-skills | High if unguarded | Medium | Require explicit skill declaration; fail rather than invent (§7.3.4). |
| **Fleet scanner treated as a central publisher, holding org-wide Exchange write scopes** | **Medium** | **High — one operator becomes the org's publisher of record; §7.7 is void** | Scanner never publishes; it opens PRs. Tier above `propose` raised only by a file in the target repo (§7.10.2, §7.10.3). |
| Central scanner importing untrusted repo code | Medium | High — arbitrary code execution across the org with a write credential in scope | Fleet scanning is static-first and cannot be switched to import mode for repos it does not own (§7.10.3). |
| Bulk scan floods the catalog with low-quality entries | High if unguarded | High — erodes registry trust at fleet scale | Quality gate not downgradable by the scanner; A2A permanently `propose`-only; cross-repo dedupe holds back clusters (§7.10.6, §7.10.8). |
| Scheduled fleet re-scan becomes a PR spam generator | High if unguarded | Medium — feature gets switched off | Digest-gated re-scan; one PR and one issue per repo, updated in place (§7.10.8). |
| `auto:static` under-reporting is invisible at fleet scale | Medium | Medium — 200 partial descriptors look like 200 complete ones | Completeness warning surfaced in the proposal PR body, where the owning team sees it (§7.10.3). |
| Publication seen as a threat to catalog ownership | Medium | High | Own-business-group default, shared-target flag, platform-owned allow-list (§7.7). |
| Maven-only publication path for non-Mule assets | Medium | Medium — JVM in Python/TS CI | M0 gate (§7.9). Prefer Exchange REST API; document the JVM requirement if unavoidable. |
| Security review rejects policy-from-code | Medium | High | Allow-list catalog + CI-only apply, shipped in v1 (§5.4). |

---

## 11. Working instructions for the implementing model

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
11. **Nothing in the runtime path mutates shared state.** `resolve()` and `verify()` read. `simulate()` touches only ephemeral local resources. Every mutation of a gateway or the catalog happens in CI, from a reviewed spec, under platform-controlled credentials. If you find yourself writing a network call that creates or updates a control-plane or Exchange resource outside `provisioning/`, stop — it is in the wrong module.
12. **An extension point may add governance, never remove it.** The `PolicyPlugin` interface (§6.10) exists so `core/` does not accrete a special case per custom policy. It is not a hook for changing what the SDK enforces. A plugin can contribute a header, type a rejection, validate a config; it cannot overwrite a core header, cannot turn a rejection into a success, and cannot do I/O on the request path. If you find yourself adding a plugin return value that means "allow this," stop — you are building a governance bypass with a plugin API on the front of it.
