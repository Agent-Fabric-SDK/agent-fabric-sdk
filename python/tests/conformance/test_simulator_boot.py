"""The out-of-process boot of the local gateway simulator (BG §1.4).

``local_gateway``-marked, so deselected by default and run only via
``pytest -m local_gateway`` (with the ``[local]`` extra installed). It proves the
same fixtures the in-process unit tests replay are served identically over a real
TCP port — the surface a stock ``openai`` client or ``curl`` points
``AGENT_FABRIC_LLM_PROXY_URL`` at.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.local_gateway


def test_boot_serves_the_happy_path_over_a_real_port(simulator_base_url: str) -> None:
    resp = httpx.post(f"{simulator_base_url}/v1/responses", json={"model": "gpt-5.1"}, timeout=10.0)
    assert resp.status_code == 200
    assert resp.headers["x-fabric-simulator"] == "true"
    assert resp.json()["object"] == "response"
    assert "x-token-remaining" in resp.headers  # synthesized budget window


def test_boot_replays_a_rejection_shape_over_a_real_port(simulator_base_url: str) -> None:
    resp = httpx.post(
        f"{simulator_base_url}/v1/responses",
        json={"model": "fabric-sim/pii-detected"},
        timeout=10.0,
    )
    assert resp.status_code == 403
    assert resp.headers["x-fabric-simulator"] == "true"
    assert resp.json()["error"]["type"] == "pii_detected"
