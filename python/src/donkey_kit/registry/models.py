"""Registry value types (§4.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

AssetType = Literal["mcp", "a2a-agent", "agent", "api"]


@dataclass(frozen=True)
class AssetRef:
    """``group_id/asset_id/version`` plus discovery metadata (§4.2).

    Accept a shorthand string form (``"com.acme/vendor-shipment-mcp/1.0.0"``)
    everywhere a ref is taken, via :meth:`parse`.
    """

    group_id: str
    asset_id: str
    version: str
    name: str | None = None
    type: AssetType | None = None
    tags: tuple[str, ...] = ()
    description: str | None = None
    exchange_url: str | None = None

    @classmethod
    def parse(cls, value: AssetRef | str) -> AssetRef:
        if isinstance(value, AssetRef):
            return value
        parts = value.split("/")
        if len(parts) != 3:
            raise ValueError(
                f"Asset ref {value!r} must be 'group_id/asset_id/version' "
                f"(e.g. 'com.acme/vendor-shipment-mcp/1.0.0')."
            )
        group_id, asset_id, version = parts
        return cls(group_id=group_id, asset_id=asset_id, version=version)

    @property
    def coordinates(self) -> str:
        return f"{self.group_id}/{self.asset_id}/{self.version}"


@dataclass(frozen=True)
class McpServerHandle:
    """A resolved MCP server. Carries connection info; does NOT open a
    connection (§4.3 — connect on first tool use)."""

    ref: AssetRef
    endpoint_url: str
    transport: str = "streamable_http"
    auth_required: bool = True
    #: if exposed without a live connection
    tool_descriptors: tuple[dict[str, object], ...] | None = None


@dataclass(frozen=True)
class AgentHandle:
    """A resolved A2A-compliant agent (§4.5)."""

    ref: AssetRef
    endpoint_url: str
    skills: tuple[str, ...] = field(default_factory=tuple)
