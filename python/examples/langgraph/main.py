"""LangGraph / LangChain adapter example (§3.3). Tier 1.

Demonstrates constructing a native ``langchain_openai.ChatOpenAI`` pointed at
the governed Agent Fabric LLM proxy with a single factory call:

    from agent_fabric.integrations.langgraph import chat_model
    model = chat_model("gpt-4o")

Honest status (§0.3/§8): the proxy *contract* (base URL, client_id/secret
auth, attribution headers) is live-verified. ``ChatOpenAI`` is LangGraph's own
class, and its ``.ainvoke`` call is LangChain's well-established, documented
API (not a guess) — this is the one example in this set with a live
inference call. Construction via the factory is the SDK's verified surface;
everything after that is LangChain's own runtime.
"""

from __future__ import annotations

import asyncio
import os

from agent_fabric.core.errors import ConfigError
from agent_fabric.integrations.langgraph import chat_model


def _missing_env() -> list[str]:
    names = (
        "AGENT_FABRIC_LLM_PROXY_URL",
        "AGENT_FABRIC_LLM_PROXY_CLIENT_ID",
        "AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET",
    )
    return [n for n in names if not os.environ.get(n)]


async def main() -> None:
    missing = _missing_env()
    if missing:
        print("Set the following environment variables and re-run:")
        print('    export AGENT_FABRIC_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"  # no /v1')
        print('    export AGENT_FABRIC_LLM_PROXY_CLIENT_ID="<consumer client id>"')
        print('    export AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"')
        return

    model_id = os.environ.get("DEMO_MODEL", "gpt-4o")

    try:
        model = chat_model(model_id)
    except ImportError:
        print('LangGraph not installed. Install it with:')
        print('    pip install "agent-fabric[langgraph]"')
        return
    except ConfigError as e:
        print(f"Config error: {e}")
        return

    print(f"Constructed native object: {type(model).__module__}.{type(model).__name__}")

    try:
        result = await model.ainvoke([("user", "Say hi in three words.")])
        print(f"Model reply: {result.content}")
    except Exception as e:  # noqa: BLE001 — surface any runtime/network failure clearly
        print(f"Inference call failed ({type(e).__name__}: {e}).")
        print("Construction succeeded; check proxy connectivity/credentials.")


if __name__ == "__main__":
    asyncio.run(main())
