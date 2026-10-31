"""Start window: pick a build on the departure board, then the overlay takes off with it."""
from __future__ import annotations

import subprocess
import sys

__all__ = ["pick_build", "relaunch"]


def pick_build(cfg: dict) -> str | None:
    """Show the board; -> the chosen build's file name, or None (closed, or restarting for an update)."""
    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QApplication

    from pilot.catalog import load_catalog
    from pilot.paths import CONTENT, read_manifest

    from .board import BoardWindow

    QApplication.instance() or QApplication(sys.argv[:1])
    updater = None
    if cfg.get("check_updates", True):
        from pilot.updates import Updater
        updater = Updater(cfg.get("update_repo") or Updater().repo)
    win = BoardWindow(load_catalog(), last=cfg.get("build_code_file"),
                      content_version=(read_manifest(CONTENT) or {}).get("version", ""), updater=updater)
    loop = QEventLoop()
    win.finished.connect(loop.quit)
    win.show()
    win.raise_()
    win.activateWindow()
    loop.exec()
    if win.restart:
        relaunch()
        return None
    return win.result


def relaunch(extra: list[str] | None = None) -> None:
    """Start a fresh copy of the app (same options, minus --build) and let the caller quit."""
    args, skip = [], False
    for a in sys.argv[1:]:
        if skip:
            skip = False
        elif a == "--build":
            skip = True
        elif not a.startswith("--build="):
            args.append(a)
    head = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "pilot.app"]
    if "--wait-lock" not in args:
        args.append("--wait-lock")                # the new copy waits until this one has quit
    subprocess.Popen(head + args + (extra or []), close_fds=True)
