# LangGraph — governed model access

LangGraph (and LangChain more broadly) gets a governed `ChatOpenAI` pointed at
the Agent Fabric LLM proxy, with full header and transport injection.

> **Deep adapter — conformance-gated in blocking CI.** This is the best-case adapter: every
> proxy header and the shared async transport are injected into the native
> client.

## Install

```bash
pip install "donkey-kit[langgraph]"
```

## Quickstart

```python
from donkey_kit.integrations.langgraph import chat_model

llm = chat_model("gpt-4o")
```

`llm` is a real, native **`langchain_openai.ChatOpenAI`** instance — nothing
LangGraph-specific wraps it. Drop it straight into your graph nodes or chains.

There's no first-party Agent Fabric TypeScript SDK yet (it's on the
[roadmap](https://donkey-development-kit.github.io/donkey-development-kit/concepts/verification.md)). The proxy is OpenAI-compatible, so point the
official `openai` npm client at it — the same base URL and
`client_id`/`client_secret` headers also drop straight into **LangChain.js**
(`ChatOpenAI`, via its `configuration.baseURL` + `defaultHeaders`).

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: process.env.DONKEY_LLM_PROXY_URL,   // no /v1
  apiKey: "unused",                              // required slot; proxy uses the headers below
  defaultHeaders: {
    client_id: process.env.DONKEY_LLM_PROXY_CLIENT_ID!,
    client_secret: process.env.DONKEY_LLM_PROXY_CLIENT_SECRET!,
  },
});

const reply = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Say hi in three words." }],
});
console.log(reply.choices[0].message.content);
```

## Three ways to construct

**1. Off a shared `Donkey` instance** (reuses one HTTP client + lifecycle
across every adapter you touch in a run):

```python
from donkey_kit import Donkey

async with Donkey.from_env() as donkey:
    llm = donkey.langgraph.chat_model("gpt-4o")
```

**2. Module-level factory** (shortest — uses a cached, env-configured default
`Donkey` under the hood):

```python
from donkey_kit.integrations.langgraph import chat_model

llm = chat_model("gpt-4o")
```

**3. Governed kwargs, native constructor** (you call `ChatOpenAI` yourself):

```python
from donkey_kit import Donkey
from langchain_openai import ChatOpenAI

async with Donkey.from_env() as donkey:
    llm = ChatOpenAI(model="gpt-4o", **donkey.langgraph.connection_kwargs())
```

## The manual equivalent (eject at any time)

Everything above is sugar over this native constructor call:

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4o",
    base_url=...,             # from DONKEY_LLM_PROXY_URL, no /v1 suffix
    api_key=...,
    default_headers=...,      # client_id / client_secret header pair, not bearer
    http_async_client=...,    # the SDK's shared httpx async client
    max_retries=0,            # the SDK retries in its own transport layer
)
```

Nothing here is hidden — `connection_kwargs()` returns exactly these keys, so
you can always drop the factory and construct `ChatOpenAI` by hand.

## Notes & limitations

> LangGraph is the reference adapter: `base_url`, `api_key`, `default_headers`,
> and a custom `http_async_client` are all forwarded, so proxy auth headers and
> the SDK's transport (retries, correlation IDs) both reach every request.

> `max_retries=0` is intentional — retry logic lives in the SDK's transport
> layer, not in the OpenAI client, so the two don't double-retry.

The proxy is OpenAI-compatible but is **not** a full OpenAI API surface: there
is no `/v1` prefix on the base URL and no `/models` endpoint, and auth is a
`client_id`/`client_secret` header pair rather than a bearer token. See the
[error taxonomy](https://donkey-development-kit.github.io/donkey-development-kit/errors.md) for how proxy rejections surface as typed
exceptions, and the [verification policy](https://donkey-development-kit.github.io/donkey-development-kit/concepts/verification.md) page for
the current status of every constructor signature this adapter depends on.
