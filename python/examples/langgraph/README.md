# LangGraph example

Tier 1.

**What this shows.** A one-line factory call gets you a *native*
`langchain_openai.ChatOpenAI` already pointed at the governed Agent Fabric LLM
proxy — correct base URL, `client_id`/`client_secret` header auth (not
bearer), attribution headers, and the SDK's shared transport (retry/telemetry
hooks). The returned object is LangGraph/LangChain's own class, not a
wrapper, so it drops straight into any LangGraph graph or LangChain chain.
This example also makes one live `.ainvoke(...)` call — LangChain's own,
well-documented runtime API — to prove the object actually talks to the
proxy.

## Run

```bash
pip install "agent-fabric[langgraph]"

export AGENT_FABRIC_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # note: no /v1
export AGENT_FABRIC_LLM_PROXY_CLIENT_ID="<consumer client id>"
export AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"

python examples/langgraph/main.py
```

## The manual equivalent

The factory call is equivalent to building `ChatOpenAI` yourself with the
governed connection values (§3.1):

```python
import httpx
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model="gpt-4o",
    base_url=AGENT_FABRIC_LLM_PROXY_URL,
    api_key="unused",  # the proxy enforces client_id/client_secret headers instead
    default_headers={
        "client_id": AGENT_FABRIC_LLM_PROXY_CLIENT_ID,
        "client_secret": AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET,
    },
    http_async_client=httpx.AsyncClient(...),  # your own transport, retries, hooks
    max_retries=0,
)
```

The factory (`agent_fabric.integrations.langgraph.chat_model`) fills in
`base_url`, `api_key`, `default_headers`, and `http_async_client` from one
governed config source and gives you the SDK's shared transport (with its
retry policy and telemetry hooks) for free.

## Links

- LangGraph docs: https://langchain-ai.github.io/langgraph/
- LangChain `ChatOpenAI` docs: see the framework's official documentation
