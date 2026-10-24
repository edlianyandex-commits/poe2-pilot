"""Separate gem window (Alt+G): the skills for the current level and the supports that go in them.

skill icon (40 px) > support icons (32 px, shrinking to 24 px, never wrapping)
* hover an icon  -> tooltip: English name (bold), kind, description
* click an icon  -> English name goes to the clipboard (for the in-game search); nothing is
                    ever sent to the game
The window is frameless, always on top, never takes focus (WS_EX_NOACTIVATE) and, unlike the HUD,
is NOT click-through: it has to receive hover and clicks.
"""
from __future__ import annotations

import logging
import math
from typing import Callable, NamedTuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath,
                           QPen, QPixmap, QTextDocument)
from PySide6.QtWidgets import QWidget

from pilot.contracts import GemCard, GemRow

from . import theme, winapi
from .fmt import elide
from .hud import clamp_scale

log = logging.getLogger(__name__)

BASE_W = 340
PAD = 14
HEADER_H = 34
FOOTER_H = 26
ROW_H = 62
ROW_GAP = 6
SKILL_COL = 92
SKILL_ICON = 40
SUP_ICON_MAX, SUP_ICON_MIN = 32, 24
SUP_GAP = 5
ARROW_W = 22
TIP_MAX_W = 360
FLASH_S = 1.0

ATTR_COLORS = {            # fallback gem fill by attribute
    "str": (206, 78, 66),
    "dex": (84, 178, 98),
    "int": (86, 136, 232),
    "none": (150, 150, 150),
}
KIND_LABEL = {"skill": "Скилл", "support": "Поддержка", "spirit": "Дух"}
BG = QColor(0, 0, 0, 140)
OUTLINE = QColor(0, 0, 0, 215)


# ---------------------------------------------------------------- pure helpers
def initials(name: str) -> str:
    """'Prolonged Duration II' -> 'PD', 'Twister' -> 'Tw'."""
    words = [w for w in name.replace("-", " ").split() if w]
    if not words:
        return "?"
    if len(words) == 1:
        w = words[0]
        return (w[0].upper() + w[1:2].lower())
    return (words[0][0] + words[1][0]).upper()


