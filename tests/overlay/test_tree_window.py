import os
import tempfile
import math
from pathlib import Path

import pytest

from pilot.contracts import TreeNodeView, TreeView
from pilot.overlay import tree_window as tw
from pilot.overlay import winapi
from pilot.overlay.demo import demo_tree_view

# docs/screens is refreshed only on request (POE2_PILOT_SCREENS=1); a plain run renders to the temp dir
SCREENS = (Path(__file__).resolve().parents[2] / "docs" / "screens" if os.environ.get("POE2_PILOT_SCREENS")
           else Path(tempfile.gettempdir()) / "poe2-pilot-screens")


def N(sid, name, x, y, state="other", kind="small", order=None, level=None, stats=(), url=None):
    return TreeNodeView(sid, name, kind, x, y, tuple(stats), state, order, level, url)


def small_view():
    nodes = (
        N("a", "Start", 0, 0, "taken", "start"),
        N("b", "Life", 60, 0, "taken"),
        N("c", "Projectile Damage", 120, 0, "next", "notable", 1, 14, ("10% increased Projectile Damage", "+5 Dex")),
        N("d", "Attack Speed", 120, 60, "next", "small", 2, 15),
        N("e", "Armour", 180, 0, "planned", "small", None, 17),
        N("f", "Evasion", 0, 60, "offplan"),
        N("g", "Far", 900, 900, "other"),
    )
    edges = (("a", "b"), ("b", "c"), ("b", "d"), ("c", "e"), ("a", "f"), ("e", "g"))
    return TreeView(nodes, edges, level=13, points_free=2)


class FakeCache:
    def __init__(self):
        self.calls = []

    def get(self, url, on_ready=None):
        self.calls.append(url)
        return None


@pytest.fixture
def make(qapp):
    made = []

    def _make(cfg=None, view=None, shown=False, clock=None):
        cfg = {"hide_when_unfocused": False, "icon_cache": FakeCache(), **(cfg or {})}
        w = tw.TreeWindow(cfg, clock=clock)
        made.append(w)
        if view is not None:
            w.set_view(view)
        if shown:
            w.toggle()
        return w

    yield _make
    for w in made:
        w.hide()
        w.tip.hide()


# ---------------------------------------------------------------- viewport math
def test_viewport_roundtrip():
    vp = tw.Viewport(400, 280)
    vp.cx, vp.cy, vp.zoom = 123.0, -45.0, 0.37
    for x, y in [(0, 0), (100, 200), (-340.5, 12.25)]:
        sx, sy = vp.to_screen(x, y)
        bx, by = vp.to_tree(sx, sy)
        assert (bx, by) == pytest.approx((x, y))
    assert vp.to_screen(123.0, -45.0) == pytest.approx((200, 140))       # centre maps to the middle
    # y grows downwards in both spaces
    assert vp.to_screen(123.0, 0)[1] > vp.to_screen(123.0, -45.0)[1]


def test_zoom_anchored_at_cursor():
    vp = tw.Viewport(400, 280)
    vp.cx, vp.cy, vp.zoom = 10, 20, 0.5
    anchor = (310.0, 90.0)
    t0 = vp.to_tree(*anchor)
    vp.zoom_at(*anchor, 1.5)
    assert vp.zoom == pytest.approx(0.75)
    assert vp.to_tree(*anchor) == pytest.approx(t0)
    vp.zoom_at(*anchor, 1e9)
    assert vp.zoom == tw.ZOOM_MAX
    vp.zoom_at(*anchor, 1e-12)
    assert vp.zoom == tw.ZOOM_MIN


def test_pan_moves_content_with_cursor():
    vp = tw.Viewport(400, 280)
    vp.zoom = 2.0
    before = vp.to_screen(5, 5)
    vp.pan(30, -10)
    after = vp.to_screen(5, 5)
    assert (after[0] - before[0], after[1] - before[1]) == pytest.approx((30, -10))


def test_fit_contains_points_and_centres_focus():
    vp = tw.Viewport(400, 280)
    pts = [(0, 0), (200, 100), (-50, 300)]
    vp.fit(pts, focus=(50, 50), margin=20)
    assert vp.to_screen(50, 50) == pytest.approx((200, 140))
    for p in pts:
        sx, sy = vp.to_screen(*p)
        assert 0 <= sx <= 400 and 0 <= sy <= 280
    vp.fit([(5, 5)], margin=20)                    # single point
    assert vp.zoom == tw.ZOOM_MAX
    vp.fit([])
    assert vp.zoom == 1.0


