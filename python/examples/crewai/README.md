# CrewAI example

Tier 1.

**What this shows.** A one-line factory call gets you a *native* `crewai.LLM`
already pointed at the governed Agent Fabric LLM proxy — correct base URL,
`client_id`/`client_secret` header auth (not bearer), and attribution headers.
The returned object is CrewAI's own class, not a wrapper, so it drops straight
into a `crewai` `Agent`/`Crew`.

`crewai.LLM` wraps LiteLLM, so the OpenAI-compatible route uses the `openai/`
model prefix and headers go via `extra_headers`. LiteLLM owns the transport, so
the SDK's per-run correlation ID degrades to per-client — a documented
conformance exemption (§8.1), the same one ADK has.

> 📖 **Prefer reading to running?** The canonical walkthrough — install,
> configure, and the manual equivalent — is in the docs:
> **[CrewAI](https://agent-fabric-sdk.github.io/agent-fabric-sdk/frameworks/crewai)**.
> This README duplicates the runnable essentials on purpose so you can run it in
> place; if the two ever differ, the docs page is canonical.

## Run

```bash
pip install "agent-fabric[crewai]"

export AGENT_FABRIC_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # note: no /v1
export AGENT_FABRIC_LLM_PROXY_CLIENT_ID="<consumer client id>"
export AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"

python examples/crewai/main.py
```

## The manual equivalent

The factory call is equivalent to building `crewai.LLM` yourself with the
governed connection values (§3.1):

```python
from crewai import LLM

model = LLM(
    model="openai/gpt-4o",          # LiteLLM's OpenAI-compatible route
    base_url=AGENT_FABRIC_LLM_PROXY_URL,
    api_key="unused",               # proxy enforces client_id/client_secret headers
    extra_headers={
        "client_id": AGENT_FABRIC_LLM_PROXY_CLIENT_ID,
        "client_secret": AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET,
    },
)
```

The factory (`agent_fabric.integrations.crewai.llm`) fills in the `openai/`
prefix, `base_url`, `api_key`, and `extra_headers` from one governed config
source.

## Links

- CrewAI docs: https://docs.crewai.com/
