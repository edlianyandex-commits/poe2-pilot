"""Start window, pastel gacha style: pick a hero (class), then one of its builds, then start.

  ┌ title bar: mark · PoE2 Pilot · ✦ page title ✦ · clock · — ✕ ──────────────────────┐
  │ page 1: eight hero cards with our chibi art (heroes.py)                           │
  │ page 2: build list (rarity SSR/SR/R, stars) │ hero card of the build │ [ СТАРТ ]   │
  └ footer: [← Герои] content version · update news [Обновить] · keys ────────────────┘
Keys, heroes: arrows pick, Enter opens, Esc quits. Builds: ↑ ↓ PgUp PgDn Home End pick, Enter
starts, Esc / Backspace back to the heroes. Double click a build starts it too.
Build status shows as rarity: verified SSR 5★, guide SR 4★, custom R 3★, older patch OLD.
"""
from __future__ import annotations

import math
import random
import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, QUrl, QVariantAnimation, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QFontMetricsF, QPainter, QPainterPath,
                           QPen, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from pilot import __version__, brand
from pilot.catalog import Catalog, Entry

from . import style as S
from .heroes import HeroPicker, badge, class_art

ROW_H = 84
ROW_GAP = 10
HEAD_H = 54
TWINKLE_MS = 90


# ---------------------------------------------------------------- title bar
class TitleBar(QWidget):
    H = 64

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedHeight(self.H)
        self.setMouseTracking(True)
        self.title = ""
        self.hover: str | None = None
        t = QTimer(self)
        t.setInterval(10_000)
        t.timeout.connect(self.update)
        t.start()

    def set_title(self, text: str) -> None:
        self.title = text
        self.update()

    def _buttons(self) -> dict[str, QRectF]:
        r = self.width() - 20
        return {"close": QRectF(r - 32, 16, 32, 32), "min": QRectF(r - 72, 16, 32, 32)}

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        brand.draw_logo(p, QRectF(22, 14, 36, 36))
        f = S.font(22, QFont.ExtraBold, 0.5)
        path = QPainterPath()
        path.addText(QPointF(70, 34), f, "PoE2 Pilot")
        p.setPen(Qt.NoPen)
        p.setBrush(S.gradient(path.boundingRect(), S.PINK, QColor(130, 90, 255), horizontal=True))
        p.drawPath(path)
        p.setPen(S.DIM)
        p.setFont(S.font(11.5, QFont.Bold))
        p.drawText(QPointF(71, 51), f"штурман кампании  ·  v{__version__}")

        if self.title:
            tf = S.font(19, QFont.ExtraBold, 1)
            tw = QFontMetricsF(tf).horizontalAdvance(self.title)
            pill = QRectF((self.width() - tw) / 2 - 46, 13, tw + 92, 38)
            S.soft_card(p, pill, 19, QColor(255, 255, 255, 215), S.WHITE, 1.5, shadow=False)
            p.setFont(tf)
            p.setPen(S.INK)
            p.drawText(pill, Qt.AlignCenter, self.title)
            for dx in (-1, 1):
                cx = pill.center().x() + dx * (tw / 2 + 24)
                S.sparkle(p, QPointF(cx, pill.center().y()), 7, S.PINK if dx < 0 else S.GOLD)

        bx = self._buttons()
        clock = QRectF(bx["min"].left() - 92, 16, 80, 32)
        S.soft_card(p, clock, 16, QColor(255, 255, 255, 200), None, shadow=False)
        p.setFont(S.font(15, QFont.ExtraBold, 1))
        p.setPen(S.INK)
        p.drawText(clock, Qt.AlignCenter, time.strftime("%H:%M"))
        for name, r in bx.items():
            on = self.hover == name
            p.setPen(Qt.NoPen)
            p.setBrush(S.PINK if on and name == "close" else QColor(255, 255, 255, 230 if on else 170))
            p.drawEllipse(r)
            p.setPen(QPen(S.WHITE if on and name == "close" else S.INK, 2, Qt.SolidLine, Qt.RoundCap))
            c = r.center()
            if name == "close":
                p.drawLine(c + QPointF(-5, -5), c + QPointF(5, 5))
                p.drawLine(c + QPointF(-5, 5), c + QPointF(5, -5))
            else:
                p.drawLine(c + QPointF(-5, 0), c + QPointF(5, 0))

    def mouseMoveEvent(self, e):
        hit = next((n for n, r in self._buttons().items() if r.contains(e.position())), None)
        if hit != self.hover:
            self.hover = hit
            self.update()

    def leaveEvent(self, _):
        self.hover = None
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self.hover == "close":
            self.window().close()
        elif self.hover == "min":
            self.window().showMinimized()
        elif self.window().windowHandle():
            self.window().windowHandle().startSystemMove()