def test_fit_viewport_next_centred_and_taken_planned_visible(make):
    view = small_view()
    vp = tw.Viewport(400, 280)
    tw.fit_viewport(vp, view, 24)
    # centroid of the next nodes is the viewport centre
    assert vp.to_screen(120, 30) == pytest.approx((200, 140))
    for n in view.nodes:
        sx, sy = vp.to_screen(n.x, n.y)
        if n.state in ("taken", "next", "planned"):
            assert 0 <= sx <= 400 and 0 <= sy <= 280, n.sid
    assert vp.to_screen(900, 900)[0] > 400          # 'other' far nodes are not forced in


def test_fit_viewport_readable_floor():
    nodes = tuple(N(f"n{i}", f"N{i}", i * 100, 0, "taken") for i in range(200)) + (
        N("x", "X", 19900, 0, "next", order=1),)
    edges = tuple((f"n{i}", f"n{i+1}") for i in range(199))
    vp = tw.Viewport(400, 280)
    tw.fit_viewport(vp, TreeView(nodes, edges))
    assert vp.zoom * 100 >= tw.READABLE_EDGE_PX - 1e-6       # nodes never squashed together


# ---------------------------------------------------------------- state colours / labels
def test_state_colors():
    gold = tw.node_colors("taken")
    nxt = tw.node_colors("next")
    planned = tw.node_colors("planned")
    off = tw.node_colors("offplan")
    other = tw.node_colors("other")
    assert gold["fill"][0] > gold["fill"][2] and gold["fill"][1] > gold["fill"][2]      # gold: r,g > b
    assert nxt["fill"][2] > nxt["fill"][0]                                               # bright cyan-ish
    assert planned["fill"][3] < 60 and planned["line"][3] > 100                          # outlined, hollow
    assert off["line"][0] > off["line"][1] and off["line"][0] > off["line"][2]           # red outline
    assert other["line"][3] < 120                                                        # faint
    assert tw.node_colors("???") == other
    cb = tw.node_colors("offplan", "colorblind")["line"]                                  # orange, not red
    assert cb[1] > off["line"][1]


def test_radius_by_kind_and_order_labels():
    r = {k: tw.node_radius(N("x", "x", 0, 0, kind=k)) for k in ("small", "attribute", "notable", "keystone")}
    assert r["small"] < r["attribute"] < r["notable"] < r["keystone"]
    assert tw.node_radius(N("x", "x", 0, 0, "next", "small", 1)) >= tw.NEXT_MIN_RADIUS   # room for number
    assert tw.order_label(N("x", "x", 0, 0, "next", order=3)) == "3"
    assert tw.order_label(N("x", "x", 0, 0, "taken", order=3)) == ""
    assert tw.order_label(N("x", "x", 0, 0, "next")) == ""


def test_next_nodes_sorted_and_list_line():
    v = small_view()
    ns = tw.next_nodes(v)
    assert [n.sid for n in ns] == ["c", "d"]
    assert tw.list_line(ns[0]) == "1 Projectile Damage · ур 14"
    assert tw.list_line(N("z", "Zed", 0, 0, "next")) == "Zed"
    assert tw.next_nodes(None) == []


# ---------------------------------------------------------------- window behaviour
def test_toggle_and_provider_refresh(make):
    calls = []
    w = make({"tree_provider": lambda: calls.append(1) or small_view()})
    assert not w.is_open and not w.isVisible()
    w.toggle()
    assert w.is_open and w.isVisible() and w.view == small_view()
    assert w._timer.isActive()
    n = len(calls)
    w.refresh()
    assert len(calls) == n + 1
    w.toggle()
    assert not w.isVisible() and not w._timer.isActive()


def test_none_view_and_provider_errors_ok(make):
    def boom():
        raise RuntimeError

    w = make({"tree_provider": boom})
    w.refresh()
    w.set_view(None)
    assert w.grab().width() == w.width()
    w2 = make({"tree_provider": lambda: None}, shown=True)
    assert w2.view is None


def test_refit_only_when_next_changes(make):
    w = make(view=small_view())
    w.fit()
    w.vp.pan(50, 50)                               # user panned
    cx = w.vp.cx
    w.set_view(TreeView(small_view().nodes, small_view().edges, level=13, points_free=1))   # same next set
    assert w.vp.cx == cx
    nodes = tuple(n if n.sid != "e" else N("e", "Armour", 180, 0, "next", order=1) for n in small_view().nodes)
    w.set_view(TreeView(nodes, small_view().edges))
    assert w.vp.cx != cx                           # next set changed -> fitted again


