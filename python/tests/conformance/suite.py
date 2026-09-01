"""The adapter conformance kit — the most important test asset (§8.1).

ONE suite, defined once, executed identically against every framework adapter.
A framework is "supported" only when it passes all of it, or records a
documented, asserted exemption in ``KNOWN_LIMITATIONS`` (§8.1) — never a silent
skip.

The scenario bodies are wired in M1+ against captured contract fixtures (§8.2)
and the local gateway (§8.3). This module fixes the scenario list and the
exemption table now so the kit exists before the second adapter is built
(working instruction #5).
"""

from __future__ import annotations

CONFORMANCE_SCENARIOS = [
    "simple_completion",
    "streaming_completion",
    "single_tool_call",
    "multi_tool_multi_server",
    "tool_filtering",
    "policy_violation_terminal",
    "attribution_headers_present",
    "correlation_id_propagated",
    "governed_filter_excludes",
    "governance_resolve_drift",
    "governance_target_switch",
    "descriptor_auto_stable",
    "publication_verify_drift",
    "publication_idempotent",
    "descriptor_matches_framework",
    "auto_vs_live_agree",
    "dynamic_tools_detected",
    "asset_type_detection",
]

# Documented, ASSERTED exemptions — published in the README (§8.1). A framework
# that cannot satisfy a scenario records WHY here rather than skipping silently.
_LITELLM_TRANSPORT_EXEMPTION = (
    "LiteLLM owns the transport; we cannot inject our httpx client, so the "
    "correlation ID is per-client, not per-run (§3.3). A LiteLLM custom "
    "logger callback may later recover trace correlation."
)

KNOWN_LIMITATIONS: dict[str, dict[str, str]] = {
    # ADK and CrewAI both reach models through LiteLLM (§3.3).
    "adk": {"correlation_id_propagated": _LITELLM_TRANSPORT_EXEMPTION},
    "crewai": {"correlation_id_propagated": _LITELLM_TRANSPORT_EXEMPTION},
}
