# CrewAI example

Tier 1.

**What this shows.** A one-line factory call gets you a *native* `crewai.LLM`
already pointed at the governed MuleSoft LLM proxy — correct base URL,
`client_id`/`client_secret` header auth (not bearer), and attribution headers.
The returned object is CrewAI's own class, not a wrapper, so it drops straight
into a `crewai` `Agent`/`Crew`.

`crewai.LLM` wraps LiteLLM, so the OpenAI-compatible route uses the `openai/`
model prefix and headers go via `extra_headers`. LiteLLM owns the transport, so
the SDK's per-run correlation ID degrades to per-client — a documented
conformance exemption (§8.1), the same one ADK has.

## Run

```bash
pip install "mulesoft-agent-fabric[crewai]"

export MULESOFT_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # note: no /v1
export MULESOFT_LLM_PROXY_CLIENT_ID="<consumer client id>"
export MULESOFT_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"

python examples/crewai/main.py
```

## The manual equivalent

The factory call is equivalent to building `crewai.LLM` yourself with the
governed connection values (§3.1):

```python
from crewai import LLM

model = LLM(
    model="openai/gpt-4o",          # LiteLLM's OpenAI-compatible route
    base_url=MULESOFT_LLM_PROXY_URL,
    api_key="unused",               # proxy enforces client_id/client_secret headers
    extra_headers={
        "client_id": MULESOFT_LLM_PROXY_CLIENT_ID,
        "client_secret": MULESOFT_LLM_PROXY_CLIENT_SECRET,
    },
)
```

The factory (`agent_fabric.integrations.crewai.llm`) fills in the `openai/`
prefix, `base_url`, `api_key`, and `extra_headers` from one governed config
source.

## Links

- CrewAI docs: https://docs.crewai.com/
