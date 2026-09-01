"""The ``agent-fabric`` CLI (§5.2, §7).

Telemetry is ON by default in the CLI (§2.5). Commands that need a verified
platform API print an honest, actionable "blocked pending verification" message
and exit non-zero rather than fabricating calls (working instruction #2).
Commands that need no platform API (spec validation) do real work now.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import typer
except ImportError:  # pragma: no cover - install-time guidance
    print(
        'The CLI needs the [cli] extra. Install it with:\n'
        '    pip install "mulesoft-agent-fabric[cli]"',
        file=sys.stderr,
    )
    raise SystemExit(1) from None

from ..core.errors import FabricError
from .spec import FabricSpec

app = typer.Typer(
    add_completion=False,
    help="SDK for MuleSoft Agent Fabric — governed models, tools, provisioning-as-code.",
)


def _load_spec(file: Path) -> FabricSpec:
    try:
        return FabricSpec.from_yaml(file.read_text())
    except Exception as exc:  # noqa: BLE001 - surface a clean message
        typer.secho(f"Invalid spec {file}: {exc}", fg="red", err=True)
        raise typer.Exit(2) from exc


def _blocked(what: str) -> None:
    typer.secho(f"blocked on verification: {what}", fg="yellow", err=True)
    typer.secho(
        "See docs/verified-apis.md — this command is scaffolded but not wired "
        "until the underlying platform API is confirmed against a sandbox (§0.3).",
        err=True,
    )
    raise typer.Exit(3)


@app.command()
def validate(file: Path = typer.Option(..., "-f", "--file", help="fabric.yaml")) -> None:
    """Validate a fabric.yaml against the schema (needs no platform API)."""
    spec = _load_spec(file)
    typer.secho(
        f"OK: {spec.metadata.name} — {len(spec.mcpBridges)} MCP bridge(s), "
        f"env {spec.metadata.environment}.",
        fg="green",
    )


@app.command()
def plan(file: Path = typer.Option(..., "-f", "--file"),
         dry_run: bool = typer.Option(False, "--dry-run"),
         out: Path | None = typer.Option(None, "--out", help="write plan.json for CI")) -> None:
    """Show the create/update/remove plan (read-before-write, §5.2)."""
    _load_spec(file)
    _blocked("MCP Bridge provisioning read API (§5.2, §5)")


@app.command()
def apply(file: Path = typer.Option(..., "-f", "--file"),
          auto_approve: bool = typer.Option(False, "--auto-approve")) -> None:
    """Apply the plan (CI-only, platform-controlled creds, §5.4)."""
    _load_spec(file)
    _blocked("MCP Bridge provisioning write API (§5.2, §5.4)")


@app.command()
def drift(file: Path = typer.Option(..., "-f", "--file")) -> None:
    """Compare live state against the spec; exit non-zero on drift (§5.2)."""
    _load_spec(file)
    _blocked("MCP Bridge provisioning read API (§5.2)")


@app.command()
def lint(file: Path = typer.Option(..., "-f", "--file")) -> None:
    """Governance lint (§5.3). Local spec-shape checks run now; ruleset
    resolution is gated (§0.3)."""
    _load_spec(file)
    _blocked("governance rulesets resolution API (§5.3, §0.3)")


@app.command()
def generate(file: Path = typer.Option(..., "-f", "--file"),
             target: str = typer.Option("terraform", "--target")) -> None:
    """Emit Terraform from the spec — the §5.5 pivot if provisioning is UI-only."""
    _load_spec(file)
    _blocked("Terraform provider coverage enumeration (§5.5, §0.3)")


@app.command()
def status() -> None:
    """Render published / reachable / governed per asset (§7.6)."""
    _blocked("Exchange + API Manager read APIs (§7.6)")


@app.command()
def init() -> None:
    """Scan the project, propose publishable assets, write .agent-fabric.toml (§7.8)."""
    _blocked("per-framework asset detection + descriptor derivation (§7.8, §7.3)")


@app.command()
def publish(if_changed: bool = typer.Option(True, "--if-changed/--always")) -> None:
    """Publish code-first assets to Exchange (CI-only, §7.5/§7.7)."""
    _blocked("Exchange publication mechanism + digest metadata (§7.5, §7.9)")


@app.command()
def verify() -> None:
    """Check the live server against the Exchange descriptor (§7.4)."""
    _blocked("Exchange descriptor read + live introspection (§7.4, §7.9)")


def main() -> None:  # pragma: no cover
    try:
        app()
    except FabricError as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":  # pragma: no cover
    main()