# ---------------------------------------------------------------- build list
def rarity_badge(p: QPainter, r: QRectF, e: Entry) -> None:
    tag, _, _, top, bottom = S.rarity(e)
    S.soft_card(p, r, r.height() * 0.24, S.gradient(r, top, bottom), S.WHITE, 2, shadow=False)
    gloss = QPainterPath()
    gloss.addRoundedRect(r.adjusted(3, 3, -3, -r.height() * 0.5), r.height() * 0.2, r.height() * 0.2)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 60))
    p.drawPath(gloss)
    p.setFont(S.font(r.height() * (0.34 if len(tag) > 2 else 0.4), QFont.ExtraBold, 0.5))
    p.setPen(S.WHITE)
    p.drawText(r, Qt.AlignCenter, tag)


class BuildList(QWidget):
    selected = Signal(int)
    activated = Signal(int)

    def __init__(self, last: str | None, parent: QWidget):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.last = last
        self.cls = ""
        self.entries: tuple[Entry, ...] = ()
        self.sel = 0
        self.hover = -1
        self.top = 0
        self.setMinimumWidth(560)

    def set_entries(self, entries: tuple[Entry, ...], cls: str = "") -> None:
        self.entries, self.cls = entries, cls
        self.sel = next((i for i, e in enumerate(entries) if e.file == self.last), 0)
        self.hover = -1
        self.top = 0
        self.update()

    def visible_rows(self) -> int:
        return max(1, int((self.height() - HEAD_H + ROW_GAP) // (ROW_H + ROW_GAP)))

    def select(self, i: int) -> None:
        if not self.entries:
            return
        i = max(0, min(len(self.entries) - 1, i))
        old, self.sel = self.sel, i
        n = self.visible_rows()
        self.top = min(max(self.top, i - n + 1), i)
        self.update()
        if old != i:
            self.selected.emit(i)

    def row_rect(self, k: int) -> QRectF:
        return QRectF(10, HEAD_H + k * (ROW_H + ROW_GAP), self.width() - 22, ROW_H)

    def row_at(self, y: float) -> int:
        if y < HEAD_H:
            return -1
        i = self.top + int((y - HEAD_H) // (ROW_H + ROW_GAP))
        return i if i < len(self.entries) else -1

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.cls:
            badge(p, self.cls, QPointF(30, 24), 20)
            p.setFont(S.font(24, QFont.ExtraBold, 0.5))
            p.setPen(S.INK)
            p.drawText(QPointF(60, 33), self.cls)
            w = QFontMetricsF(p.font()).horizontalAdvance(self.cls)
            S.chip(p, 72 + w, 13, S.builds_word(len(self.entries)), S.font(12, QFont.Bold), S.WHITE,
                   S.class_color(self.cls), h=24)
        for k in range(self.visible_rows()):
            i = self.top + k
            if i >= len(self.entries):
                break
            self._row(p, i, self.row_rect(k))
        p.setFont(S.font(11, QFont.Bold))
        p.setPen(S.DIM)
        if self.top + self.visible_rows() < len(self.entries):
            p.drawText(QRectF(0, self.height() - 16, self.width() - 12, 16), Qt.AlignRight, "ещё ▼")

    def _row(self, p: QPainter, i: int, r: QRectF) -> None:
        e = self.entries[i]
        sel, hov = i == self.sel, i == self.hover
        if sel:
            r = r.translated(4, 0)
            for k, a in ((8, 30), (4, 60)):
                g = QColor(S.PINK)
                g.setAlpha(a)
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                p.drawRoundedRect(r.adjusted(-k, -k, k, k), 18 + k, 18 + k)
        border = S.PINK if sel else QColor(200, 185, 255) if hov else S.WHITE
        S.soft_card(p, r, 18, QColor(255, 255, 255, 240 if sel else 215), border, 2.5 if sel else 1.5)
        rarity_badge(p, QRectF(r.left() + 14, r.top() + 14, 56, 56), e)

        x = r.left() + 86
        right = r.right() - 150
        p.setFont(S.font(17, QFont.ExtraBold))
        p.setPen(S.INK)
        fm = QFontMetricsF(p.font())
        title = fm.elidedText(e.title, Qt.ElideRight, right - x - 10)
        p.drawText(QPointF(x, r.top() + 33), title)
        if e.file == self.last:
            S.chip(p, x + fm.horizontalAdvance(title) + 10, r.top() + 15, "последний",
                   S.font(10.5, QFont.Bold), S.WHITE, S.PINK, h=20)
        S.chips(p, QRectF(x, r.top() + 44, right - x, 24), [e.role, *e.skills], S.font(11.5, QFont.Bold),
                S.INK, S.LAVENDER, h=24)

        tag, n, label = S.rarity(e)[:3]
        sx = r.right() - 132
        S.stars(p, sx, r.top() + 30, 7.5, n)
        p.setFont(S.font(12, QFont.Bold))
        p.setPen(S.PINK.darker(115) if tag == "SSR" else S.DIM)
        p.drawText(QRectF(sx, r.top() + 44, 120, 18), Qt.AlignLeft, label)
        p.setFont(S.font(11, QFont.Bold))
        p.setPen(S.DIM)
        p.drawText(QRectF(sx, r.top() + 60, 120, 16), Qt.AlignLeft, f"патч {e.patch}")
        if sel:
            tip = QPainterPath(QPointF(r.left() - 12, r.center().y() - 9))
            tip.lineTo(QPointF(r.left() - 3, r.center().y()))
            tip.lineTo(QPointF(r.left() - 12, r.center().y() + 9))
            tip.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(S.PINK)
            p.drawPath(tip)

    def resizeEvent(self, _):
        self.select(self.sel)

    def mouseMoveEvent(self, e):
        h = self.row_at(e.position().y())
        if h != self.hover:
            self.hover = h
            self.setCursor(Qt.PointingHandCursor if h >= 0 else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, _):
        self.hover = -1
        self.update()

    def mousePressEvent(self, e):
        i = self.row_at(e.position().y())
        if i >= 0:
            self.select(i)

    def mouseDoubleClickEvent(self, e):
        i = self.row_at(e.position().y())
        if i >= 0:
            self.activated.emit(i)

    def wheelEvent(self, e):
        self.select(self.sel + (1 if e.angleDelta().y() < 0 else -1))


# ---------------------------------------------------------------- hero card of the build
class HeroCard(QWidget):
    W, H = 384, 548
    BANNER = 214

    def __init__(self, catalog: Catalog, parent: QWidget):
        super().__init__(parent)
        self.setFixedSize(self.W, self.H)
        self.setMouseTracking(True)
        self.cat = catalog
        self.entry: Entry | None = None
        self.link = QRectF()
        self.phase = 0.0
        self._t = 1.0
        self.anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=240)
        self.anim.valueChanged.connect(self._step)

    def _step(self, v):
        self._t = float(v)
        self.update()

    def set_entry(self, e: Entry | None) -> None:
        self.entry = e
        self.anim.stop()
        self.anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        e, t = self.entry, self._t
        card = QRectF(10, 6, self.W - 20, self.H - 18)
        S.soft_card(p, card, 24, QColor(255, 255, 255, 235), S.WHITE, 2)
        if e is None:
            return
        col = S.class_color(e.cls)

        banner = QRectF(card.left() + 8, card.top() + 8, card.width() - 16, self.BANNER)
        clip = QPainterPath()
        clip.addRoundedRect(banner, 18, 18)
        p.save()
        p.setClipPath(clip)
        p.fillPath(clip, S.gradient(banner, col.lighter(170), col.lighter(115)))
        hub = QPointF(banner.right() - 100, banner.bottom() - 30)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 34))
        for k in range(9):                                 # light rays from behind the hero
            a = math.radians(100 + k * 20 + self.phase * 4)
            ray = QPainterPath(hub)
            ray.lineTo(hub + QPointF(420 * math.cos(a - 0.06), -420 * math.sin(a - 0.06)))
            ray.lineTo(hub + QPointF(420 * math.cos(a + 0.06), -420 * math.sin(a + 0.06)))
            ray.closeSubpath()
            p.drawPath(ray)
        glow = QRadialGradient(hub, banner.width() * 0.5)
        glow.setColorAt(0, QColor(255, 255, 255, 200))
        glow.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(glow)
        p.drawRect(banner)
        side = int(self.BANNER + 6)
        art = class_art(e.cls, side)
        if art is not None:
            p.setOpacity(0.35 + 0.65 * t)
            p.drawPixmap(QPointF(banner.right() - side + 14 + (1 - t) * 30, banner.bottom() - side + 10), art)
            p.setOpacity(1.0)
        for k, (fx, fy, s) in enumerate(((0.12, 0.70, 6), (0.40, 0.18, 8), (0.30, 0.86, 5), (0.92, 0.12, 6))):
            a = int(160 + 90 * math.sin(self.phase * 2 + k * 1.3))
            S.sparkle(p, QPointF(banner.left() + fx * banner.width(), banner.top() + fy * banner.height()), s,
                      QColor(255, 255, 255, max(0, min(255, a))))
        p.restore()

        rarity_badge(p, QRectF(banner.left() + 14, banner.top() + 14, 64, 40), e)
        S.stars(p, banner.left() + 15, banner.top() + 68, 7, S.rarity(e)[1])
        p.setFont(S.font(12, QFont.ExtraBold))
        p.setPen(S.WHITE)
        p.drawText(QRectF(banner.left() + 14, banner.top() + 80, 160, 20), Qt.AlignLeft, S.rarity(e)[2].upper())

        L, R = card.left() + 22, card.right() - 22
        y = banner.bottom() + 36
        p.setFont(S.font(22, QFont.ExtraBold))
        p.setPen(S.INK)
        p.drawText(QPointF(L, y), QFontMetricsF(p.font()).elidedText(e.role, Qt.ElideRight, R - L))
        p.setFont(S.font(13, QFont.Bold))
        p.setPen(S.DIM)
        sub = e.title if not e.ascendancy else f"{e.title}  ·  {e.cls}"
        p.drawText(QPointF(L, y + 22), QFontMetricsF(p.font()).elidedText(sub, Qt.ElideRight, R - L))

        y += 40
        third = (R - L) / 3
        for k, (lab, val) in enumerate((("автор", e.author), ("патч", e.patch), ("версия", str(e.rev)))):
            x = L + k * third
            p.setFont(S.font(11, QFont.Bold))
            p.setPen(S.DIM)
            p.drawText(QPointF(x, y + 12), lab)
            p.setFont(S.font(14, QFont.ExtraBold))
            p.setPen(S.INK)
            p.drawText(QPointF(x, y + 32), QFontMetricsF(p.font()).elidedText(val, Qt.ElideRight, third - 8))

        y += 46
        p.setFont(S.font(11, QFont.Bold))
        p.setPen(S.DIM)
        p.drawText(QPointF(L, y + 10), "скиллы")
        y += 16 + S.chips(p, QRectF(L, y + 16, R - L, 54), e.skills, S.font(12, QFont.Bold), S.INK, S.LAVENDER,
                          h=24)
        y += 12
        p.setFont(S.font(11, QFont.Bold))
        p.setPen(S.DIM)
        p.drawText(QPointF(L, y + 10), "обязательно пройти")
        y += 16 + S.chips(p, QRectF(L, y + 16, R - L, 54), e.musts or ("ничего",), S.font(12, QFont.Bold),
                          S.PINK.darker(110), QColor(255, 236, 246), S.PINK, h=24)
        if e.note:
            p.setFont(S.font(12))
            p.setPen(S.DIM)
            p.drawText(QRectF(L, y + 12, R - L, card.bottom() - y - 46), Qt.TextWordWrap, e.note)

        self.link = QRectF()
        if e.source:
            p.setFont(S.font(13, QFont.ExtraBold))
            txt = "открыть гайд ↗"
            w = QFontMetricsF(p.font()).horizontalAdvance(txt)
            self.link = QRectF(R - w, card.bottom() - 34, w, 22)
            p.setPen(S.PINK)
            p.drawText(self.link, Qt.AlignLeft | Qt.AlignVCenter, txt)

    def mouseMoveEvent(self, e):
        self.setCursor(Qt.PointingHandCursor if self.link.contains(e.position()) else Qt.ArrowCursor)

    def mousePressEvent(self, e):
        if self.entry and self.entry.source and self.link.contains(e.position()):
            QDesktopServices.openUrl(QUrl(self.entry.source))


