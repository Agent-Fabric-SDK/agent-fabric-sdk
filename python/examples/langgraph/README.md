# LangGraph example

Deep adapter — conformance-tested (BG §1.8).

**What this shows.** A real, two-node LangGraph app (`prepare` → `call_model`,
a compiled `StateGraph`) — not a bare model call — built against the governed
Agent Fabric LLM proxy. `build(donkey)` is a **conformance-able agent factory**:
it returns an object with an awaitable `run(text)`, which is exactly the shape
the customer-facing conformance plugin drives (and the SDK's own
`tests/conformance/test_langgraph_conformance.py` runs the four scenarios
against). `main()` then builds the agent from the environment and makes one live
governed call.

The model itself is a *native* `langchain_openai.ChatOpenAI` pointed at the
proxy — correct base URL (no `/v1`), `client_id`/`client_secret` header auth (not
bearer), attribution headers, the SDK's shared transport (retry/telemetry
hooks), and `use_responses_api=True` (the proxy's live-verified `/responses`
data plane). It's LangGraph/LangChain's own class, not a wrapper, so it drops
straight into any graph or chain.

The graph demonstrates the two deep-adapter guarantees this example exists to
prove (#198):

- **Correlation reaches every node for free (AC2).** `prepare` logs
  `current_correlation_id()` without it ever being threaded through graph
  state — a run id bound with `donkey.run(id=…)` shows up there because
  LangGraph runs nodes on context-copying `asyncio` tasks (#195).
- **Typed refusals inside a node (AC3).** `call_model` wraps `model.ainvoke`
  in `typed_refusals()`, so a proxy refusal surfaces out of `graph.ainvoke`
  as the SDK's typed `DonkeyError` (e.g. `PIIDetected`), not a
  framework-wrapped generic error.

> 📖 **Prefer reading to running?** The canonical walkthrough — install,
> configure, and the manual equivalent — is in the docs:
> **[LangGraph](https://donkey-development-kit.github.io/donkey-development-kit/frameworks/langgraph)**.
> This README duplicates the runnable essentials on purpose so you can run it in
> place; if the two ever differ, the docs page is canonical.

## Run

```bash
pip install "donkey-kit[langgraph]"

export DONKEY_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # note: no /v1
export DONKEY_LLM_PROXY_CLIENT_ID="<consumer client id>"
export DONKEY_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"

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
    base_url=DONKEY_LLM_PROXY_URL,
    api_key="unused",  # the proxy enforces client_id/client_secret headers instead
    default_headers={
        "client_id": DONKEY_LLM_PROXY_CLIENT_ID,
        "client_secret": DONKEY_LLM_PROXY_CLIENT_SECRET,
    },
    http_async_client=httpx.AsyncClient(...),  # your own transport, retries, hooks
    max_retries=0,
    use_responses_api=True,  # the proxy's live-verified data plane is /responses
)
```

The factory (`donkey_kit.integrations.langgraph.chat_model`) fills in
`base_url`, `api_key`, `default_headers`, `http_async_client`, and
`use_responses_api` from one governed config source and gives you the SDK's
shared transport (with its retry policy and telemetry hooks) for free. Pass
`use_responses_api=False` only if a deployment exposes chat-completions instead
— `/responses` is the endpoint verified against a live proxy.

## Links

- LangGraph docs: https://langchain-ai.github.io/langgraph/
- LangChain `ChatOpenAI` docs: see the framework's official documentation
