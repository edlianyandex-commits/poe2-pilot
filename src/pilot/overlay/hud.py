"""The HUD window: one painted, frameless, click-through bar (see docs/UX.md)."""
from __future__ import annotations

import logging
import time
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath,
                           QPen)
from PySide6.QtWidgets import QWidget

from pilot.contracts import HudState

from . import winapi
from .fmt import (act_label, delta_kind, details_lines, elide, format_delta, format_time,
                  warn_text)
from .toasts import ToastStack

log = logging.getLogger(__name__)

BASE_W = 520          # px at scale 1.0
BASE_FONT = 18        # px, line 1
SUB_FONT = 15         # px, line 2 / details
SCALE_MIN, SCALE_MAX = 0.75, 2.0

WHITE = QColor(255, 255, 255)
GREEN = QColor(92, 240, 120)
RED = QColor(255, 92, 92)
YELLOW = QColor(255, 216, 74)
OUTLINE = QColor(0, 0, 0, 215)
BG = QColor(0, 0, 0, 140)   # ~55 %

DEFAULT_CONFIG = {
    "hide_when_unfocused": True,
    "game_exes": list(winapi.GAME_EXES),
    "dim_opacity": 0.4,
    "scale": 1.0,
    "x": None,
    "y": None,
    "details_provider": None,
    "on_save": None,
}


def clamp_scale(v: float) -> float:
    return max(SCALE_MIN, min(SCALE_MAX, round(float(v), 2)))


