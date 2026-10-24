import threading
from pathlib import Path

import pytest

from pilot.contracts import GemCard, GemRow
from pilot.overlay import gems_window as gw
from pilot.overlay import winapi

SCREENS = Path(__file__).resolve().parents[2] / "docs" / "screens"


def card(name, kind="support", color="int", desc="", url=None):
    return GemCard(name, kind, color, desc, url)


def rows3():
    return (
        GemRow(card("Twister", "skill", "dex", "Spiral through enemies as a whirlwind, building up Wind. "
                    "Releasing the buildup unleashes a Twister that damages enemies nearby.", "https://cdn.poe2db.tw/a.png"),
               (card("Salvo", color="dex", desc="Supported skills fire a salvo."),
                card("Prolonged Duration II", color="int", desc="More duration."))),
        GemRow(card("Barrage", "skill", "dex", "Rapid volley."), (card("Heightened Charges", color="str"),)),
        GemRow(card("Whirling Slash", "skill", "str", "Leap and spin."), (card("Exploit Weakness", color="str"),)),
    )


class FakeCache:
    """IconCache stand-in: get() -> path or None; fire(url) 'downloads' it from a worker thread."""

    def __init__(self, root: Path):
        self.root = root
        self.ready: dict[str, str] = {}
        self.waiting: dict[str, list] = {}
        self.calls = 0

    def get(self, url, on_ready=None):
        self.calls += 1
        if url in self.ready:
            return self.ready[url]
        if on_ready:
            self.waiting.setdefault(url, []).append(on_ready)
        return None

    def fire(self, url, rgb=(200, 60, 60)):
        from PySide6.QtGui import QColor, QImage

        img = QImage(64, 64, QImage.Format_ARGB32)
        img.fill(QColor(*rgb))
        path = self.root / (str(abs(hash(url))) + ".png")
        assert img.save(str(path))
        self.ready[url] = str(path)

        def worker():                                   # like the real cache: another thread
            for cb in self.waiting.pop(url, []):
                cb()

        t = threading.Thread(target=worker)
        t.start()
        t.join()


@pytest.fixture
def make(qapp, tmp_path):
    made = []

    def _make(cfg=None, rows=None, shown=False):
        cfg = {"hide_when_unfocused": False, "icon_cache": FakeCache(tmp_path), **(cfg or {})}
        w = gw.GemsWindow(cfg)
        made.append(w)
        if rows is not None:
            w.set_rows(rows)
        if shown:
            w.toggle()
        return w

    yield _make
    for w in made:
        w.hide()
        w.tip.hide()


# ---------------------------------------------------------------- pure helpers
def test_initials():
    assert gw.initials("Prolonged Duration II") == "PD"
    assert gw.initials("Twister") == "Tw"
    assert gw.initials("Whirling Slash") == "WS"
    assert gw.initials("") == "?"


def test_fit_icon_size():
    assert gw.fit_icon_size(2, 400) == 32
    assert gw.fit_icon_size(0, 400) == 32
    assert gw.fit_icon_size(10, 330) == 28                     # (330-9*5)//10
    assert gw.fit_icon_size(20, 330) == 24                     # never below the minimum
    assert 24 <= gw.fit_icon_size(7, 300) <= 32


def test_attr_colors():
    r, g, b = gw.attr_color("str"); assert r > g and r > b
    r, g, b = gw.attr_color("dex"); assert g > r and g > b
    r, g, b = gw.attr_color("int"); assert b > r and b > g
    r, g, b = gw.attr_color("none"); assert r == g == b
    assert gw.attr_color("wat") == gw.attr_color("none")


# ---------------------------------------------------------------- toggle / visibility
def test_toggle_and_refresh_from_provider(make):
    calls = []
    cfg = {"gem_provider": lambda: calls.append(1) or rows3(), "level_provider": lambda: 12}
    w = make(cfg)
    assert not w.is_open and not w.isVisible()
    w.toggle()
    assert w.is_open and w.isVisible()
    assert w.rows == rows3() and w.level == 12
    assert len(calls) == 1
    w.refresh()                                  # what the 1 s timer does
    assert len(calls) == 2 and w._timer.isActive()
    w.toggle()
    assert not w.is_open and not w.isVisible() and not w._timer.isActive()


def test_rows_update_on_levelup(make):
    state = {"rows": rows3()[:1], "lv": 5}
    w = make({"gem_provider": lambda: state["rows"], "level_provider": lambda: state["lv"]}, shown=True)
    h1 = w.height()
    state.update(rows=rows3(), lv=6)
    w.refresh()
    assert w.level == 6 and len(w.rows) == 3 and w.height() > h1


def test_provider_errors_are_swallowed(make):
    def boom():
        raise RuntimeError

    w = make({"gem_provider": boom, "level_provider": boom})
    w.refresh()


def test_hide_when_unfocused(make):
    fg = winapi.Foreground
    w = make({"hide_when_unfocused": True})
    w._open = True
    assert w.should_be_visible(fg(1, "pathofexile_x64steam.exe"))
    assert not w.should_be_visible(fg(1, "chrome.exe"))
    assert w.should_be_visible(fg(__import__("os").getpid(), "python.exe"))   # our own windows
    w.config["hide_when_unfocused"] = False
    assert w.should_be_visible(fg(1, "chrome.exe"))
    w._open = False
    assert not w.should_be_visible(fg(1, "pathofexile.exe"))


