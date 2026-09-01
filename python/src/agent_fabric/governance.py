"""The Governance object and its three-verb lifecycle (§6.2–§6.4).

ONE object, THREE verbs, THREE trust levels (§6.3):

  * ``simulate()`` — local, developer laptop. Ephemeral local gateway; touches
    nothing shared.
  * ``export()``   — compiles to a ``fabric.yaml`` fragment (§5.1). Writes a
    file; touches nothing.
  * ``resolve()``  — runtime, READ-ONLY. Looks up the already-provisioned route,
    verifies the declared policies are actually applied, returns the base_url.
    Raises :class:`GovernanceDrift` on mismatch.

There is deliberately NO ``apply()`` on the runtime object (§6.3): applying to
sandbox/prod goes through ``agent-fabric apply`` in CI, against a reviewed spec,
under platform-controlled credentials. An escape hatch exists for platform teams
(:meth:`apply`) with an explicit, hard-to-miss kwarg.

Local is NOT sandbox-with-a-different-URL (§6.4): feature sets differ, policies
are not portable across modes, identity/secrets differ. ``simulate()`` must
loudly report which declared policies are skipped locally and why.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal, cast

if sys.version_info >= (3, 11):
    import tomllib
else:  # 3.10 has no stdlib tomllib; the [core] dep ``tomli`` backfills it.
    import tomli as tomllib

from .core import _verify
from .core.errors import ConfigError

GatewayMode = Literal["local", "managed", "self-managed"]


class PolicyPortability(Enum):
    """Whether a policy works in Local Mode, Connected Mode, or both (§6.4).

    The concrete classification per policy MUST come from real data captured in
    M0 (§6.7), not inference — until then policies default to ``UNKNOWN``.
    """

    BOTH = "both"
    CONNECTED_ONLY = "connected_only"
    LOCAL_ONLY = "local_only"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PolicyBinding:
    asset_id: str
    version: str
    config: dict[str, Any] = field(default_factory=dict)
    #: Populated from the M0 portability table (§6.4/§6.7); UNKNOWN until then.
    portability: PolicyPortability = PolicyPortability.UNKNOWN


@dataclass(frozen=True)
class GatewayTarget:
    mode: GatewayMode
    base_url: str
    environment: str | None = None
    gateway_name: str | None = None
    connected: bool = True  # local-mode gateways are unconnected

    @classmethod
    def from_env(cls) -> GatewayTarget:
        """Select a profile from ``.agent-fabric.toml`` via ``FABRIC_TARGET``
        (``local|sandbox|production``) (§6.2)."""

        target = os.environ.get("FABRIC_TARGET", "local")
        profiles = _load_targets()
        if target not in profiles:
            raise ConfigError(
                f"FABRIC_TARGET={target!r} has no matching [targets.{target}] "
                f"profile in .agent-fabric.toml. Defined: {sorted(profiles) or 'none'}."
            )
        p = profiles[target]
        mode: GatewayMode = cast(GatewayMode, p.get("mode", "local"))
        return cls(
            mode=mode,
            base_url=p["base_url"],
            environment=p.get("environment"),
            gateway_name=p.get("gateway_name"),
            connected=(mode != "local"),
        )


@dataclass(frozen=True)
class Governance:
    name: str
    gateway: GatewayTarget
    policies: list[PolicyBinding] = field(default_factory=list)

    # ---- verb 1: simulate (local) -----------------------------------------
    def simulate(self) -> SimulationContext:
        """Start an ephemeral local Omni Gateway harness (§6.5).

        Requires the ``[local]`` extra (docker). Whether Local Mode can run the
        LLM Proxy / MCP Bridge at all is an M0 gate (§6.7); if not, LLM traffic
        is served by a clearly-labelled local mock proxy. Either way, skipped
        connected-only policies are reported loudly and non-suppressibly (§6.4).
        """

        return SimulationContext(self)

    # ---- verb 2: export (sandbox/prod, laptop) ----------------------------
    def export(self, path: str | Path | None = None) -> str:
        """Compile to a ``fabric.yaml`` fragment (§5.1). Lands with M4 (§9.1)."""
        raise _verify.blocked(
            "Governance.export() emits the M4 fabric.yaml spec format; it ships "
            "with provisioning (M4, §9.1). Schema is shared with §5.1 — do not "
            "diverge it (§5.1)."
        )

    # ---- verb 3: resolve (runtime, READ-ONLY) -----------------------------
    async def resolve(self, fabric: Any) -> GatewayTarget:
        """READ-ONLY: verify the declared policies are actually applied on the
        provisioned gateway and return its route. Raises
        :class:`~agent_fabric.core.errors.GovernanceDrift` on mismatch (§6.3).

        Blocked until the API Manager read APIs are verified (§6.7)."""
        raise _verify.blocked(
            "runtime governed-route lookup + applied-policy read for resolve() "
            "(§6.3, §6.7)."
        )

    # ---- escape hatch (platform teams only) -------------------------------
    async def apply(self, target: GatewayTarget, *, i_am_the_platform_team: bool = False) -> None:
        """Platform-team-only direct apply (§6.3). Requires write scopes the
        default connected app will not hold; every use is logged at WARNING."""
        if not i_am_the_platform_team:
            raise PermissionError(
                "Governance.apply() inverts the platform-team ownership model "
                "(§5.4). Runtime code should use resolve() (read-only). If you are "
                "the platform team automating your own gateway, pass "
                "i_am_the_platform_team=True and ensure the connected app holds "
                "write scopes."
            )
        raise _verify.blocked("direct policy apply endpoint (§5, §6.3, §6.7).")


class SimulationContext:
    """Async context manager for ``gov.simulate()`` (§6.5)."""

    def __init__(self, gov: Governance) -> None:
        self._gov = gov

    def skipped_policies(self) -> list[tuple[PolicyBinding, str]]:
        """Declared policies that will NOT be exercised locally, with reasons —
        printed loudly before start and repeated at teardown (§6.4)."""
        skipped: list[tuple[PolicyBinding, str]] = []
        for p in self._gov.policies:
            if p.portability in (PolicyPortability.CONNECTED_ONLY, PolicyPortability.UNKNOWN):
                reason = (
                    "connected-mode only (needs API Manager client apps)"
                    if p.portability is PolicyPortability.CONNECTED_ONLY
                    else "portability UNKNOWN pending M0 verification (§6.7)"
                )
                skipped.append((p, reason))
        return skipped

    async def __aenter__(self) -> Any:
        raise _verify.blocked(
            "local Omni Gateway docker harness + Local-Mode LLM-Proxy/MCP-Bridge "
            "availability (§6.5, §6.7). The [local] extra and the loud "
            "skipped-policy report (skipped_policies()) are scaffolded; the docker "
            "orchestration is M2.5 and gated on the M0 local-mode findings."
        )

    async def __aexit__(self, *exc: object) -> None:
        return None


def _load_targets() -> dict[str, dict[str, Any]]:
    path = Path.cwd() / ".agent-fabric.toml"
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Malformed {path}: {exc}") from exc
    targets = data.get("targets", {})
    return targets if isinstance(targets, dict) else {}
