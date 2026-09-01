# Strands Agents example

Tier 1.

**What this shows.** A one-line factory call gets you a *native*
`strands.models.openai.OpenAIModel` pointed at the governed MuleSoft LLM
proxy — correct `base_url`, `client_id`/`client_secret` header auth (not
bearer), attribution headers, and the SDK's shared transport, all forwarded
through Strands' `client_args`. Strands forwards `client_args` straight to
the underlying OpenAI client, so both header AND transport injection are
available (full injection, like LangGraph). The returned object is Strands'
own class, not a wrapper. This example only constructs the object; it
deliberately does not attempt a live inference call, since Strands models
are normally driven through a `strands.Agent` session rather than a simple
method call on the model.

## Run

```bash
pip install "mulesoft-agent-fabric[strands]"

export MULESOFT_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # note: no /v1
export MULESOFT_LLM_PROXY_CLIENT_ID="<consumer client id>"
export MULESOFT_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"

python examples/strands/main.py
```

## The manual equivalent

The factory call is equivalent to building `OpenAIModel` yourself with the
governed connection values (§3.3):

```python
import httpx
from strands.models.openai import OpenAIModel

m = OpenAIModel(
    model_id="gpt-4o",
    client_args={
        "base_url": MULESOFT_LLM_PROXY_URL,
        "api_key": "unused",  # the proxy enforces client_id/client_secret headers instead
        "default_headers": {
            "client_id": MULESOFT_LLM_PROXY_CLIENT_ID,
            "client_secret": MULESOFT_LLM_PROXY_CLIENT_SECRET,
        },
        "http_client": httpx.AsyncClient(...),
    },
)
```

The factory (`agent_fabric.integrations.strands.model`) fills in all of
`client_args` from one governed config source, including the SDK's shared
transport.

## Links

- Strands Agents docs: see the framework's official documentation
