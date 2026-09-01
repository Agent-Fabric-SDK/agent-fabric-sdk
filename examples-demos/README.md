# examples-demos

Runnable demos of **"What users can now do with #1"** — the live-verified LLM
data-plane wiring (base URL, `client_id`/`client_secret` consumer auth,
attribution, error contract) exposed through the framework-free client and the
eight framework adapters.

| Demo | Deliverable | Needs creds? | Network? |
|------|-------------|--------------|----------|
| [`01_framework_free_client.py`](01_framework_free_client.py) | Framework-free `fabric.llm.client()` — chat + streaming | ✅ | ✅ live |
| [`02_native_framework_objects.py`](02_native_framework_objects.py) | Native objects for all 8 frameworks (`fabric.langgraph.chat_model`, …) | ✅ | ❌ builds objects only |
| [`03_governed_error_taxonomy.py`](03_governed_error_taxonomy.py) | The 4 proxy rejections → typed exceptions via `classify()` | ❌ | ❌ uses committed live fixtures |
| [`04_model_handles.py`](04_model_handles.py) | `resolve()` handles; honest `list_models(live=True)` | ❌ | ❌ |

Demos **03** and **04** run offline with no setup — start there.

## Setup

```bash
# From the repo root. Editable install is preferred; the demos also fall back to
# a dev path shim (_paths.py) so they run straight from a checkout.
pip install -e "python[llm]"                 # + e.g. python[langgraph] for demo 02

# Governed model access (demos 01 and 02). The proxy authenticates on a
# client_id/client_secret HEADER PAIR — not a bearer token.
export MULESOFT_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # note: no /v1
export MULESOFT_LLM_PROXY_CLIENT_ID="<consumer client id>"
export MULESOFT_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"
export DEMO_MODEL="gpt-4o"                    # optional; a model your proxy routes
```

## Run

```bash
python examples-demos/03_governed_error_taxonomy.py   # offline, deterministic
python examples-demos/04_model_handles.py             # offline
python examples-demos/01_framework_free_client.py     # live (needs creds)
python examples-demos/02_native_framework_objects.py  # needs creds + framework extras
```

Every demo runs cleanly with missing prerequisites: no credentials → setup
guidance and a clean exit; a framework extra not installed → the curated
`ImportError` with the exact `pip install` command.

## Honest status (§0.3)

The proxy **contract** these demos exercise is live-verified (see
[`docs/verified-apis.md`](../docs/verified-apis.md) §2–§4). The exact framework
class names/kwargs in demo 02 are still being confirmed against installed
versions (§8); Tier-1 adapters raise a clear "blocked on verification" error
rather than guess. Tool discovery and provisioning are not part of #1.
