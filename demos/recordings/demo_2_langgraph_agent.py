"""DEMO 2 — the same governance, inside a LangGraph agent.

    python demos/recordings/demo_2_langgraph_agent.py

Credentials come from demos/.env.local (loaded by _paths).
"""

# ruff: noqa: I001, E402  (the _paths shim must import before agent_fabric — do not reorder)
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # demos/ (holds _paths.py)
import _paths  # noqa: F401  (dev path shim + .env.local loader)

from langchain.agents import create_agent
from langchain_core.tools import tool

from agent_fabric import Fabric

MODEL = "gpt-4o-mini"
QUESTION = "Can I ship SKU AF-1001 today, and what does it cost?"


@tool
def check_inventory(sku: str) -> str:
    """Return the units in stock and warehouse for a product SKU."""
    return {"AF-1001": "42 units in Amsterdam", "AF-2002": "0 units"}.get(sku, "unknown SKU")


@tool
def get_price(sku: str) -> str:
    """Return the list price for a product SKU."""
    return {"AF-1001": "EUR 129.00", "AF-2002": "EUR 89.50"}.get(sku, "unknown SKU")


async def main() -> None:
    async with Fabric.from_env() as fabric:
        model = fabric.langgraph.chat_model(MODEL, temperature=0)  # a real ChatOpenAI

        print("model    :", type(model).__module__ + "." + type(model).__name__)
        print("governed :", ", ".join(sorted(fabric.langgraph.connection_kwargs())))

        agent = create_agent(model, tools=[check_inventory, get_price])

        print("\nquestion :", QUESTION, "\n")
        async for step in agent.astream(
            {"messages": [("user", QUESTION)]}, stream_mode="updates"
        ):
            for node, update in step.items():
                for message in update.get("messages", []):
                    if getattr(message, "tool_calls", None):
                        for call in message.tool_calls:
                            print(f"  tool call   {call['name']}({call['args']})")
                    elif node == "tools":
                        print(f"  tool result {message.content}")
                    elif message.content:
                        print(f"\nanswer   : {message.content}")


asyncio.run(main())
