# Demos

Runnable demos of **"What users can now do with #1"** — the live-verified LLM
data-plane wiring (base URL, `client_id`/`client_secret` consumer auth,
attribution, error contract) exposed through the framework-free client and the
eight framework adapters.

These are scenario/presentation demos, grouped by **purpose**. For the
per-framework *reference* snippets (one `main.py` per framework, CI-gated), see
[`python/examples/`](../python/examples/) instead.

```
demos/
  smoke.py            # smallest live check: one governed chat.completions call
  deliverables/       # the "what you can do with #1" walkthrough (start here)
  recordings/         # screen-recording scripts + the runbook (DEMO.md)
  scratchpads/        # minimal snippets to type live on camera
```

## Deliverables — `deliverables/`

The headline walkthrough. Demos **03** and **04** run offline with no setup —
start there.

| Demo | Deliverable | Needs creds? | Network? |
|------|-------------|--------------|----------|
| [`deliverables/01_framework_free_client.py`](deliverables/01_framework_free_client.py) | Framework-free `fabric.llm.client()` — chat + streaming, through **both** the async and the blocking (`sync=True`) client | ✅ | ✅ live |
| [`deliverables/02_native_framework_objects.py`](deliverables/02_native_framework_objects.py) | Native objects for all 8 frameworks (`fabric.langgraph.chat_model`, …) | ✅ | ❌ builds objects only |
| [`deliverables/03_governed_error_taxonomy.py`](deliverables/03_governed_error_taxonomy.py) | The 4 proxy rejections → typed exceptions via `classify()` | ❌ | ❌ uses committed live fixtures |
| [`deliverables/04_model_handles.py`](deliverables/04_model_handles.py) | `resolve()` handles; honest `list_models(live=True)` | ❌ | ❌ |

## Recordings — `recordings/`

Two short scripts for a screen recording — small enough to write live on camera,
and they just print to the terminal.

| Demo | Shows | Needs creds? |
|------|-------|--------------|
| [`recordings/demo_1_chat_completions.py`](recordings/demo_1_chat_completions.py) | Governed `chat.completions` + streaming with the plain OpenAI SDK, a live 404 becoming a typed exception, then the same call blocking via `sync=True` | ✅ live |
| [`recordings/demo_2_langgraph_agent.py`](recordings/demo_2_langgraph_agent.py) | The same governance inside a live LangGraph tool-calling agent | ✅ live |

[`recordings/DEMO.md`](recordings/DEMO.md) is the recording runbook: setup, a
three-act structure covering the docs site plus both scripts, and a
troubleshooting table.

## Scratchpads — `scratchpads/`

Minimal versions to type on camera. Each is fully typed, so every `.` opens a
real completion list.

| File | Lines of code | Shape |
|------|---------------|-------|
| [`scratchpads/live_1_chat.py`](scratchpads/live_1_chat.py) | 9 | `chat.completions` through `AsyncOpenAI` |
| [`scratchpads/live_1_chat_sync.py`](scratchpads/live_1_chat_sync.py) | 7 | the same call through the blocking `OpenAI` (`sync=True`) — no asyncio |
| [`scratchpads/live_2_langgraph.py`](scratchpads/live_2_langgraph.py) | 3 | a governed `ChatOpenAI`, no asyncio either |

## Setup

```bash
# From the repo root. Editable install is preferred; the demos also fall back to
# a dev path shim (_paths.py) so they run straight from a checkout.
pip install -e "python[llm]"                 # + e.g. python[langgraph] for demo 02

# Governed model access (demos 01 and 02). The proxy authenticates on a
# client_id/client_secret HEADER PAIR — not a bearer token.
export AGENT_FABRIC_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # note: no /v1
export AGENT_FABRIC_LLM_PROXY_CLIENT_ID="<consumer client id>"
export AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"
export DEMO_MODEL="gpt-4o"                    # optional; a model your proxy routes
```

`_paths.py` also auto-loads a git-ignored `demos/.env.local` (then `.env`) from
this directory or the repo root, so the `export`s above are optional on your own
machine — a shell `export` always wins over a file value.

## Run

```bash
python demos/deliverables/03_governed_error_taxonomy.py   # offline, deterministic
python demos/deliverables/04_model_handles.py             # offline
python demos/deliverables/01_framework_free_client.py     # live (needs creds)
python demos/deliverables/02_native_framework_objects.py  # needs creds + framework extras
python demos/smoke.py                                     # smallest live check
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
