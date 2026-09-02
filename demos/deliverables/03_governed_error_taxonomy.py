"""Deliverable #1.3 — the proxy's rejections become typed exceptions.

`core.errors.classify()` maps the four LIVE-CAPTURED rejection shapes (§4) to
typed exceptions so you branch on governance outcomes instead of parsing bodies.

This demo is deterministic and OFFLINE: it rebuilds the real captured responses
from the committed fixtures under python/tests/fixtures/anypoint/llm_proxy/ and
runs them through classify().

Note: the raw `fabric.llm.client()` (demo 01) surfaces failures as the OpenAI
SDK's own `openai.APIStatusError` — classify() is the bridge you apply to
`error.response` to get these typed governance exceptions, not something the
raw client raises automatically.

Run:
    python demos/deliverables/03_governed_error_taxonomy.py
"""

# ruff: noqa: I001, E402  (the _paths shim must import before agent_fabric — do not reorder)
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # demos/ (holds _paths.py)
import _paths  # noqa: F401

import httpx

from agent_fabric.core.errors import (
    AuthError,
    PIIDetected,
    PolicyViolation,
    TokenBudgetExceeded,
    classify,
)

FIXTURES = (
    Path(__file__).resolve().parents[2]  # demos/deliverables/ -> repo root
    / "python" / "tests" / "fixtures" / "anypoint" / "llm_proxy"
)


def _headers(name: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (FIXTURES / name).read_text().splitlines():
        if line.startswith("HTTP/") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip().lower()] = v.strip()
    return out


def _json(name: str) -> object:
    return json.loads((FIXTURES / name).read_text())


def _cases() -> list[tuple[str, httpx.Response]]:
    """The four verified rejection shapes, rebuilt from the live fixtures."""
    return [
        (
            "client-id-enforcement (401, flat string error)",
            httpx.Response(
                401,
                headers=_headers("reject.client-id-missing.headers.txt"),
                json=_json("reject.client-id-missing.body.json"),
            ),
        ),
        (
            "PII detection (403, nested type=pii_detected, NO www-authenticate)",
            httpx.Response(
                403,
                headers=_headers("reject.pii-detected.headers.txt"),
                json=_json("reject.pii-detected.body.json"),
            ),
        ),
        (
            "token-rate-limit (429, EMPTY body, header-only reset)",
            httpx.Response(
                429,
                headers=_headers("reject.token-rate-limit.headers.txt"),
                # deliberately no body — the live proxy returns content-length: 0
            ),
        ),
        (
            "upstream passthrough (400, nested provider error object)",
            httpx.Response(400, json=_json("reject.model-not-found.body.json")),
        ),
    ]


def _describe(err: Exception) -> str:
    parts = [type(err).__name__]
    for attr in ("policy", "entities", "retry_after", "code", "error_type", "param"):
        if hasattr(err, attr):
            val = getattr(err, attr)
            if val not in (None, [], ""):
                parts.append(f"{attr}={val!r}")
    return "  ".join(parts)


def main() -> None:
    print("Mapping the four LIVE-VERIFIED proxy rejections (§4) through classify():\n")
    for title, resp in _cases():
        err = classify(resp)
        print(f"• {title}")
        print(f"    HTTP {resp.status_code} -> {_describe(err)}")
        # The point of the taxonomy: PII is NOT auth, token-limit is retryable.
        if isinstance(err, PIIDetected):
            assert not isinstance(err, AuthError)
        if isinstance(err, TokenBudgetExceeded):
            assert isinstance(err, PolicyViolation)
        print()

    print("Handle them like this:\n")
    print(
        "    try:\n"
        "        resp = await client.chat.completions.create(model=..., messages=...)\n"
        "    except PIIDetected as e:        # 403, not auth\n"
        "        ...\n"
        "    except TokenBudgetExceeded as e:  # 429, e.retry_after seconds\n"
        "        ...\n"
        "    except PolicyViolation as e:    # any other gateway policy refusal\n"
        "        ...\n"
        "    except AuthError as e:          # 401 bad/missing client_id/secret\n"
        "        ...\n"
        "    except FabricError as e:        # upstream/provider + everything else\n"
        "        ..."
    )


if __name__ == "__main__":
    main()
