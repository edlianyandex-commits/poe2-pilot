"""First page of the start window: one hero card per class, our chibi art on each.

Art: data/ui/classes/<class>.png, .jpg or .svg (square, face in the upper half); the small round
badge in the corner carries the class pictogram (draw_glyph).
"""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from pilot.catalog import Catalog
from pilot.paths import DATA

from . import style as S

# every class of the game, in the order of the character select screen; builds decide which light up
CLASSES = ("Warrior", "Ranger", "Huntress", "Mercenary", "Monk", "Witch", "Sorceress", "Druid")
COLS = 4
GAP = 14


@lru_cache(maxsize=64)
def class_art(cls: str, size: int) -> QPixmap | None:
    base = DATA / "ui" / "classes" / cls.lower()
    svg = base.with_suffix(".svg")
    raster = next((f for f in (base.with_suffix(".png"), base.with_suffix(".jpg")) if f.is_file()), None)
    if raster is not None:
        pm = QPixmap(str(raster))
        return None if pm.isNull() else pm.scaled(size, size, Qt.KeepAspectRatioByExpanding,
                                                  Qt.SmoothTransformation)
    if svg.is_file():
        from PySide6.QtSvg import QSvgRenderer
        r = QSvgRenderer(str(svg))
        if not r.isValid():
            return None
        pm = QPixmap(QSize(size, size))
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p, QRectF(0, 0, size, size))
        p.end()
        return pm
    return None


@lru_cache(maxsize=16)
def class_art_grey(cls: str, size: int) -> QPixmap | None:
    """The art in greys, for classes that have no builds yet."""
    art = class_art(cls, size)
    return None if art is None else QPixmap.fromImage(art.toImage().convertToFormat(QImage.Format_Grayscale8))


