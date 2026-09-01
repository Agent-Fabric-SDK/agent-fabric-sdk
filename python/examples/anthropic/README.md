# Anthropic SDK example

Tier 1.

**What this shows.** A one-line factory call gets you a *native*
`anthropic.AsyncAnthropic` client already pointed at the governed MuleSoft LLM
proxy — `client_id`/`client_secret` header auth (not bearer), attribution
headers, and the SDK's shared transport (retry/telemetry hooks). The returned
object is Anthropic's own client, not a wrapper.

**Divergence, by design (§11.10).** Anthropic's native surface is a *client*,
and the model id is a per-call argument (`c.messages.create(model=..., ...)`),
not a constructor one. So this adapter exposes `client()` rather than the
`model(...)` factory the OpenAI-compatible adapters use.

**Unverified dependency (§8).** The Omni Gateway LLM proxy is verified
OpenAI-compatible; whether it also exposes an **Anthropic-native Messages API
route** is an open M0 verification item. Until confirmed, `client()` emits a
one-time warning and no live call is made. Once a real route is confirmed,
override `base_url` if needed.

## Run

```bash
pip install "mulesoft-agent-fabric[anthropic]"

export MULESOFT_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # note: no /v1
export MULESOFT_LLM_PROXY_CLIENT_ID="<consumer client id>"
export MULESOFT_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"

python examples/anthropic/main.py
```

## The manual equivalent

The factory call is equivalent to building `AsyncAnthropic` yourself with the
governed connection values (§3.1):

```python
import httpx
from anthropic import AsyncAnthropic

c = AsyncAnthropic(
    base_url=MULESOFT_LLM_PROXY_URL,   # UNVERIFIED: needs an Anthropic-native route
    api_key="unused",                  # proxy enforces client_id/client_secret headers
    default_headers={
        "client_id": MULESOFT_LLM_PROXY_CLIENT_ID,
        "client_secret": MULESOFT_LLM_PROXY_CLIENT_SECRET,
    },
    http_client=httpx.AsyncClient(...),  # your own transport, retries, hooks
    max_retries=0,
)
```

The factory (`agent_fabric.integrations.anthropic.client`) fills in `base_url`,
`api_key`, `default_headers`, and the SDK's shared transport from one governed
config source.

## Links

- Anthropic Python SDK: https://github.com/anthropics/anthropic-sdk-python
