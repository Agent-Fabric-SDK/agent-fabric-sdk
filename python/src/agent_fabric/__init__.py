"""mulesoft-agent-fabric — an SDK for consuming MuleSoft Agent Fabric
capabilities from your own agent framework.

See the README for the maintainer + support statement and the trademark note
(§0.4). "Agent Fabric" is a MuleSoft product name; this package is descriptive.

Public surface (§3.2):

    from agent_fabric import Fabric
    fabric = Fabric.from_env()
    fabric.langgraph.chat_model("gpt-4o")   # native ChatOpenAI

Working-instruction reminder (§0.3, #2): many platform endpoints/headers/class
names are UNVERIFIED. Those code paths raise
``NotImplementedError("blocked on verification: …")`` rather than guessing. See
docs/verified-apis.md.
"""

from __future__ import annotations

from .core.config import FabricConfig, Region
from .core.errors import (
    AuthError,
    ConfigError,
    ContentSafetyBlocked,
    FabricError,
    GovernanceDrift,
    PIIDetected,
    PolicyViolation,
    PromptInjectionBlocked,
    ProvisioningError,
    PublicationDrift,
    RegistryError,
    TokenBudgetExceeded,
    ToolInvocationError,
    UpstreamModelError,
)
from .fabric import Fabric
from .governance import (
    GatewayTarget,
    Governance,
    PolicyBinding,
    PolicyPortability,
)
from .registry import (
    STRICT,
    AssetRef,
    AssetType,
    Contact,
    GovernanceCriteria,
    Publication,
)

__version__ = "0.1.0.dev0"

__all__ = [
    "STRICT",
    "AssetRef",
    "AssetType",
    "AuthError",
    "ConfigError",
    "Contact",
    "ContentSafetyBlocked",
    "Fabric",
    "FabricConfig",
    "FabricError",
    "GatewayTarget",
    "Governance",
    "GovernanceCriteria",
    "GovernanceDrift",
    "PIIDetected",
    "PolicyBinding",
    "PolicyPortability",
    "PolicyViolation",
    "PromptInjectionBlocked",
    "Publication",
    "ProvisioningError",
    "PublicationDrift",
    "Region",
    "RegistryError",
    "TokenBudgetExceeded",
    "ToolInvocationError",
    "UpstreamModelError",
    "__version__",
]
