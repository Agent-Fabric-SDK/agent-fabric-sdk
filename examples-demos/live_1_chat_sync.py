"""Live-coding scratchpad — the same governed call as live_1_chat.py, blocking.

`sync=True` returns a real `openai.OpenAI` instead of `AsyncOpenAI`, governed on
identical terms. No event loop, no `await`, and nothing to forget awaiting.

Every `.` gives full IntelliSense — the two forms are typed overloads, so the
call site narrows to one concrete class rather than a union:

    fabric.llm.client()            -> openai.AsyncOpenAI
    fabric.llm.client(sync=True)   -> openai.OpenAI
    client.                        -> the whole OpenAI surface

Drop the `_paths` line if you have already exported the three
AGENT_FABRIC_LLM_PROXY_* variables in your shell.
"""

# ruff: noqa: I001  (the _paths shim must import before agent_fabric — do not reorder)
import _paths  # noqa: F401  (loads examples-demos/.env.local into the environment)

from agent_fabric import Fabric

with Fabric.from_env() as fabric:
    client = fabric.llm.client(sync=True)
    reply = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Say hi in three words."}],
    )
    print(reply.choices[0].message.content)
