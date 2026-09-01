"""Deliverable #1.4 — model capability handles without a /models endpoint.

The governed proxy has NO catalog endpoint (`GET /models` -> 404, verified §2):
model-based-routing only routes requests that carry `model` in the body. So the
SDK never fabricates a /models path. Instead:

  * `fabric.llm.resolve(id)` returns a heuristic capability handle for a known id.
  * `fabric.llm.list_models(live=True)` raises a clear ConfigError explaining the
    proxy exposes no catalog — rather than guessing an endpoint.

Run (no credentials or network needed):
    python examples-demos/04_model_handles.py
"""

# ruff: noqa: I001  (the _paths shim must import before agent_fabric — do not reorder)
from __future__ import annotations

import asyncio

import _paths  # noqa: F401

from agent_fabric import Fabric
from agent_fabric.core.errors import ConfigError


async def main() -> None:
    fabric = Fabric.from_env()  # lazy; needs no creds until you call the proxy

    print("Heuristic capability handles via resolve():\n")
    for model_id in ("gpt-4o", "gpt-4o-mini", "o3", "claude-3-5-sonnet"):
        handle = fabric.llm.resolve(model_id)
        print(f"  {model_id:<20} {handle.capabilities}")

    print("\nlist_models(live=True) is honest about the missing catalog endpoint:\n")
    try:
        await fabric.llm.list_models(live=True)  # never returns; no /models on the proxy
    except ConfigError as e:
        print(f"  ConfigError: {e}")


if __name__ == "__main__":
    asyncio.run(main())
