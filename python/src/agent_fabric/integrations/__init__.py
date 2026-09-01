"""integrations/ — one optional extra per framework (§1.1).

Each adapter returns NATIVE framework objects (§3.1). Modules are imported
lazily by :class:`agent_fabric.fabric.Fabric` so an uninstalled framework never
breaks ``import agent_fabric``.

The registry below maps the attribute name used on ``Fabric`` to the adapter's
module + class + pip extra, so ``Fabric.__getattr__`` can raise a curated
ImportError with the exact install command (§3.2).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdapterSpec:
    attr: str
    module: str
    cls: str
    extra: str
    tier: int
    #: A representative top-level module of the framework, probed with
    #: ``importlib.util.find_spec`` so ``Fabric.__getattr__`` can raise the
    #: curated ImportError at ACCESS time (§3.2). The adapters import their
    #: framework lazily inside methods, so importing the adapter module alone
    #: never fails — this probe is what makes access-time detection work.
    probe: str


ADAPTERS: dict[str, AdapterSpec] = {
    "langgraph": AdapterSpec(
        "langgraph", ".langgraph", "LangGraphAdapter", "langgraph", 1, "langchain_openai"
    ),
    "adk": AdapterSpec("adk", ".adk", "ADKAdapter", "adk", 1, "google.adk"),
    "strands": AdapterSpec("strands", ".strands", "StrandsAdapter", "strands", 1, "strands"),
    "agent_framework": AdapterSpec(
        "agent_framework", ".agent_framework", "AgentFrameworkAdapter", "agent_framework", 1,
        "agent_framework",
    ),
    "openai": AdapterSpec(
        "openai", ".openai_agents", "OpenAIAgentsAdapter", "openai", 1, "agents"
    ),
    "anthropic": AdapterSpec(
        "anthropic", ".anthropic", "AnthropicAdapter", "anthropic", 1, "anthropic"
    ),
    "crewai": AdapterSpec(
        "crewai", ".crewai", "CrewAIAdapter", "crewai", 1, "crewai"
    ),
    "llamaindex": AdapterSpec(
        "llamaindex", ".llamaindex", "LlamaIndexAdapter", "llamaindex", 2,
        "llama_index.llms.openai_like",
    ),
}
