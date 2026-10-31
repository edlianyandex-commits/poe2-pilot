"""Passive tree window (Alt+T): what to take next.

Draws a TreeView (planner output): thin edges, circles sized by node kind, colored by state
(taken = gold, next = bright with its order number, planned = dim outline, offplan = red
outline, other = faint). Same window behaviour as the gem window: frameless, on top, never
takes focus, not click-through, draggable by the header. Nothing is sent to the game.
"""
from __future__ import annotations

import logging
import math
import statistics
from typing import Callable, NamedTuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import QWidget

from pilot.contracts import TreeNodeView, TreeView
from pilot.i18n import tr

from . import theme, winapi
from .fmt import elide
from .gems_window import _Tip
from .hud import clamp_scale

log = logging.getLogger(__name__)

PAD = 12
HEADER_H = 34
FOOTER_H = 28
MAP_W, MAP_H = 400, 280
STRIP_W = 176
STRIP_GAP = 10
LIST_LINE_H = 26
MAX_LIST = 5
ZOOM_MIN, ZOOM_MAX = 0.02, 3.0
READABLE_EDGE_PX = 26.0       # when fitting, never zoom out below this spacing between nodes
                              # (next nodes are >= 9 px in radius and carry an order badge)
FLASH_S = 1.0
PULSE_PERIOD_S = 1.4

BG = QColor(0, 0, 0, 140)
OUTLINE = QColor(0, 0, 0, 215)

GOLD = (255, 205, 90)
NEXT = (110, 224, 255)
OTHER = (160, 160, 160)
PLANNED = (214, 214, 214)

# radius in px at ui scale 1.0
RADIUS = {"small": 5.0, "attribute": 7.0, "notable": 10.0, "keystone": 14.0, "jewel": 9.0, "start": 9.0}
KIND_LABEL = {"small": "Малый", "attribute": "Атрибут", "notable": "Значимый",
              "keystone": "Ключевой", "jewel": "Самоцвет", "start": "Старт"}
NEXT_MIN_RADIUS = 9.0         # room for the order number
DRAW_ORDER = {"other": 0, "planned": 1, "offplan": 2, "taken": 3, "next": 4}


# ---------------------------------------------------------------- pure helpers
def node_colors(state: str, palette: str | None = "default") -> dict:
    """{'line': rgba, 'fill': rgba|None, 'width': float} for a node state."""
    pal = theme.palette(palette)
    if state == "taken":
        return {"line": (*GOLD, 255), "fill": (*GOLD, 235), "width": 1.5}
    if state == "next":
        return {"line": (255, 255, 255, 255), "fill": (*NEXT, 245), "width": 1.8}
    if state == "planned":
        return {"line": (*PLANNED, 170), "fill": (255, 255, 255, 22), "width": 1.5}
    if state == "offplan":
        return {"line": (*pal["behind"], 255), "fill": (*pal["behind"], 40), "width": 2.0}
    return {"line": (*OTHER, 85), "fill": (*OTHER, 38), "width": 1.0}


def node_radius(node: TreeNodeView) -> float:
    r = RADIUS.get(node.kind, RADIUS["small"])
    if node.state == "next" and node.order is not None:
        r = max(r, NEXT_MIN_RADIUS)
    return r


def order_label(node: TreeNodeView) -> str:
    return str(node.order) if node.state == "next" and node.order is not None else ""


def next_nodes(view: TreeView | None) -> list[TreeNodeView]:
    if not view:
        return []
    ns = [n for n in view.nodes if n.state == "next"]
    return sorted(ns, key=lambda n: (n.order is None, n.order or 0, n.name))


def list_line(node: TreeNodeView) -> str:
    s = f"{node.order} {node.name}" if node.order is not None else node.name
    if node.level is not None:
        s += tr(" · ур {level}", level=node.level)
    return s


def tip_text(node: TreeNodeView) -> tuple[str, str, str]:
    """(title, kind line, stats body)."""
    kind = tr(KIND_LABEL.get(node.kind, node.kind))
    if node.level is not None:
        kind += tr(" · ур {level}", level=node.level)
    return node.name, kind, "\n".join(node.stats)


