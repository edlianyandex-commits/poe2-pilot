"""Render the HUD offscreen over a noisy game-like background and save PNGs to docs/screens."""
import random
from pathlib import Path

import pytest

from pilot.contracts import HudState, Toast

SCREENS = Path(__file__).resolve().parents[2] / "docs" / "screens"


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


BASE = dict(act=2, area_name="Тропа Изменницы", area_level=19, char_level=17,
            step_short="→ Ворота Халани", next_short="WP · Дорога", step_index=31, step_total=84,
            run_time_s=4360.0, running=True)


@pytest.fixture
def make_hud(qapp):
    from pilot.overlay.hud import HudWindow

    t = [100.0]

    def make(state, cfg=None, t_after=100.0):
        hud = HudWindow(cfg or {}, clock=lambda: t[0])
        hud.set_state(state)
        t[0] = t_after
        return hud

    return make


def test_screen_normal(make_hud):
    hud = make_hud(HudState(**BASE, split_delta_s=-42.0))
    assert _shot(hud, "hud_normal.png").stat().st_size > 1000


def test_screen_ahead_toast(make_hud):
    st = HudState(**{**BASE, "split_delta_s": -42.0},
                  toasts=(Toast("Акт 2 · сплит −0:42", "split"), Toast("Ур. 17: +Быстрота · Ледяная стрела", "level")))
    hud = make_hud(st, t_after=101.0)
    _shot(hud, "hud_ahead_toast.png")


def test_screen_warn(make_hud):
    hud = make_hud(HudState(**BASE, split_delta_s=75.0, warn="Ур. ниже зоны −4"))
    _shot(hud, "hud_warn.png")


def test_screen_details(make_hud):
    cfg = {"details_provider": lambda: ["затем: Лагерь", "затем: Дорога", "Гем: Ледяная стрела", "Пассивка: Стойкость"]}
    hud = make_hud(HudState(**BASE, split_delta_s=-42.0), cfg)
    hud.set_details_visible(True)
    _shot(hud, "hud_details.png")


def test_screen_extras(make_hud):
    """Interlude + dimmed (not running) variants, handy for eyeballing."""
    hud = make_hud(HudState(**{**BASE, "act": 102, "area_level": 45}, split_delta_s=-3.0))
    _shot(hud, "hud_interlude.png")
    hud = make_hud(HudState(**{**BASE, "running": False}))
    _shot(hud, "hud_dim.png")
