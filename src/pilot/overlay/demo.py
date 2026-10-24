"""`python -m pilot.overlay.demo [--seconds N]` - HUD without the game.

Cycles scripted states: zone change, level-up toast, ahead/behind delta, warning, interlude.
Hotkeys work (alt+q hold, alt+e edit); quit from the tray icon, or --seconds N.
"""
from __future__ import annotations

import argparse
import time

from pilot.contracts import HudState, Toast

CYCLE_S = 36.0


def _s(_unused, **kw) -> HudState:
    return HudState(running=True, game_focused=True, **kw)


class DemoSource:
    """Fake SnapshotSource. Scenes are picked by time within a looping cycle."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._t0 = clock()
        self.log: list[str] = []

    def snapshot(self) -> HudState:
        t = (self._clock() - self._t0)
        ph = t % CYCLE_S
        run = 4360.0 + t
        base = dict(run_time_s=run, step_total=84)
        if ph < 6:       # steady state, slightly behind
            return _s(0, act=1, area_name="Клирфелл", area_level=2, char_level=3,
                      step_short="→ Грельвуд", next_short="Крепость Гелта", step_index=7,
                      split_delta_s=5.0, **base)
        if ph < 9:       # zone change toast
            return _s(0, act=1, area_name="Грельвуд", area_level=4, char_level=4,
                      step_short="→ Крепость Гелта", next_short="WP", step_index=8,
                      split_delta_s=5.0,
                      toasts=(Toast("Грельвуд · сплит +0:05", "split", 3.0),), **base)
        if ph < 15:      # level-up toast, ahead of PB
            return _s(0, act=1, area_name="Грельвуд", area_level=4, char_level=5,
                      step_short="⚔ Хищник", next_short="Склеп", step_index=9,
                      split_delta_s=-42.0,
                      toasts=(Toast("Ур. 5: +Быстрота · Ледяная стрела", "level", 3.0),), **base)
        if ph < 21:      # act 2, behind PB, two stacked toasts
            return _s(0, act=2, area_name="Тропа Изменницы", area_level=19, char_level=17,
                      step_short="→ Ворота Халани", next_short="WP · Дорога", step_index=31,
                      split_delta_s=75.0,
                      toasts=(Toast("Акт 2 · сплит +1:15", "split", 3.0),
                              Toast("Ур. 17: пассивка Стойкость", "level", 3.0)), **base)
        if ph < 28:      # warning replaces line 2
            return _s(0, act=2, area_name="Тропа Изменницы", area_level=19, char_level=14,
                      step_short="→ Ворота Халани", next_short="WP", step_index=32,
                      split_delta_s=75.0, warn="Ур. ниже зоны −5", **base)
        return _s(0, act=102, area_name="Интерлюдия", area_level=45, char_level=44,   # interlude
                  step_short="→ Врата Тёмного Города", next_short="Убить босса", step_index=60,
                  split_delta_s=-3.0,
                  toasts=(Toast("Интерлюдия 2", "zone", 3.0),) if ph < 31 else (), **base)


class DemoActions:
    def next_step(self): pass
    def prev_step(self): pass
    def reset_run(self): pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=0, help="auto-quit after N seconds")
    args = ap.parse_args(argv)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from . import run_overlay

    app = QApplication.instance() or QApplication([])
    if args.seconds > 0:
        QTimer.singleShot(int(args.seconds * 1000), app.quit)
    cfg = {
        "hide_when_unfocused": False,
        "details_provider": lambda: [
            "затем: Склеп",
            "затем: WP",
            "Гем: Ледяная стрела",
            "Пассивка: Быстрота",
        ],
    }
    return run_overlay(DemoSource(), DemoActions(), cfg)


if __name__ == "__main__":
    raise SystemExit(main())