class Viewport:
    """Tree <-> map-pixel transform. Tree y grows downwards, like the screen."""

    def __init__(self, w: float, h: float):
        self.w, self.h = float(w), float(h)
        self.cx = self.cy = 0.0
        self.zoom = 1.0

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        return (self.w / 2 + (x - self.cx) * self.zoom, self.h / 2 + (y - self.cy) * self.zoom)

    def to_tree(self, sx: float, sy: float) -> tuple[float, float]:
        return (self.cx + (sx - self.w / 2) / self.zoom, self.cy + (sy - self.h / 2) / self.zoom)

    def zoom_at(self, sx: float, sy: float, factor: float, zmin: float = ZOOM_MIN,
                zmax: float = ZOOM_MAX) -> None:
        """Zoom keeping the tree point under (sx, sy) fixed."""
        tx, ty = self.to_tree(sx, sy)
        self.zoom = max(zmin, min(zmax, self.zoom * factor))
        self.cx = tx - (sx - self.w / 2) / self.zoom
        self.cy = ty - (sy - self.h / 2) / self.zoom

    def pan(self, dx: float, dy: float) -> None:
        self.cx -= dx / self.zoom
        self.cy -= dy / self.zoom

    def fit(self, points, focus=None, margin: float = 24.0, zmin: float = ZOOM_MIN,
            zmax: float = ZOOM_MAX) -> None:
        """Show all `points`, centred on `focus` (default: their bbox centre)."""
        pts = list(points)
        if not pts:
            self.cx = self.cy = 0.0
            self.zoom = 1.0
            return
        if focus is None:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            focus = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        fx, fy = focus
        hx = max(abs(p[0] - fx) for p in pts)
        hy = max(abs(p[1] - fy) for p in pts)
        zx = (self.w / 2 - margin) / hx if hx > 1e-9 else zmax
        zy = (self.h / 2 - margin) / hy if hy > 1e-9 else zmax
        self.zoom = max(zmin, min(zmax, zx, zy))
        self.cx, self.cy = fx, fy


def median_edge_len(view: TreeView) -> float | None:
    pos = {n.sid: (n.x, n.y) for n in view.nodes}
    ls = [math.dist(pos[a], pos[b]) for a, b in view.edges if a in pos and b in pos]
    ls = [l for l in ls if l > 0]
    return statistics.median(ls) if ls else None


def fit_viewport(vp: Viewport, view: TreeView, margin: float = 24.0) -> None:
    """Fit taken + next + planned nodes, with the next nodes' centroid in the middle."""
    shown = [n for n in view.nodes if n.state in ("taken", "next", "planned")] or list(view.nodes)
    nxt = [n for n in view.nodes if n.state == "next"]
    focus = None
    if nxt:
        focus = (sum(n.x for n in nxt) / len(nxt), sum(n.y for n in nxt) / len(nxt))
    zmin = ZOOM_MIN
    med = median_edge_len(view)
    if med:
        zmin = max(zmin, min(READABLE_EDGE_PX / med, ZOOM_MAX))
    vp.fit([(n.x, n.y) for n in shown], focus, margin, zmin, ZOOM_MAX)


class _Hit(NamedTuple):
    node: TreeNodeView
    pos: tuple[float, float]       # map-local px
    r: float


