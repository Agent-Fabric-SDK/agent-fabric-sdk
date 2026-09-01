"""CrewAI adapter example (§3.3). Tier 1.

Demonstrates constructing a native ``crewai.LLM`` pointed at the governed
MuleSoft LLM proxy with a single factory call:

    from agent_fabric.integrations.crewai import llm
    model = llm("gpt-4o")

Honest status (§0.3/§8): the proxy *contract* (base URL, client_id/secret
auth, attribution headers) is live-verified. ``crewai.LLM`` wraps LiteLLM, so
the OpenAI-compatible route uses the ``openai/`` model prefix and header
injection via ``extra_headers``; LiteLLM owns the transport, so per-run
correlation degrades (a documented conformance exemption, §8.1). No live
inference call is attempted here: CrewAI LLMs are driven through a ``Crew`` /
``Agent``, and guessing that runtime call risks inventing an API (§0.3).
Construction is this example's verified surface.
"""

from __future__ import annotations

import os

from agent_fabric.core.errors import ConfigError
from agent_fabric.integrations.crewai import llm


def _missing_env() -> list[str]:
    names = (
        "MULESOFT_LLM_PROXY_URL",
        "MULESOFT_LLM_PROXY_CLIENT_ID",
        "MULESOFT_LLM_PROXY_CLIENT_SECRET",
    )
    return [n for n in names if not os.environ.get(n)]


def main() -> None:
    missing = _missing_env()
    if missing:
        print("Set the following environment variables and re-run:")
        print('    export MULESOFT_LLM_PROXY_URL="https://<ingress-gw>/<instance>/"  # no /v1')
        print('    export MULESOFT_LLM_PROXY_CLIENT_ID="<consumer client id>"')
        print('    export MULESOFT_LLM_PROXY_CLIENT_SECRET="<consumer client secret>"')
        return

    model_id = os.environ.get("DEMO_MODEL", "gpt-4o")

    try:
        model = llm(model_id)
    except ImportError:
        print("CrewAI not installed. Install it with:")
        print('    pip install "mulesoft-agent-fabric[crewai]"')
        return
    except ConfigError as e:
        print(f"Config error: {e}")
        return

    print(f"Constructed native object: {type(model).__module__}.{type(model).__name__}")
    print(
        "Construction is the SDK's verified surface; pass this object into a "
        "crewai Agent/Crew per CrewAI's own docs — that runtime call is "
        "UNVERIFIED here and deliberately not guessed (§0.3)."
    )


if __name__ == "__main__":
    main()
