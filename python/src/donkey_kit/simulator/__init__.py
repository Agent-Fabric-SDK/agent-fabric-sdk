"""The local gateway simulator (BG §1.4) — the engine behind ``donkey mock``.

A dev-only sibling of the production layers. The five production layers
(``core``/``llm``/``registry``/``tools``/``integrations``) MUST NOT import it —
an ``import-linter`` forbidden contract enforces that, so no ``starlette``/
``uvicorn`` import can ever drift onto the base ``import donkey_kit`` path. The
simulator itself only imports *downward* into the framework-free ``core`` (for
verified header names), never the reverse.

Only framework-free submodules are imported at module top here, and neither
:mod:`~donkey_kit.simulator.app` nor :mod:`~donkey_kit.simulator.server`
imports ``starlette``/``uvicorn`` at module scope (they defer those to
``build_app()``/``serve()``). So ``import donkey_kit.simulator`` succeeds under
the base-only CI job with the ``[local]`` extra absent.
"""

from __future__ import annotations

from .app import ASGIApp, SimulatorConfig, build_app
from .server import serve

__all__ = ["ASGIApp", "SimulatorConfig", "build_app", "serve"]