def fit_icon_size(n: int, avail: float, gap: float = SUP_GAP,
                  hi: int = SUP_ICON_MAX, lo: int = SUP_ICON_MIN) -> int:
    """Largest support icon size in [lo, hi] such that n icons fit in `avail` on one line.
    Never below `lo`: callers widen the window instead of wrapping."""
    if n <= 0:
        return hi
    size = int((avail - gap * (n - 1)) // n)
    return max(lo, min(hi, size))


def attr_color(color: str | None) -> tuple[int, int, int]:
    return ATTR_COLORS.get(color or "none", ATTR_COLORS["none"])


class Item(NamedTuple):
    rect: QRectF
    card: GemCard
    size: int


class _Tip(QWidget):
    """Dark tooltip: bold English name, kind, wrapped description (<= TIP_MAX_W wide)."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint
                            | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.doc = QTextDocument()
        self.title = ""
        self.kind_text = ""
        self.desc = ""
        self.scale = 1.0

    def set_card(self, card: GemCard, scale: float = 1.0) -> None:
        self.scale = scale
        self.title = card.name
        self.kind_text = KIND_LABEL.get(card.kind, card.kind)
        self.desc = card.description or ""
        px = round(14 * scale)
        html = (f"<div style='font-size:{px}px; color:#fff'>"
                f"<b>{_esc(self.title)}</b><br>"
                f"<span style='color:#a8a8a8'>{_esc(self.kind_text)}</span>")
        if self.desc:
            html += f"<br><span style='color:#e4e4e4'>{_esc(self.desc)}</span>"
        html += "</div>"
        f = QFont("Segoe UI")
        f.setPixelSize(px)
        self.doc.setDefaultFont(f)
        self.doc.setHtml(html)
        self.doc.setTextWidth(TIP_MAX_W * scale)
        w = min(self.doc.idealWidth(), TIP_MAX_W * scale)
        self.doc.setTextWidth(w)
        pad = 10 * scale
        self.setFixedSize(int(math.ceil(w + 2 * pad)), int(math.ceil(self.doc.size().height() + 2 * pad)))

    def plain_text(self) -> str:
        return self.doc.toPlainText()

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        p.setBrush(QColor(14, 14, 14, 238))
        p.drawRoundedRect(r, 8 * self.scale, 8 * self.scale)
        p.translate(10 * self.scale, 10 * self.scale)
        self.doc.drawContents(p)
        p.end()


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class GemsWindow(QWidget):
    icon_ready = Signal()          # emitted from IconCache worker threads (queued to the GUI thread)

    def __init__(self, config: dict | None = None, clock: Callable[[], float] | None = None):
        super().__init__(None)
        import time
        self.config = config if config is not None else {}
        self._clock = clock or time.monotonic
        saved = self.config.get("gems_window") or {}
        self.scale = clamp_scale(saved.get("scale") or 1.0)
        self.rows: tuple[GemRow, ...] = ()
        self.level: int | None = None
        self._open = False
        self._items: list[Item] = []
        self._hover: Item | None = None
        self._flash: tuple[str, float] | None = None
        self._drag_off: QPointF | None = None
        self._moved = False
        self._paths: dict[str, str | None] = {}
        self._pm_cache: dict[tuple[str, int], QPixmap | None] = {}
        self._cache = self.config.get("icon_cache")
        self._cache_tried = self._cache is not None

        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setWindowTitle("PoE2 Pilot · gems")

        self.tip = _Tip()
        self.icon_ready.connect(self._on_icon_ready)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh)
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._end_flash)

        self._rebuild_fonts()
        self._relayout(initial=True)

    # ------------------------------------------------------------------ geometry
    def u(self, n: float) -> float:
        return n * self.scale

    def _rebuild_fonts(self) -> None:
        s = self.scale
        self.f_head = QFont("Segoe UI")
        self.f_head.setPixelSize(max(8, round(17 * s)))
        self.f_head.setWeight(QFont.DemiBold)
        self.f_small = QFont("Segoe UI")
        self.f_small.setPixelSize(max(8, round(11.5 * s)))
        self.f_foot = QFont("Segoe UI")
        self.f_foot.setPixelSize(max(8, round(13 * s)))
        for f in (self.f_head, self.f_small, self.f_foot):
            f.setStyleStrategy(QFont.PreferAntialias)
        self.m_head, self.m_small, self.m_foot = (QFontMetrics(f) for f in
                                                  (self.f_head, self.f_small, self.f_foot))

    def _base_width(self) -> float:
        most = max((len(r.supports) for r in self.rows), default=0)
        need = 2 * PAD + SKILL_COL + ARROW_W + most * SUP_ICON_MIN + max(0, most - 1) * SUP_GAP
        return max(BASE_W, need)

    def compute_items(self) -> tuple[list[Item], float, float]:
        """-> (items, width, height) in device-independent px at the current scale."""
        s = self.scale
        W = self._base_width() * s
        items: list[Item] = []
        y = self.u(HEADER_H)
        if not self.rows:
            y += self.u(34)
        for row in self.rows:
            sk = self.u(SKILL_ICON)
            cx = self.u(PAD) + self.u(SKILL_COL) / 2
            items.append(Item(QRectF(cx - sk / 2, y, sk, sk), row.skill, round(sk)))
            n = len(row.supports)
            x0 = self.u(PAD + SKILL_COL + ARROW_W)
            avail = W - x0 - self.u(PAD)
            size = fit_icon_size(n, avail / s) * s
            gap = self.u(SUP_GAP)
            cy = y + sk / 2
            for i, card in enumerate(row.supports):
                items.append(Item(QRectF(x0 + i * (size + gap), cy - size / 2, size, size), card,
                                  round(size)))
            y += self.u(ROW_H + ROW_GAP)
        y += self.u(FOOTER_H) if self.rows else self.u(FOOTER_H)
        return items, W, y

    def _relayout(self, initial: bool = False) -> None:
        old_w = self.width()
        self._items, W, H = self.compute_items()
        self.setFixedSize(int(math.ceil(W)), int(math.ceil(H)))
        if initial:
            self._place()
        elif old_w and old_w != self.width() and self._open:
            pass  # keep the left edge: the window only grows to the right

    def _place(self) -> None:
        saved = self.config.get("gems_window") or {}
        if saved.get("x") is not None and saved.get("y") is not None:
            self.move(int(saved["x"]), int(saved["y"]))
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.right() - self.width() - 24, geo.top() + 90)

    # ------------------------------------------------------------------ data
    def set_rows(self, rows, level: int | None = None) -> None:
        rows = tuple(rows or ())
        if rows == self.rows and level == self.level:
            return
        self.rows, self.level = rows, level
        self._hover = None
        self.tip.hide()
        self._resolve_icons()
        self._relayout()
        self.update()

    def refresh(self) -> None:
        """Pull rows (and the level, if known) from the providers."""
        prov = self.config.get("gem_provider")
        rows = self.rows
        if prov:
            try:
                rows = tuple(prov() or ())
            except Exception:
                log.exception("gem_provider failed")
        lv = self.level
        lp = self.config.get("level_provider")
        if lp:
            try:
                lv = lp()
            except Exception:
                log.exception("level_provider failed")
        self.set_rows(rows, lv)

    # ------------------------------------------------------------------ icons
    def _get_cache(self):
        if not self._cache_tried:
            self._cache_tried = True
            try:
                from pilot.assets import IconCache
                self._cache = IconCache()
            except Exception:
                log.exception("icon cache unavailable")
        return self._cache

    def _resolve_icons(self) -> None:
        cache = self._get_cache()
        if cache is None:
            return
        for row in self.rows:
            for card in (row.skill, *row.supports):
                url = card.icon_url
                if not url or self._paths.get(url):
                    continue
                try:
                    self._paths[url] = cache.get(url, self.icon_ready.emit)
                except Exception:
                    log.exception("icon cache get failed")
                    self._paths[url] = None

    def _on_icon_ready(self) -> None:
        self._resolve_icons()
        self._pm_cache.clear()
        self.update()

    def icon_pixmap(self, card: GemCard, size: int) -> QPixmap | None:
        path = self._paths.get(card.icon_url or "")
        if not path:
            return None
        key = (path, size)
        if key not in self._pm_cache:
            pm = QPixmap(path)
            if pm.isNull():
                self._pm_cache[key] = None
            else:
                dpr = self.devicePixelRatioF()
                pm = pm.scaled(int(size * dpr), int(size * dpr), Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
                pm.setDevicePixelRatio(dpr)
                self._pm_cache[key] = pm
        return self._pm_cache[key]

    # ------------------------------------------------------------------ show / hide
    @property
    def is_open(self) -> bool:
        return self._open

    def toggle(self) -> None:
        self._open = not self._open
        if self._open:
            self.refresh()
        self.refresh_visibility()

    def should_be_visible(self, fg=None, *, check: bool = True) -> bool:
        if not self._open:
            return False
        if not self.config.get("hide_when_unfocused", True):
            return True
        if check and fg is None:
            fg = winapi.foreground_info()
        return winapi.is_game_foreground(fg, self.config.get("game_exes") or winapi.GAME_EXES)

    def refresh_visibility(self, fg=None) -> None:
        want = self.should_be_visible(fg)
        if want and not self.isVisible():
            self.show()
            self._apply_native()
            self._timer.start()
        elif not want and self.isVisible():
            self.hide()
            self.tip.hide()
            self._timer.stop()
        elif want:
            winapi.keep_topmost(self._hwnd())

    def _hwnd(self) -> int:
        if QGuiApplication.platformName() != "windows":
            return 0
        return int(self.winId())

    def _apply_native(self) -> None:
        # layered + toolwindow + NOACTIVATE, but not TRANSPARENT: we need hover and clicks
        winapi.make_click_through(self._hwnd(), interactive=True)

    # ------------------------------------------------------------------ interaction
    def item_at(self, pos) -> Item | None:
        pt = QPointF(pos)
        for it in self._items:
            if it.rect.contains(pt):
                return it
        return None

    def _header_rect(self) -> QRectF:
        return QRectF(0, 0, self.width(), self.u(HEADER_H))

    def set_hover(self, item: Item | None) -> None:
        if item == self._hover:
            return
        self._hover = item
        if item is None:
            self.tip.hide()
        else:
            self.tip.set_card(item.card, self.scale)
            gp = self.mapToGlobal(item.rect.bottomLeft().toPoint())
            x, y = gp.x(), gp.y() + int(self.u(8))
            screen = self.screen() or QGuiApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                x = max(geo.left(), min(x, geo.right() - self.tip.width()))
                if y + self.tip.height() > geo.bottom():
                    y = self.mapToGlobal(item.rect.topLeft().toPoint()).y() - self.tip.height() - int(self.u(8))
            self.tip.move(x, y)
            self.tip.show()
        self.update()

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._drag_off is not None:
            p = e.globalPosition() - self._drag_off
            self.move(int(p.x()), int(p.y()))
            self._moved = True
            return
        self.set_hover(self.item_at(e.position()))

    def leaveEvent(self, _e):  # noqa: N802
        if self._drag_off is None:
            self.set_hover(None)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() != Qt.LeftButton:
            return
        it = self.item_at(e.position())
        if it is not None:
            self.copy_name(it.card)
        elif self._header_rect().contains(e.position()):
            self._drag_off = e.globalPosition() - QPointF(self.pos())
            self._moved = False
            self.tip.hide()

    def mouseReleaseEvent(self, _e):  # noqa: N802
        if self._drag_off is not None:
            self._drag_off = None
            if self._moved:
                self._save()

    def wheelEvent(self, e):  # noqa: N802
        if not self._header_rect().contains(e.position()):
            return
        self.set_scale(self.scale + 0.05 * (e.angleDelta().y() / 120.0))
        self._save()

    def set_scale(self, v: float) -> None:
        v = clamp_scale(v)
        if v == self.scale:
            return
        self.scale = v
        self._rebuild_fonts()
        self._pm_cache.clear()
        self._hover = None
        self.tip.hide()
        self._relayout()
        self.update()

    def _save(self) -> None:
        self.config["gems_window"] = {"x": self.x(), "y": self.y(), "scale": self.scale}
        cb = self.config.get("on_save")
        if cb:
            try:
                cb(self.config)
            except Exception:
                log.exception("on_save failed")

    def copy_name(self, card: GemCard) -> None:
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(card.name)
        self._flash = (f"Скопировано: {card.name}", self._clock() + FLASH_S)
        self._flash_timer.start(int(FLASH_S * 1000))
        self.update()

    def _end_flash(self) -> None:
        self._flash = None
        self.update()

    @property
    def flash_text(self) -> str | None:
        return self._flash[0] if self._flash else None

    # ------------------------------------------------------------------ painting
    def _text(self, p: QPainter, x: float, base_y: float, text: str, font: QFont,
              color: QColor, alpha: float = 1.0) -> None:
        if not text:
            return
        path = QPainterPath()
        path.addText(x, base_y, font, text)
        pen = QPen(QColor(0, 0, 0, int(OUTLINE.alpha() * alpha)), max(2.0, self.u(3.0)))
        pen.setJoinStyle(Qt.RoundJoin)
        p.strokePath(path, pen)
        c = QColor(color)
        c.setAlphaF(c.alphaF() * alpha)
        p.fillPath(path, c)

    @staticmethod
    def _base(top: float, h: float, fm: QFontMetrics) -> float:
        return top + h * 0.5 + fm.ascent() * 0.5 - fm.descent() * 0.5

    def _draw_fallback(self, p: QPainter, rect: QRectF, card: GemCard) -> None:
        r, g, b = attr_color(card.color)
        base, dark, light = QColor(r, g, b), QColor(r // 3, g // 3, b // 3), QColor(
            min(255, r + 70), min(255, g + 70), min(255, b + 70))
        c = rect.center()
        rad = rect.width() / 2 - 1
        path = QPainterPath()
        if card.kind == "support":                       # diamond
            pts = [(0, -1.0), (0.9, 0), (0, 1.0), (-0.9, 0)]
        else:                                            # hexagon (skills, spirit)
            pts = [(math.cos(math.radians(60 * i - 90)) * 0.95,
                    math.sin(math.radians(60 * i - 90)) * 0.95) for i in range(6)]
        for i, (dx, dy) in enumerate(pts):
            pt = QPointF(c.x() + dx * rad, c.y() + dy * rad)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        path.closeSubpath()
        p.setPen(QPen(QColor(0, 0, 0, 200), max(2.0, rect.width() * 0.09)))
        p.setBrush(dark)
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(base)
        p.drawPath(path)
        p.setPen(QPen(light, max(1.0, rect.width() * 0.04)))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        f = QFont("Segoe UI")
        f.setPixelSize(max(8, int(rect.width() * (0.36 if card.kind == "support" else 0.38))))
        f.setWeight(QFont.Bold)
        fm = QFontMetrics(f)
        txt = initials(card.name)
        p.setFont(f)
        p.setPen(QColor(0, 0, 0, 170))
        tx = c.x() - fm.horizontalAdvance(txt) / 2
        ty = self._base(rect.top(), rect.height(), fm)
        p.drawText(QPointF(tx + 1, ty + 1), txt)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QPointF(tx, ty), txt)

    def _draw_item(self, p: QPainter, it: Item, hovered: bool) -> None:
        rect = it.rect
        pm = self.icon_pixmap(it.card, it.size)
        if pm is not None:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 120))
            p.drawRoundedRect(rect, self.u(5), self.u(5))
            w, h = pm.width() / pm.devicePixelRatio(), pm.height() / pm.devicePixelRatio()
            p.drawPixmap(QPointF(rect.center().x() - w / 2, rect.center().y() - h / 2), pm)
        else:
            self._draw_fallback(p, rect, it.card)
        if hovered:
            p.setPen(QPen(QColor(255, 255, 255, 230), max(1.5, self.u(2))))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), self.u(6), self.u(6))

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing
                         | QPainter.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.transparent)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        W, H = self.width(), self.height()
        r = self.u(8)
        p.setPen(Qt.NoPen)
        p.setBrush(BG)
        p.drawRoundedRect(QRectF(0, 0, W, H), r, r)

        pad = self.u(PAD)
        head = "Гемы" + (f" · ур {self.level}" if self.level is not None else "")
        self._text(p, pad, self._base(0, self.u(HEADER_H), self.m_head), head, self.f_head,
                   QColor(255, 255, 255))
        # thin separator under the header
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawLine(QPointF(pad, self.u(HEADER_H) - 2), QPointF(W - pad, self.u(HEADER_H) - 2))

        if not self.rows:
            self._text(p, pad, self._base(self.u(HEADER_H), self.u(34), self.m_foot), "—",
                       self.f_foot, QColor(255, 255, 255), 0.6)

        # rows: name under the skill icon, chevron between skill and supports
        i = 0
        y = self.u(HEADER_H) + (0 if self.rows else self.u(34))
        for row in self.rows:
            sk_item = self._items[i]
            i += 1 + len(row.supports)
            name = elide(row.skill.name, self.m_small, self.u(SKILL_COL))
            nw = self.m_small.horizontalAdvance(name)
            cx = pad + self.u(SKILL_COL) / 2
            self._text(p, cx - nw / 2, self._base(sk_item.rect.bottom() + self.u(3), self.u(15), self.m_small),
                       name, self.f_small, QColor(255, 255, 255), 0.85)
            if row.supports:
                ax = pad + self.u(SKILL_COL) + self.u(ARROW_W) / 2
                ay = sk_item.rect.center().y()
                chev = QPainterPath()
                chev.moveTo(ax - self.u(3), ay - self.u(6))
                chev.lineTo(ax + self.u(3), ay)
                chev.lineTo(ax - self.u(3), ay + self.u(6))
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(0, 0, 0, 200), self.u(4), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPath(chev)
                p.setPen(QPen(QColor(255, 255, 255, 190), self.u(2), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPath(chev)
            y += self.u(ROW_H + ROW_GAP)
        for it in self._items:
            self._draw_item(p, it, it == self._hover)

        # footer: copy flash (palette aware) or a dim hint
        fy = H - self.u(FOOTER_H)
        base = self._base(fy, self.u(FOOTER_H), self.m_foot)
        if self._flash:
            pal = theme.palette(self.config.get("palette"))
            col = QColor(*pal["ahead"])
            self._text(p, pad, base, elide(self._flash[0], self.m_foot, W - 2 * pad), self.f_foot, col)
        elif self.rows:
            self._text(p, pad, base, "клик — копировать имя", self.f_foot, QColor(255, 255, 255), 0.45)
        p.end()
