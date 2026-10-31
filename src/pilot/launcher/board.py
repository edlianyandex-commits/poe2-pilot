"""Start window: a departure board of builds, a boarding pass for the chosen one, take-off.

  ┌ title bar: mark · POE2 PILOT · flap "ВЫЛЕТЫ" · flap clock · — ✕ ─────────────────┐
  │ board: РЕЙС  НАПРАВЛЕНИЕ  СТАТУС         │ boarding pass (paper, stamp, barcode) │
  │   one flap row per build + its skills    │ [ ВЗЛЁТ ]                             │
  └ footer: content version · update news [Обновить] ────────────────────────────────┘
Keys: ↑ ↓ PgUp PgDn Home End pick, Enter take off, Esc quit. Double click a row takes off too.
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, QUrl, QVariantAnimation, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QFontMetrics, QLinearGradient, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

from pilot import __version__, brand
from pilot.catalog import Catalog, Entry

from .flaps import FlapLine, draw_flaps, tile_font

FONT = "Bahnschrift"
BG = QColor(12, 13, 16)
EDGE = QColor(42, 45, 51)
ROW_SEL = QColor(30, 27, 20)
ROW_HOVER = QColor(20, 21, 25)
INK = QColor(242, 234, 215)
DIM = QColor(128, 133, 142)
FAINT = QColor(70, 74, 82)
AMBER = brand.AMBER
GREEN = QColor(98, 217, 139)
RED = QColor(255, 93, 79)
PAPER = QColor(239, 229, 207)
PAPER_INK = QColor(34, 32, 27)
PAPER_DIM = QColor(125, 116, 98)

# status -> (board text, board ink, stamp text, stamp ink)
STATUS = {
    "verified": ("ПРОВЕРЕН", GREEN, "ПРОВЕРЕН", QColor(40, 122, 76)),
    "guide": ("ПО ГАЙДУ", INK, "ПО ГАЙДУ", QColor(44, 88, 150)),
    "custom": ("ТЕСТОВЫЙ", AMBER, "ТЕСТОВЫЙ РЕЙС", QColor(184, 69, 47)),
}
OUTDATED = ("ЗАДЕРЖАН", RED, "ЖДЁТ ПАТЧА", QColor(184, 40, 40))
BOARDING = ("ПОСАДКА", AMBER)

TW, TH, TG = 16, 26, 2              # flap tile width, height, gap
COLS = (("РЕЙС", 6), ("НАПРАВЛЕНИЕ", 24), ("СТАТУС", 8))
COL_GAP = 14
PAD_L = 22
HEAD_H = 30
ROW_H = 64
FLIP_MS = 38


def font(px: int, weight: QFont.Weight = QFont.Normal, spacing: float = 0) -> QFont:
    f = QFont(FONT)
    f.setPixelSize(px)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


def status_of(e: Entry) -> tuple:
    return OUTDATED if e.outdated else STATUS[e.status]


class _Flipper:
    """One timer that steps every FlapLine of a widget until they all settle."""

    def __init__(self, widget: QWidget, lines: Callable[[], list[FlapLine]]):
        self.w, self.lines = widget, lines
        self.timer = QTimer(widget)
        self.timer.setInterval(FLIP_MS)
        self.timer.timeout.connect(self._tick)

    def kick(self) -> None:
        if not self.timer.isActive():
            self.timer.start()

    def _tick(self) -> None:
        busy = False
        for line in self.lines():
            busy |= line.step()
        self.w.update()
        if not busy:
            self.timer.stop()


# ---------------------------------------------------------------- title bar
class TitleBar(QWidget):
    H = 66

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedHeight(self.H)
        self.setMouseTracking(True)
        self.title = FlapLine(10)
        self.title.set("ВЫЛЕТЫ", spins=(6, 14))
        self.clock = FlapLine(5)
        self.clock.set(time.strftime("%H:%M"), spins=(8, 16))
        self.flipper = _Flipper(self, lambda: [self.title, self.clock])
        self.flipper.kick()
        self._ticks = 0
        t = QTimer(self)
        t.setInterval(1000)
        t.timeout.connect(self._second)
        t.start()
        self.hover: str | None = None

    def _second(self) -> None:
        self._ticks += 1
        self.clock.set(time.strftime("%H:%M"), spins=(4, 8), stagger=0)
        if self._ticks % 9 == 0:     # the board speaks both languages, like a real one
            self.title.set("DEPARTURES" if self.title.text == "ВЫЛЕТЫ" else "ВЫЛЕТЫ", spins=(3, 10))
        self.flipper.kick()

    def _buttons(self) -> dict[str, QRectF]:
        r = self.width() - 18
        return {"close": QRectF(r - 30, 18, 30, 30), "min": QRectF(r - 66, 18, 30, 30)}

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        brand.draw_logo(p, QRectF(20, 15, 36, 36))
        p.setPen(INK)
        p.setFont(font(19, QFont.Bold, 1.5))
        p.drawText(QPointF(68, 33), "POE2 PILOT")
        p.setPen(DIM)
        p.setFont(font(11, spacing=0.8))
        p.drawText(QPointF(69, 50), f"штурман кампании · v{__version__}")

        big = tile_font(22)
        x0 = (self.width() - self.title.width * 22) / 2
        draw_flaps(p, self.title, x0, 16, 20, 32, INK, font=big)

        bx = self._buttons()
        cx = bx["min"].left() - 22 - 5 * 18
        draw_flaps(p, self.clock, cx, 21, 16, 24, AMBER)
        for name, r in bx.items():
            if self.hover == name:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(200, 60, 50) if name == "close" else QColor(40, 43, 49))
                p.drawRoundedRect(r, 6, 6)
            p.setPen(QPen(INK if self.hover == name else DIM, 1.6))
            c = r.center()
            if name == "close":
                p.drawLine(c + QPointF(-6, -6), c + QPointF(6, 6))
                p.drawLine(c + QPointF(-6, 6), c + QPointF(6, -6))
            else:
                p.drawLine(c + QPointF(-6, 0), c + QPointF(6, 0))
        p.setPen(QPen(EDGE, 1))
        p.drawLine(18, self.H - 1, self.width() - 18, self.H - 1)

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


# ---------------------------------------------------------------- the board
class Board(QWidget):
    selected = Signal(int)
    activated = Signal(int)

    def __init__(self, entries: tuple[Entry, ...], last: str | None, parent: QWidget):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.entries = entries
        self.last = last
        self.sel = next((i for i, e in enumerate(entries) if e.file == last), 0)
        self.hover = -1
        self.top = 0
        self.rows = [tuple(FlapLine(w) for _, w in COLS) for _ in entries]
        for i, (code, title, status) in enumerate(self.rows):
            e = entries[i]
            spins = (3 + i * 2, 9 + i * 2)            # rows settle top to bottom
            code.set(e.code, spins)
            title.set(e.title, spins)
            status.set(self._status(i)[0], spins)
        self.flipper = _Flipper(self, lambda: [ln for row in self.rows for ln in row])
        self.flipper.kick()
        w = PAD_L + sum(n for _, n in COLS) * (TW + TG) + COL_GAP * (len(COLS) - 1) + 18
        self.setMinimumWidth(w)

    def _status(self, i: int) -> tuple[str, QColor]:
        if i == self.sel:
            return BOARDING
        return status_of(self.entries[i])[:2]

    def visible_rows(self) -> int:
        return max(1, (self.height() - HEAD_H) // ROW_H)

    def select(self, i: int) -> None:
        if not self.entries:
            return
        i = max(0, min(len(self.entries) - 1, i))
        old, self.sel = self.sel, i
        for k in {old, i}:
            self.rows[k][2].set(self._status(k)[0], spins=(2, 7), stagger=0.3)
        n = self.visible_rows()
        self.top = min(max(self.top, i - n + 1), i)
        self.flipper.kick()
        self.update()
        if old != i:
            self.selected.emit(i)

    def row_at(self, y: float) -> int:
        if y < HEAD_H:
            return -1
        i = self.top + int((y - HEAD_H) // ROW_H)
        return i if i < len(self.entries) else -1

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        x = PAD_L
        p.setFont(font(11, QFont.DemiBold, 2))
        p.setPen(AMBER.darker(125))
        for label, n in COLS:
            p.drawText(QPointF(x, 18), label)
            x += n * (TW + TG) + COL_GAP
        p.setPen(QPen(EDGE, 1))
        p.drawLine(0, HEAD_H - 4, self.width(), HEAD_H - 4)
        if not self.entries:
            p.setPen(DIM)
            p.setFont(font(15))
            p.drawText(self.rect().adjusted(0, HEAD_H, 0, 0), Qt.AlignCenter,
                       "Рейсов нет: в папке builds пусто")
            return
        sub = font(12)
        fm = QFontMetrics(sub)
        for k in range(self.visible_rows()):
            i = self.top + k
            if i >= len(self.entries):
                break
            e, y = self.entries[i], HEAD_H + k * ROW_H
            row = QRectF(4, y + 2, self.width() - 8, ROW_H - 4)
            if i == self.sel or i == self.hover:
                p.setPen(Qt.NoPen)
                p.setBrush(ROW_SEL if i == self.sel else ROW_HOVER)
                p.drawRoundedRect(row, 8, 8)
            if i == self.sel:
                p.setBrush(AMBER)
                p.drawRoundedRect(QRectF(4, y + 12, 4, ROW_H - 24), 2, 2)
            x = PAD_L
            for (label, n), line in zip(COLS, self.rows[i]):
                ink = self._status(i)[1] if label == "СТАТУС" else INK
                x = draw_flaps(p, line, x, y + 9, TW, TH, ink, TG) + COL_GAP
            right = f"патч {e.patch}" + ("  ·  прошлый рейс" if e.file == self.last else "")
            p.setFont(sub)
            p.setPen(DIM)
            rw = fm.horizontalAdvance(right)
            p.drawText(QPointF(self.width() - 18 - rw, y + TH + 28), right)
            left = " · ".join([e.role, *e.skills])
            p.setPen(INK if i == self.sel else DIM)
            p.drawText(QPointF(PAD_L, y + TH + 28),
                       fm.elidedText(left, Qt.ElideRight, int(self.width() - PAD_L - rw - 36)))
        p.setFont(font(11))
        p.setPen(DIM)
        if self.top > 0:
            p.drawText(QPointF(self.width() - 60, 18), "▲ ещё")
        if self.top + self.visible_rows() < len(self.entries):
            p.drawText(QPointF(self.width() - 60, self.height() - 4), "▼ ещё")

    def resizeEvent(self, _):
        self.select(self.sel)

    def mouseMoveEvent(self, e):
        h = self.row_at(e.position().y())
        if h != self.hover:
            self.hover = h
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


# ---------------------------------------------------------------- boarding pass
class BoardingPass(QWidget):
    W, H = 372, 548
    STUB_H = 112

    def __init__(self, catalog: Catalog, parent: QWidget):
        super().__init__(parent)
        self.setFixedSize(self.W, self.H)
        self.setMouseTracking(True)
        self.cat = catalog
        self.entry: Entry | None = None
        self.link = QRectF()
        self._t = 1.0
        self.anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=220)
        self.anim.valueChanged.connect(self._step)

    def _step(self, v):
        self._t = float(v)
        self.update()

    def set_entry(self, e: Entry | None) -> None:
        self.entry = e
        self.anim.stop()
        self.anim.start()

    def _paper(self, r: QRectF) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        cut = QPainterPath()
        y = r.bottom() - self.STUB_H
        for cx in (r.left(), r.right()):
            cut.addEllipse(QPointF(cx, y), 13, 13)
        return path.subtracted(cut)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        e = self.entry
        t = self._t
        p.setOpacity(0.35 + 0.65 * t)
        p.translate(0, (1 - t) * 16)
        card = QRectF(8, 4, self.W - 16, self.H - 14)
        paper = self._paper(card)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 140))
        p.drawPath(paper.translated(0, 5))
        p.setBrush(PAPER)
        p.drawPath(paper)

        band = QPainterPath()
        band.addRoundedRect(QRectF(card.left(), card.top(), card.width(), 46), 12, 12)
        band.addRect(QRectF(card.left(), card.top() + 30, card.width(), 16))
        p.setBrush(PAPER_INK)
        p.drawPath(band.simplified())
        p.setPen(PAPER)
        p.setFont(font(11, QFont.DemiBold, 2.2))
        p.drawText(QPointF(card.left() + 18, card.top() + 28), "ПОСАДОЧНЫЙ ТАЛОН")
        brand.draw_logo(p, QRectF(card.right() - 40, card.top() + 9, 28, 28))
        if e is None:
            return

        L, R = card.left() + 20, card.right() - 20
        y = card.top() + 74

        def label(text: str, x: float, yy: float) -> None:
            p.setPen(PAPER_DIM)
            p.setFont(font(10, QFont.DemiBold, 1.6))
            p.drawText(QPointF(x, yy), text)

        def value(text: str, x: float, yy: float, px: int = 15, w: float | None = None,
                  weight: QFont.Weight = QFont.DemiBold) -> None:
            f = font(px, weight)
            p.setFont(f)
            p.setPen(PAPER_INK)
            if w:
                text = QFontMetrics(f).elidedText(text, Qt.ElideRight, int(w))
            p.drawText(QPointF(x, yy), text)

        label("ПАССАЖИР", L, y)
        value(e.role.upper(), L, y + 28, 24, R - L - 10, QFont.Bold)
        if e.ascendancy:
            p.setPen(PAPER_DIM)
            p.setFont(font(13))
            p.drawText(QPointF(L, y + 48), e.cls)

        y += 84                                          # from -> to, with the plane between
        label("ОТКУДА", L, y)
        label("КУДА", R - 70, y)
        value("A1", L, y + 36, 34, weight=QFont.Bold)
        value("END", R - 70, y + 36, 34, weight=QFont.Bold)
        mid_l, mid_r, my = L + 64, R - 82, y + 24
        p.setPen(QPen(PAPER_DIM, 1.4, Qt.DashLine))
        p.drawLine(QPointF(mid_l, my), QPointF(mid_r, my))
        cx = (mid_l + mid_r) / 2
        p.setPen(Qt.NoPen)
        p.setBrush(PAPER)
        p.drawEllipse(QPointF(cx, my), 15, 15)
        plane = QPainterPath(QPointF(cx + 11, my))
        for dx, dy in ((-9, -8), (-4, 0), (-9, 8)):
            plane.lineTo(QPointF(cx + dx, my + dy))
        plane.closeSubpath()
        p.setBrush(PAPER_INK)
        p.drawPath(plane)
        p.setPen(PAPER_DIM)
        p.setFont(font(11))
        fm = QFontMetrics(p.font())
        p.drawText(QPointF(L, y + 54), fm.elidedText(self.cat.start, Qt.ElideRight, 140))
        fin = fm.elidedText(self.cat.finish, Qt.ElideRight, 150)
        p.drawText(QPointF(R - fm.horizontalAdvance(fin), y + 54), fin)

        y += 82
        third = (R - L) / 3
        for k, (lab, val) in enumerate((("РЕЙС", e.code), ("ПАТЧ", e.patch), ("РЕВИЗИЯ", str(e.rev)))):
            label(lab, L + k * third, y)
            value(val, L + k * third, y + 22, 17)
        y += 44
        label("АВТОР", L, y)
        value(e.author, L, y + 20, 14, R - L)
        y += 40
        label("СКИЛЛЫ", L, y)
        p.setFont(font(13, QFont.DemiBold))
        p.setPen(PAPER_INK)
        p.drawText(QRectF(L, y + 5, R - L, 36), Qt.TextWordWrap, " · ".join(e.skills))
        y += 46
        label("ОБЯЗАТЕЛЬНО", L, y)
        value(", ".join(e.musts) or "—", L, y + 20, 13, R - L)
        y += 30
        if e.note:
            f = font(12)
            f.setItalic(True)
            p.setFont(f)
            p.setPen(PAPER_DIM)
            p.drawText(QRectF(L, y, R - L, card.bottom() - self.STUB_H - y - 6), Qt.TextWordWrap, e.note)

        sy = card.bottom() - self.STUB_H              # perforation, then the stub
        p.setPen(QPen(PAPER_DIM, 1.2, Qt.DotLine))
        p.drawLine(QPointF(card.left() + 18, sy), QPointF(card.right() - 18, sy))
        bars = hashlib.sha256(f"{e.file}:{e.rev}".encode()).digest()
        bx = L
        p.setPen(Qt.NoPen)
        p.setBrush(PAPER_INK)
        for b in bars:
            w = 1 + (b & 3)
            p.drawRect(QRectF(bx, sy + 22, w, 56))
            bx += w + 1 + ((b >> 2) & 1) * 2
            if bx > L + 176:
                break
        p.setPen(PAPER_DIM)
        p.setFont(font(10, spacing=1.4))
        p.drawText(QPointF(L, sy + 94), e.file.rsplit(".", 1)[0][:30])
        stamp_text, ink = status_of(e)[2:]
        p.save()
        p.translate(R - 70, sy + 46)
        p.rotate(-9)
        sf = font(13, QFont.Bold, 1.6)
        sw = QFontMetrics(sf).horizontalAdvance(stamp_text) + 22
        c = QColor(ink)
        c.setAlpha(200)
        p.setPen(QPen(c, 2.2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(-sw / 2, -17, sw, 34), 6, 6)
        p.setPen(QPen(c, 1))
        p.drawRoundedRect(QRectF(-sw / 2 + 4, -13, sw - 8, 26), 4, 4)
        p.setFont(sf)
        p.drawText(QRectF(-sw / 2, -17, sw, 34), Qt.AlignCenter, stamp_text)
        p.restore()

        self.link = QRectF()
        if e.source:
            p.setFont(font(12, QFont.DemiBold))
            p.setPen(QColor(44, 88, 150))
            txt = "ГАЙД ↗"
            w = QFontMetrics(p.font()).horizontalAdvance(txt)
            self.link = QRectF(R - w, sy + 64, w, 22).translated(0, (1 - t) * 16)
            p.drawText(QPointF(R - w, sy + 80), txt)

    def mouseMoveEvent(self, e):
        self.setCursor(Qt.PointingHandCursor if self.link.contains(e.position()) else Qt.ArrowCursor)

    def mousePressEvent(self, e):
        if self.entry and self.entry.source and self.link.contains(e.position()):
            QDesktopServices.openUrl(QUrl(self.entry.source))


# ---------------------------------------------------------------- take-off button
class TakeoffButton(QAbstractButton):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedHeight(58)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, _):
        self.update()

    def leaveEvent(self, _):
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(8, 2, -8, -4)
        on = self.isEnabled()
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        top = AMBER.lighter(112) if self.underMouse() and on else AMBER
        if self.isDown():
            top = AMBER.darker(115)
        g.setColorAt(0, top if on else FAINT)
        g.setColorAt(1, top.darker(118) if on else FAINT.darker(120))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, 12, 12)
        p.setPen(PAPER_INK)
        p.setFont(font(21, QFont.Bold, 4))
        p.drawText(r.adjusted(0, 0, -30, 0), Qt.AlignCenter, "ВЗЛЁТ")
        c = QPointF(r.right() - 34, r.center().y())
        plane = QPainterPath(c + QPointF(12, -9))
        for pt in (QPointF(-12, 0), QPointF(-3, 2), QPointF(0, 10)):
            plane.lineTo(c + pt)
        plane.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(PAPER_INK)
        p.drawPath(plane)
        p.setPen(QColor(34, 32, 27, 150))
        p.setFont(font(10, QFont.DemiBold, 1.5))
        p.drawText(QRectF(r.left() + 16, r.top(), 60, r.height()), Qt.AlignVCenter, "ENTER")


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


BUTTON_CSS = (
    "QPushButton{color:#ffb23e;background:transparent;border:1px solid #ffb23e;border-radius:8px;"
    "padding:3px 14px;font:600 12px 'Bahnschrift';}"
    "QPushButton:hover{background:#ffb23e;color:#22201b;}"
    "QPushButton:disabled{color:#5a5e66;border-color:#3a3d44;}")


class BoardWindow(QWidget):
    finished = Signal()

    def __init__(self, catalog: Catalog, last: str | None = None, content_version: str = "",
                 updater: object | None = None):
        """updater: pilot.updates-like object with check() / apply(manifest) -> int, or None (offline)."""
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("PoE2 Pilot")
        self.setWindowIcon(brand.logo_icon())
        self.cat = catalog
        self.result: str | None = None
        self.restart = False
        self.updater = updater
        self._remote: dict | None = None
        self._open_url: str | None = None

        self.bar = TitleBar(self)
        self.board = Board(catalog.entries, last, self)
        self.ticket = BoardingPass(catalog, self)
        self.go = TakeoffButton(self)
        self.go.setEnabled(bool(catalog.entries))
        self.go.clicked.connect(self.take_off)
        self.board.selected.connect(lambda i: self.ticket.set_entry(catalog.entries[i]))
        self.board.activated.connect(lambda i: self.take_off())
        if catalog.entries:
            self.ticket.set_entry(catalog.entries[self.board.sel])

        side = QVBoxLayout()
        side.setSpacing(14)
        side.addWidget(self.ticket)
        side.addWidget(self.go)
        side.addStretch(1)
        body = QHBoxLayout()
        body.setContentsMargins(14, 12, 18, 6)
        body.setSpacing(16)
        body.addWidget(self.board, 1)
        body.addLayout(side)

        self.info = QLabel(f"контент {content_version or '—'}  ·  игра {catalog.game or '—'}", self)
        self.news = QLabel("", self)
        for lab in (self.info, self.news):
            lab.setStyleSheet("color:#80858e;font:12px 'Bahnschrift';")
        self.action = QPushButton(self)
        self.action.setStyleSheet(BUTTON_CSS)
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.hide()
        self.action.clicked.connect(self._act)
        keys = QLabel("↑ ↓ выбрать   ·   Enter взлёт   ·   Esc выход", self)
        keys.setStyleSheet("color:#464a52;font:12px 'Bahnschrift';")
        foot = QHBoxLayout()
        foot.setContentsMargins(22, 4, 22, 14)
        foot.setSpacing(12)
        foot.addWidget(self.info)
        foot.addStretch(1)
        foot.addWidget(self.news)
        foot.addWidget(self.action)
        foot.addSpacing(18)
        foot.addWidget(keys)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.bar)
        root.addLayout(body, 1)
        root.addLayout(foot)
        self.resize(1190, 720)
        self.setMinimumSize(1100, 640)

        if updater is not None:
            self.news.setText("проверяю обновления…")
            run_async(self, updater.check, self._checked)

    # -- updates
    def _checked(self, res, err) -> None:
        if err is not None:
            self.news.setText("GitHub недоступен — летим с тем, что есть")
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

    # -- take-off and keys
    def take_off(self) -> None:
        if self.cat.entries:
            self.result = self.cat.entries[self.board.sel].file
            self.close()

    def keyPressEvent(self, e):
        k, b = e.key(), self.board
        step = {Qt.Key_Up: -1, Qt.Key_Down: 1, Qt.Key_PageUp: -b.visible_rows(),
                Qt.Key_PageDown: b.visible_rows()}
        if k in step:
            b.select(b.sel + step[k])
        elif k == Qt.Key_Home:
            b.select(0)
        elif k == Qt.Key_End:
            b.select(len(self.cat.entries) - 1)
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            self.take_off()
        elif k == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(EDGE, 1))
        p.setBrush(BG)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)

    def closeEvent(self, e):
        super().closeEvent(e)
        self.finished.emit()