# ---------------------------------------------------------------- pictograms (class badge)
def draw_glyph(p: QPainter, cls: str, r: QRectF, ink: QColor, hole: QColor) -> None:
    """Line-art pictogram of `cls` inside `r` (0..1 coordinates scaled to r)."""
    def at(x: float, y: float) -> QPointF:
        return QPointF(r.left() + x * r.width(), r.top() + y * r.height())

    u = r.width()
    stroke = QPen(ink, u * 0.075, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    thin = QPen(ink, u * 0.03, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    def poly(*pts, color: QColor = ink) -> None:
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
    elif cls == "Huntress":                              # spear
        line((0.18, 0.84), (0.62, 0.40))
        poly((0.58, 0.44), (0.72, 0.40), (0.86, 0.14), (0.60, 0.28))
    elif cls == "Mercenary":                             # crossbow
        line((0.5, 0.26), (0.5, 0.86))
        curve((0.14, 0.44), (0.5, 0.14), (0.86, 0.44))
        line((0.14, 0.44), (0.5, 0.56), thin)
        line((0.86, 0.44), (0.5, 0.56), thin)
        poly((0.5, 0.06), (0.43, 0.20), (0.57, 0.20))
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
    elif cls == "Sorceress":                             # lightning
        poly((0.62, 0.06), (0.30, 0.52), (0.50, 0.52), (0.36, 0.94), (0.74, 0.40), (0.54, 0.40),
             (0.70, 0.06))
    elif cls == "Druid":                                 # claw marks
        for k in (-1, 0, 1):
            dx = 0.18 * k
            curve((0.34 + dx, 0.14), (0.56 + dx, 0.48), (0.38 + dx, 0.86),
                  QPen(ink, u * 0.085, Qt.SolidLine, Qt.RoundCap))
    p.restore()


def badge(p: QPainter, cls: str, c: QPointF, rad: float, live: bool = True) -> None:
    """White round badge with the class pictogram in the class colour."""
    p.setPen(QPen(QColor(255, 255, 255, 230), 2))
    p.setBrush(QColor(255, 255, 255, 235))
    p.drawEllipse(c, rad, rad)
    ink = S.class_color(cls) if live else S.FAINT
    k = rad * 0.62
    draw_glyph(p, cls, QRectF(c.x() - k, c.y() - k, 2 * k, 2 * k), ink, QColor(255, 255, 255))


# ---------------------------------------------------------------- hero cards
class HeroPicker(QWidget):
    opened = Signal(str)

    def __init__(self, catalog: Catalog, focus: str | None, parent: QWidget):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.builds = {c: [e for e in catalog.entries if e.cls == c] for c in CLASSES}
        self.focus = CLASSES.index(focus) if focus in CLASSES else next(
            (i for i, c in enumerate(CLASSES) if self.builds[c]), 0)
        self.hover = -1
        self.phase = 0.0                     # twinkle, advanced by the window's timer

    def card(self, i: int) -> QRectF:
        rows = math.ceil(len(CLASSES) / COLS)
        w = (self.width() - GAP * (COLS - 1)) / COLS
        h = (self.height() - GAP * (rows - 1) - 6) / rows
        return QRectF((i % COLS) * (w + GAP), (i // COLS) * (h + GAP) + 4, w, h)

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
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        for i, c in enumerate(CLASSES):
            self._card(p, i, c)

    def _card(self, p: QPainter, i: int, c: str) -> None:
        builds = self.builds[c]
        live = bool(builds)
        lit = live and i in (self.hover, self.focus)
        r = self.card(i).adjusted(4, 4, -4, -4)
        if lit:
            r.translate(0, -4)
        base = S.class_color(c) if live else QColor(205, 200, 220)
        if lit:                                           # golden glow
            for k, a in ((12, 30), (8, 50), (4, 80)):
                g = QColor(S.GOLD)
                g.setAlpha(a)
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                p.drawRoundedRect(r.adjusted(-k, -k, k, k), 20 + k, 20 + k)
        S.soft_card(p, r, 20, S.gradient(r, base.lighter(165), base.lighter(112)),
                    S.GOLD if lit else S.WHITE, 3.5 if lit else 3)

        clip = QPainterPath()
        clip.addRoundedRect(r.adjusted(3, 3, -3, -3), 18, 18)
        p.save()
        p.setClipPath(clip)
        plate_h = 52
        side = int(max(r.width(), r.height()))            # the scene fills the card, the face stays in view
        art = class_art(c, side) if live else class_art_grey(c, side)
        if art is not None:
            p.setOpacity(1.0 if live else 0.45)
            p.drawPixmap(QPointF(r.center().x() - side / 2, r.top() - side * 0.04), art)
            p.setOpacity(1.0)
        if lit:
            for k, (fx, fy, s) in enumerate(((0.16, 0.22, 7), (0.86, 0.30, 9), (0.78, 0.12, 5), (0.24, 0.55, 5))):
                a = int(150 + 100 * math.sin(self.phase * 2 + k * 1.7))
                S.sparkle(p, QPointF(r.left() + fx * r.width(), r.top() + fy * r.height()), s,
                          QColor(255, 255, 255, max(0, min(255, a))))
        p.restore()

        plate = QRectF(r.left() + 10, r.bottom() - plate_h - 6, r.width() - 20, plate_h)
        S.soft_card(p, plate, 14, QColor(255, 255, 255, 240), None, shadow=False)
        p.setFont(S.font(16.5, QFont.ExtraBold, 0.5))
        p.setPen(S.INK if live else S.FAINT)
        p.drawText(plate.adjusted(12, 5, -10, -23), Qt.AlignLeft | Qt.AlignVCenter, c)
        p.setFont(S.font(11, QFont.Bold))
        p.setPen(S.class_color(c).darker(125) if live else S.FAINT)
        p.drawText(plate.adjusted(12, 27, -10, -5), Qt.AlignLeft | Qt.AlignVCenter, S.builds_word(len(builds)))
        if live:
            best = max(S.rarity(e)[1] for e in builds)
            S.stars(p, plate.right() - 12 - 5 * 4 * 2.3, plate.top() + 37, 4, best)
        badge(p, c, QPointF(r.left() + 22, r.top() + 22), 15, live)
        if not live:
            S.chip(p, r.right() - 62, r.top() + 11, "скоро", S.font(11, QFont.Bold), S.WHITE,
                   QColor(170, 164, 190))

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
