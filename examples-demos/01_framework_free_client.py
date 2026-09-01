"""Deliverable #1.1 — the framework-free governed client (LIVE-VERIFIED).

`fabric.llm.client()` returns a native `AsyncOpenAI` aimed at the governed Omni
Gateway proxy. The SDK injects the verified `client_id`/`client_secret` header
pair, attribution headers, and its retry policy — you use the OpenAI SDK exactly
as you normally would.

Run:
    export MULESOFT_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # no /v1
    export MULESOFT_LLM_PROXY_CLIENT_ID="<consumer client id>"
    export MULESOFT_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"
    export DEMO_MODEL="gpt-4o"          # optional; a model your proxy routes
    python examples-demos/01_framework_free_client.py

This makes REAL calls against your proxy. With no credentials set it prints
setup guidance and exits cleanly instead of failing.
"""

# ruff: noqa: I001  (the _paths shim must import before agent_fabric — do not reorder)
from __future__ import annotations

import asyncio
import os

import _paths  # noqa: F401  (dev path shim; harmless with an editable install)

import openai

from agent_fabric import Fabric, PIIDetected, TokenBudgetExceeded
from agent_fabric.core.errors import classify

MODEL = os.environ.get("DEMO_MODEL", "gpt-4o")


def _configured() -> bool:
    return all(
        os.environ.get(v)
        for v in (
            "MULESOFT_LLM_PROXY_URL",
            "MULESOFT_LLM_PROXY_CLIENT_ID",
            "MULESOFT_LLM_PROXY_CLIENT_SECRET",
        )
    )


async def main() -> None:
    if not _configured():
        print(__doc__)
        print(">> Set the three MULESOFT_LLM_PROXY_* env vars to run this live demo.")
        return

    async with Fabric.from_env() as fabric:
        client = fabric.llm.client()  # -> AsyncOpenAI, pointed at the proxy
        print(f"base_url        : {client.base_url}")
        print(f"client_id hdr   : {'client_id' in client.default_headers}")
        print(f"client_secret   : {'client_secret' in client.default_headers}")
        print(f"model           : {MODEL}\n")

        try:
            # --- Chat Completions -------------------------------------------
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": "Say hi in exactly three words."}],
            )
            print("chat.completions ->", resp.choices[0].message.content)

            # --- Responses API, streaming -----------------------------------
            print("\nresponses (stream) -> ", end="", flush=True)
            stream = await client.responses.create(
                model=MODEL, input="Name three primary colors.", stream=True,
            )
            async for event in stream:
                # Print incremental text deltas as they arrive.
                delta = getattr(event, "delta", None)
                if isinstance(delta, str):
                    print(delta, end="", flush=True)
            print()

        # The RAW OpenAI client raises openai.* errors on HTTP failures — the
        # SDK does not silently re-map them. Bridge to the governed taxonomy
        # with classify() on the underlying response (§4/§8.2, same mapping as
        # demo 03). This is how you branch on PII / token-budget / auth outcomes.
        except openai.APIStatusError as e:
            governed = classify(e.response)
            if isinstance(governed, PIIDetected):
                print("PII blocked; entities:", governed.entities)
            elif isinstance(governed, TokenBudgetExceeded):
                print("token budget hit; retry after", governed.retry_after, "s")
            else:
                print(
                    f"openai.{type(e).__name__} ({e.status_code}) "
                    f"-> {type(governed).__name__}: {governed}"
                )
        except openai.APIConnectionError as e:
            print("connection error (no response to classify):", e)


if __name__ == "__main__":
    asyncio.run(main())
