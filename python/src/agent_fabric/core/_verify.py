"""Centralized home for every value that §0.3 says must be verified against a
real Anypoint sandbox before it can be trusted.

Working instruction #2: *never invent an endpoint, header name, or class name.*

Nothing in this module is a verified fact. Each value is either:

  * a ``PLACEHOLDER`` — a documented best-guess that is emitted with a loud,
    one-time :class:`UnverifiedValueWarning` whenever it is read, and is fully
    overridable via config / env so a customer can point it at the real value
    without waiting for us; or
  * absent, in which case the calling code raises
    ``NotImplementedError("blocked on verification: …")``.

When a value is confirmed against a sandbox, flip its row in
``docs/verified-apis.md`` to ``VERIFIED`` and set ``verified=True`` here so the
warning stops firing.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass


class UnverifiedValueWarning(UserWarning):
    """Emitted the first time an unverified placeholder constant is read."""


_warned: set[str] = set()


@dataclass(frozen=True)
class Unverified:
    """A placeholder value that is not yet confirmed against a real sandbox.

    Read it with :meth:`get`, which warns once. Treat the returned value as a
    default that the user can and should override.
    """

    key: str
    placeholder: str
    doc_ref: str
    verified: bool = False

    def get(self) -> str:
        if not self.verified and self.key not in _warned:
            _warned.add(self.key)
            warnings.warn(
                f"Using UNVERIFIED placeholder for {self.key!r} "
                f"({self.placeholder!r}). This has NOT been confirmed against a "
                f"real Anypoint sandbox — see {self.doc_ref}. Override it via "
                f"config/env, or verify it and flip the row in "
                f"docs/verified-apis.md.",
                UnverifiedValueWarning,
                stacklevel=2,
            )
        return self.placeholder


def blocked(what: str) -> NotImplementedError:
    """Construct the standard verification-blocked error.

    Use for surfaces where we have no defensible placeholder at all (e.g. the
    MCP Bridge provisioning endpoint, §0.3 / §5).
    """

    return NotImplementedError(f"blocked on verification: {what}")


# --- Attribution headers (§3, the single most important unknown) -----------
# These names are GUESSES. The gateway may read entirely different header names.
ATTRIBUTION_APP_HEADER = Unverified(
    key="attribution.application_header",
    placeholder="X-Anypoint-Client-Application",
    doc_ref="docs/verified-apis.md §3",
)
ATTRIBUTION_BUSINESS_GROUP_HEADER = Unverified(
    key="attribution.business_group_header",
    placeholder="X-Anypoint-Business-Group",
    doc_ref="docs/verified-apis.md §3",
)

# --- Control-plane token endpoint (§1) --------------------------------------
# Path is appended to the region base URL. VERIFIED (§12.1) from static analysis
# of the shipping `mulesoft-anypoint-cli-agent-fabric-plugin` (+ `anypoint-cli-
# command`): OAuth2 client_credentials → `POST /accounts/api/v2/oauth2/token`.
OAUTH_TOKEN_PATH = Unverified(
    key="anypoint.oauth_token_path",
    placeholder="/accounts/api/v2/oauth2/token",
    doc_ref="docs/verified-apis.md §12.1",
    verified=True,
)

# --- LLM proxy consumer auth (§2/§3) — VERIFIED (LIVE 2026-08-28) ------------
# The directly-called ingress LLM proxy authenticates the caller with a
# `client_id` + `client_secret` REQUEST-header pair (client-id-enforcement
# 1.3.3), NOT a bearer token. This pair IS the per-agent attribution unit. These
# are confirmed header names, not placeholders — see docs/verified-apis.md §2/§3.
LLM_PROXY_CLIENT_ID_HEADER = "client_id"
LLM_PROXY_CLIENT_SECRET_HEADER = "client_secret"

# --- Region host map (§1) ----------------------------------------------------
# UNVERIFIED — Hyperforce region hosts in particular need confirmation.
REGION_HOSTS: dict[str, str] = {
    "us": "https://anypoint.mulesoft.com",
    "eu": "https://eu1.anypoint.mulesoft.com",
    "ca": "https://ca1.anypoint.mulesoft.com",
    "jp": "https://jp1.anypoint.mulesoft.com",
}
REGION_HOSTS_VERIFIED = False