def test_window_flags_and_native(make):
    w = make()
    f = w.windowFlags()
    assert not (f & tw.Qt.WindowTransparentForInput)
    assert f & tw.Qt.WindowDoesNotAcceptFocus and f & tw.Qt.Tool and f & tw.Qt.WindowStaysOnTopHint


def test_hide_when_unfocused(make):
    fg = winapi.Foreground
    w = make({"hide_when_unfocused": True})
    w._open = True
    assert w.should_be_visible(fg(1, "pathofexile.exe"))
    assert not w.should_be_visible(fg(1, "chrome.exe"))
    w.config["hide_when_unfocused"] = False
    assert w.should_be_visible(fg(1, "chrome.exe"))


# ---------------------------------------------------------------- hover / click / list
def test_hover_node_tooltip(make):
    w = make(view=small_view(), shown=True)
    c = w.node_screen_pos("c")
    assert w.node_at(c).sid == "c"
    w.set_hover(w.node_at(c))
    assert w.tip.isVisible()
    assert w.tip.title == "Projectile Damage"
    assert w.tip.kind_text == "Значимый · ур 14"
    assert "10% increased Projectile Damage" in w.tip.plain_text() and "+5 Dex" in w.tip.plain_text()
    assert w.hover_sid == "c"
    w.set_hover(None)
    assert not w.tip.isVisible() and w.hover_sid is None


def test_tip_text_without_level():
    assert tw.tip_text(N("a", "Life", 0, 0, kind="small")) == ("Life", "Малый", "")


def test_hover_event_over_node_and_empty(make):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QMouseEvent

    w = make(view=small_view(), shown=True)

    def move(pt):
        w.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, pt, w.mapToGlobal(pt.toPoint()), Qt.NoButton,
                                     Qt.NoButton, Qt.NoModifier))

    move(w.node_screen_pos("d"))
    assert w.hover_sid == "d"
    m = w.map_rect()
    move(m.bottomLeft() + type(m.topLeft())(3, -3))
    assert w.hover_sid is None


def test_click_node_and_list_copy_name(make, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    w = make(view=small_view(), shown=True)
    QGuiApplication.clipboard().setText("")
    QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, w.node_screen_pos("c").toPoint())
    assert QGuiApplication.clipboard().text() == "Projectile Damage"
    assert w.flash_text == "Скопировано: Projectile Damage"
    rect, node = w.list_items()[1]
    QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, rect.center().toPoint())
    assert QGuiApplication.clipboard().text() == "Attack Speed"
    w._end_flash()
    assert w.flash_text is None and w._flash_timer.interval() == 1000


def test_list_hover_highlights_node(make):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QMouseEvent

    w = make(view=small_view(), shown=True)
    items = w.list_items()
    assert [n.sid for _r, n in items] == ["c", "d"]
    rect, node = items[1]
    pt = rect.center()
    w.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, pt, w.mapToGlobal(pt.toPoint()), Qt.NoButton,
                                 Qt.NoButton, Qt.NoModifier))
    assert w.hover_sid == "d"
    assert not w.tip.isVisible()                   # highlight only, no tooltip from the list
    assert w.grab().width() > 0


def test_list_limited_to_five(make):
    nodes = tuple(N(f"n{i}", f"Node {i}", i * 50, 0, "next", order=i + 1) for i in range(8))
    w = make(view=TreeView(nodes, ()))
    assert len(w.list_items()) == tw.MAX_LIST


def test_wheel_zoom_and_pan_and_recentre(make):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    saved = []
    w = make({"on_save": saved.append}, view=small_view(), shown=True)
    w.fit()
    z0 = w.vp.zoom
    pos = w.map_rect().center() + QPointF(60, 20)
    anchor_before = w.vp.to_tree(pos.x() - w.map_rect().left(), pos.y() - w.map_rect().top())
    ev = QWheelEvent(pos, w.mapToGlobal(pos), QPoint(0, 0), QPoint(0, 120), Qt.NoButton,
                     Qt.NoModifier, Qt.NoScrollPhase, False)
    w.wheelEvent(ev)
    assert w.vp.zoom > z0
    anchor_after = w.vp.to_tree(pos.x() - w.map_rect().left(), pos.y() - w.map_rect().top())
    assert anchor_after == pytest.approx(anchor_before)
    assert saved and saved[-1]["tree_window"]["zoom"] > 1.0
    # drag empty space pans
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    cx = w.vp.cx
    start = w.map_rect().bottomRight() - QPointF(30, 20)
    assert w.node_at(start) is None

    def me(t, pt, btn=Qt.LeftButton):
        return QMouseEvent(t, pt, w.mapToGlobal(pt.toPoint()), btn, btn, Qt.NoModifier)

    w.mousePressEvent(me(QEvent.MouseButtonPress, start))
    w.mouseMoveEvent(me(QEvent.MouseMove, start - QPointF(40, 0)))
    w.mouseReleaseEvent(me(QEvent.MouseButtonRelease, start - QPointF(40, 0)))
    assert w.vp.cx > cx                                  # content followed the cursor to the left
    # centre button restores the fit
    w.mousePressEvent(me(QEvent.MouseButtonPress, w.center_button_rect().center()))
    assert w.user_zoom == 1.0 and w.vp.zoom == pytest.approx(w._fit_zoom)
    assert w.vp.to_screen(120, 30) == pytest.approx((w.vp.w / 2, w.vp.h / 2))


