"""OpenAI Agents SDK adapter example (§3.3). Tier 1.

Demonstrates constructing a native ``agents.OpenAIChatCompletionsModel`` pointed
at the governed Agent Fabric LLM proxy with a single factory call:

    from agent_fabric.integrations.openai_agents import model
    m = model("gpt-4o")

Honest status (§0.3/§8): the proxy *contract* (base URL, client_id/secret
auth, attribution headers) is live-verified. Because the adapter builds the
underlying ``AsyncOpenAI`` client itself, header AND transport injection are
both available (full injection). No live inference call is attempted here: the
Agents SDK runs models through an ``agents.Agent`` + ``Runner``, and guessing
that runtime call risks inventing an API (§0.3). Construction is this example's
verified surface — pass ``m`` into ``agents.Agent(model=m)`` per the SDK's docs.
"""

from __future__ import annotations

import os

from agent_fabric.core.errors import ConfigError
from agent_fabric.integrations.openai_agents import model


def _missing_env() -> list[str]:
    names = (
        "AGENT_FABRIC_LLM_PROXY_URL",
        "AGENT_FABRIC_LLM_PROXY_CLIENT_ID",
        "AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET",
    )
    return [n for n in names if not os.environ.get(n)]


def main() -> None:
    missing = _missing_env()
    if missing:
        print("Set the following environment variables and re-run:")
        print('    export AGENT_FABRIC_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"  # no /v1')
        print('    export AGENT_FABRIC_LLM_PROXY_CLIENT_ID="<consumer client id>"')
        print('    export AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"')
        return

    model_id = os.environ.get("DEMO_MODEL", "gpt-4o")

    try:
        m = model(model_id)
    except ImportError:
        print("OpenAI Agents SDK not installed. Install it with:")
        print('    pip install "agent-fabric[openai]"')
        return
    except ConfigError as e:
        print(f"Config error: {e}")
        return

    print(f"Constructed native object: {type(m).__module__}.{type(m).__name__}")
    print(
        "Construction is the SDK's verified surface; pass this object into "
        "agents.Agent(model=...) and drive it with Runner per the SDK's own "
        "docs — that runtime call is UNVERIFIED here and deliberately not "
        "guessed (§0.3)."
    )


if __name__ == "__main__":
    main()