class HudWindow(QWidget):
    def __init__(self, config: dict | None = None, clock: Callable[[], float] = time.monotonic):
        super().__init__(None)
        self.config = config if config is not None else {}
        for k, v in DEFAULT_CONFIG.items():
            self.config.setdefault(k, v)
        self._clock = clock
        self.state = HudState()
        self.toasts = ToastStack()
        self.scale = clamp_scale(self.config.get("scale") or 1.0)
        self._details_on = False
        self._details: list[str] = []
        self._edit = False
        self._user_hidden = False
        self._drag_off: QPointF | None = None

        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
                            | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowTitle("PoE2 Pilot")

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(33)
        self._fade_timer.timeout.connect(self._tick)

        self._rebuild_fonts()
        self._relayout(initial=True)

    # ------------------------------------------------------------------ fonts / layout
    def _rebuild_fonts(self) -> None:
        s = self.scale
        self.f1 = QFont("Segoe UI")
        self.f1.setPixelSize(max(8, round(BASE_FONT * s)))
        self.f1.setWeight(QFont.DemiBold)
        self.f2 = QFont("Segoe UI")
        self.f2.setPixelSize(max(8, round(SUB_FONT * s)))
        for f in (self.f1, self.f2):
            f.setStyleStrategy(QFont.PreferAntialias)
        self.m1 = QFontMetrics(self.f1)
        self.m2 = QFontMetrics(self.f2)

    def u(self, n: float) -> float:
        return n * self.scale

    @property
    def width_px(self) -> int:
        return round(BASE_W * self.scale)

    def _toast_items(self, now: float):
        return self.toasts.visible(now)

    def _geometry(self, now: float):
        """Return (total_height, bar_rect, details_rect|None, [toast_rects])."""
        W = self.width_px
        pad_y, row1, row2 = self.u(6), self.u(28), self.u(22)
        bar_h = pad_y * 2 + row1 + row2
        y = bar_h
        bar = QRectF(0, 0, W, bar_h)
        det = None
        if self._details_on and self._details:
            y += self.u(6)
            lh = self.u(22)
            dh = self.u(8) * 2 + lh * len(self._details)
            det = QRectF(0, y, W, dh)
            y += dh
        trects = []
        for toast, _a in self._toast_items(now):
            y += self.u(6)
            th = self.u(30)
            tw = min(W, self.m2.horizontalAdvance(toast.text) + self.u(32))
            trects.append(QRectF((W - tw) / 2, y, tw, th))
            y += th
        return int(y + 1), bar, det, trects

    def _relayout(self, initial: bool = False) -> None:
        old_w = self.width()
        h, *_ = self._geometry(self._clock())
        w = self.width_px
        self.setFixedSize(w, h)
        if initial:
            self._place()
        elif old_w and old_w != w:
            self.move(self.x() + (old_w - w) // 2, self.y())

    def _place(self) -> None:
        x, y = self.config.get("x"), self.config.get("y")
        if x is not None and y is not None:
            self.move(int(x), int(y))
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.center().x() - self.width() // 2, geo.top() + 12)

    # ------------------------------------------------------------------ state in
    def set_state(self, state: HudState) -> None:
        now = self._clock()
        changed = state != self.state
        self.state = state
        self.toasts.update(state.toasts, now)
        if self._details_on:
            self._refresh_details()
        if changed or self.toasts.active():
            self._sync_timer()
            self._relayout()
            self.update()

    def push_toast(self, toast) -> None:
        self.toasts.push(toast, self._clock())
        self._sync_timer()
        self._relayout()
        self.update()

    def _sync_timer(self) -> None:
        if self.toasts.active():
            if not self._fade_timer.isActive():
                self._fade_timer.start()
        elif self._fade_timer.isActive():
            self._fade_timer.stop()

    def _tick(self) -> None:
        if not self.toasts.active():
            self._fade_timer.stop()
        self._relayout()
        self.update()

    # ------------------------------------------------------------------ details
    def _refresh_details(self) -> None:
        extra: list[str] = []
        prov = self.config.get("details_provider")
        if prov:
            try:
                extra = list(prov() or [])
            except Exception:
                log.exception("details_provider failed")
        self._details = details_lines(self.state, extra)

    def set_details_visible(self, on: bool) -> None:
        self._details_on = bool(on)
        if on:
            self._refresh_details()
        self._relayout()
        self.update()

    # ------------------------------------------------------------------ visibility
    def should_be_visible(self, fg=None, *, check: bool = True) -> bool:
        if self._edit:
            return True
        if self._user_hidden:
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
        elif not want and self.isVisible():
            self.hide()
        elif want:
            winapi.keep_topmost(self._hwnd())

    def toggle_hidden(self) -> None:
        self._user_hidden = not self._user_hidden
        self.refresh_visibility()

    def _hwnd(self) -> int:
        if QGuiApplication.platformName() != "windows":
            return 0
        return int(self.winId())

    def _apply_native(self) -> None:
        winapi.make_click_through(self._hwnd(), interactive=self._edit)

    # ------------------------------------------------------------------ edit mode
    @property
    def edit_mode(self) -> bool:
        return self._edit

    def toggle_edit(self) -> None:
        if self._edit:
            self._edit = False
            self.config["x"], self.config["y"] = self.x(), self.y()
            self.config["scale"] = self.scale
            cb = self.config.get("on_save")
            if cb:
                try:
                    cb(self.config)
                except Exception:
                    log.exception("on_save failed")
        else:
            self._edit = True
        self._drag_off = None
        was_visible = self.isVisible()
        pos = self.pos()
        self.setWindowFlag(Qt.WindowTransparentForInput, not self._edit)
        if was_visible:
            self.show()
            self.move(pos)
            self._apply_native()
        self.refresh_visibility()
        self.update()

    def mousePressEvent(self, e):  # noqa: N802
        if self._edit and e.button() == Qt.LeftButton:
            self._drag_off = e.globalPosition() - QPointF(self.pos())

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._edit and self._drag_off is not None:
            p = e.globalPosition() - self._drag_off
            self.move(int(p.x()), int(p.y()))

    def mouseReleaseEvent(self, e):  # noqa: N802
        self._drag_off = None

    def wheelEvent(self, e):  # noqa: N802
        if not self._edit:
            return
        steps = e.angleDelta().y() / 120.0
        self.set_scale(self.scale + 0.05 * steps)

    def set_scale(self, v: float) -> None:
        v = clamp_scale(v)
        if v == self.scale:
            return
        self.scale = v
        self._rebuild_fonts()
        self._relayout()
        self.update()

    # ------------------------------------------------------------------ painting
    def _text(self, p: QPainter, x: float, base_y: float, text: str, font: QFont,
              color: QColor, alpha: float = 1.0) -> None:
        if not text:
            return
        path = QPainterPath()
        path.addText(x, base_y, font, text)
        pen = QPen(QColor(OUTLINE.red(), OUTLINE.green(), OUTLINE.blue(), int(OUTLINE.alpha() * alpha)),
                   max(2.0, self.u(3.0)))
        pen.setJoinStyle(Qt.RoundJoin)
        p.strokePath(path, pen)
        c = QColor(color)
        c.setAlphaF(c.alphaF() * alpha)
        p.fillPath(path, c)

    def paintEvent(self, _event):  # noqa: N802
        now = self._clock()
        st = self.state
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.transparent)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        dim = 1.0 if (st.running or self._edit) else float(self.config.get("dim_opacity", 0.4))
        p.setOpacity(dim)

        _h, bar, det, trects = self._geometry(now)
        r = self.u(8)
        p.setPen(Qt.NoPen)
        p.setBrush(BG)
        p.drawRoundedRect(bar, r, r)

        padx = self.u(12)
        W = bar.width()
        # ---- line 1
        base1 = self.u(6) + self.u(28) * 0.5 + self.m1.ascent() * 0.5 - self.m1.descent() * 0.5
        col_w = self.m1.horizontalAdvance("И3 · 88") + self.u(16)
        label = act_label(st.act, st.area_level)
        self._text(p, padx, base1, label, self.f1, WHITE)
        timer_txt = format_time(st.run_time_s)
        tw = self.m1.horizontalAdvance("0:00:00") + self.u(2)
        self._text(p, W - padx - self.m1.horizontalAdvance(timer_txt), base1, timer_txt, self.f1, WHITE)
        step_x = padx + col_w
        step_w = (W - padx - tw) - step_x - self.u(12)
        step = elide(st.step_short or "", self.m1, step_w)
        self._text(p, step_x, base1, step, self.f1, WHITE)
        # ---- line 2
        base2 = self.u(6) + self.u(28) + self.u(22) * 0.5 + self.m2.ascent() * 0.5 - self.m2.descent() * 0.5
        delta_txt = format_delta(st.split_delta_s)
        dw = self.m2.horizontalAdvance(delta_txt) if delta_txt else 0
        avail = W - padx - step_x - (dw + self.u(14) if delta_txt else 0)
        if st.warn:
            self._text(p, step_x, base2, elide(warn_text(st.warn), self.m2, avail), self.f2, YELLOW)
        else:
            if st.next_short:
                nxt = elide("затем: " + st.next_short, self.m2, avail)
                self._text(p, step_x, base2, nxt, self.f2, WHITE, 0.7)
            if delta_txt:
                kind = delta_kind(st.split_delta_s)
                col = GREEN if kind == "ahead" else RED if kind == "behind" else WHITE
                self._text(p, W - padx - dw, base2, delta_txt, self.f2, col)
        # ---- details panel
        if det is not None:
            p.setPen(Qt.NoPen)
            p.setBrush(BG)
            p.drawRoundedRect(det, r, r)
            lh = self.u(22)
            y = det.top() + self.u(8)
            for i, line in enumerate(self._details):
                by = y + lh * 0.5 + self.m2.ascent() * 0.5 - self.m2.descent() * 0.5
                f = self.f2
                self._text(p, padx, by, elide(line, self.m2, W - 2 * padx), f, WHITE, 1.0 if i else 0.75)
                y += lh
        # ---- toasts
        for (toast, a), rect in zip(self._toast_items(now), trects):
            p.setOpacity(dim * a)
            p.setPen(Qt.NoPen)
            p.setBrush(BG)
            p.drawRoundedRect(rect, r, r)
            by = rect.top() + rect.height() * 0.5 + self.m2.ascent() * 0.5 - self.m2.descent() * 0.5
            txt = elide(toast.text, self.m2, rect.width() - self.u(24))
            self._text(p, rect.left() + self.u(16), by, txt, self.f2,
                       YELLOW if toast.kind == "warn" else WHITE)
        # ---- edit hint: dashed outline only
        if self._edit:
            p.setOpacity(1.0)
            pen = QPen(WHITE, 1.5, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(bar.adjusted(1, 1, -1, -1), r, r)
        p.end()
