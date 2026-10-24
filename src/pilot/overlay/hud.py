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
from . import theme
from .fmt import (act_label, details_lines, elide, format_time, level_text, pill_style,
                  progress_segments, step_parts, strip_warn_glyph, zone_pill)
from .icons import draw_icon, kind_color, toast_color, toast_icon
from .toasts import ToastStack

log = logging.getLogger(__name__)

BASE_W = 560          # px at scale 1.0
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
    "palette": "default",     # "default" | "colorblind"
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
        self.f3 = QFont("Segoe UI")           # pills
        self.f3.setPixelSize(max(8, round(13 * s)))
        self.f3.setWeight(QFont.DemiBold)
        self.f3.setStyleStrategy(QFont.PreferAntialias)
        self.m3 = QFontMetrics(self.f3)

    def u(self, n: float) -> float:
        return n * self.scale

    @property
    def width_px(self) -> int:
        return round(BASE_W * self.scale)

    def _toast_items(self, now: float):
        return self.toasts.visible(now)

    def _bar_h(self) -> float:
        return self.u(6) * 2 + self.u(28) + self.u(10) + self.u(22)

    def _toast_width(self, text: str) -> float:
        return min(self.width_px, self.m2.horizontalAdvance(text) + self.u(16) + self.u(8) + self.u(30))

    def _geometry(self, now: float):
        """Return (total_height, bar_rect, details_rect|None, [toast_rects])."""
        W = self.width_px
        bar_h = self._bar_h()
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
            tw = self._toast_width(toast.text)
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

    # ------------------------------------------------------------------ bar layout
    def _tab_w(self, text: str, fm: QFontMetrics) -> float:
        """Width with tabular digits: every digit takes the widest digit's cell."""
        cell = max(fm.horizontalAdvance(str(d)) for d in range(10))
        return sum(cell if c.isdigit() else fm.horizontalAdvance(c) for c in text)

    def _draw_tab(self, p, x, base_y, text, font, fm, color, alpha=1.0) -> None:
        cell = max(fm.horizontalAdvance(str(d)) for d in range(10))
        for c in text:
            adv = fm.horizontalAdvance(c)
            if c.isdigit():
                self._text(p, x + (cell - adv) / 2, base_y, c, font, color, alpha)
                x += cell
            else:
                self._text(p, x, base_y, c, font, color, alpha)
                x += adv

    def _base(self, top: float, h: float, fm: QFontMetrics) -> float:
        return top + h * 0.5 + fm.ascent() * 0.5 - fm.descent() * 0.5

    def bar_layout(self, st: HudState) -> dict:
        """All positions of the two-line bar (also used by tests to check nothing clips)."""
        W = self.width_px
        padx, pad_y, row1, row2 = self.u(12), self.u(6), self.u(28), self.u(22)
        pal_name = self.config.get("palette")
        L: dict = {"W": W, "padx": padx}
        col = max(self.m1.horizontalAdvance("A4"), self.m1.horizontalAdvance("И3")) + self.u(10)
        isz = self.u(18)
        L["label"] = act_label(st.act, None)
        L["base1"] = self._base(pad_y, row1, self.m1)
        L["icon1"] = QRectF(padx + col, pad_y + (row1 - isz) / 2, isz, isz)
        name_x = padx + col + isz + self.u(7)
        L["name_x"] = name_x
        timer_txt = format_time(st.run_time_s)
        timer_w = max(self._tab_w("8:88:88", self.m1), self._tab_w(timer_txt, self.m1))
        L["timer_txt"] = timer_txt
        L["timer_x"] = W - padx - self._tab_w(timer_txt, self.m1)
        timer_left = W - padx - timer_w
        L["pill"] = pill_style(st.split_delta_s, pal_name)
        right = timer_left - self.u(10)
        if L["pill"]:
            pw = self._tab_w(L["pill"].text, self.m3) + self.u(14)
            ph = self.u(20)
            L["pill_rect"] = QRectF(right - pw, pad_y + (row1 - ph) / 2, pw, ph)
            right = right - pw - self.u(10)
        kind, name = step_parts(st.step_short, st.step_kind)
        L["kind"] = kind
        L["name"] = elide(name, self.m1, right - name_x)
        L["name_right"] = right
        # progress bar
        L["prog"] = QRectF(padx, pad_y + row1 + self.u(3), W - 2 * padx, self.u(4))
        # line 2
        top2 = pad_y + row1 + self.u(10)
        L["base2"] = self._base(top2, row2, self.m2)
        L["icon2"] = QRectF(padx + col + (isz - self.u(14)) / 2, top2 + (row2 - self.u(14)) / 2,
                            self.u(14), self.u(14))
        if st.warn:
            L["warn"] = elide(strip_warn_glyph(st.warn), self.m2, W - padx - name_x)
            return L
        r = W - padx
        zp = zone_pill(st.area_level, st.char_level)
        L["zone"] = zp
        if zp:
            zw = self.m3.horizontalAdvance(zp.text) + self.u(14)
            zh = self.u(18)
            L["zone_rect"] = QRectF(r - zw, top2 + (row2 - zh) / 2, zw, zh)
            r -= zw + self.u(8)
        lv = level_text(st.char_level)
        L["lv"] = lv
        if lv:
            lw = self.m2.horizontalAdvance(lv)
            L["lv_x"] = r - lw
            r -= lw + self.u(12)
        nkind, nname = step_parts(st.next_short, st.next_kind)
        L["nkind"] = nkind
        L["nname"] = elide(nname, self.m2, r - name_x) if nname else ""
        L["nname_right"] = r
        return L

    def _pill(self, p, rect: QRectF, text: str, fg, bg, font, fm, tab=False) -> None:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(*bg))
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.setFont(font)
        p.setPen(QColor(*fg))
        base = self._base(rect.top(), rect.height(), fm)
        w = self._tab_w(text, fm) if tab else fm.horizontalAdvance(text)
        x = rect.left() + (rect.width() - w) / 2
        if tab:
            cell = max(fm.horizontalAdvance(str(d)) for d in range(10))
            for c in text:
                adv = fm.horizontalAdvance(c)
                if c.isdigit():
                    p.drawText(QPointF(x + (cell - adv) / 2, base), c)
                    x += cell
                else:
                    p.drawText(QPointF(x, base), c)
                    x += adv
        else:
            p.drawText(QPointF(x, base), text)

    def _progress(self, p, rect: QRectF, st: HudState) -> None:
        pal = theme.palette(self.config.get("palette"))
        done_col = QColor(*pal["ahead"])
        gap = self.u(2)
        rad = rect.height() / 2
        p.setPen(Qt.NoPen)
        for s in progress_segments(st.progress, st.split_marks):
            ax = rect.left() + s.a * rect.width() + (gap / 2 if s.a > 0 else 0)
            bx = rect.left() + s.b * rect.width() - (gap / 2 if s.b < 1 else 0)
            seg = QRectF(ax, rect.top(), max(1.0, bx - ax), rect.height())
            p.setBrush(QColor(255, 255, 255, 46))
            p.drawRoundedRect(seg, rad, rad)
            if s.state == "done":
                p.setBrush(done_col)
                p.drawRoundedRect(seg, rad, rad)
            elif s.state == "current" and s.frac > 0:
                p.setBrush(QColor(238, 238, 238))
                p.drawRoundedRect(QRectF(seg.left(), seg.top(), max(rad * 2, seg.width() * s.frac),
                                         seg.height()), rad, rad)
        prog = min(1.0, max(0.0, st.progress or 0.0))
        tw, th = max(2.0, self.u(2.5)), rect.height() + self.u(6)
        tick = QRectF(rect.left() + prog * rect.width() - tw / 2, rect.center().y() - th / 2, tw, th)
        p.setBrush(QColor(0, 0, 0, 200))
        p.drawRoundedRect(tick.adjusted(-1, -1, 1, 1), 1.5, 1.5)
        p.setBrush(QColor(255, 255, 255))
        p.drawRoundedRect(tick, 1, 1)

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

        L = self.bar_layout(st)
        padx, W = L["padx"], L["W"]
        # ---- line 1: act | icon name | delta pill | timer
        self._text(p, padx, L["base1"], L["label"], self.f1, WHITE)
        if L["kind"]:
            draw_icon(p, L["kind"], L["icon1"], kind_color(L["kind"]))
        self._text(p, L["name_x"], L["base1"], L["name"], self.f1, WHITE)
        pill = L["pill"]
        if pill:
            self._pill(p, L["pill_rect"], pill.text, pill.fg, pill.bg, self.f3, self.m3, tab=True)
        self._draw_tab(p, L["timer_x"], L["base1"], L["timer_txt"], self.f1, self.m1, WHITE)
        # ---- progress
        self._progress(p, L["prog"], st)
        # ---- line 2
        if st.warn:
            draw_icon(p, "alert", L["icon2"], theme.YELLOW)
            self._text(p, L["name_x"], L["base2"], L["warn"], self.f2, YELLOW)
        else:
            if L["nname"]:
                if L["nkind"]:
                    draw_icon(p, L["nkind"], L["icon2"], kind_color(L["nkind"]), 0.75)
                self._text(p, L["name_x"], L["base2"], L["nname"], self.f2, WHITE, 0.7)
            if L["lv"]:
                self._text(p, L["lv_x"], L["base2"], L["lv"], self.f2, WHITE, 0.85)
            zp = L["zone"]
            if zp:
                fg, bg = theme.ZONE_AMBER if zp.amber else theme.ZONE_NEUTRAL
                self._pill(p, L["zone_rect"], zp.text, fg, bg, self.f3, self.m3)
        # ---- details panel
        if det is not None:
            p.setPen(Qt.NoPen)
            p.setBrush(BG)
            p.drawRoundedRect(det, r, r)
            lh = self.u(22)
            y = det.top() + self.u(8)
            for i, line in enumerate(self._details):
                by = self._base(y, lh, self.m2)
                self._text(p, padx, by, elide(line, self.m2, W - 2 * padx), self.f2, WHITE,
                           1.0 if i else 0.75)
                y += lh
        # ---- toasts
        isz = self.u(16)
        for (toast, a), rect in zip(self._toast_items(now), trects):
            p.setOpacity(dim * a)
            p.setPen(Qt.NoPen)
            p.setBrush(BG)
            p.drawRoundedRect(rect, r, r)
            draw_icon(p, toast_icon(toast.kind),
                      QRectF(rect.left() + self.u(12), rect.center().y() - isz / 2, isz, isz),
                      toast_color(toast.kind))
            tx = rect.left() + self.u(12) + isz + self.u(8)
            txt = elide(toast.text, self.m2, rect.right() - self.u(14) - tx)
            self._text(p, tx, self._base(rect.top(), rect.height(), self.m2), txt, self.f2,
                       YELLOW if toast.kind == "warn" else WHITE)
        # ---- edit hint: dashed outline only
        if self._edit:
            p.setOpacity(1.0)
            p.setPen(QPen(WHITE, 1.5, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(bar.adjusted(1, 1, -1, -1), r, r)
        p.end()
