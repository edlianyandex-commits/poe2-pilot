"""`python -m pilot.overlay.demo [--seconds N] [--palette colorblind]` - HUD without the game.

Cycles scripted states: zone change, level-up + gear toasts, ahead/behind delta, warning,
interlude. Hotkeys work (alt+q hold, alt+e edit, alt+g gems, alt+t tree); quit from the tray icon, or --seconds N.
"""
from __future__ import annotations

import argparse
import time

from pilot.contracts import GemCard, GemRow, HudState, Toast, TreeNodeView, TreeView

CYCLE_S = 36.0
MARKS = (0.12, 0.31, 0.47, 0.62, 0.78)


def _s(**kw) -> HudState:
    return HudState(running=True, game_focused=True, split_marks=MARKS, step_total=84, **kw)


class DemoSource:
    """Fake SnapshotSource. Scenes are picked by time within a looping cycle."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._t0 = clock()

    def snapshot(self) -> HudState:
        t = self._clock() - self._t0
        ph = t % CYCLE_S
        base = dict(run_time_s=4360.0 + t)
        if ph < 6:       # steady state, slightly behind
            return _s(act=1, area_name="Клирфелл", area_level=2, char_level=3,
                      step_short="→ Грельвуд", step_kind="move",
                      next_short="◆ Крепость Гелта", next_kind="wp",
                      step_index=7, progress=0.08, split_delta_s=5.0, **base)
        if ph < 9:       # zone change toast
            return _s(act=1, area_name="Грельвуд", area_level=4, char_level=4,
                      step_short="◆ Крепость Гелта", step_kind="wp",
                      next_short="⚔ Рудья, Ужасный Инженер", next_kind="boss",
                      step_index=8, progress=0.13, split_delta_s=5.0,
                      toasts=(Toast("Грельвуд", "zone", 3.0),), **base)
        if ph < 15:      # level-up + gear toasts, ahead of PB
            return _s(act=1, area_name="Грельвуд", area_level=4, char_level=5,
                      step_short="⚔ Рудья, Ужасный Инженер", step_kind="boss",
                      next_short="⌂ Клирфелл", next_kind="town",
                      step_index=9, progress=0.2, split_delta_s=-42.0,
                      toasts=(Toast("Ур 5: +Быстрота · Ледяная стрела", "level", 3.0),
                              Toast("Надеть: Кожаный пояс", "gear", 3.0)), **base)
        if ph < 21:      # act 2, behind PB, two stacked toasts
            return _s(act=2, area_name="Тропа Изменницы", area_level=19, char_level=17,
                      step_short="→ Ворота Халани", step_kind="move",
                      next_short="! Квест Дреммара", next_kind="quest",
                      step_index=31, progress=0.4, split_delta_s=75.0,
                      toasts=(Toast("Акт 2 · сплит +1:15", "split", 3.0),
                              Toast("Ур 17: пассивка Стойкость", "level", 3.0)), **base)
        if ph < 28:      # warning replaces line 2, zone far above the character
            return _s(act=2, area_name="Тропа Изменницы", area_level=19, char_level=14,
                      step_short="✦ Испытание", step_kind="trial",
                      next_short="◆ WP", next_kind="wp",
                      step_index=32, progress=0.55, split_delta_s=75.0,
                      warn="Ур. ниже зоны −5", **base)
        return _s(act=102, area_name="Интерлюдия", area_level=45, char_level=44,
                  step_short="→ Врата Тёмного Города", step_kind="move",
                  next_short="⚔ Убить босса", next_kind="boss",
                  step_index=60, progress=0.7, split_delta_s=-3.0,
                  toasts=(Toast("Интерлюдия 2", "zone", 3.0),) if ph < 31 else (), **base)


def demo_gem_rows() -> tuple[GemRow, ...]:
    def g(name, kind, color, desc=""):
        return GemCard(name, kind, color, desc)

    return (
        GemRow(g("Twister", "skill", "dex", "Spiral through enemies as a whirlwind, damaging them "
                 "and building up Wind. Releasing the buildup unleashes a Twister."),
               (g("Salvo", "support", "dex", "Supported skills fire a salvo of projectiles."),
                g("Prolonged Duration II", "support", "int", "Supported skills have more skill effect duration."))),
        GemRow(g("Barrage", "skill", "dex", "Fire a rapid volley of arrows at the target."),
               (g("Heightened Charges", "support", "str", "Supported skills have more effect from charges."),)),
        GemRow(g("Whirling Slash", "skill", "str", "Leap and spin, slashing all nearby enemies."),
               (g("Exploit Weakness", "support", "str", "Supported skills deal more damage to enemies with Armour broken."),)),
    )


def demo_tree_view(level: int = 14) -> TreeView:
    """A small hex cluster (~40 nodes) with taken / next / planned / offplan / other nodes."""
    import math
    from collections import deque

    sp = 64.0
    cells = [(0, 0)]
    dirs = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]
    ring = 1
    while len(cells) < 41:
        q, r = ring * dirs[4][0], ring * dirs[4][1]
        for d in dirs:
            for _ in range(ring):
                cells.append((q, r))
                q, r = q + d[0], r + d[1]
        ring += 1
    cells = cells[:41]
    pos = {c: (sp * (c[0] + c[1] / 2), sp * c[1] * math.sqrt(3) / 2) for c in cells}
    # spanning tree by BFS from the centre, plus a few cross links
    parent, depth, order = {(0, 0): None}, {(0, 0): 0}, []
    dq = deque([(0, 0)])
    while dq:
        c = dq.popleft()
        order.append(c)
        for d in dirs:
            nb = (c[0] + d[0], c[1] + d[1])
            if nb in pos and nb not in parent:
                parent[nb], depth[nb] = c, depth[c] + 1
                dq.append(nb)
    edges = [(parent[c], c) for c in order if parent[c] is not None]
    edges += [e for e in [((1, 0), (1, 1)), ((-1, 1), (-2, 2)), ((0, -1), (1, -2))] if e[0] in pos and e[1] in pos and e not in edges]
    names = ["Projectile Damage", "Attack Speed", "Evasion", "Life Regeneration", "Accuracy", "Critical Chance",
             "Flask Charges", "Armour", "Stun Threshold", "Mana Regeneration", "Skill Speed", "Area of Effect"]
    taken = set(order[:14])
    frontier = [c for c in order if c not in taken and parent[c] in taken]
    nxt = frontier[:3]
    planned = [c for c in order if c not in taken and c not in nxt and depth[c] <= 4][:8]
    offplan = [c for c in order if c not in taken and c not in nxt and c not in planned][3::5][:2]
    nodes = []
    for i, c in enumerate(order):
        x, y = pos[c]
        state, ordn, lv = "other", None, None
        if c in taken:
            state = "taken"
        elif c in nxt:
            state, ordn, lv = "next", nxt.index(c) + 1, level + nxt.index(c) // 2
        elif c in planned:
            state, lv = "planned", level + 2 + planned.index(c)
        elif c in offplan:
            state = "offplan"
        kind = "start" if i == 0 else "keystone" if i == 33 else "notable" if i % 7 == 3 else             "attribute" if i % 5 == 0 else "jewel" if i == 18 else "small"
        name = f"{names[i % len(names)]}" + (" Mastery" if kind == "notable" else "")
        nodes.append(TreeNodeView(f"n{i}", name, kind, x, y,
                                  (f"{8 + i % 9}% increased {names[i % len(names)].lower()}",) if kind != "start" else (),
                                  state, ordn, lv))
    ids = {c: f"n{i}" for i, c in enumerate(order)}
    return TreeView(tuple(nodes), tuple((ids[a], ids[b]) for a, b in edges), level=level, points_free=2)


class DemoActions:
    def next_step(self): pass
    def prev_step(self): pass
    def reset_run(self): pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=0, help="auto-quit after N seconds")
    ap.add_argument("--palette", choices=["default", "colorblind"], default="default")
    args = ap.parse_args(argv)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from . import run_overlay

    app = QApplication.instance() or QApplication([])
    if args.seconds > 0:
        QTimer.singleShot(int(args.seconds * 1000), app.quit)
    source = DemoSource()
    cfg = {
        "hide_when_unfocused": False,
        "gem_provider": demo_gem_rows,
        "tree_provider": demo_tree_view,
        "level_provider": lambda: source.snapshot().char_level,
        "palette": args.palette,
        "details_provider": lambda: [
            "затем: Склеп",
            "затем: WP",
            "Гем: Ледяная стрела",
            "Пассивка: Быстрота",
        ],
    }
    return run_overlay(source, DemoActions(), cfg)


if __name__ == "__main__":
    raise SystemExit(main())
