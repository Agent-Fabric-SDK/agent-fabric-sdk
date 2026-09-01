"""llm/ — governed model access, framework-free surface (§3.2, §3.4)."""

from .catalog import ModelCapabilities, ModelHandle, heuristic_capabilities
from .client import LLMClient

__all__ = ["LLMClient", "ModelCapabilities", "ModelHandle", "heuristic_capabilities"]
