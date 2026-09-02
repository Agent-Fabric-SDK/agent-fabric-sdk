"""Deliverable #1.1 — the framework-free governed client (LIVE-VERIFIED).

`fabric.llm.client()` returns a native `AsyncOpenAI` aimed at the governed Omni
Gateway proxy; `fabric.llm.client(sync=True)` returns the blocking `OpenAI`. Both
are governed on identical terms — the SDK injects the verified
`client_id`/`client_secret` header pair, attribution headers, and its retry
policy — so you use the OpenAI SDK exactly as you normally would.

This demo runs the same three things through each surface, so you can see that
the only difference is `await`.

Run:
    export AGENT_FABRIC_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"   # no /v1
    export AGENT_FABRIC_LLM_PROXY_CLIENT_ID="<consumer client id>"
    export AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"
    export DEMO_MODEL="gpt-4o"          # optional; a model your proxy routes
    python demos/deliverables/01_framework_free_client.py

This makes REAL calls against your proxy. With no credentials set it prints
setup guidance and exits cleanly instead of failing.
"""

# ruff: noqa: I001, E402  (the _paths shim must import before agent_fabric — do not reorder)
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # demos/ (holds _paths.py)
import _paths  # noqa: F401  (dev path shim; harmless with an editable install)

import openai

from agent_fabric import Fabric, PIIDetected, TokenBudgetExceeded
from agent_fabric.core.errors import classify

MODEL = os.environ.get("DEMO_MODEL", "gpt-4o")
PROMPT = "Say hi in exactly three words."
STREAM_PROMPT = "Name three primary colors."


def _configured() -> bool:
    return all(
        os.environ.get(v)
        for v in (
            "AGENT_FABRIC_LLM_PROXY_URL",
            "AGENT_FABRIC_LLM_PROXY_CLIENT_ID",
            "AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET",
        )
    )


def _describe(label: str, client: openai.OpenAI | openai.AsyncOpenAI) -> None:
    print(f"\n=== {label} — {type(client).__name__} ===")
    print(f"base_url        : {client.base_url}")
    print(f"client_id hdr   : {'client_id' in client.default_headers}")
    print(f"client_secret   : {'client_secret' in client.default_headers}")
    print(f"model           : {MODEL}")


def _report(error: openai.APIStatusError) -> None:
    """The RAW OpenAI client raises openai.* errors on HTTP failures — the SDK
    does not silently re-map them. Bridge to the governed taxonomy with
    classify() on the underlying response (§4/§8.2, same mapping as demo 03).
    Identical for both clients: same exception, same classify() call."""

    governed = classify(error.response)
    if isinstance(governed, PIIDetected):
        print("PII blocked; entities:", governed.entities)
    elif isinstance(governed, TokenBudgetExceeded):
        print("token budget hit; retry after", governed.retry_after, "s")
    else:
        print(
            f"openai.{type(error).__name__} ({error.status_code}) "
            f"-> {type(governed).__name__}: {governed}"
        )


def run_sync() -> None:
    """The blocking surface: no event loop, no await."""

    with Fabric.from_env() as fabric:
        client = fabric.llm.client(sync=True)  # -> openai.OpenAI at the proxy
        _describe("sync", client)

        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": PROMPT}],
            )
            print("chat.completions ->", resp.choices[0].message.content)

            print("chat (stream)    -> ", end="", flush=True)
            for chunk in client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": STREAM_PROMPT}],
                stream=True,
            ):
                # The final usage chunk carries no choices.
                if chunk.choices and chunk.choices[0].delta.content:
                    print(chunk.choices[0].delta.content, end="", flush=True)
            print()

        except openai.APIStatusError as e:
            _report(e)
        except openai.APIConnectionError as e:
            print("connection error (no response to classify):", e)


async def run_async() -> None:
    """The default surface. Same calls, same governance, with await."""

    async with Fabric.from_env() as fabric:
        client = fabric.llm.client()  # -> openai.AsyncOpenAI at the proxy
        _describe("async", client)

        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": PROMPT}],
            )
            print("chat.completions ->", resp.choices[0].message.content)

            # The Responses API is the live-verified route on this proxy (§2).
            print("responses (stream) -> ", end="", flush=True)
            stream = await client.responses.create(
                model=MODEL, input=STREAM_PROMPT, stream=True,
            )
            async for event in stream:
                delta = getattr(event, "delta", None)
                if isinstance(delta, str):
                    print(delta, end="", flush=True)
            print()

        except openai.APIStatusError as e:
            _report(e)
        except openai.APIConnectionError as e:
            print("connection error (no response to classify):", e)


if __name__ == "__main__":
    if not _configured():
        print(__doc__)
        print(">> Set the three AGENT_FABRIC_LLM_PROXY_* env vars to run this live demo.")
    else:
        run_sync()
        asyncio.run(run_async())
