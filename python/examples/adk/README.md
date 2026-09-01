# Google ADK example

Tier 1.

**What this shows.** A one-line factory call gets you a *native*
`google.adk.models.lite_llm.LiteLlm` pointed at the governed MuleSoft LLM
proxy — correct `api_base`, `client_id`/`client_secret` auth via
`extra_headers` (not bearer), and the model id auto-prefixed with `openai/`
so LiteLLM routes it correctly. The returned object is ADK's own class, not
a wrapper. Note: LiteLLM owns its own HTTP transport, so (unlike LangGraph)
the SDK's shared http client/retry hooks are not injected here — this is a
documented conformance exemption, not an oversight. This example only
constructs the object; it deliberately does not attempt a live inference
call, since ADK drives models through its own `Runner`/`Agent` session
machinery rather than a simple method call.

## Run

```bash
pip install "mulesoft-agent-fabric[adk]"

export MULESOFT_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # note: no /v1
export MULESOFT_LLM_PROXY_CLIENT_ID="<consumer client id>"
export MULESOFT_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"

python examples/adk/main.py
```

## The manual equivalent

The factory call is equivalent to building `LiteLlm` yourself with the
governed connection values (§3.3):

```python
from google.adk.models.lite_llm import LiteLlm

m = LiteLlm(
    model="openai/gpt-4o",  # LiteLLM's OpenAI-compatible route needs this prefix
    api_base=MULESOFT_LLM_PROXY_URL,
    api_key="unused",  # the proxy enforces client_id/client_secret headers instead
    extra_headers={
        "client_id": MULESOFT_LLM_PROXY_CLIENT_ID,
        "client_secret": MULESOFT_LLM_PROXY_CLIENT_SECRET,
    },
)
```

The factory (`agent_fabric.integrations.adk.model`) fills in `api_base`,
`api_key`, `extra_headers`, and the `openai/` prefix from one governed
config source.

## Links

- Google Agent Development Kit (ADK) docs: see the framework's official
  documentation
