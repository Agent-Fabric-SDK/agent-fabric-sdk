"""DEMO 1 — governed chat.completions with the plain OpenAI SDK.

    python demos/recordings/demo_1_chat_completions.py

Credentials come from demos/.env.local (loaded by _paths).
"""

# ruff: noqa: I001, E402  (the _paths shim must import before agent_fabric — do not reorder)
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # demos/ (holds _paths.py)
import _paths  # noqa: F401  (dev path shim + .env.local loader)

import openai

from agent_fabric import Fabric
from agent_fabric.core.errors import classify

MODEL = "gpt-4o"


async def main() -> None:
    async with Fabric.from_env() as fabric:
        client = fabric.llm.client()  # a real openai.AsyncOpenAI, at the governed proxy
        
        print("client   :", type(client).__module__ + "." + type(client).__name__)
        print("base_url :", client.base_url)
        # The rest of default_headers is the OpenAI SDK's own; these two are ours.
        print("injected :", [h for h in client.default_headers if h.startswith("client_")])

        # --- 1. a governed chat completion --------------------------------
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Say hi in three words."}],
        )
        print("\nreply    :", resp.choices[0].message.content)
        print("tokens   :", resp.usage.total_tokens if resp.usage else "?")

        # --- 2. streaming still works -------------------------------------
        print("\nstream   : ", end="", flush=True)
        stream = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Count to five."}],
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print()

        # --- 3. gateway rejections become typed exceptions ----------------
        try:
            await client.chat.completions.create(
                model="not-a-real-model",
                messages=[{"role": "user", "content": "hello"}],
            )
        except openai.APIStatusError as e:
            governed = classify(e.response)
            print(f"\nrejected : HTTP {e.status_code} -> {type(governed).__name__}")
            print("detail   :", governed)


def without_asyncio() -> None:
    """--- 4. the same governance, blocking ------------------------------

    sync=True swaps AsyncOpenAI for OpenAI and the async transport for its
    blocking twin. Same base URL, same injected headers, same correlation ID and
    retry policy — the only thing that goes away is the event loop.
    """

    with Fabric.from_env() as fabric:
        client = fabric.llm.client(sync=True)

        print("\nclient   :", type(client).__module__ + "." + type(client).__name__)
        print("injected :", [h for h in client.default_headers if h.startswith("client_")])

        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Say hi in three words."}],
        )
        print("reply    :", resp.choices[0].message.content)


asyncio.run(main())
without_asyncio()