def test_header_drag_saves_position_scale_zoom(make):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    saved = []
    w = make({"on_save": saved.append}, view=small_view(), shown=True)
    w.move(100, 100)
    g0 = QPointF(w.mapToGlobal(QPointF(30, 10).toPoint()))

    def ev(t, g):
        return QMouseEvent(t, g - QPointF(w.pos()), g, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)

    w.mousePressEvent(ev(QEvent.MouseButtonPress, g0))
    w.mouseMoveEvent(ev(QEvent.MouseMove, g0 + QPointF(40, 25)))
    w.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, g0 + QPointF(40, 25)))
    assert (w.x(), w.y()) == (140, 125)
    assert saved[0]["tree_window"] == {"x": 140, "y": 125, "scale": 1.0, "zoom": 1.0}


def test_saved_state_restored(make):
    w = make({"tree_window": {"x": 50, "y": 60, "scale": 1.5, "zoom": 0.5}}, view=small_view())
    assert (w.x(), w.y(), w.scale, w.user_zoom) == (50, 60, 1.5, 0.5)
    w.fit()
    assert w.vp.zoom == pytest.approx(w._fit_zoom * 0.5)


@pytest.mark.parametrize("scale", [0.75, 1.5, 2.0])
def test_scales_render_and_hit_test(make, scale):
    w = make({"tree_window": {"scale": scale}}, view=demo_tree_view(), shown=True)
    assert w.scale == scale and w.grab().width() == w.width()
    first = w.list_items()[0][1]
    assert w.node_at(w.node_screen_pos(first.sid)).sid == first.sid


def test_icons_requested_for_notables_only(make):
    nodes = (N("a", "Notable", 0, 0, "taken", "notable", url="https://cdn.poe2db.tw/n.png"),
             N("b", "Small", 50, 0, "taken", "small", url="https://cdn.poe2db.tw/s.png"))
    w = make(view=TreeView(nodes, ()))
    assert w.config["icon_cache"].calls == ["https://cdn.poe2db.tw/n.png"]


def test_header_text_parts(make):
    # smoke: with points_free the amber part paints; without it the header stays short
    w = make(view=small_view())
    assert w.grab().width() > 0
    v = small_view()
    w.set_view(TreeView(v.nodes, v.edges, level=None, points_free=None))
    assert w.grab().width() > 0


# ---------------------------------------------------------------- screenshots
def _compose(win, with_tip=False, margin=24):
    from PySide6.QtGui import QPainter

    from test_screens import _backdrop

    pm = win.grab()
    extra = 70 if with_tip else 0
    img = _backdrop(pm.width() + 2 * margin, pm.height() + 2 * margin + extra)
    p = QPainter(img)
    p.drawPixmap(margin, margin, pm)
    if with_tip:
        off = win.tip.pos() - win.pos()
        p.drawPixmap(margin + off.x(), margin + off.y(), win.tip.grab())
    p.end()
    return img


def test_screenshots(make):
    t = [10.3]
    w = make({"tree_provider": demo_tree_view}, shown=True, clock=lambda: t[0])
    SCREENS.mkdir(parents=True, exist_ok=True)
    assert _compose(w).save(str(SCREENS / "tree_window.png"))
    n = next(n for n in w.view.nodes if n.kind == "notable" and n.state == "planned") \
        if any(n.kind == "notable" and n.state == "planned" for n in w.view.nodes) \
        else next(n for n in w.view.nodes if n.state == "next")
    w.set_hover(n)
    assert _compose(w, with_tip=True).save(str(SCREENS / "tree_window_hover.png"))
    w.set_hover(None)
    w.copy_name(n.name)
    assert _compose(w).save(str(SCREENS / "tree_window_copied.png"))
