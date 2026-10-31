"""First page of the start window: one gate per class, an airport-style pictogram on each.

Pictograms are our own line art (no game art in the repo). A PNG at data/ui/classes/<class>.png,
if present, is drawn in the sign instead.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from pilot.catalog import Catalog
from pilot.paths import DATA

from .flaps import FlapLine, draw_flaps
from .flaps import ui_font as _font

# every class of the game, in the order of the character select screen; builds decide which light up
CLASSES = ("Warrior", "Ranger", "Huntress", "Mercenary", "Monk", "Witch", "Sorceress", "Druid")
COLS = 4
GAP = 16
SIGN_INK = QColor(28, 26, 22)


def flights(n: int) -> str:
    if n == 0:
        return "рейсов нет"
    last2, last = n % 100, n % 10
    word = "рейс" if last == 1 and last2 != 11 else (
        "рейса" if 2 <= last <= 4 and not 12 <= last2 <= 14 else "рейсов")
    return f"{n} {word}"


# ---------------------------------------------------------------- pictograms
def draw_glyph(p: QPainter, cls: str, r: QRectF, ink: QColor, hole: QColor) -> None:
    """Line-art pictogram of `cls` inside `r` (0..1 coordinates scaled to r)."""
    def at(x: float, y: float) -> QPointF:
        return QPointF(r.left() + x * r.width(), r.top() + y * r.height())

    u = r.width()
    stroke = QPen(ink, u * 0.075, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    thin = QPen(ink, u * 0.03, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    def poly(*pts: tuple[float, float], color: QColor = ink) -> None:
        path = QPainterPath(at(*pts[0]))
        for pt in pts[1:]:
            path.lineTo(at(*pt))
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(path)

    def curve(a, c, b, pen: QPen = stroke) -> None:
        path = QPainterPath(at(*a))
        path.quadTo(at(*c), at(*b))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def line(a, b, pen: QPen = stroke) -> None:
        p.setPen(pen)
        p.drawLine(at(*a), at(*b))

    def disc(c, rad: float, color: QColor = ink) -> None:
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(at(*c), rad * u, rad * u)

    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    if cls == "Warrior":                                 # mace
        line((0.26, 0.80), (0.58, 0.42))
        disc((0.26, 0.80), 0.05)
        for k in range(8):
            a = k * math.pi / 4
            line((0.64 + 0.15 * math.cos(a), 0.35 + 0.15 * math.sin(a)),
                 (0.64 + 0.25 * math.cos(a), 0.35 + 0.25 * math.sin(a)))
        disc((0.64, 0.35), 0.17)
    elif cls == "Ranger":                                # bow and arrow
        curve((0.36, 0.14), (0.88, 0.5), (0.36, 0.86))
        line((0.36, 0.14), (0.36, 0.86), thin)
        line((0.16, 0.5), (0.74, 0.5), QPen(ink, u * 0.05, Qt.SolidLine, Qt.RoundCap))
        poly((0.86, 0.5), (0.72, 0.42), (0.72, 0.58))
        line((0.16, 0.5), (0.10, 0.42), thin)
        line((0.16, 0.5), (0.10, 0.58), thin)
    elif cls == "Huntress":                              # spear
        line((0.18, 0.84), (0.62, 0.40))
        poly((0.58, 0.44), (0.72, 0.40), (0.86, 0.14), (0.60, 0.28))
        line((0.50, 0.40), (0.60, 0.50), thin)
        line((0.30, 0.64), (0.38, 0.72), thin)
    elif cls == "Mercenary":                             # crossbow
        line((0.5, 0.26), (0.5, 0.86))
        curve((0.14, 0.44), (0.5, 0.14), (0.86, 0.44))
        line((0.14, 0.44), (0.5, 0.56), thin)
        line((0.86, 0.44), (0.5, 0.56), thin)
        poly((0.5, 0.06), (0.43, 0.20), (0.57, 0.20))
        line((0.5, 0.72), (0.38, 0.84))
    elif cls == "Monk":                                  # whirlwind
        for y, x0, x1 in ((0.18, 0.12, 0.88), (0.32, 0.20, 0.82), (0.46, 0.30, 0.74),
                          (0.60, 0.36, 0.64), (0.74, 0.42, 0.60), (0.87, 0.50, 0.56)):
            line((x0, y), (x1, y))
    elif cls == "Witch":                                 # skull
        p.setPen(Qt.NoPen)
        p.setBrush(ink)
        p.drawEllipse(at(0.5, 0.42), 0.27 * u, 0.25 * u)
        p.drawRoundedRect(QRectF(at(0.35, 0.56), at(0.65, 0.80)), 0.05 * u, 0.05 * u)
        disc((0.40, 0.44), 0.07, hole)
        disc((0.60, 0.44), 0.07, hole)
        poly((0.5, 0.53), (0.46, 0.60), (0.54, 0.60), color=hole)
        for x in (0.44, 0.5, 0.56):
            line((x, 0.68), (x, 0.80), QPen(hole, u * 0.025))
    elif cls == "Sorceress":                             # staff with an orb, lightning
        line((0.38, 0.88), (0.38, 0.40))
        p.setPen(stroke)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(at(0.38, 0.27), 0.11 * u, 0.11 * u)
        disc((0.38, 0.27), 0.045)
        poly((0.74, 0.12), (0.58, 0.46), (0.69, 0.46), (0.56, 0.84), (0.84, 0.38), (0.72, 0.38),
             (0.84, 0.12))
    elif cls == "Druid":                                 # claw marks
        for k in (-1, 0, 1):
            dx = 0.18 * k
            curve((0.34 + dx, 0.14), (0.56 + dx, 0.48), (0.38 + dx, 0.86),
                  QPen(ink, u * (0.09 if k == 0 else 0.075), Qt.SolidLine, Qt.RoundCap))
    p.restore()


def class_art(cls: str) -> QPixmap | None:
    path = DATA / "ui" / "classes" / f"{cls.lower()}.png"
    return QPixmap(str(path)) if path.is_file() else None


# ---------------------------------------------------------------- the gates
class ClassPicker(QWidget):
    opened = Signal(str)

    def __init__(self, catalog: Catalog, focus: str | None, parent: QWidget,
                 amber: QColor, ink: QColor, dim: QColor, faint: QColor, edge: QColor):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.amber, self.ink, self.dim, self.faint, self.edge = amber, ink, dim, faint, edge
        self.builds = {c: [e for e in catalog.entries if e.cls == c] for c in CLASSES}
        self.focus = CLASSES.index(focus) if focus in CLASSES else next(
            (i for i, c in enumerate(CLASSES) if self.builds[c]), 0)
        self.hover = -1
        self.names = [FlapLine(10) for _ in CLASSES]
        for i, (line, c) in enumerate(zip(self.names, CLASSES)):
            line.set(c.center(line.width), spins=(4 + i, 10 + i * 2), stagger=0.4)
        self.art = {c: class_art(c) for c in CLASSES}

    def lines(self) -> list[FlapLine]:
        return self.names

    def card(self, i: int) -> QRectF:
        rows = math.ceil(len(CLASSES) / COLS)
        w = (self.width() - GAP * (COLS - 1)) / COLS
        h = (self.height() - GAP * (rows - 1)) / rows
        return QRectF((i % COLS) * (w + GAP), (i // COLS) * (h + GAP), w, h)

    def at(self, pos: QPointF) -> int:
        return next((i for i in range(len(CLASSES)) if self.card(i).contains(pos)), -1)

    def move_focus(self, dx: int, dy: int) -> None:
        i = self.focus + dx + dy * COLS
        if 0 <= i < len(CLASSES):
            self.focus = i
            self.update()

    def open(self, i: int | None = None) -> None:
        c = CLASSES[self.focus if i is None else i]
        if self.builds[c]:
            self.opened.emit(c)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for i, c in enumerate(CLASSES):
            builds = self.builds[c]
            live = bool(builds)
            lit = live and i in (self.hover, self.focus)
            r = self.card(i).adjusted(1, 1, -1, -1)
            if lit:
                r.translate(0, -3)
            p.setPen(QPen(self.amber if lit else self.edge, 1.6 if lit else 1))
            p.setBrush(QColor(24, 22, 18) if lit else QColor(19, 20, 24))
            p.drawRoundedRect(r, 14, 14)

            p.setFont(_font(11, QFont.DemiBold, 1.8))
            p.setPen(self.amber.darker(130) if live else self.faint)
            p.drawText(QPointF(r.left() + 16, r.top() + 24), f"ГЕЙТ {i + 1}")
            p.setPen(self.ink if lit else self.dim if live else self.faint)
            p.setFont(_font(11))
            p.drawText(QRectF(r.left(), r.top() + 10, r.width() - 16, 20), Qt.AlignRight, flights(len(builds)))

            side = min(r.width() * 0.5, r.height() * 0.46)
            tw = min(20.0, (r.width() - 24) / 10 - 2)
            block = side + 16 + tw * 1.45 + 30           # sign, name, builds: centred in the card
            top = max(r.top() + 36, r.center().y() - block / 2 + 8)
            sign = QRectF(r.center().x() - side / 2, top, side, side)
            fill = self.amber if live else QColor(46, 48, 54)
            if lit:
                fill = fill.lighter(108)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(sign, side * 0.12, side * 0.12)
            art = self.art[c]
            if art is not None and not art.isNull():
                clip = QPainterPath()
                clip.addRoundedRect(sign, side * 0.12, side * 0.12)
                p.save()
                p.setClipPath(clip)
                p.setOpacity(1.0 if live else 0.35)
                p.drawPixmap(sign.toRect(), art.scaled(sign.size().toSize(), Qt.KeepAspectRatioByExpanding,
                                                       Qt.SmoothTransformation))
                p.restore()
            else:
                draw_glyph(p, c, sign.adjusted(side * 0.14, side * 0.14, -side * 0.14, -side * 0.14),
                           SIGN_INK if live else QColor(30, 31, 35), fill)

            x = r.center().x() - (10 * (tw + 2) - 2) / 2
            draw_flaps(p, self.names[i], x, sign.bottom() + 16, tw, tw * 1.45,
                       self.ink if live else self.faint)
            p.setFont(_font(12))
            p.setPen(self.dim if live else self.faint)
            fm = p.fontMetrics()
            sub = " · ".join(e.title for e in builds) or "ждём билды"
            p.drawText(QRectF(r.left() + 14, sign.bottom() + 24 + tw * 1.45, r.width() - 28, 20),
                       Qt.AlignHCenter, fm.elidedText(sub, Qt.ElideRight, int(r.width() - 28)))

    def mouseMoveEvent(self, e):
        h = self.at(e.position())
        if h != self.hover:
            self.hover = h
            live = h >= 0 and bool(self.builds[CLASSES[h]])
            self.setCursor(Qt.PointingHandCursor if live else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, _):
        self.hover = -1
        self.update()

    def mousePressEvent(self, e):
        i = self.at(e.position())
        if i >= 0 and e.button() == Qt.LeftButton:
            self.focus = i
            self.open(i)

