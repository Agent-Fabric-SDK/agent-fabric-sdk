# OpenAI Agents SDK example

Tier 1.

**What this shows.** A one-line factory call gets you a *native*
`agents.OpenAIChatCompletionsModel` already pointed at the governed Agent Fabric LLM
proxy. Because the adapter builds the underlying `AsyncOpenAI` client itself,
header **and** transport injection are both available (full injection) — correct
base URL, `client_id`/`client_secret` header auth (not bearer), attribution
headers, and the SDK's shared transport (retry/telemetry hooks). The returned
object is the OpenAI Agents SDK's own class, not a wrapper, so it drops straight
into `agents.Agent(model=...)`.

> 📖 **Prefer reading to running?** The canonical walkthrough — install,
> configure, and the manual equivalent — is in the docs:
> **[OpenAI Agents SDK](https://agent-fabric-sdk.github.io/agent-fabric-sdk/frameworks/openai)**.
> This README duplicates the runnable essentials on purpose so you can run it in
> place; if the two ever differ, the docs page is canonical.

## Run

```bash
pip install "agent-fabric[openai]"

export AGENT_FABRIC_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # note: no /v1
export AGENT_FABRIC_LLM_PROXY_CLIENT_ID="<consumer client id>"
export AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"

python examples/openai/main.py
```

## The manual equivalent

The factory call is equivalent to building the model yourself with the governed
connection values (§3.1):

```python
import httpx
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel

m = OpenAIChatCompletionsModel(
    model="gpt-4o",
    openai_client=AsyncOpenAI(
        base_url=AGENT_FABRIC_LLM_PROXY_URL,
        api_key="unused",  # proxy enforces client_id/client_secret headers
        default_headers={
            "client_id": AGENT_FABRIC_LLM_PROXY_CLIENT_ID,
            "client_secret": AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET,
        },
        http_client=httpx.AsyncClient(...),  # your own transport, retries, hooks
        max_retries=0,
    ),
)
```

The factory (`agent_fabric.integrations.openai_agents.model`) fills in the
`AsyncOpenAI` client, headers, and the SDK's shared transport from one governed
config source.

## Links

- OpenAI Agents SDK docs: https://openai.github.io/openai-agents-python/
