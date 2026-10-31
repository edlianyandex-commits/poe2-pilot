"""The PoE2 Pilot mark: a split-flap tile with an amber paper plane across its seam.

Drawn with QPainter so the tray, the start window and the exe icon (tools/make_icon.py) share it.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

AMBER = QColor(255, 178, 62)
AMBER_DARK = QColor(196, 118, 22)


def draw_logo(p: QPainter, r: QRectF) -> None:
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0, QColor(44, 47, 54))
    g.setColorAt(0.5, QColor(30, 32, 37))
    g.setColorAt(0.5001, QColor(23, 25, 29))
    g.setColorAt(1, QColor(16, 17, 20))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(r, r.width() * 0.2, r.width() * 0.2)

    def at(x: float, y: float) -> QPointF:
        return QPointF(r.left() + x * r.width(), r.top() + y * r.height())

    wing = QPainterPath(at(0.83, 0.18))            # nose up-right, tails down-left
    wing.lineTo(at(0.16, 0.47))
    wing.lineTo(at(0.42, 0.57))
    wing.closeSubpath()
    keel = QPainterPath(at(0.83, 0.18))
    keel.lineTo(at(0.42, 0.57))
    keel.lineTo(at(0.53, 0.84))
    keel.closeSubpath()
    p.setBrush(AMBER)
    p.drawPath(wing)
    p.setBrush(AMBER_DARK)
    p.drawPath(keel)
    seam = QPen(QColor(8, 9, 11, 210), max(1.0, r.height() * 0.035))
    p.setPen(seam)
    p.drawLine(at(0.04, 0.5), at(0.96, 0.5))
    p.restore()


def logo_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    draw_logo(p, QRectF(0, 0, size, size).adjusted(0.5, 0.5, -0.5, -0.5))
    p.end()
    return pm


def logo_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(s))
    return icon
