"""Look of the start window: pastel gacha style. Colours, the bundled font, small drawing helpers.

Font: M PLUS Rounded 1c (SIL OFL, assets/fonts: Regular, Bold, ExtraBold), loaded once per process;
Segoe UI if it can't be.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QLinearGradient, QPainter,
                           QPainterPath, QPen)

from pilot.paths import root
from pilot.i18n import lang, tr

INK = QColor(46, 37, 84)
DIM = QColor(138, 130, 168)
FAINT = QColor(196, 190, 214)
WHITE = QColor(255, 255, 255)
PINK = QColor(255, 95, 162)
GOLD = QColor(255, 185, 56)
LAVENDER = QColor(238, 233, 255)
SHADOW = QColor(120, 90, 180, 40)

# per class: the card colour; classes without a colour use LAVENDER
CLASS_COLOR = {
    "Warrior": QColor(255, 122, 89), "Ranger": QColor(107, 203, 119), "Huntress": QColor(46, 196, 182),
    "Mercenary": QColor(244, 163, 64), "Monk": QColor(91, 184, 255), "Witch": QColor(155, 107, 255),
    "Sorceress": QColor(77, 124, 255), "Druid": QColor(95, 175, 110),
}

# build status -> rarity: (badge, stars, label, badge gradient top, bottom)
RARITY = {
    "verified": ("SSR", 5, "проверен", QColor(255, 196, 64), QColor(255, 95, 162)),
    "guide": ("SR", 4, "по гайду", QColor(190, 140, 255), QColor(120, 80, 230)),
    "custom": ("R", 3, "тестовый", QColor(110, 200, 255), QColor(60, 130, 240)),
}
OUTDATED = ("OLD", 0, "ждёт патча", QColor(200, 196, 212), QColor(150, 146, 166))

FAMILY = "Rounded Mplus 1c"            # how M PLUS Rounded 1c names itself; Bold comes as its own family
BOLD_FAMILY = "Rounded Mplus 1c Bold"
_families: set[str] | None = None


def load_fonts() -> str:
    """Register the bundled font; -> the family to use (Segoe UI if the files are missing)."""
    global _families
    if _families is None:
        _families = set()
        for f in sorted((root() / "assets" / "fonts").glob("*.ttf")):
            fid = QFontDatabase.addApplicationFont(str(f))
            if fid >= 0:
                _families.update(QFontDatabase.applicationFontFamilies(fid))
    return FAMILY if FAMILY in _families else "Segoe UI"


def family(weight: int) -> str:
    base = load_fonts()
    return BOLD_FAMILY if base == FAMILY and 600 <= weight < 750 and BOLD_FAMILY in _families else base


def font(px: float, weight: QFont.Weight = QFont.Normal, spacing: float = 0) -> QFont:
    w = weight.value if hasattr(weight, "value") else int(weight)
    f = QFont(family(w))
    f.setPixelSize(max(1, int(px)))
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


def rarity(e) -> tuple:
    """(badge, stars, label in the UI language, gradient top, bottom)."""
    tag, n, label, top, bottom = OUTDATED if e.outdated else RARITY[e.status]
    return tag, n, tr(label), top, bottom


def class_color(cls: str) -> QColor:
    return CLASS_COLOR.get(cls, QColor(180, 170, 220))


# ---------------------------------------------------------------- drawing helpers
def sparkle(p: QPainter, c: QPointF, s: float, color: QColor) -> None:
    """Four-point twinkle with concave sides."""
    path = QPainterPath(QPointF(c.x(), c.y() - s))
    for dx, dy in ((s, 0), (0, s), (-s, 0), (0, -s)):
        path.quadTo(c, QPointF(c.x() + dx, c.y() + dy))
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(path)


def star_path(c: QPointF, r: float) -> QPainterPath:
    path = QPainterPath()
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rad = r if k % 2 == 0 else r * 0.46
        pt = QPointF(c.x() + rad * math.cos(a), c.y() + rad * math.sin(a))
        path.moveTo(pt) if k == 0 else path.lineTo(pt)
    path.closeSubpath()
    return path


def stars(p: QPainter, x: float, cy: float, r: float, filled: int, total: int = 5) -> float:
    """Row of rating stars from x; -> the x after the last one."""
    p.setPen(Qt.NoPen)
    for k in range(total):
        p.setBrush(GOLD if k < filled else FAINT)
        p.drawPath(star_path(QPointF(x + r + k * r * 2.3, cy), r))
    return x + total * r * 2.3


def soft_card(p: QPainter, r: QRectF, radius: float, fill, border: QColor | None = WHITE,
              border_w: float = 1.5, shadow: bool = True) -> None:
    if shadow:
        p.setPen(Qt.NoPen)
        for k, a in ((10, 14), (6, 22), (3, 30)):
            c = QColor(SHADOW)
            c.setAlpha(a)
            p.setBrush(c)
            p.drawRoundedRect(r.adjusted(-k / 3, k / 2, k / 3, k), radius + k / 2, radius + k / 2)
    p.setPen(QPen(border, border_w) if border is not None else Qt.NoPen)
    p.setBrush(fill)
    p.drawRoundedRect(r, radius, radius)


def gradient(r: QRectF, top: QColor, bottom: QColor, horizontal: bool = False) -> QLinearGradient:
    g = QLinearGradient(r.topLeft(), r.topRight() if horizontal else r.bottomLeft())
    g.setColorAt(0, top)
    g.setColorAt(1, bottom)
    return g


def chip(p: QPainter, x: float, y: float, text: str, f: QFont, fg: QColor, bg: QColor | None,
         outline: QColor | None = None, h: float = 22) -> float:
    """Pill with text, top-left at (x, y); -> its width."""
    w = QFontMetricsF(f).horizontalAdvance(text) + h * 0.9
    p.setPen(QPen(outline, 1.4) if outline else Qt.NoPen)
    p.setBrush(bg if bg is not None else Qt.NoBrush)
    p.drawRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)
    p.setFont(f)
    p.setPen(fg)
    p.drawText(QRectF(x, y, w, h), Qt.AlignCenter, text)
    return w


def chips(p: QPainter, r: QRectF, texts, f: QFont, fg: QColor, bg: QColor | None,
          outline: QColor | None = None, h: float = 22, gap: float = 6) -> float:
    """Chips flowing into rows inside r; -> the height used."""
    fm = QFontMetricsF(f)
    x, y = r.left(), r.top()
    for t in texts:
        w = fm.horizontalAdvance(t) + h * 0.9
        if x > r.left() and x + w > r.right():
            x, y = r.left(), y + h + gap
        if y + h > r.bottom() + 0.5:
            break
        x += chip(p, x, y, t, f, fg, bg, outline, h) + gap
    return y + h - r.top()


def plural(n: int, one: str, few: str, many: str) -> str:
    last2, last = n % 100, n % 10
    if last == 1 and last2 != 11:
        return one
    if 2 <= last <= 4 and not 12 <= last2 <= 14:
        return few
    return many


def builds_word(n: int) -> str:
    if not n:
        return tr("скоро")
    if lang() == "en":
        return f"{n} build" + ("" if n == 1 else "s")
    return f"{n} {plural(n, 'билд', 'билда', 'билдов')}"
