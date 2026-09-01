"""Exchange publication, content digest, ``--if-changed`` (§7.5).

Prevents catalog spam (a new version on every merge). The content-digest
computation is pure and implemented; the publish call and the "compare against
latest published digest" read are gated on the verified Exchange mechanism
(§7.9).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..core import _verify


def content_digest(descriptor: dict[str, Any], metadata: dict[str, Any]) -> str:
    """Stable hash over the canonical descriptor + metadata (§7.5).

    Canonicalised with sorted keys so semantically-identical inputs hash equal,
    which is what makes ``--if-changed`` reliable.
    """

    canonical = json.dumps(
        {"descriptor": descriptor, "metadata": metadata},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


async def publish_if_changed(publication: object, fabric: object) -> str:
    """CI default (§7.5): compare digest against the latest published version;
    if identical, skip and exit zero. Blocked on the verified publication
    mechanism + digest-metadata support (§7.9)."""
    raise _verify.blocked(
        "Exchange publication mechanism (REST/CLI/Maven) + digest metadata support "
        "(§7.5, §7.9). content_digest() is implemented; wire publish once the "
        "mechanism is confirmed. Never delete/overwrite; deprecate via metadata (§7.5)."
    )
