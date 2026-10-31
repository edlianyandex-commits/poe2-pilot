"""Split-flap text: a fixed-width row of tiles that flip through the drum toward their target letter.

FlapLine is plain state (no Qt) so it can be tested; draw_flaps() paints one row.
"""
from __future__ import annotations

import random

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen

# the drum: a tile always flips forward through this order
DRUM = " ABCDEFGHIJKLMNOPQRSTUVWXYZАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ0123456789.-/+:&'·"


class FlapLine:
    def __init__(self, width: int, rng: random.Random | None = None):
        self.width = width
        self.shown = [" "] * width
        self.target = [" "] * width
        self.left = [0] * width          # flips still to go per tile
        self.moved: set[int] = set()     # tiles that flipped on the last step (drawn mid-flip)
        self.rng = rng or random.Random()

    def set(self, text: str, spins: tuple[int, int] = (3, 9), stagger: float = 0.5) -> None:
        """Flip toward `text` (upper-cased, cut or padded to width). Unchanged tiles stay still."""
        want = list(text.upper()[:self.width].ljust(self.width))
        for i, c in enumerate(want):
            if c != self.target[i] or self.left[i]:
                self.target[i] = c
                self.left[i] = self.rng.randint(*spins) + int(i * stagger)

    def snap(self, text: str) -> None:
        self.target = list(text.upper()[:self.width].ljust(self.width))
        self.shown = list(self.target)
        self.left = [0] * self.width
        self.moved = set()

    @property
    def text(self) -> str:
        return "".join(self.target).rstrip()

    @property
    def busy(self) -> bool:
        return any(self.left)

    def step(self) -> bool:
        """Advance one flip; -> True while any tile is still moving."""
        self.moved = set()
        for i in range(self.width):
            if not self.left[i]:
                continue
            self.left[i] -= 1
            if self.left[i] == 0:
                self.shown[i] = self.target[i]
            else:
                k = DRUM.find(self.shown[i])
                self.shown[i] = DRUM[(k + 1) % len(DRUM)]
            self.moved.add(i)
        return self.busy


def ui_font(px: int, weight: QFont.Weight = QFont.Normal, spacing: float = 0) -> QFont:
    """The start window's type: Bahnschrift, the DIN-like face that ships with Windows."""
    f = QFont("Bahnschrift")
    f.setPixelSize(px)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


def tile_font(px: int) -> QFont:
    f = QFont("Bahnschrift")
    f.setPixelSize(px)
    f.setWeight(QFont.DemiBold)
    return f


def draw_flaps(p: QPainter, line: FlapLine, x: float, y: float, w: float, h: float,
               ink: QColor, gap: float = 2.0, font: QFont | None = None) -> float:
    """Paint the row with its top-left at (x, y); -> the x right after the last tile."""
    p.setFont(font or tile_font(int(h * 0.68)))
    seam = QPen(QColor(6, 7, 9), 1.2)
    gloss = QPen(QColor(0, 0, 0, 70), 1)
    rim = QPen(QColor(255, 255, 255, 22), 1)
    for i, ch in enumerate(line.shown):
        r = QRectF(x + i * (w + gap), y, w, h)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        flipping = i in line.moved
        g.setColorAt(0, QColor(46, 49, 56) if flipping else QColor(37, 40, 46))
        g.setColorAt(0.5, QColor(29, 31, 36))
        g.setColorAt(0.5001, QColor(22, 24, 28))
        g.setColorAt(1, QColor(17, 18, 21))
        p.setPen(rim)                   # the rim keeps the lower half visible on dark cards
        p.setBrush(g)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 2.5, 2.5)
        p.setPen(seam)                  # under the letter: a seam across 'I' would read as '!'
        p.drawLine(r.left() + 0.5, r.center().y(), r.right() - 0.5, r.center().y())
        if ch != " ":
            c = QColor(ink)
            if flipping:
                c.setAlpha(150)
            p.setPen(c)
            p.drawText(r.adjusted(0, -1, 0, 0) if not flipping else r.adjusted(0, -3, 0, -2),
                       Qt.AlignCenter, ch)
        p.setPen(gloss)
        p.drawLine(r.left() + 0.5, r.center().y() + 0.5, r.right() - 0.5, r.center().y() + 0.5)
    return x + line.width * (w + gap) - gap
