"""Smallest live smoke test — one governed chat completion, blocking.

The bare minimum that proves a checkout can reach the governed proxy:
``Fabric.from_env()`` -> a real ``openai.OpenAI`` -> one ``chat.completions``
call. For the narrated walkthrough see ``deliverables/`` and ``recordings/``.

Run (needs the three AGENT_FABRIC_LLM_PROXY_* vars, or a demos/.env.local):
    python demos/smoke.py

With no credentials it prints setup guidance and exits cleanly.
"""

# ruff: noqa: I001  (the _paths shim must import before agent_fabric — do not reorder)
import os

import _paths  # noqa: F401  (dev path shim + .env.local loader; sibling of this file)

from agent_fabric import Fabric

_REQUIRED = (
    "AGENT_FABRIC_LLM_PROXY_URL",
    "AGENT_FABRIC_LLM_PROXY_CLIENT_ID",
    "AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET",
)


def main() -> None:
    if not all(os.environ.get(v) for v in _REQUIRED):
        print(__doc__)
        print(">> Set the three AGENT_FABRIC_LLM_PROXY_* env vars to run this live smoke test.")
        return

    with Fabric.from_env() as fabric:
        client = fabric.llm.client(sync=True)
        response = client.chat.completions.create(
            model=os.environ.get("DEMO_MODEL", "gpt-4o"),
            messages=[{"role": "user", "content": "What is the capital of Switzerland?"}],
        )
        print(response.choices[0].message.content)


if __name__ == "__main__":
    main()
