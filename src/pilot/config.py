"""User config at %APPDATA%/poe2-pilot/config.json (lead-owned)."""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS: dict = {
    "log_path": None,                      # None -> auto-detect
    "build_code_file": None,               # last build taken off with (name in builds/ or a path)
    "check_updates": True,                 # start window asks GitHub for new builds and releases
    "update_repo": None,                   # "owner/name"; None -> pilot.updates.REPO
    "hud": {"x": None, "y": 24, "scale": 1.0, "opacity": 1.0},
    "hide_when_unfocused": True,
    "pause_when_unfocused": True,          # timer stops while the game window has no focus
    "afk_pause_s": 300,                    # a log silent this long = AFK: that stretch is not counted
    "hotkeys": {                           # names match overlay.hotkeys.DEFAULT_HOTKEYS
        "details": "alt+q",
        "next": "alt+]",
        "prev": "alt+[",
        "reset": "alt+r",
        "edit": "alt+e",
        "hide": "alt+h",
        "gems": "alt+g",
        "tree": "alt+t",
        "pause": "alt+p",
    },
}


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "poe2-pilot"


def config_path() -> Path:
    return config_dir() / "config.json"


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load_config(path: Path | None = None) -> dict:
    path = path or config_path()
    try:
        user = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        user = {}
    return _merge(DEFAULTS, user)


def save_config(cfg: dict, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in cfg.items() if not callable(v) and not k.startswith("_")}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
