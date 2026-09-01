"""Plan / diff (§5.2).

Requirements the implementer must honour when this is wired to a real API:
  * Read-before-write, always — fetch current state, diff, render, then apply.
    Never blind-PUT.
  * Idempotent — re-running apply with no change makes zero mutating calls.
  * ``--dry-run`` / ``--out plan.json`` for CI gating.

GATE (§5, §0.3): whether a usable MCP Bridge provisioning API exists is an M0
finding. If UI-only, this whole module is cut and we emit Terraform instead
(§5.5). Until confirmed, planning against live state is blocked.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core import _verify
from .spec import FabricSpec


@dataclass(frozen=True)
class Change:
    action: str  # "create" | "update" | "remove"
    kind: str    # "mcpBridge" | "tool" | "policy"
    name: str
    detail: str = ""


@dataclass(frozen=True)
class Plan:
    changes: list[Change] = field(default_factory=list)

    def render(self) -> str:
        if not self.changes:
            return "No changes. Infrastructure matches the spec."
        sign = {"create": "+", "update": "~", "remove": "-"}
        lines = [
            f"  {sign.get(c.action, '?')} {c.kind:<10} {c.name:<28} "
            f"({c.action}) {c.detail}".rstrip()
            for c in self.changes
        ]
        lines.append(f"\n{len(self.changes)} changes. Run `apply` to proceed.")
        return "\n".join(lines)


async def build_plan(spec: FabricSpec, fabric: object) -> Plan:
    raise _verify.blocked(
        "MCP Bridge provisioning read API for read-before-write planning "
        "(§5.2, §5, §0.3). If M0 finds it UI-only, pivot to Terraform generation "
        "(§5.5) — do NOT reverse-engineer internal endpoints."
    )
