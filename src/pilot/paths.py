"""Where bundled data lives: the repo root from source, the unpacked bundle inside the exe."""
from __future__ import annotations

import sys
from pathlib import Path


def root() -> Path:
    if getattr(sys, "frozen", False):          # PyInstaller: data/ and builds/ sit next to the code
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


DATA = root() / "data"
BUILDS = root() / "builds"
