"""Declarative spec models (§5.1).

``Governance.export()`` and ``Publication.export()`` emit fragments of exactly
this format — the features share ONE schema, deliberately. Do not let them
diverge (§5.1).

Design boundaries baked in here:
  * ``inputSchema: "auto"`` — derive from the API's published spec in Exchange
    (§5.1). The OAS/RAML→JSON-Schema transform runs offline in CI (planner).
  * DataWeave is a HARD boundary (§5.1): a raw ``httpMapping.dataweave`` string
    passes through untouched; we never generate or parse DataWeave.
  * No secrets in the spec — reference them (``${secret:...}``), resolved at
    apply time (§5.1).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    name: str
    method: str
    resource: str
    description: str
    #: "auto" derives JSON Schema from the OAS/RAML spec in Exchange (§5.1),
    #: or an explicit JSON Schema object.
    inputSchema: Literal["auto"] | dict[str, Any] = "auto"


class HttpMapping(BaseModel):
    """DataWeave passthrough only — never generated or parsed (§5.1)."""

    dataweave: str | None = None


class ApiSpec(BaseModel):
    assetId: str
    version: str
    upstream: str
    tools: list[ToolSpec] = Field(default_factory=list)
    httpMapping: HttpMapping | None = None


class PolicySpec(BaseModel):
    assetId: str
    version: str
    config: dict[str, Any] = Field(default_factory=dict)


class McpBridgeSpec(BaseModel):
    name: str
    gateway: str
    apis: list[ApiSpec] = Field(default_factory=list)
    policies: list[PolicySpec] = Field(default_factory=list)


class SpecMetadata(BaseModel):
    name: str
    environment: str
    businessGroup: str | None = None


class FabricSpec(BaseModel):
    apiVersion: Literal["fabric/v1"] = "fabric/v1"
    kind: Literal["FabricSpec"] = "FabricSpec"
    metadata: SpecMetadata
    mcpBridges: list[McpBridgeSpec] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, text: str) -> FabricSpec:
        import yaml  # part of the [cli] extra

        data = yaml.safe_load(text)
        return cls.model_validate(data)
