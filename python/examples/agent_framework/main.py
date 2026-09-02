"""Microsoft Agent Framework adapter example (§3.3). Tier 1.

Demonstrates constructing a native Agent Framework OpenAI-compatible chat
client pointed at the governed Agent Fabric LLM proxy with a single factory
call:

    from agent_fabric.integrations.agent_framework import chat_client
    client = chat_client("gpt-4o")

Honest status (§0.3/§8): the proxy *contract* (base URL, client_id/secret
auth, attribution headers) is live-verified, but the exact chat-client class
name/path (``agent_framework.openai.OpenAIChatClient``) and its base-URL
kwarg (``model_id``) are UNVERIFIED — Agent Framework is young and has
renamed classes recently. The factory raises ``NotImplementedError`` with a
"blocked on verification" message if that import fails, rather than
guessing further. This example also does not attempt a live inference call:
Agent Framework drives chat clients through its own ``Agent`` object, not a
simple method on the client, and guessing that call risks inventing an API.
"""

from __future__ import annotations

import os

from agent_fabric.core.errors import ConfigError
from agent_fabric.integrations.agent_framework import chat_client


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
        client = chat_client(model_id)
    except ImportError:
        print("Microsoft Agent Framework not installed. Install it with:")
        print('    pip install "agent-fabric[agent_framework]"')
        return
    except NotImplementedError as e:
        print(f"Blocked on verification: {e}")
        return
    except ConfigError as e:
        print(f"Config error: {e}")
        return

    print(f"Constructed native object: {type(client).__module__}.{type(client).__name__}")
    print(
        "Construction is the SDK's verified surface; drive this object with "
        "Agent Framework's own Agent API (see this example's README) — that "
        "runtime call is UNVERIFIED here and deliberately not guessed (§0.3)."
    )


if __name__ == "__main__":
    main()