def test_window_is_not_click_through_and_never_activates(make):
    w = make()
    assert not (w.windowFlags() & gw.Qt.WindowTransparentForInput)
    assert w.windowFlags() & gw.Qt.WindowDoesNotAcceptFocus
    assert w.windowFlags() & gw.Qt.Tool and w.windowFlags() & gw.Qt.WindowStaysOnTopHint
    assert w.hasMouseTracking()


# ---------------------------------------------------------------- layout
def test_row_layout_sizes_and_order(make):
    w = make(rows=rows3())
    items, W, H = w.compute_items()
    assert len(items) == 3 + 4
    skill, sup1, sup2 = items[0], items[1], items[2]
    assert skill.size == 40 and sup1.size == 32 and sup2.size == 32
    assert skill.rect.right() < sup1.rect.left() < sup2.rect.left()       # skill > supports, one line
    assert abs(skill.rect.center().y() - sup1.rect.center().y()) < 1
    rows_y = [it.rect.top() for it in items if it.card.kind == "skill"]
    assert rows_y == sorted(rows_y) and len(set(rows_y)) == 3
    assert all(it.rect.right() <= W and it.rect.bottom() <= H for it in items)
    assert (w.width(), w.height()) == (int(-(-W // 1)), int(-(-H // 1)))


def test_many_supports_shrink_then_widen_without_wrapping(make):
    sup = lambda n: tuple(card(f"Support {i}", color="int") for i in range(n))
    w = make(rows=(GemRow(card("A", "skill", "str"), sup(9)),))
    items, W, _ = w.compute_items()
    sizes = {it.size for it in items[1:]}
    assert len(sizes) == 1 and 24 <= sizes.pop() < 32                    # shrunk
    assert len({it.rect.top() for it in items[1:]}) == 1                 # still one line
    w = make(rows=(GemRow(card("A", "skill", "str"), sup(20)),))
    items, W2, _ = w.compute_items()
    assert {it.size for it in items[1:]} == {24}                         # floor
    assert W2 > gw.BASE_W                                                # grew instead of wrapping
    assert len({it.rect.top() for it in items[1:]}) == 1
    assert all(it.rect.right() <= W2 for it in items)


@pytest.mark.parametrize("scale", [0.75, 1.5, 2.0])
def test_scaling(make, scale):
    w = make({"gems_window": {"scale": scale}}, rows=rows3())
    assert w.scale == scale
    items, W, H = w.compute_items()
    assert all(it.rect.right() <= W and it.rect.bottom() <= H for it in items)
    assert w.grab().width() == w.width()


# ---------------------------------------------------------------- icons
def test_fallback_icon_colors(make):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    w = make()

    def center_color(c):
        img = QImage(60, 60, QImage.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        w._draw_fallback(p, QRectF(0, 0, 60, 60), c)
        p.end()
        return img.pixelColor(30, 8)          # top part of the shape: above the initials

    red = center_color(card("X", "skill", "str"))
    green = center_color(card("X", "skill", "dex"))
    blue = center_color(card("X", "skill", "int"))
    gray = center_color(card("X", "skill", "none"))
    assert red.red() > red.green() and red.red() > red.blue()
    assert green.green() > green.red() and green.green() > green.blue()
    assert blue.blue() > blue.red() and blue.blue() > blue.green()
    assert abs(gray.red() - gray.green()) < 6 and abs(gray.green() - gray.blue()) < 6
    # support (diamond) also paints
    assert center_color(card("X", "support", "int")).alpha() >= 0


def test_icon_swap_after_on_ready(make, qapp):
    rows = rows3()
    w = make(rows=rows)
    cache = w.config["icon_cache"]
    skill = rows[0].skill
    assert w.icon_pixmap(skill, 40) is None                   # fallback in use
    assert skill.icon_url in cache.waiting
    cache.fire(skill.icon_url)                                # worker thread calls on_ready
    qapp.processEvents()                                      # queued signal -> GUI thread
    pm = w.icon_pixmap(skill, 40)
    assert pm is not None and not pm.isNull()
    assert w.grab().width() > 0                               # paints with the real icon
    # cards without a url never ask the cache
    assert rows[0].supports[0].icon_url is None


def test_default_icon_cache_is_created_lazily(qapp, monkeypatch):
    created = []

    class Dummy:
        def __init__(self):
            created.append(1)

        def get(self, url, on_ready=None):
            return None

    import pilot.assets as assets
    monkeypatch.setattr(assets, "IconCache", Dummy)
    w = gw.GemsWindow({"hide_when_unfocused": False})
    w.set_rows((GemRow(card("A", "skill", "str", url="https://cdn.poe2db.tw/x.png")),))
    assert created == [1]


# ---------------------------------------------------------------- hover / click
def center(it):
    return it.rect.center()


def test_hover_tooltip_text(make):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    w = make(rows=rows3(), shown=True)
    skill = w._items[0]
    ev = QMouseEvent(QEvent.MouseMove, center(skill), w.mapToGlobal(center(skill)), Qt.NoButton,
                     Qt.NoButton, Qt.NoModifier)
    w.mouseMoveEvent(ev)
    assert w.tip.isVisible()
    assert w.tip.title == "Twister"
    assert w.tip.kind_text == "Скилл"
    assert "whirlwind" in w.tip.plain_text() and "Twister" in w.tip.plain_text()
    assert w.tip.width() <= gw.TIP_MAX_W + 20 + 1                 # word-wrapped, capped width
    sup = w._items[1]
    w.set_hover(sup)
    assert w.tip.title == "Salvo" and w.tip.kind_text == "Поддержка"
    w.set_hover(None)
    assert not w.tip.isVisible()


def test_tooltip_long_description_wraps(make):
    long = "word " * 120
    w = make(rows=(GemRow(card("A", "skill", "str", long)),), shown=True)
    w.set_hover(w._items[0])
    assert w.tip.width() <= gw.TIP_MAX_W + 21
    assert w.tip.height() > 100


def test_click_copies_english_name(make, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    w = make(rows=rows3(), shown=True)
    QGuiApplication.clipboard().setText("")
    QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, center(w._items[0]).toPoint())
    assert QGuiApplication.clipboard().text() == "Twister"
    assert w.flash_text == "Скопировано: Twister"
    QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, center(w._items[2]).toPoint())   # a support
    assert QGuiApplication.clipboard().text() == "Prolonged Duration II"
    assert w.flash_text == "Скопировано: Prolonged Duration II"
    w._end_flash()                                                                      # after 1 s
    assert w.flash_text is None
    assert w._flash_timer.interval() == 1000


def test_click_on_empty_space_copies_nothing(make):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    w = make(rows=rows3(), shown=True)
    QGuiApplication.clipboard().setText("keep")
    QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, QPoint(w.width() - 3, w.height() - 3))
    assert QGuiApplication.clipboard().text() == "keep"


# ---------------------------------------------------------------- drag / save
def test_header_drag_saves_position(make):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    saved = []
    cfg = {"on_save": saved.append}
    w = make(cfg, rows=rows3(), shown=True)
    w.move(100, 100)
    start = QPointF(30, 10)
    g0 = QPointF(w.mapToGlobal(start.toPoint()))

    def ev(t, g, btn=Qt.LeftButton):
        return QMouseEvent(t, g - QPointF(w.pos()), g, btn, btn, Qt.NoModifier)

    w.mousePressEvent(ev(QEvent.MouseButtonPress, g0))
    w.mouseMoveEvent(ev(QEvent.MouseMove, g0 + QPointF(50, 30)))
    w.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, g0 + QPointF(50, 30)))
    assert (w.x(), w.y()) == (150, 130)
    assert saved and saved[0]["gems_window"] == {"x": 150, "y": 130, "scale": 1.0}


