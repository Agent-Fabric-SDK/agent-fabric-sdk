"""core/ — the framework-free foundation (§2).

HARD RULE (§1.1): nothing in this package may import from
``agent_fabric.integrations``. Enforced by import-linter in CI.
"""

from .auth import AnypointConnectedApp, AuthProvider, ChainedAuth, StaticToken
from .cache import TTLCache
from .config import FabricConfig, Region
from .errors import (
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
    classify,
)
from .telemetry import current_correlation_id, new_correlation_id, run_context
from .transport import (
    FabricAsyncClient,
    FabricClient,
    attribution_headers,
    build_http_client,
    build_sync_http_client,
)

__all__ = [
    "AnypointConnectedApp",
    "AuthError",
    "AuthProvider",
    "ChainedAuth",
    "ConfigError",
    "ContentSafetyBlocked",
    "FabricAsyncClient",
    "FabricClient",
    "FabricConfig",
    "FabricError",
    "GovernanceDrift",
    "PIIDetected",
    "PolicyViolation",
    "PromptInjectionBlocked",
    "ProvisioningError",
    "PublicationDrift",
    "Region",
    "RegistryError",
    "StaticToken",
    "TTLCache",
    "TokenBudgetExceeded",
    "ToolInvocationError",
    "UpstreamModelError",
    "attribution_headers",
    "build_http_client",
    "build_sync_http_client",
    "classify",
    "current_correlation_id",
    "new_correlation_id",
    "run_context",
]
