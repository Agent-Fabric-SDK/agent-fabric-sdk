"""Deliverable #1.2 — native framework objects, one call per framework.

Each adapter returns the *framework's own* object (not a wrapper) already
pointed at the proxy through the verified `client_id`/`client_secret` contract.
This demo constructs one object per framework and reports what came back.

Honest status (§0.3 / §8): the proxy *contract* is verified, but the exact
framework class names/kwargs are still being confirmed against installed
versions. So per framework you'll see one of:
  * OK <ClassName>          — built the native object
  * not installed           — extra missing (ImportError w/ install command)
  * blocked on verification — Tier-1 adapter refused to guess a class name

Run:
    export AGENT_FABRIC_LLM_PROXY_URL / _CLIENT_ID / _CLIENT_SECRET   # see demo 01
    pip install "agent-fabric[langgraph]"   # + any frameworks you want
    python examples-demos/02_native_framework_objects.py

No network calls are made — objects are only constructed.
"""

# ruff: noqa: I001  (the _paths shim must import before agent_fabric — do not reorder)
from __future__ import annotations

import os

import _paths  # noqa: F401

from agent_fabric import Fabric
from agent_fabric.core.errors import ConfigError

# (fabric attribute, method name, takes-model-arg, expected-native-type hint)
# — matches §3.3. `anthropic.client()` takes no model id: the model is a
# per-call arg on the native `AsyncAnthropic` client, not a constructor kwarg.
ADAPTER_CALLS = [
    ("langgraph", "chat_model", True, "langchain_openai.ChatOpenAI"),
    ("adk", "model", True, "google.adk … LiteLlm"),
    ("strands", "model", True, "strands … OpenAIModel"),
    ("agent_framework", "chat_client", True, "agent_framework … OpenAIChatClient"),
    ("openai", "model", True, "agents … OpenAIChatCompletionsModel"),
    ("anthropic", "client", False, "anthropic … AsyncAnthropic"),
    ("crewai", "llm", True, "crewai … LLM"),
    ("llamaindex", "llm", True, "llama_index … OpenAILike"),
]

MODEL = os.environ.get("DEMO_MODEL", "gpt-4o")


def _configured() -> bool:
    return all(
        os.environ.get(v)
        for v in (
            "AGENT_FABRIC_LLM_PROXY_URL",
            "AGENT_FABRIC_LLM_PROXY_CLIENT_ID",
            "AGENT_FABRIC_LLM_PROXY_CLIENT_SECRET",
        )
    )


def main() -> None:
    if not _configured():
        print(__doc__)
        print(">> Set the three AGENT_FABRIC_LLM_PROXY_* env vars to construct adapters.")
        return

    fabric = Fabric.from_env()
    width = max(len(a) for a, _, _, _ in ADAPTER_CALLS)

    for attr, method, takes_model, hint in ADAPTER_CALLS:
        label = f"{attr:<{width}}"
        try:
            adapter = getattr(fabric, attr)          # ImportError if extra missing
            factory = getattr(adapter, method)
            obj = factory(MODEL) if takes_model else factory()  # build the native object
            print(f"{label}  OK  {type(obj).__module__}.{type(obj).__name__}")
        except ImportError:
            print(f"{label}  not installed  (pip install 'agent-fabric[{attr}]')")
        except NotImplementedError as e:
            print(f"{label}  blocked on verification  ({e})")
        except ConfigError as e:
            print(f"{label}  config error  ({e})")
        except Exception as e:  # noqa: BLE001 — demo: surface anything else clearly
            print(f"{label}  {type(e).__name__}: {e}   [expected native: {hint}]")


if __name__ == "__main__":
    main()
