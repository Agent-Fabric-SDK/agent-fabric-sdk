"""Live-coding scratchpad — a governed chat completion, in as few lines as it goes.

Type this out on camera. Every `.` gives full IntelliSense:

    fabric.        -> llm, langgraph, adk, strands, anthropic, crewai, …
    fabric.llm.    -> client(), resolve(), list_models()
    client.        -> the whole AsyncOpenAI surface (chat, responses, embeddings…)

Drop the `_paths` line if you have already exported the three
MULESOFT_LLM_PROXY_* variables in your shell.
"""

# ruff: noqa: I001  (the _paths shim must import before agent_fabric — do not reorder)
import asyncio

import _paths  # noqa: F401  (loads examples-demos/.env.local into the environment)

from agent_fabric import Fabric


async def main() -> None:
    async with Fabric.from_env() as fabric:
        client = fabric.llm.client()
        reply = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Say hi in three words."}],
        )
        print(reply.choices[0].message.content)


asyncio.run(main())
