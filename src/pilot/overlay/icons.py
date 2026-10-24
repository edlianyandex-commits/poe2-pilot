"""Vector icons drawn with QPainterPath (no fonts, no image files).

Every icon is defined in a unit square; `draw_icon` scales it into a rect, draws a dark
under-stroke for contrast on busy backgrounds, then the colored shape.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from .theme import KIND_COLORS, RGB, TOAST_COLORS, TOAST_ICONS

# op: ("stroke"|"fill", path)
Op = tuple[str, QPainterPath]


def _poly(pts, close=True) -> QPainterPath:
    p = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        p.lineTo(x, y)
    if close:
        p.closeSubpath()
    return p


def _line(a, b) -> QPainterPath:
    return _poly([a, b], close=False)


def _circle(cx, cy, r) -> QPainterPath:
    p = QPainterPath()
    p.addEllipse(QPointF(cx, cy), r, r)
    return p


def _star() -> QPainterPath:
    pts = []
    for i in range(10):
        r = 0.48 if i % 2 == 0 else 0.20
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((0.5 + r * math.cos(a), 0.52 + r * math.sin(a)))
    return _poly(pts)


def _pin() -> QPainterPath:
    p = QPainterPath(QPointF(0.5, 0.96))
    p.cubicTo(0.12, 0.58, 0.16, 0.06, 0.5, 0.06)
    p.cubicTo(0.84, 0.06, 0.88, 0.58, 0.5, 0.96)
    p.closeSubpath()
    return p


def _shield() -> QPainterPath:
    p = QPainterPath(QPointF(0.14, 0.1))
    p.lineTo(0.86, 0.1)
    p.lineTo(0.86, 0.5)
    p.cubicTo(0.86, 0.75, 0.66, 0.88, 0.5, 0.96)
    p.cubicTo(0.34, 0.88, 0.14, 0.75, 0.14, 0.5)
    p.closeSubpath()
    return p


def _build() -> dict[str, list[Op]]:
    arrow_head = _poly([(0.55, 0.2), (0.86, 0.5), (0.55, 0.8)], close=False)
    return {
        "move": [("stroke", _line((0.1, 0.5), (0.82, 0.5))), ("stroke", arrow_head)],
        "wp": [("fill", _poly([(0.5, 0.04), (0.94, 0.5), (0.5, 0.96), (0.06, 0.5)]))],
        "boss": [  # crossed swords
            ("stroke", _line((0.82, 0.04), (0.3, 0.72))),       # blade A
            ("stroke", _line((0.18, 0.04), (0.7, 0.72))),       # blade B
            ("stroke", _line((0.16, 0.62), (0.44, 0.82))),      # guard A
            ("stroke", _line((0.84, 0.62), (0.56, 0.82))),      # guard B
            ("stroke", _line((0.3, 0.72), (0.18, 0.94))),       # grip A
            ("stroke", _line((0.7, 0.72), (0.82, 0.94))),       # grip B
        ],
        "town": [("fill", _poly([(0.5, 0.06), (0.96, 0.52), (0.82, 0.52), (0.82, 0.94),
                                  (0.18, 0.94), (0.18, 0.52), (0.04, 0.52)]))],
        "quest": [("stroke", _circle(0.5, 0.5, 0.42)),
                  ("stroke", _line((0.5, 0.26), (0.5, 0.56))),
                  ("fill", _circle(0.5, 0.74, 0.07))],
        "trial": [("fill", _star())],
        "skip": [("stroke", _line((0.18, 0.18), (0.82, 0.82))),
                 ("stroke", _line((0.82, 0.18), (0.18, 0.82)))],
        # toast icons
        "level": [("stroke", _circle(0.5, 0.5, 0.43)),
                  ("stroke", _line((0.5, 0.74), (0.5, 0.28))),
                  ("stroke", _poly([(0.32, 0.46), (0.5, 0.27), (0.68, 0.46)], close=False))],
        "flag": [("stroke", _line((0.2, 0.08), (0.2, 0.94))),
                 ("fill", _poly([(0.2, 0.1), (0.88, 0.28), (0.2, 0.5)]))],
        "alert": [("stroke", _poly([(0.5, 0.08), (0.95, 0.9), (0.05, 0.9)])),
                  ("stroke", _line((0.5, 0.38), (0.5, 0.64))),
                  ("fill", _circle(0.5, 0.78, 0.055))],
        "shield": [("fill", _shield())],
        "pin": [("fill", _pin())],
    }


_ICONS: dict[str, list[Op]] | None = None


def icon_names() -> list[str]:
    return list(_get())


def _get() -> dict[str, list[Op]]:
    global _ICONS
    if _ICONS is None:
        _ICONS = _build()
        _ICONS["boss_opt"] = _ICONS["boss"]     # optional boss: same swords, its own (grey) colour
    return _ICONS


def kind_color(kind: str | None) -> RGB:
    return KIND_COLORS.get(kind or "", KIND_COLORS["move"])


def toast_icon(kind: str) -> str:
    return TOAST_ICONS.get(kind, "pin")


def toast_color(kind: str) -> RGB:
    return TOAST_COLORS.get(kind, (255, 255, 255))


def draw_icon(p: QPainter, name: str | None, rect: QRectF, color: RGB, alpha: float = 1.0) -> None:
    ops = _get().get(name or "")
    if not ops:
        return
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    side = min(rect.width(), rect.height())
    p.translate(rect.center().x() - side / 2, rect.center().y() - side / 2)
    p.scale(side, side)
    w = max(1.6, side * 0.12) / side          # stroke width in unit coordinates
    under = QColor(0, 0, 0, int(215 * alpha))
    col = QColor(*color)
    col.setAlphaF(alpha)
    for mode, path in ops:                       # dark outline pass
        pen = QPen(under, w + 2.4 / side, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    for mode, path in ops:                       # colored pass
        if mode == "fill":
            p.setPen(QPen(col, 0.6 / side, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(col)
        else:
            p.setPen(QPen(col, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    p.restore()
