"""Google ADK adapter example (§3.3). Tier 1.

Demonstrates constructing a native ``google.adk.models.lite_llm.LiteLlm``
pointed at the governed Agent Fabric LLM proxy with a single factory call:

    from agent_fabric.integrations.adk import model
    m = model("gpt-4o")  # sent to LiteLLM as "openai/gpt-4o"

Honest status (§0.3/§8): the proxy *contract* (base URL, client_id/secret
auth, attribution headers) is live-verified, and ``LiteLlm``/its kwargs are
verified per the FACTS table. What is NOT attempted here is a live
inference call: ADK drives models through its own ``Runner``/``Agent``
session machinery, not a simple one-line method on the model object, and
guessing that call risks inventing an API (§0.3). Construction is this
example's verified surface — once you have ``m``, wire it into your own ADK
``Agent``/``Runner`` per ADK's own docs.
"""

from __future__ import annotations

import os

from agent_fabric.core.errors import ConfigError
from agent_fabric.integrations.adk import model


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
        print("Google ADK not installed. Install it with:")
        print('    pip install "agent-fabric[adk]"')
        return
    except ConfigError as e:
        print(f"Config error: {e}")
        return

    print(f"Constructed native object: {type(m).__module__}.{type(m).__name__}")
    print(
        "Construction is the SDK's verified surface; drive this object with "
        "ADK's own Agent/Runner API (see this example's README) — that "
        "runtime call is UNVERIFIED here and deliberately not guessed (§0.3)."
    )


if __name__ == "__main__":
    main()
