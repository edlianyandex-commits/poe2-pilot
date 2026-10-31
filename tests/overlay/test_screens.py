"""Render the HUD offscreen over a noisy game-like background and save PNGs (docs/screens on request)."""
import os
import tempfile
import random
from pathlib import Path

import pytest

from pilot.contracts import HudState, Toast

# docs/screens is refreshed only on request (POE2_PILOT_SCREENS=1); a plain run renders to the temp dir
SCREENS = (Path(__file__).resolve().parents[2] / "docs" / "screens" if os.environ.get("POE2_PILOT_SCREENS")
           else Path(tempfile.gettempdir()) / "poe2-pilot-screens")


def _backdrop(w, h, seed=7):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter

    rnd = random.Random(seed)
    img = QImage(w, h, QImage.Format_ARGB32)
    p = QPainter(img)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor(46, 38, 30))
    g.setColorAt(0.5, QColor(70, 58, 44))
    g.setColorAt(1, QColor(28, 34, 36))
    p.fillRect(img.rect(), g)
    p.setPen(Qt.NoPen)
    for _ in range(2200):               # busy foliage / stone noise
        c = rnd.randint(20, 140)
        p.setBrush(QColor(c + rnd.randint(0, 40), c, max(0, c - rnd.randint(0, 30)), 170))
        r = rnd.randint(2, 14)
        p.drawEllipse(rnd.randint(-10, w), rnd.randint(-10, h), r, r)
    for _ in range(40):                 # a few bright highlights (spell effects)
        p.setBrush(QColor(255, rnd.randint(150, 255), rnd.randint(60, 220), 120))
        r = rnd.randint(10, 40)
        p.drawEllipse(rnd.randint(0, w), rnd.randint(0, h), r, r)
    p.end()
    return img


def _shot(hud, name, margin=24):
    from PySide6.QtGui import QPainter

    pm = hud.grab()
    w, h = pm.width() + 2 * margin, pm.height() + 2 * margin
    img = _backdrop(w, h)
    p = QPainter(img)
    p.drawPixmap(margin, margin, pm)
    p.end()
    SCREENS.mkdir(parents=True, exist_ok=True)
    out = SCREENS / name
    assert img.save(str(out))
    return out


MARKS = (0.12, 0.31, 0.47, 0.62, 0.78)
BASE = dict(act=2, area_name="Тропа Изменницы", area_level=19, char_level=17,
            step_short="⚔ Рудья, Ужасный Инженер", step_kind="boss",
            next_short="◆ Ворота Халани", next_kind="wp", step_index=31, step_total=84,
            run_time_s=4360.0, running=True, progress=0.40, split_marks=MARKS)


@pytest.fixture
def make_hud(qapp):
    from pilot.overlay.hud import HudWindow

    t = [100.0]

    def make(state, cfg=None, t_after=100.0, scale=1.0):
        cfg = dict(cfg or {})
        cfg.setdefault("scale", scale)
        hud = HudWindow(cfg, clock=lambda: t[0])
        hud.set_state(state)
        t[0] = t_after
        return hud

    return make


def test_screen_normal(make_hud):
    hud = make_hud(HudState(**BASE, split_delta_s=-42.0))
    assert _shot(hud, "hud_normal.png").stat().st_size > 1000


def test_screen_ahead_toast(make_hud):
    st = HudState(**{**BASE, "split_delta_s": -42.0, "char_level": 18},
                  toasts=(Toast("Ур 18: +Быстрота · Ледяная стрела", "level"),
                          Toast("Акт 2 · сплит −0:42", "split"),
                          Toast("Надеть: Кожаный пояс", "gear")))
    hud = make_hud(st, t_after=101.0)
    _shot(hud, "hud_ahead_toast.png")


def test_screen_toast_kinds(make_hud):
    st = HudState(**BASE, toasts=(Toast("Грельвуд", "zone"), Toast("Ур. ниже зоны −5", "warn")))
    _shot(make_hud(st, t_after=101.0), "hud_toast_kinds.png")


def test_screen_warn(make_hud):
    hud = make_hud(HudState(**BASE, split_delta_s=75.0, warn="Ур. ниже зоны −4"))
    _shot(hud, "hud_warn.png")


def test_screen_details(make_hud):
    cfg = {"details_provider": lambda: ["затем: Лагерь", "затем: Дорога", "Гем: Ледяная стрела",
                                        "Пассивка: Стойкость"]}
    hud = make_hud(HudState(**BASE, split_delta_s=-42.0), cfg)
    hud.set_details_visible(True)
    _shot(hud, "hud_details.png")


def test_screen_interlude(make_hud):
    st = HudState(**{**BASE, "act": 102, "area_level": 45, "char_level": 44,
                     "step_short": "→ Врата Тёмного Города", "step_kind": "move",
                     "next_short": "⚔ Убить босса", "next_kind": "boss", "progress": 0.7},
                  split_delta_s=-3.0)
    _shot(make_hud(st), "hud_interlude.png")


def test_screen_colorblind(make_hud):
    st = HudState(**BASE, split_delta_s=-42.0)
    _shot(make_hud(st, {"palette": "colorblind"}), "hud_colorblind.png")
    st = HudState(**{**BASE, "progress": 0.55}, split_delta_s=75.0)
    _shot(make_hud(st, {"palette": "colorblind"}), "hud_colorblind_behind.png")


def test_screen_dim_and_scales(make_hud):
    _shot(make_hud(HudState(**{**BASE, "running": False}, split_delta_s=5.0)), "hud_dim.png")
    st = HudState(**BASE, split_delta_s=-42.0, toasts=(Toast("Ур 18: +Быстрота", "level"),))
    _shot(make_hud(st, scale=0.75, t_after=101.0), "hud_scale_075.png")
    _shot(make_hud(st, scale=2.0, t_after=101.0), "hud_scale_200.png")