# ---------------------------------------------------------------- start button
class StartButton(QAbstractButton):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedHeight(66)
        self.setCursor(Qt.PointingHandCursor)
        self.phase = 0.0

    def enterEvent(self, _):
        self.update()

    def leaveEvent(self, _):
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(12, 4, -12, -8)
        on, hot = self.isEnabled(), self.underMouse() and self.isEnabled()
        a, b = (S.PINK, S.GOLD) if on else (S.FAINT, S.FAINT)
        if hot:
            a, b = a.lighter(108), b.lighter(108)
        if self.isDown():
            a, b = a.darker(110), b.darker(110)
        S.soft_card(p, r, r.height() / 2, S.gradient(r, a, b, horizontal=True), S.WHITE, 3)
        gloss = QPainterPath()
        gloss.addRoundedRect(r.adjusted(10, 5, -10, -r.height() * 0.52), r.height() / 4, r.height() / 4)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 70))
        p.drawPath(gloss)
        if on:                                              # a shine sweeping across
            x = r.left() + ((self.phase * 0.35) % 1.6 - 0.3) * r.width()
            shine = QPainterPath(QPointF(x, r.top()))
            for pt in ((x + 26, r.top()), (x + 6, r.bottom()), (x - 20, r.bottom())):
                shine.lineTo(QPointF(*pt))
            shine.closeSubpath()
            clip = QPainterPath()
            clip.addRoundedRect(r, r.height() / 2, r.height() / 2)
            p.save()
            p.setClipPath(clip)
            p.setBrush(QColor(255, 255, 255, 70))
            p.drawPath(shine)
            p.restore()
        p.setFont(S.font(23, QFont.ExtraBold, 4))
        p.setPen(S.WHITE)
        p.drawText(r, Qt.AlignCenter, "СТАРТ")
        tw = QFontMetricsF(p.font()).horizontalAdvance("СТАРТ")
        for dx in (-1, 1):
            S.sparkle(p, QPointF(r.center().x() + dx * (tw / 2 + 22), r.center().y()), 8, S.WHITE)
        p.setFont(S.font(10, QFont.ExtraBold, 1))
        p.setPen(QColor(255, 255, 255, 190))
        p.drawText(r.adjusted(22, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, "ENTER")


# ---------------------------------------------------------------- the window
class _Async(QObject):
    done = Signal(object, object)       # result, error


def run_async(owner: QWidget, fn: Callable[[], object], cb: Callable[[object, object], None]) -> None:
    """fn() on a worker thread; cb(result, error) back on the Qt thread."""
    bridge = _Async(owner)
    bridge.done.connect(cb)

    def work():
        try:
            bridge.done.emit(fn(), None)
        except Exception as exc:        # network, disk: shown in the footer, never fatal
            bridge.done.emit(None, exc)
    threading.Thread(target=work, daemon=True).start()


def button_css(fam: str) -> str:
    return (f"QPushButton{{color:#ffffff;background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff5fa2,"
            f"stop:1 #ffb938);border:2px solid #ffffff;border-radius:11px;padding:4px 16px;min-height:16px;"
            f"font:800 12px '{fam}';}}"
            f"QPushButton:hover{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff79b3,stop:1 #ffc95c);}}"
            f"QPushButton:disabled{{background:#d9d4e8;}}")


class BoardWindow(QWidget):
    finished = Signal()

    def __init__(self, catalog: Catalog, last: str | None = None, content_version: str = "",
                 updater: object | None = None):
        """updater: pilot.updates-like object with check() / apply(manifest) -> int, or None (offline)."""
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("PoE2 Pilot")
        self.setWindowIcon(brand.logo_icon())
        fam, bold = S.load_fonts(), S.family(700)
        self.cat = catalog
        self.result: str | None = None
        self.restart = False
        self.updater = updater
        self._remote: dict | None = None
        self._open_url: str | None = None
        rng = random.Random(7)
        self.twinkles = [(rng.random(), rng.random(), rng.uniform(3, 9), rng.uniform(0, 6.3),
                          rng.choice((S.WHITE, S.GOLD, S.PINK, QColor(150, 200, 255)))) for _ in range(30)]
        self.phase = 0.0

        self.bar = TitleBar(self)
        prev = catalog.find(last)
        self.heroes = HeroPicker(catalog, prev.cls if prev else None, self)
        self.heroes.opened.connect(self.open_class)
        self.builds = BuildList(last, self)
        self.card = HeroCard(catalog, self)
        self.go = StartButton(self)
        self.go.clicked.connect(self.take_off)
        self.builds.selected.connect(lambda i: self.card.set_entry(self.builds.entries[i]))
        self.builds.activated.connect(lambda i: self.take_off())

        side = QVBoxLayout()
        side.setSpacing(8)
        side.addWidget(self.card)
        side.addWidget(self.go)
        side.addStretch(1)
        flight = QWidget(self)
        body = QHBoxLayout(flight)
        body.setContentsMargins(18, 8, 18, 4)
        body.setSpacing(18)
        body.addWidget(self.builds, 1)
        body.addLayout(side)
        hero_page = QWidget(self)
        hl = QVBoxLayout(hero_page)
        hl.setContentsMargins(22, 10, 22, 6)
        hl.addWidget(self.heroes, 1)
        self.pages = QStackedWidget(self)
        self.pages.addWidget(hero_page)
        self.pages.addWidget(flight)

        css = f"color:#8a82a8;font:700 12px '{bold}';"
        self.info = QLabel(f"контент {content_version or '—'}  ·  игра {catalog.game or '—'}", self)
        self.news = QLabel("", self)
        self.keys = QLabel(self)
        for lab in (self.info, self.news):
            lab.setStyleSheet(css)
        self.keys.setStyleSheet(f"color:#b0a9c9;font:700 12px '{bold}';")
        self.action = QPushButton(self)
        self.back = QPushButton("← Герои", self)
        for b in (self.action, self.back):
            b.setStyleSheet(button_css(fam))           # ExtraBold lives in the base family
            b.setCursor(Qt.PointingHandCursor)
        self.action.hide()
        self.action.clicked.connect(self._act)
        self.back.clicked.connect(self.show_heroes)
        foot = QHBoxLayout()
        foot.setContentsMargins(24, 2, 24, 14)
        foot.setSpacing(12)
        foot.addWidget(self.back)
        foot.addWidget(self.info)
        foot.addStretch(1)
        foot.addWidget(self.news)
        foot.addWidget(self.action)
        foot.addSpacing(16)
        foot.addWidget(self.keys)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.bar)
        root.addWidget(self.pages, 1)
        root.addLayout(foot)
        self.resize(1190, 720)
        self.setMinimumSize(1100, 660)
        self.show_heroes()

        self.timer = QTimer(self)                         # twinkles and the start button's shine
        self.timer.setInterval(TWINKLE_MS)
        self.timer.timeout.connect(self._twinkle)
        self.timer.start()

        if updater is not None:
            self.news.setText("проверяю обновления…")
            run_async(self, updater.check, self._checked)

    def _twinkle(self) -> None:
        self.phase += TWINKLE_MS / 1000
        for w in (self.heroes, self.card, self.go):
            w.phase = self.phase
        self.update()

    # -- updates
    def _checked(self, res, err) -> None:
        if err is not None:
            self.news.setText("GitHub недоступен — играем с тем, что есть")
            return
        if res.content:
            self._remote = res.content
            self.news.setText(f"новые билды и данные: {res.content.get('version')}")
            self._button("Обновить")
        elif res.needs_app or res.app_version:
            v = res.app_version or res.needs_app
            self.news.setText(f"вышла версия программы {v}"
                              + (" — новые билды только для неё" if res.needs_app else ""))
            self._open_url = res.app_url or self.updater.releases_url()
            self._button("Скачать")
        else:
            self.news.setText("билды свежие")

    def _button(self, text: str) -> None:
        self.action.setText(text)
        self.action.setEnabled(True)
        self.action.show()

    def _act(self) -> None:
        if self._open_url:
            QDesktopServices.openUrl(QUrl(self._open_url))
            return
        if self._remote is None:
            return
        self.action.setEnabled(False)
        self.news.setText("загружаю…")
        run_async(self, lambda: self.updater.apply(self._remote), self._applied)

    def _applied(self, n, err) -> None:
        if err is not None:
            self.news.setText(f"не удалось обновить: {err}")
            self.action.setEnabled(True)
            return
        self.news.setText(f"обновлено файлов: {n}. Перезапуск…")
        self.restart = True
        QTimer.singleShot(700, self.close)

    # -- pages
    def show_heroes(self) -> None:
        self.pages.setCurrentIndex(0)
        self.back.hide()
        self.bar.set_title("Выбери героя")
        self.keys.setText("← → ↑ ↓ выбрать  ·  Enter открыть  ·  Esc выход")

    def open_class(self, cls: str) -> None:
        entries = tuple(e for e in self.cat.entries if e.cls == cls)
        if not entries:
            return
        self.builds.set_entries(entries, cls)
        self.card.set_entry(entries[self.builds.sel])
        self.pages.setCurrentIndex(1)
        self.back.show()
        self.bar.set_title("Выбери билд")
        self.keys.setText("↑ ↓ выбрать  ·  Enter старт  ·  Esc назад")

    @property
    def on_board(self) -> bool:
        return self.pages.currentIndex() == 1

    # -- start and keys
    def take_off(self) -> None:
        if self.on_board and self.builds.entries:
            self.result = self.builds.entries[self.builds.sel].file
            self.close()

    def keyPressEvent(self, e):
        k = e.key()
        if not self.on_board:
            arrows = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
            if k in arrows:
                self.heroes.move_focus(*arrows[k])
            elif k in (Qt.Key_Return, Qt.Key_Enter):
                self.heroes.open()
            elif k == Qt.Key_Escape:
                self.close()
            else:
                super().keyPressEvent(e)
            return
        b = self.builds
        step = {Qt.Key_Up: -1, Qt.Key_Down: 1, Qt.Key_PageUp: -b.visible_rows(),
                Qt.Key_PageDown: b.visible_rows()}
        if k in step:
            b.select(b.sel + step[k])
        elif k == Qt.Key_Home:
            b.select(0)
        elif k == Qt.Key_End:
            b.select(len(b.entries) - 1)
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            self.take_off()
        elif k in (Qt.Key_Escape, Qt.Key_Backspace):
            self.show_heroes()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        shape = QPainterPath()
        shape.addRoundedRect(r, 22, 22)
        g = S.gradient(r, QColor(255, 228, 241), QColor(221, 243, 255))
        g.setFinalStop(r.bottomRight())
        g.setColorAt(0.5, QColor(238, 230, 255))
        p.fillPath(shape, g)
        p.save()
        p.setClipPath(shape)
        for fx, fy, rad, col in ((0.12, 0.18, 300, QColor(255, 255, 255, 150)),
                                 (0.88, 0.92, 340, QColor(255, 194, 224, 110)),
                                 (0.92, 0.08, 260, QColor(191, 230, 255, 120))):
            blob = QRadialGradient(r.left() + fx * r.width(), r.top() + fy * r.height(), rad)
            blob.setColorAt(0, col)
            blob.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
            p.setPen(Qt.NoPen)
            p.setBrush(blob)
            p.drawRect(r)
        for fx, fy, s, ph, col in self.twinkles:
            c = QColor(col)
            c.setAlpha(int(110 + 110 * math.sin(self.phase * 1.6 + ph)))
            S.sparkle(p, QPointF(r.left() + fx * r.width(), r.top() + fy * r.height()), s, c)
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 230), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawPath(shape)

    def closeEvent(self, e):
        super().closeEvent(e)
        self.timer.stop()
        self.finished.emit()
