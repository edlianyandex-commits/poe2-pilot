"""PoE2 Pilot overlay: run_overlay(source, actions, config) -> int."""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

__all__ = ["run_overlay"]


def run_overlay(source, actions, config: dict) -> int:
    """Show the HUD, poll `source.snapshot()` at 10 Hz, serve hotkeys. Blocks until Quit.

    config keys (all optional): hotkeys{}, hide_when_unfocused, game_exes, scale, x, y,
    dim_opacity, details_provider, on_save, palette,
    gem_provider() -> tuple[GemRow], level_provider() -> int|None, icon_cache (IconCache),
    gems_window {x, y, scale}, tree_provider() -> TreeView|None, tree_window {x, y, scale, zoom},
    on_switch_build() (starts the start window again; the overlay then quits),
    _show_help (show the hotkeys cheat sheet once the overlay is up).
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

    from pilot.brand import logo_icon

    from . import winapi
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

    def hotkeys_follow_game():
        if not config.get("hide_when_unfocused", True):
            hotkeys.set_active(True)
            return
        fg = winapi.foreground_info()
        hotkeys.set_active(winapi.is_game_foreground(fg, config.get("game_exes") or winapi.GAME_EXES))

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

    def switch_build():
        config["on_switch_build"]()
        app.quit()

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    from pilot import __version__
    from pilot.config import config_dir
    from pilot.i18n import tr
    from pilot.launcher.help import HotkeysDialog
    from pilot.updates import REPO

    cheat = []

    def show_help():
        if not cheat:
            cheat.append(HotkeysDialog(config.get("hotkeys")))
        cheat[0].show()
        cheat[0].raise_()
        cheat[0].activateWindow()

    tray = QSystemTrayIcon(logo_icon())
    tray.setToolTip(f"PoE2 Pilot {__version__}")
    menu = QMenu()
    menu.addAction(f"PoE2 Pilot {__version__}").setEnabled(False)
    menu.addSeparator()
    if config.get("on_switch_build"):
        menu.addAction(tr("Сменить билд…"), switch_build)
        menu.addSeparator()
    menu.addAction(tr("Положение HUD"), hud.toggle_edit)
    menu.addAction(tr("Гемы"), gems.toggle)
    menu.addAction(tr("Дерево"), tree.toggle)
    menu.addSeparator()
    menu.addAction(tr("Хоткеи…"), show_help)
    menu.addAction(tr("Папка логов"), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(config_dir()))))
    menu.addAction(tr("Страница проекта"), lambda: QDesktopServices.openUrl(QUrl(f"https://github.com/{REPO}")))
    menu.addSeparator()
    menu.addAction(tr("Выход"), app.quit)
    tray.setContextMenu(menu)
    tray.show()

    tick()
    hud.refresh_visibility()
    poll.start()
    vis.start()
    hotkeys.start()
    vis.timeout.connect(hotkeys_follow_game)
    if config.get("_show_help"):
        QTimer.singleShot(600, show_help)
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
