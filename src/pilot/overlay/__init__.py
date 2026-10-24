"""PoE2 Pilot overlay: run_overlay(source, actions, config) -> int."""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

__all__ = ["run_overlay"]


def _tray_icon():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(20, 20, 20))
    p.setPen(QColor(255, 216, 74))
    p.drawRoundedRect(2, 2, 28, 28, 7, 7)
    p.setPen(QColor(255, 255, 255))
    f = p.font()
    f.setBold(True)
    f.setPixelSize(16)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "P2")
    p.end()
    return QIcon(pm)


def run_overlay(source, actions, config: dict) -> int:
    """Show the HUD, poll `source.snapshot()` at 10 Hz, serve hotkeys. Blocks until Quit.

    config keys (all optional): hotkeys{}, hide_when_unfocused, game_exes, scale, x, y,
    dim_opacity, details_provider, on_save, palette,
    gem_provider() -> tuple[GemRow], level_provider() -> int|None, icon_cache (IconCache),
    gems_window {x, y, scale}, tree_provider() -> TreeView|None, tree_window {x, y, scale, zoom}.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

    from .hotkeys import HotkeyManager
    from .gems_window import GemsWindow
    from .hud import HudWindow
    from .tree_window import TreeWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)

    hud = HudWindow(config)
    gems = GemsWindow(config)
    tree = TreeWindow(config)

    def tick():
        try:
            hud.set_state(source.snapshot())
        except Exception:
            log.exception("snapshot failed")

    poll = QTimer()
    poll.setInterval(100)
    poll.timeout.connect(tick)

    vis = QTimer()
    vis.setInterval(250)
    vis.timeout.connect(hud.refresh_visibility)
    vis.timeout.connect(gems.refresh_visibility)
    vis.timeout.connect(tree.refresh_visibility)

    def act(name):
        return lambda: getattr(actions, name)()

    hotkeys = HotkeyManager(
        {
            "next": act("next_step"),
            "prev": act("prev_step"),
            "reset": act("reset_run"),
            "edit": hud.toggle_edit,
            "hide": hud.toggle_hidden,
            "details": hud.set_details_visible,
            "gems": gems.toggle,
            "tree": tree.toggle,
            "pause": act("toggle_pause"),
        },
        config.get("hotkeys"),
    )

    tray = QSystemTrayIcon(_tray_icon())
    tray.setToolTip("PoE2 Pilot")
    menu = QMenu()
    menu.addAction("Edit position", hud.toggle_edit)
    menu.addAction("Gems", gems.toggle)
    menu.addAction("Tree", tree.toggle)
    menu.addAction("Quit", app.quit)
    tray.setContextMenu(menu)
    tray.show()

    tick()
    hud.refresh_visibility()
    poll.start()
    vis.start()
    hotkeys.start()
    try:
        return app.exec()
    finally:
        hotkeys.stop()
        tray.hide()
        hud.hide()
        gems.hide()
        gems.tip.hide()
        tree.hide()
        tree.tip.hide()
