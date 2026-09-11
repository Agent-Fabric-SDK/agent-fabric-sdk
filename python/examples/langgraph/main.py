"""LangGraph adapter example — the one deep, conformance-gated adapter (BG §1.8).

Two things live here, both against a **real** LangGraph app (a compiled
``StateGraph``), not a bare model call:

* :func:`build` — a conformance-able agent factory. Given a :class:`Donkey`, it
  wires a small two-node graph (``prepare`` → ``call_model``) and returns an
  object with an awaitable ``run(text)``. This is exactly the shape the
  customer-facing conformance plugin drives
  (``pytest --donkey-conformance --agent=examples.langgraph.main:build``), and
  the SDK's own ``tests/conformance/test_langgraph_conformance.py`` runs the
  four scenarios against it.
* :func:`main` — a runnable demo: build the agent from the environment and make
  one live governed call.

What the graph demonstrates (the #198 acceptance criteria):

* **AC2 — correlation reaches every node.** ``prepare`` logs
  ``current_correlation_id()`` without it ever being threaded through graph
  state; a run id bound with ``donkey.run(id=…)`` shows up there for free
  because LangGraph runs nodes on context-copying ``asyncio`` tasks (#195).
* **AC3 — typed refusals inside a node.** ``call_model`` wraps ``model.ainvoke``
  in :func:`~donkey_kit.integrations.langgraph.typed_refusals`, so a proxy
  refusal surfaces out of ``graph.ainvoke`` as the typed
  :class:`~donkey_kit.core.errors.DonkeyError` (e.g. ``PIIDetected``), not a
  framework-wrapped generic error.

Honest status (§0.3/§8): the proxy *contract* (base URL, client_id/secret auth,
attribution headers) is live-verified. ``ChatOpenAI``/``StateGraph`` are the
frameworks' own classes and ``.ainvoke`` is their documented API — construction
via the SDK factory is the verified surface; everything after is the
frameworks' own runtime.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from donkey_kit import Donkey
from donkey_kit.core.errors import ConfigError
from donkey_kit.core.telemetry import current_correlation_id
from donkey_kit.integrations.langgraph import typed_refusals

logger = logging.getLogger("examples.langgraph")


class State(TypedDict):
    """Graph state. The ``add_messages`` reducer accumulates turns across nodes,
    so a node that returns no message update (like ``prepare``) doesn't drop the
    conversation — untyped ``dict`` state would only carry the last node's
    return."""

    messages: Annotated[list, add_messages]


class TriageAgent:
    """Minimal agent surface the conformance harness drives: an awaitable
    ``run(text)`` that pushes one turn through the compiled graph."""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    async def run(self, text: str) -> Any:
        return await self._graph.ainvoke({"messages": [("user", text)]})


async def _prepare(_state: State) -> dict:
    """First node: emit the run's correlation id into our own logs (AC2). The id
    is read from the contextvar, never from graph state — proving it propagated
    into the node on its own."""
    logger.info("triage: preparing", extra={"correlation_id": current_correlation_id()})
    return {}


def build(donkey: Donkey) -> TriageAgent:
    """Wire the two-node graph against ``donkey``'s governed transport and return
    the agent. Uses ``donkey.langgraph`` (not the module-level factory) so the
    model shares this ``Donkey``'s HTTP client — which is what lets the
    conformance harness swap a fixture transport in and have the node observe
    it."""
    model = donkey.langgraph.chat_model(os.environ.get("DEMO_MODEL", "gpt-4o"))

    async def _call_model(state: State) -> dict:
        # A proxy refusal raised here comes back typed, not framework-wrapped (AC3).
        with typed_refusals():
            reply = await model.ainvoke(state["messages"])
        return {"messages": [reply]}  # add_messages appends to the running list

    builder = StateGraph(State)
    builder.add_node("prepare", _prepare)
    builder.add_node("call_model", _call_model)
    builder.set_entry_point("prepare")
    builder.add_edge("prepare", "call_model")
    builder.add_edge("call_model", END)
    return TriageAgent(builder.compile())


def _missing_env() -> list[str]:
    names = (
        "DONKEY_LLM_PROXY_URL",
        "DONKEY_LLM_PROXY_CLIENT_ID",
        "DONKEY_LLM_PROXY_CLIENT_SECRET",
    )
    return [n for n in names if not os.environ.get(n)]


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    missing = _missing_env()
    if missing:
        print("Set the following environment variables and re-run:")
        print('    export DONKEY_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"  # no /v1')
        print('    export DONKEY_LLM_PROXY_CLIENT_ID="<consumer client id>"')
        print('    export DONKEY_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"')
        return

    async with Donkey.from_env() as donkey:
        try:
            agent = build(donkey)
        except ImportError:
            print('LangGraph not installed. Install it with:')
            print('    pip install "donkey-kit[langgraph]"')
            return
        except ConfigError as e:
            print(f"Config error: {e}")
            return

        # Bind a run id once; it reaches every node via the contextvar (AC2).
        try:
            async with donkey.run(id="langgraph-example"):
                result = await agent.run("Say hi in three words.")
            reply = result["messages"][-1]
            print(f"Model reply: {getattr(reply, 'content', reply)}")
        except Exception as e:  # noqa: BLE001 — surface any runtime/network failure clearly
            print(f"Inference call failed ({type(e).__name__}: {e}).")
            print("Construction succeeded; check proxy connectivity/credentials.")


if __name__ == "__main__":
    asyncio.run(main())