class TreeWindow(QWidget):
    icon_ready = Signal()

    def __init__(self, config: dict | None = None, clock: Callable[[], float] | None = None):
        super().__init__(None)
        import time
        self.config = config if config is not None else {}
        self._clock = clock or time.monotonic
        saved = self.config.get("tree_window") or {}
        self.scale = clamp_scale(saved.get("scale") or 1.0)
        self.user_zoom = float(saved.get("zoom") or 1.0)       # multiplier on top of the fit zoom
        self.view: TreeView | None = None
        self._nodes: dict[str, TreeNodeView] = {}
        self._next_key: tuple = ()
        self.vp = Viewport(MAP_W * self.scale, MAP_H * self.scale)
        self._fit_zoom = 1.0
        self._open = False
        self._hover_sid: str | None = None
        self._hover_from_list = False
        self._flash: str | None = None
        self._drag_off: QPointF | None = None
        self._moved = False
        self._pan_last: QPointF | None = None
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
        self.setWindowTitle("PoE2 Pilot · tree")

        self.tip = _Tip()
        self.icon_ready.connect(self._on_icon_ready)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh)
        self._pulse = QTimer(self)
        self._pulse.setInterval(60)
        self._pulse.timeout.connect(self.update)
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._end_flash)

        self._rebuild_fonts()
        self._resize(initial=True)

    # ------------------------------------------------------------------ geometry
    def u(self, n: float) -> float:
        return n * self.scale

    def _rebuild_fonts(self) -> None:
        s = self.scale
        self.f_head = QFont("Segoe UI")
        self.f_head.setPixelSize(max(8, round(17 * s)))
        self.f_head.setWeight(QFont.DemiBold)
        self.f_list = QFont("Segoe UI")
        self.f_list.setPixelSize(max(8, round(13 * s)))
        self.f_foot = QFont("Segoe UI")
        self.f_foot.setPixelSize(max(8, round(12.5 * s)))
        self.f_num = QFont("Segoe UI")
        self.f_num.setPixelSize(max(8, round(12 * s)))
        self.f_num.setWeight(QFont.Bold)
        for f in (self.f_head, self.f_list, self.f_foot, self.f_num):
            f.setStyleStrategy(QFont.PreferAntialias)
        self.m_head, self.m_list, self.m_foot, self.m_num = (
            QFontMetrics(f) for f in (self.f_head, self.f_list, self.f_foot, self.f_num))

    def map_rect(self) -> QRectF:
        return QRectF(self.u(PAD), self.u(HEADER_H), self.u(MAP_W), self.u(MAP_H))

    def strip_rect(self) -> QRectF:
        m = self.map_rect()
        return QRectF(m.right() + self.u(STRIP_GAP), m.top(), self.u(STRIP_W), m.height())

    def center_button_rect(self) -> QRectF:
        m = self.map_rect()
        w, h = self.u(52), self.u(20)
        return QRectF(m.right() - w - self.u(6), m.top() + self.u(6), w, h)

    def _resize(self, initial: bool = False) -> None:
        W = self.u(PAD + MAP_W + STRIP_GAP + STRIP_W + PAD)
        H = self.u(HEADER_H + MAP_H + FOOTER_H)
        self.setFixedSize(int(math.ceil(W)), int(math.ceil(H)))
        self.vp.w, self.vp.h = self.u(MAP_W), self.u(MAP_H)
        if initial:
            self._place()

    def _place(self) -> None:
        saved = self.config.get("tree_window") or {}
        if saved.get("x") is not None and saved.get("y") is not None:
            self.move(int(saved["x"]), int(saved["y"]))
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.right() - self.width() - 24, geo.top() + 120)

    # ------------------------------------------------------------------ data
    def set_view(self, view: TreeView | None) -> None:
        if view == self.view:
            return
        self.view = view
        self._nodes = {n.sid: n for n in view.nodes} if view else {}
        if self._hover_sid not in self._nodes:
            self._hover_sid = None
            self.tip.hide()
        key = tuple((n.sid, n.order) for n in next_nodes(view))
        refit = key != self._next_key
        self._next_key = key
        self._resolve_icons()
        if refit:
            self.fit()
        self.update()

    def refresh(self) -> None:
        prov = self.config.get("tree_provider")
        if not prov:
            return
        try:
            self.set_view(prov())
        except Exception:
            log.exception("tree_provider failed")

    def fit(self) -> None:
        """Auto-fit taken + next + planned, next nodes centred; re-apply the user's zoom."""
        if not self.view or not self.view.nodes:
            return
        fit_viewport(self.vp, self.view, self.u(24))
        self._fit_zoom = self.vp.zoom
        self.vp.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self._fit_zoom * self.user_zoom))
        self.update()

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
        if not self.view:
            return
        cache = None
        for n in self.view.nodes:
            url = n.icon_url
            if not url or n.kind not in ("notable", "keystone") or self._paths.get(url):
                continue
            if cache is None:
                cache = self._get_cache()
                if cache is None:
                    return
            try:
                self._paths[url] = cache.get(url, self.icon_ready.emit)
            except Exception:
                log.exception("icon cache get failed")
                self._paths[url] = None

    def _on_icon_ready(self) -> None:
        self._resolve_icons()
        self._pm_cache.clear()
        self.update()

    def icon_pixmap(self, node: TreeNodeView, size: int) -> QPixmap | None:
        path = self._paths.get(node.icon_url or "")
        if not path:
            return None
        key = (path, size)
        if key not in self._pm_cache:
            pm = QPixmap(path)
            if pm.isNull():
                self._pm_cache[key] = None
            else:
                dpr = self.devicePixelRatioF()
                pm = pm.scaled(int(size * dpr), int(size * dpr), Qt.KeepAspectRatioByExpanding,
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
            self.fit()
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
            self._pulse.start()
        elif not want and self.isVisible():
            self.hide()
            self.tip.hide()
            self._timer.stop()
            self._pulse.stop()
        elif want:
            winapi.keep_topmost(self._hwnd())

    def _hwnd(self) -> int:
        if QGuiApplication.platformName() != "windows":
            return 0
        return int(self.winId())

    def _apply_native(self) -> None:
        winapi.make_click_through(self._hwnd(), interactive=True)   # receives hover and clicks

    # ------------------------------------------------------------------ hit testing
    def _hits(self) -> list[_Hit]:
        """Visible nodes with map-local positions, in draw order (last = on top)."""
        if not self.view:
            return []
        m = self.map_rect()
        out = []
        for n in sorted(self.view.nodes, key=lambda n: DRAW_ORDER.get(n.state, 0)):
            sx, sy = self.vp.to_screen(n.x, n.y)
            r = self.u(node_radius(n))
            if -r <= sx <= m.width() + r and -r <= sy <= m.height() + r:
                out.append(_Hit(n, (sx, sy), r))
        return out

    def node_at(self, pos) -> TreeNodeView | None:
        """Node under a widget-space point (map area only)."""
        m = self.map_rect()
        pt = QPointF(pos)
        if not m.contains(pt):
            return None
        mx, my = pt.x() - m.left(), pt.y() - m.top()
        for h in reversed(self._hits()):
            if math.hypot(mx - h.pos[0], my - h.pos[1]) <= h.r + self.u(3):
                return h.node
        return None

    def list_items(self) -> list[tuple[QRectF, TreeNodeView]]:
        s = self.strip_rect()
        return [(QRectF(s.left(), s.top() + self.u(4) + i * self.u(LIST_LINE_H), s.width(), self.u(LIST_LINE_H)), n)
                for i, n in enumerate(next_nodes(self.view)[:MAX_LIST])]

    def list_at(self, pos) -> TreeNodeView | None:
        pt = QPointF(pos)
        for rect, n in self.list_items():
            if rect.contains(pt):
                return n
        return None

    def node_screen_pos(self, sid: str) -> QPointF:
        """Widget-space centre of a node."""
        n = self._nodes[sid]
        m = self.map_rect()
        sx, sy = self.vp.to_screen(n.x, n.y)
        return QPointF(m.left() + sx, m.top() + sy)

    # ------------------------------------------------------------------ hover
    @property
    def hover_sid(self) -> str | None:
        return self._hover_sid

    def set_hover(self, node: TreeNodeView | None, from_list: bool = False) -> None:
        sid = node.sid if node else None
        if sid == self._hover_sid and from_list == self._hover_from_list:
            return
        self._hover_sid, self._hover_from_list = sid, from_list
        if node is None or from_list:
            self.tip.hide()
        else:
            title, kind, body = tip_text(node)
            self.tip.set_content(title, kind, body, self.scale)
            c = self.node_screen_pos(node.sid)
            gp = self.mapToGlobal(c.toPoint())
            r = int(self.u(node_radius(node)))
            x, y = gp.x() + r + int(self.u(8)), gp.y() + r + int(self.u(6))
            screen = self.screen() or QGuiApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                if x + self.tip.width() > geo.right():
                    x = gp.x() - r - int(self.u(8)) - self.tip.width()
                x = max(geo.left(), x)
                if y + self.tip.height() > geo.bottom():
                    y = gp.y() - r - int(self.u(6)) - self.tip.height()
            self.tip.move(x, y)
            self.tip.show()
        self.update()

    # ------------------------------------------------------------------ mouse
    def _header_rect(self) -> QRectF:
        return QRectF(0, 0, self.width(), self.u(HEADER_H))

    def mouseMoveEvent(self, e):  # noqa: N802
        pos = e.position()
        if self._drag_off is not None:
            p = e.globalPosition() - self._drag_off
            self.move(int(p.x()), int(p.y()))
            self._moved = True
            return
        if self._pan_last is not None:
            d = pos - self._pan_last
            self._pan_last = pos
            self.vp.pan(d.x(), d.y())
            self.update()
            return
        ln = self.list_at(pos)
        if ln is not None:
            self.set_hover(ln, from_list=True)
        else:
            self.set_hover(self.node_at(pos))

    def leaveEvent(self, _e):  # noqa: N802
        if self._drag_off is None:
            self.set_hover(None)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() != Qt.LeftButton:
            return
        pos = e.position()
        if self.center_button_rect().contains(pos):
            self.recenter()
            return
        n = self.node_at(pos) or self.list_at(pos)
        if n is not None:
            self.copy_name(n.name)
        elif self._header_rect().contains(pos):
            self._drag_off = e.globalPosition() - QPointF(self.pos())
            self._moved = False
            self.tip.hide()
        elif self.map_rect().contains(pos):
            self._pan_last = pos
            self.tip.hide()

    def mouseReleaseEvent(self, _e):  # noqa: N802
        self._pan_last = None
        if self._drag_off is not None:
            self._drag_off = None
            if self._moved:
                self._save()

    def mouseDoubleClickEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton and self.map_rect().contains(e.position()) \
                and self.node_at(e.position()) is None:
            self.recenter()

    def wheelEvent(self, e):  # noqa: N802
        steps = e.angleDelta().y() / 120.0
        pos = e.position()
        m = self.map_rect()
        if m.contains(pos):
            self.vp.zoom_at(pos.x() - m.left(), pos.y() - m.top(), 1.15 ** steps)
            self.user_zoom = self.vp.zoom / self._fit_zoom if self._fit_zoom else 1.0
            self._save()
            self.tip.hide()
            self.update()
        elif self._header_rect().contains(pos):
            self.set_scale(self.scale + 0.05 * steps)
            self._save()

    def recenter(self) -> None:
        self.user_zoom = 1.0
        self.fit()

    def set_scale(self, v: float) -> None:
        v = clamp_scale(v)
        if v == self.scale:
            return
        k = v / self.scale
        self.scale = v
        self.vp.zoom *= k              # keep what is shown the same
        self._fit_zoom *= k
        self._rebuild_fonts()
        self._pm_cache.clear()
        self._hover_sid = None
        self.tip.hide()
        self._resize()
        self.update()

    def _save(self) -> None:
        self.config["tree_window"] = {"x": self.x(), "y": self.y(), "scale": self.scale,
                                      "zoom": round(self.user_zoom, 4)}
        cb = self.config.get("on_save")
        if cb:
            try:
                cb(self.config)
            except Exception:
                log.exception("on_save failed")

    def copy_name(self, name: str) -> None:
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(name)
        self._flash = tr("Скопировано: {name}", name=name)
        self._flash_timer.start(int(FLASH_S * 1000))
        self.update()

    def _end_flash(self) -> None:
        self._flash = None
        self.update()

    @property
    def flash_text(self) -> str | None:
        return self._flash

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

    def _draw_node(self, p: QPainter, h: _Hit, highlighted: bool) -> None:
        n = h.node
        cols = node_colors(n.state, self.config.get("palette"))
        cx, cy = h.pos
        r = h.r
        line, fill = QColor(*cols["line"]), QColor(*cols["fill"])
        pen_w = self.u(cols["width"])
        p.setPen(QPen(QColor(0, 0, 0, 190), pen_w + self.u(2)))        # dark halo for busy backgrounds
        p.setBrush(Qt.NoBrush)
        self._shape(p, n, cx, cy, r)
        p.setPen(QPen(line, pen_w))
        p.setBrush(fill)
        self._shape(p, n, cx, cy, r)
        pm = self.icon_pixmap(n, int(r * 2)) if n.kind in ("notable", "keystone") else None
        if pm is not None:
            p.save()
            clip = QPainterPath()
            clip.addEllipse(QPointF(cx, cy), r - pen_w / 2, r - pen_w / 2)
            p.setClipPath(clip)
            w, hh = pm.width() / pm.devicePixelRatio(), pm.height() / pm.devicePixelRatio()
            p.drawPixmap(QPointF(cx - w / 2, cy - hh / 2), pm)
            p.restore()
            p.setPen(QPen(line, pen_w))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r, r)
        if n.kind == "start":
            p.setPen(QPen(line, pen_w))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r * 0.5, r * 0.5)
        label = order_label(n)
        if label:
            # badge on the node's upper-right edge: readable over icons and dark art
            br = max(self.u(7), self.m_num.height() * 0.62)
            bx, by = cx + r * 0.72, cy - r * 0.72
            p.setPen(QPen(QColor(0, 0, 0, 200), max(1.0, self.u(1.5))))
            p.setBrush(QColor(*node_colors("next", self.config.get("palette"))["fill"]))
            p.drawEllipse(QPointF(bx, by), br, br)
            p.setFont(self.f_num)
            tw = self.m_num.horizontalAdvance(label)
            p.setPen(QColor(8, 30, 44))
            p.drawText(QPointF(bx - tw / 2, self._base(by - br, 2 * br, self.m_num)), label)
        if highlighted:
            p.setPen(QPen(QColor(255, 255, 255, 240), max(1.5, self.u(2))))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r + self.u(4), r + self.u(4))

    def _shape(self, p: QPainter, n: TreeNodeView, cx: float, cy: float, r: float) -> None:
        if n.kind == "jewel":
            path = QPainterPath()
            path.moveTo(cx, cy - r)
            path.lineTo(cx + r, cy)
            path.lineTo(cx, cy + r)
            path.lineTo(cx - r, cy)
            path.closeSubpath()
            p.drawPath(path)
        else:
            p.drawEllipse(QPointF(cx, cy), r, r)

    def _edge_pen(self, a: TreeNodeView, b: TreeNodeView) -> QPen:
        states = {a.state, b.state}
        if states <= {"taken"}:
            c = QColor(*GOLD, 200)
            w = 2.0
        elif states & {"next", "planned"} and not states & {"offplan"}:
            c = QColor(255, 255, 255, 120)
            w = 1.5
        elif "offplan" in states:
            c = QColor(*theme.palette(self.config.get("palette"))["behind"], 130)
            w = 1.3
        else:
            c = QColor(255, 255, 255, 40)
            w = 1.0
        return QPen(c, self.u(w))

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing
                         | QPainter.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.transparent)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        W, H = self.width(), self.height()
        r8 = self.u(8)
        p.setPen(Qt.NoPen)
        p.setBrush(BG)
        p.drawRoundedRect(QRectF(0, 0, W, H), r8, r8)
        pad = self.u(PAD)
        v = self.view

        # ---- header: "Дерево · ур N · свободно K"
        x = pad
        base = self._base(0, self.u(HEADER_H), self.m_head)
        parts = [(tr("Дерево"), None)]
        if v and v.level is not None:
            parts.append((tr(" · ур {level}", level=v.level), None))
        if v and v.points_free:
            parts.append((tr(" · свободно {n}", n=v.points_free), theme.YELLOW))
        for txt, col in parts:
            self._text(p, x, base, txt, self.f_head, QColor(*col) if col else QColor(255, 255, 255))
            x += self.m_head.horizontalAdvance(txt)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawLine(QPointF(pad, self.u(HEADER_H) - 2), QPointF(W - pad, self.u(HEADER_H) - 2))

        # ---- map
        m = self.map_rect()
        p.save()
        p.setClipRect(m)
        p.translate(m.topLeft())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawRoundedRect(QRectF(0, 0, m.width(), m.height()), self.u(6), self.u(6))
        hits = self._hits()
        if v:
            for a, b in v.edges:
                na, nb = self._nodes.get(a), self._nodes.get(b)
                if na is None or nb is None:
                    continue
                ax, ay = self.vp.to_screen(na.x, na.y)
                bx, by = self.vp.to_screen(nb.x, nb.y)
                p.setPen(self._edge_pen(na, nb))
                p.drawLine(QPointF(ax, ay), QPointF(bx, by))
        phase = (self._clock() % PULSE_PERIOD_S) / PULSE_PERIOD_S
        for h in hits:
            n = h.node
            if n.state == "next" and n.order == 1:                    # soft pulse on the first one
                rr = h.r + self.u(3) + self.u(9) * phase
                p.setPen(QPen(QColor(*NEXT, int(200 * (1 - phase))), self.u(2)))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(*h.pos), rr, rr)
            self._draw_node(p, h, n.sid == self._hover_sid)
        if not v or not v.nodes:
            self._text(p, self.u(14), self._base(0, self.u(30), self.m_list), "—", self.f_list,
                       QColor(255, 255, 255), 0.6)
        p.restore()
        # centre button
        cb = self.center_button_rect()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(cb, cb.height() / 2, cb.height() / 2)
        p.setFont(self.f_foot)
        p.setPen(QColor(235, 235, 235))
        centre = tr("центр")
        tw = self.m_foot.horizontalAdvance(centre)
        p.drawText(QPointF(cb.center().x() - tw / 2, self._base(cb.top(), cb.height(), self.m_foot)), centre)

        # ---- side strip: next nodes
        s = self.strip_rect()
        items = self.list_items()
        for rect, n in items:
            hov = n.sid == self._hover_sid
            if hov:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 36))
                p.drawRoundedRect(rect, self.u(5), self.u(5))
            by = self._base(rect.top(), rect.height(), self.m_list)
            if n.order is not None:
                d = self.u(18)
                badge = QRectF(rect.left() + self.u(3), rect.center().y() - d / 2, d, d)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(*NEXT))
                p.drawEllipse(badge)
                p.setFont(self.f_num)
                lab = str(n.order)
                p.setPen(QColor(8, 30, 44))
                p.drawText(QPointF(badge.center().x() - self.m_num.horizontalAdvance(lab) / 2,
                                   self._base(badge.top(), badge.height(), self.m_num)), lab)
            tx = rect.left() + self.u(28)
            # level first: a long name may be elided, the level must stay visible
            txt = elide((tr("ур {level}", level=n.level) + " · " if n.level is not None else "") + n.name, self.m_list,
                        rect.right() - tx - self.u(2))
            self._text(p, tx, by, txt, self.f_list, QColor(255, 255, 255))
        if not items:
            self._text(p, s.left() + self.u(6), self._base(s.top(), self.u(LIST_LINE_H), self.m_list),
                       "—", self.f_list, QColor(255, 255, 255), 0.6)

        # ---- footer: flash or legend
        fy = H - self.u(FOOTER_H)
        base = self._base(fy, self.u(FOOTER_H), self.m_foot)
        if self._flash:
            col = QColor(*theme.palette(self.config.get("palette"))["ahead"])
            self._text(p, pad, base, elide(self._flash, self.m_foot, W - 2 * pad), self.f_foot, col)
        else:
            self._legend(p, pad, fy, base)
        p.end()

    def _legend(self, p: QPainter, x: float, fy: float, base: float) -> None:
        pal = self.config.get("palette")
        cy = fy + self.u(FOOTER_H) / 2
        for state, label in (("taken", tr("взято")), ("next", tr("дальше")), ("planned", tr("план")),
                             ("offplan", tr("мимо"))):
            cols = node_colors(state, pal)
            r = self.u(5)
            p.setPen(QPen(QColor(*cols["line"]), self.u(1.5)))
            p.setBrush(QColor(*cols["fill"]))
            p.drawEllipse(QPointF(x + r, cy), r, r)
            x += 2 * r + self.u(5)
            self._text(p, x, base, label, self.f_foot, QColor(255, 255, 255), 0.75)
            x += self.m_foot.horizontalAdvance(label) + self.u(16)
