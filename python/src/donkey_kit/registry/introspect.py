"""descriptor='auto' derivation (§7.3).

KEY INSIGHT (§7.3.1): do NOT write a type-hint→JSON-Schema converter. Every
framework already derived the schema from signatures/type-hints/docstrings; ask
the framework for the schema it already computed. Re-deriving would produce a
second, subtly-different schema from the one the model actually sees.

Modes, by fidelity (§7.3.2):
  * ``auto``        — object introspection (default): import the entrypoint, read
    already-computed schemas. Importing user code EXECUTES it → require an
    explicit entrypoint; tool definitions must be import-safe.
  * ``auto:live``   — highest fidelity: run the server, MCP initialize +
    tools/list. Captures dynamic registration.
  * ``auto:static`` — AST only, lower fidelity: MUST emit a completeness warning
    on unresolved dynamic registration; never the default.
  * ``auto:check``  — generate, diff against a committed descriptor, fail on
    mismatch. The CI-friendly mode.

Every per-framework attribute read here is semi-public and WILL break on
upstream releases → all go in the conformance kit + nightly matrix (§7.3.1,
§8.4). Names are UNVERIFIED (docs/verified-apis.md §10).
"""

from __future__ import annotations

from ..core import _verify

DerivationMode = str  # "auto" | "auto:live" | "auto:static" | "auto:check"


async def derive_descriptor(
    entrypoint: str, *, mode: DerivationMode = "auto"
) -> dict[str, object]:
    """Derive an asset descriptor from code. Blocked until the per-framework
    attribute contracts are verified (§7.3.1 / §10)."""
    raise _verify.blocked(
        f"per-framework tool-object attribute contracts for descriptor derivation "
        f"mode {mode!r} (docs/verified-apis.md §10). Read the already-computed "
        f"schema; never re-derive it (§7.3.1)."
    )
