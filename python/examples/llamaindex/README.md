# LlamaIndex example

Tier 2.

**What this shows.** A one-line factory call gets you a *native*
`llama_index.llms.openai_like.OpenAILike` pointed at the governed Agent Fabric
LLM proxy — correct `api_base`, `client_id`/`client_secret` header auth (not
bearer), attribution headers, and `is_chat_model=True` set for you.
`OpenAILike` defaults `is_chat_model` to `False`, which silently routes
requests to the completions endpoint and fails against a chat-only proxy —
the single most common LlamaIndex-with-a-gateway bug, and one this factory
eliminates by construction. The returned object is LlamaIndex's own class,
not a wrapper. This example only constructs the object; it deliberately
does not attempt a live inference call, since guessing which one-line
LlamaIndex call to use (`.chat`, `.achat`, `.complete`, ...) risks inventing
an API.

## Run

```bash
pip install "agent-fabric[llamaindex]"

export AGENT_FABRIC_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # note: no /v1
export AGENT_FABRIC_LLM_PROXY_CLIENT_ID="<consumer client id>"
export AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"

python examples/llamaindex/main.py
```

## The manual equivalent

The factory call is equivalent to building `OpenAILike` yourself with the
governed connection values (§3.3):

```python
from llama_index.llms.openai_like import OpenAILike

m = OpenAILike(
    model="gpt-4o",
    api_base=AGENT_FABRIC_LLM_PROXY_URL,
    api_key="unused",  # the proxy enforces client_id/client_secret headers instead
    default_headers={
        "client_id": AGENT_FABRIC_LLM_PROXY_CLIENT_ID,
        "client_secret": AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET,
    },
    is_chat_model=True,  # never omit — defaults to False and silently breaks
    is_function_calling_model=True,
)
```

The factory (`agent_fabric.integrations.llamaindex.llm`) fills in
`api_base`, `api_key`, `default_headers`, and the two `is_*` flags from one
governed config source.

## Links

- LlamaIndex docs: see the framework's official documentation
