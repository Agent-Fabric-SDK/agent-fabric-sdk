"""Dev-time bootstrap for the demos: import path shim + optional .env loader.

Two conveniences, both demo-only (the SDK itself never reads env files
implicitly — see core/config.py):

1. If ``agent_fabric`` is not installed, add ``python/src`` to ``sys.path`` so
   the demos run straight from a checkout. (An editable install is preferred:
   ``pip install -e python``.)
2. Load ``.env.local`` then ``.env`` from the repo root into ``os.environ`` so
   ``export``-ing the AGENT_FABRIC_LLM_PROXY_* vars by hand is optional. Values
   already present in the environment win — an explicit shell ``export`` is
   never overridden.

Importing this module runs both steps.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# --- 1. import path shim ---------------------------------------------------
_SRC = _REPO_ROOT / "python" / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# --- 2. minimal, dependency-free .env loader -------------------------------
def _parse_env(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines. Ignores blanks, ``#`` comments, and a leading
    ``export``; strips matching single/double quotes. No interpolation."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        line = line.removeprefix("export ")
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            out[key] = value
    return out


_DEMO_DIR = Path(__file__).resolve().parent


def _load_env_files() -> None:
    # Search the demo dir, the repo root, and the cwd — in that order — so a
    # .env.local sitting next to the demos is picked up. Precedence via
    # setdefault (first writer wins): explicit os.environ export > .env.local >
    # .env, and earlier directories win over later ones.
    seen: set[Path] = set()
    for base in (_DEMO_DIR, _REPO_ROOT, Path.cwd()):
        if base in seen:
            continue
        seen.add(base)
        for name in (".env.local", ".env"):
            path = base / name
            if not path.is_file():
                continue
            for key, value in _parse_env(path.read_text()).items():
                os.environ.setdefault(key, value)


_load_env_files()
