"""Where bundled data lives: the repo root from source, the unpacked bundle inside the exe.

data/ and builds/ come from the content root: the bundled one, or the copy that the in-app update
(pilot.updates) downloaded to %APPDATA%/poe2-pilot/content when its content.json is newer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MANIFEST = "content.json"


def root() -> Path:
    if getattr(sys, "frozen", False):          # PyInstaller: data/ and builds/ sit next to the code
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def user_content() -> Path:
    from pilot.config import config_dir
    return config_dir() / "content"


def read_manifest(base: Path) -> dict | None:
    try:
        return json.loads((base / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def version_key(v: str | None) -> tuple[int, ...]:
    """'2026.10.31' / '1.0.2' -> comparable tuple; junk -> ()."""
    try:
        return tuple(int(p) for p in (v or "").split("."))
    except ValueError:
        return ()


def content_root() -> Path:
    """The downloaded content if it is newer than the bundled one, else the bundled root."""
    bundled, user = root(), user_content()
    mine, theirs = read_manifest(bundled) or {}, read_manifest(user) or {}
    if version_key(theirs.get("version")) > version_key(mine.get("version")):
        return user
    return bundled


CONTENT = content_root()
DATA = CONTENT / "data"
BUILDS = CONTENT / "builds"
