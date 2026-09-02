# Recording runbook — Agent Fabric SDK

Three acts: the documentation site, then two short scripts written live in the
editor. Both scripts run against a real Anypoint sandbox — nothing is mocked.

| Act | On screen | Time |
|-----|-----------|------|
| 1 | Docs site at `localhost:3000` | ~3 min |
| 2 | `demo_1_chat_completions.py` — the plain OpenAI SDK, governed | ~3 min |
| 3 | `demo_2_langgraph_agent.py` — the same governance in LangGraph | ~3 min |

## Before you hit record

```bash
# Dependencies (once)
pip install -e "python[llm,langgraph]" langgraph langchain

# Credentials — examples-demos/.env.local, git-ignored, loaded by _paths.py
#   AGENT_FABRIC_LLM_PROXY_URL / _CLIENT_ID / _CLIENT_SECRET

# Docs site
cd docs-site && npm install && npm run dev      # http://localhost:3000

# Smoke test everything before recording
python examples-demos/demo_1_chat_completions.py
python examples-demos/demo_2_langgraph_agent.py
python examples-demos/live_1_chat.py
python examples-demos/live_2_langgraph.py
```

## Typing it live

`demo_1` and `demo_2` are the *narrated* scripts — they print the governed
plumbing, and Acts 2 and 3 below walk through their output. If you would rather
type code on camera than run a file, use the two scratchpads instead:

| File | Lines of code | Shape |
|------|---------------|-------|
| `live_1_chat.py` | 9 | `chat.completions` through `AsyncOpenAI` |
| `live_1_chat_sync.py` | 7 | the same call through the blocking `OpenAI` — no asyncio |
| `live_2_langgraph.py` | 3 | a governed `ChatOpenAI`, no asyncio either |

If you would rather not explain `async`/`await` on camera, start from
`live_1_chat_sync.py`. `fabric.llm.client(sync=True)` returns the blocking
`openai.OpenAI`, governed identically, which removes the event loop and the
coroutine you can forget to await.

Showing both is the stronger beat, though: type the sync version, then change one
argument to get the async one. It makes the point that this is a transport swap,
not a different product — and the overloads mean the editor re-narrows the
return type from `OpenAI` to `AsyncOpenAI` as you type, live on screen.

Both are fully typed end to end, so every `.` opens a real completion list —
this is the part worth showing, because it is the argument that the SDK returns
native objects rather than wrappers:

- `fabric.` → `llm`, `langgraph`, `adk`, `strands`, `anthropic`, `crewai`, …
- `fabric.llm.` → `client()`, `resolve()`, `list_models()`
- `client.` → the entire `AsyncOpenAI` surface, because it *is* an `AsyncOpenAI`
- `model.` → the entire `ChatOpenAI` surface, for the same reason

If a completion list fails to appear, the language server has gone stale rather
than the types being wrong — **Cmd+Shift+P → Developer: Reload Window** fixes
it. Confirm the interpreter in the status bar is Python 3.13 (Framework build);
the workspace already pins it in `.vscode/settings.json`. Consider turning off
Cursor's Tab suggestions while recording, so ghost text does not sit on top of
the completion popup you are trying to point at.

## Act 1 — The documentation site

Open `http://localhost:3000`.

1. **Landing page** — read the opening line aloud: consume Agent Fabric
   capabilities *from your own agent framework, in your own IDE, without
   adopting Mule*. Then scroll to **The one design rule** — adapters return the
   framework's native object, never a wrapper. Acts 2 and 3 demonstrate that
   one sentence.
2. **Make a governed call** — click the Python / TypeScript / cURL tabs. The
   proxy is OpenAI-compatible HTTP, so the SDK is a convenience, not a lock-in.
3. **The three pillars** — model access is live; tool access and
   provisioning-as-code are roadmap. Say so plainly.
4. **Verification policy** (`/concepts/verification`) — unverified endpoints
   raise `NotImplementedError("blocked on verification: …")` rather than guess.
   Worth dwelling on for a technical audience.
5. **Frameworks → LangGraph** (`/frameworks/langgraph`) — show **The manual
   equivalent**, the eject hatch that Act 3 prints live.
6. **Error taxonomy** (`/errors`) — leave this open in a tab; Act 2 makes one of
   these rejections happen for real.

## Act 2 — Governed `chat.completions`

```bash
python examples-demos/demo_1_chat_completions.py
```

Five things print, in order:

- **The client.** A real `openai.AsyncOpenAI` pointed at the gateway, with
  `client_id` / `client_secret` injected. A header **pair**, not a bearer token,
  and no `/v1` on the base URL — both verified against the sandbox.
- **A completion.** Ordinary OpenAI SDK code, governed at the edge.
- **A stream.** A governed hop does not cost you streaming.
- **A rejection.** An unknown model returns HTTP 404, and `classify()` turns it
  into a typed `UpstreamRequestError` — the provider's mistake passed through,
  explicitly *not* a gateway policy refusal. This is the beat that sells it; cut
  to the `/errors` tab here.
- **The same thing, blocking.** `client(sync=True)` prints `openai.OpenAI` and
  the same two injected headers. Worth one sentence: governance lives in the
  transport, so it does not care whether you brought an event loop.

## Act 3 — The same governance in LangGraph

```bash
python examples-demos/demo_2_langgraph_agent.py
```

- **The model** is a genuine `langchain_openai.ChatOpenAI`. Not a wrapper.
- **`connection_kwargs()`** prints the exact constructor arguments the factory
  used, so you can build `ChatOpenAI` yourself and drop the SDK at any time.
  Tie this back to *The manual equivalent* from Act 1.
- **The tools** are ordinary `@tool` functions. The SDK governs model hops, not
  your code.
- **The agent runs live** — it plans, calls both tools in one turn, then
  synthesises. Each of those model hops left through the gateway authenticated
  and metered.

Close on the three pillars: governed model access is live and verified today;
tool access and provisioning-as-code are roadmap, with the SDK refusing to guess
until those APIs are confirmed.

## If something goes wrong on camera

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ConfigError` listing the three env vars | `.env.local` missing or misplaced | It must sit in `examples-demos/` or the repo root |
| `ImportError` on `langchain.agents` | `langchain` meta-package missing | `pip install langchain` |
| Docs site on a different port | Port 3000 taken | Next.js prints the real port at startup |
