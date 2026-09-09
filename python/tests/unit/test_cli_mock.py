"""``agent-fabric mock`` (BG §1.4): flag wiring and the missing-``[local]``-extra
guidance.

Needs only ``[dev]`` (typer): ``serve`` is monkeypatched so neither uvicorn nor
starlette is required, and importing ``agent_fabric.simulator.server`` pulls in
no web framework at module top. So this runs in the base-only job too.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from agent_fabric.provisioning.cli import app

runner = CliRunner()


def _combined(result: object) -> str:
    """click merges stderr into output on <8.2 and separates it on >=8.2; read
    both so the assertion holds across the ``floors, never ceilings`` range."""
    text = getattr(result, "stdout", "") or ""
    try:
        text += result.stderr  # type: ignore[attr-defined]
    except (ValueError, AttributeError):
        pass  # old click: stderr already folded into stdout
    return text


def test_mock_missing_local_extra_prints_pip_install_and_exits_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(**_: object) -> None:
        raise ImportError("No module named 'uvicorn'")

    monkeypatch.setattr("agent_fabric.simulator.server.serve", _raise)
    result = runner.invoke(app, ["mock"])

    assert result.exit_code == 1  # install prompt, NOT the exit-3 verification block
    out = _combined(result)
    assert 'pip install "agent-fabric[local]"' in out
    assert "blocked on verification" not in out  # this is not a §0.3 gate


def test_mock_wires_host_and_port_through_to_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _spy(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("agent_fabric.simulator.server.serve", _spy)
    result = runner.invoke(app, ["mock", "--host", "0.0.0.0", "--port", "9999"])

    assert result.exit_code == 0
    assert captured == {"host": "0.0.0.0", "port": 9999}


def test_mock_defaults_bind_localhost_8080(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "agent_fabric.simulator.server.serve", lambda **kw: captured.update(kw)
    )
    result = runner.invoke(app, ["mock"])

    assert result.exit_code == 0
    assert captured == {"host": "127.0.0.1", "port": 8080}
