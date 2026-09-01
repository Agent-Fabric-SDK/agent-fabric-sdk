# Microsoft Agent Framework example

Tier 1.

**What this shows.** A one-line factory call attempts to build a native
Agent Framework OpenAI-compatible chat client pointed at the governed
MuleSoft LLM proxy. The proxy *contract* (base URL, `client_id`/
`client_secret` header auth, attribution headers) is live-verified. The
chat-client class name/path itself — `agent_framework.openai.OpenAIChatClient`
— and its base-URL kwarg (`model_id`) are **UNVERIFIED** (§8): Agent
Framework is a young package that has renamed classes recently. If the
import fails, the factory raises a `NotImplementedError` ("blocked on
verification") rather than guessing further; this example catches that and
prints it plainly. This example only constructs the object; it deliberately
does not attempt a live inference call, since Agent Framework drives chat
clients through its own `Agent` object rather than a method on the client
itself.

## Run

```bash
pip install "mulesoft-agent-fabric[agent_framework]"

export MULESOFT_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # note: no /v1
export MULESOFT_LLM_PROXY_CLIENT_ID="<consumer client id>"
export MULESOFT_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"

python examples/agent_framework/main.py
```

## The manual equivalent

The factory call is equivalent to attempting to build the chat client
yourself with the governed connection values (§3.3) — **class name and
kwarg UNVERIFIED (§8), confirm against your installed version**:

```python
# CLASS NAME/PATH AND KWARG NAMES UNVERIFIED (§8) — confirm before relying on this
from agent_framework.openai import OpenAIChatClient

client = OpenAIChatClient(
    model_id="gpt-4o",  # kwarg name UNVERIFIED
    base_url=MULESOFT_LLM_PROXY_URL,
    api_key="unused",  # the proxy enforces client_id/client_secret headers instead
    default_headers={
        "client_id": MULESOFT_LLM_PROXY_CLIENT_ID,
        "client_secret": MULESOFT_LLM_PROXY_CLIENT_SECRET,
    },
)
```

The factory (`agent_fabric.integrations.agent_framework.chat_client`) fills
in `base_url`, `api_key`, and `default_headers` from one governed config
source, and raises a clear "blocked on verification" error instead of
silently guessing if the class import fails.

## Links

- Microsoft Agent Framework docs: see the framework's official documentation
