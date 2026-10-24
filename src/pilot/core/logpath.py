"""Locate Path of Exile 2's Client.txt (Steam, standalone, other Steam libraries)."""
from __future__ import annotations

import re
from pathlib import Path

_STEAM_ROOT = Path(r"C:\Program Files (x86)\Steam")
_STANDALONE = Path(
    r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile 2\logs\Client.txt"
)
_GAME_REL = Path("steamapps") / "common" / "Path of Exile 2" / "logs" / "Client.txt"
_RE_VDF_PATH = re.compile(r'"path"\s+"((?:[^"\\]|\\.)*)"', re.IGNORECASE)


def parse_library_folders(text: str) -> list[Path]:
    """Extract library roots from the text of Steam's libraryfolders.vdf."""
    return [Path(m.replace("\\\\", "\\")) for m in _RE_VDF_PATH.findall(text)]


def _registry_steam_root() -> Path | None:
    try:
        import winreg  # Windows only
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except (ImportError, OSError):
        return None


def candidate_paths(steam_roots: list[Path] | None = None) -> list[Path]:
    """All plausible Client.txt locations, most likely first (not checked for existence)."""
    roots: list[Path] = []
    for r in steam_roots if steam_roots is not None else [_STEAM_ROOT, _registry_steam_root()]:
        if r is not None and r not in roots:
            roots.append(r)
    out = [r / _GAME_REL for r in roots]
    out.append(_STANDALONE)
    for r in list(roots):
        vdf = r / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lib in parse_library_folders(text):
            p = lib / _GAME_REL
            if p not in out:
                out.append(p)
    return out


def find_client_log(steam_roots: list[Path] | None = None) -> Path | None:
    """First existing Client.txt, or None."""
    for p in candidate_paths(steam_roots):
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return None