def test_saved_position_and_scale_restored(make):
    w = make({"gems_window": {"x": 321, "y": 123, "scale": 1.25}}, rows=rows3())
    assert (w.x(), w.y(), w.scale) == (321, 123, 1.25)


def test_header_text_with_and_without_level(make):
    w = make({"level_provider": lambda: 17}, rows=rows3())
    w.refresh()
    assert w.level == 17
    w2 = make(rows=rows3())
    assert w2.level is None
    assert w2.grab().width() > 0 and w.grab().width() > 0


# ---------------------------------------------------------------- screenshots
def _compose(win, margin=24, with_tip=False):
    from PySide6.QtGui import QPainter

    from test_screens import _backdrop

    pm = win.grab()
    tip_pm = win.tip.grab() if with_tip else None
    extra = (win.tip.height() + 16) if with_tip else 0
    w, h = pm.width() + 2 * margin + 60, pm.height() + 2 * margin + extra
    img = _backdrop(w, h)
    p = QPainter(img)
    p.drawPixmap(margin, margin, pm)
    if tip_pm is not None:
        off = win.tip.pos() - win.pos()
        p.drawPixmap(margin + off.x(), margin + off.y(), tip_pm)
    p.end()
    return img


def test_screenshots(make, tmp_path):
    from PySide6.QtGui import QColor, QGuiApplication

    rows = rows3()
    w = make({"gem_provider": lambda: rows, "level_provider": lambda: 12}, shown=True)
    cache = w.config["icon_cache"]
    # two real-looking icons (Twister + Barrage), the rest stays on the vector fallback
    cache.fire(rows[0].skill.icon_url, (60, 140, 90))
    w._on_icon_ready()
    SCREENS.mkdir(parents=True, exist_ok=True)
    assert _compose(w).save(str(SCREENS / "gems_window.png"))
    w.set_hover(w._items[2])
    assert _compose(w, with_tip=True).save(str(SCREENS / "gems_window_hover.png"))
    w.copy_name(rows[0].supports[1])
    assert _compose(w).save(str(SCREENS / "gems_window_copied.png"))
    w.set_hover(None)
