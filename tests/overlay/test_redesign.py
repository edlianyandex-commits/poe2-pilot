import pytest

from pilot.contracts import HudState, Toast
from pilot.overlay import fmt, icons, theme
from pilot.overlay.toasts import ToastStack


# ---------------------------------------------------------------- glyph strip / names
@pytest.mark.parametrize("glyph", list("→◆⚔⌂!✦✕·"))
def test_strip_glyph_each(glyph):
    g, rest = fmt.strip_glyph(f"{glyph} Грельвуд")
    assert g == glyph and rest == "Грельвуд"


def test_strip_glyph_requires_space_and_only_one():
    assert fmt.strip_glyph("→Грельвуд") == (None, "→Грельвуд")
    assert fmt.strip_glyph("Грельвуд") == (None, "Грельвуд")
    assert fmt.strip_glyph("→ → x") == ("→", "→ x")
    assert fmt.strip_glyph("⚔️ Рудья") == ("⚔", "Рудья")
    assert fmt.strip_glyph("") == (None, "")


def test_boss_epithet_cut():
    assert fmt.short_boss("Rudja, the Dread Engineer") == "Rudja"
    assert fmt.short_boss("Рудья, Ужасный Инженер") == "Рудья"
    assert fmt.short_boss("Rudja") == "Rudja"
    assert fmt.short_boss("A & B, the Pair") == "A & B"
    assert fmt.short_boss("Рудья и Хвост, оба") == "Рудья и Хвост"


def test_step_parts():
    assert fmt.step_parts("⚔ Rudja, the Dread Engineer", "boss") == ("boss", "Rudja")
    assert fmt.step_parts("⚔ Rudja, the Dread Engineer", None) == ("boss", "Rudja")  # kind from glyph
    assert fmt.step_parts("→ Грельвуд, затем WP", "move") == ("move", "Грельвуд, затем WP")  # only bosses
    assert fmt.step_parts("◆ WP", "wp") == ("wp", "WP")
    assert fmt.step_parts("Просто текст", None) == (None, "Просто текст")
    assert fmt.step_parts(None, "wp") == ("wp", "")


# ---------------------------------------------------------------- pills
def test_pill_none_hidden():
    assert fmt.pill_style(None) is None


def test_pill_colors_default_and_colorblind():
    a = fmt.pill_style(-42)
    b = fmt.pill_style(42)
    assert (a.kind, b.kind) == ("ahead", "behind")
    assert a.text == "−0:42" and b.text == "+0:42"
    assert a.bg[1] > a.bg[0] and b.bg[0] > b.bg[1]            # green-ish vs red-ish background
    ca, cb = fmt.pill_style(-42, "colorblind"), fmt.pill_style(42, "colorblind")
    assert ca.bg[2] > ca.bg[0] and ca.bg[2] > ca.bg[1]        # blue
    assert cb.bg[0] > cb.bg[2] and cb.bg[1] > cb.bg[2]        # orange
    assert fmt.pill_style(0).kind == "even"
    assert fmt.pill_style(-1, "nonsense").bg == a.bg           # unknown palette -> default


def test_zone_pill_amber_rule():
    assert fmt.zone_pill(None, 5) is None
    assert fmt.zone_pill(19, 17) == fmt.ZonePill("зона 19", False)
    assert fmt.zone_pill(20, 17).amber is False                # diff 3 is fine
    assert fmt.zone_pill(21, 17).amber is True                 # diff 4
    assert fmt.zone_pill(30, None).amber is False              # unknown char level: neutral
    assert fmt.level_text(17) == "ур 17" and fmt.level_text(None) is None


# ---------------------------------------------------------------- progress segments
def test_progress_segments_states():
    segs = fmt.progress_segments(0.4, (0.2, 0.5, 0.8))
    assert [(s.a, s.b) for s in segs] == [(0, 0.2), (0.2, 0.5), (0.5, 0.8), (0.8, 1.0)]
    assert [s.state for s in segs] == ["done", "current", "todo", "todo"]
    assert segs[1].frac == pytest.approx(2 / 3)


def test_progress_segments_edges():
    assert [s.state for s in fmt.progress_segments(0, (0.5,))] == ["current", "todo"]
    assert [s.state for s in fmt.progress_segments(1, (0.5,))] == ["done", "done"]
    assert [s.state for s in fmt.progress_segments(0.5, (0.5,))] == ["done", "current"]
    only = fmt.progress_segments(0.3, ())
    assert len(only) == 1 and only[0].state == "current"
    # junk marks (unsorted, duplicates, out of range) are tolerated
    assert len(fmt.progress_segments(0.3, (0.7, 0.2, 0.2, 0.0, 1.0, 1.5))) == 3
    assert fmt.progress_segments(7, ())[0].state == "done"      # clamped


def test_strip_warn_glyph():
    assert fmt.strip_warn_glyph("⚠ x") == "x"
    assert fmt.strip_warn_glyph("x") == "x"


# ---------------------------------------------------------------- toasts: gear slot
def T(text, kind="level", ttl=3.0):
    return Toast(text, kind, ttl)


def test_gear_may_be_third():
    s = ToastStack()
    s.update([T("a"), T("b", "split"), T("g", "gear")], 0.0)
    assert [t.text for t, _ in s.visible(1.0)] == ["a", "b", "g"]


def test_never_more_than_three_and_two_plain():
    s = ToastStack()
    s.update([T("a"), T("b"), T("c"), T("g1", "gear"), T("g2", "gear")], 0.0)
    shown = [t for t, _ in s.visible(1.0)]
    assert len(shown) <= 3
    assert sum(t.kind != "gear" for t in shown) <= 2
    assert shown[-1].text == "g2"


# ---------------------------------------------------------------- icons / theme
def test_every_icon_and_kind_resolves():
    names = set(icons.icon_names())
    for k in theme.KIND_COLORS:
        assert k in names
    for k, icon in theme.TOAST_ICONS.items():
        assert icon in names and k in theme.TOAST_COLORS
    assert {"level", "flag", "alert", "shield", "pin"} <= names


def test_draw_all_icons(qapp):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    img = QImage(32, 32, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    for n in icons.icon_names():
        icons.draw_icon(p, n, QRectF(4, 4, 24, 24), (255, 255, 255))
    p.end()
    assert any(img.pixelColor(x, y).alpha() for x in range(32) for y in range(32))


# ---------------------------------------------------------------- layout never clips
LONG = HudState(
    act=102, area_name="Очень длинное название зоны", area_level=45, char_level=44,
    step_short="⚔ Очень-очень длинное имя босса без запятых которое не помещается",
    step_kind="boss",
    next_short="◆ Ещё более длинное название следующего шага которое тоже не влезет",
    next_kind="wp", run_time_s=36000 + 3599, split_delta_s=-3723.0, progress=0.5,
    split_marks=(0.2, 0.4, 0.6), running=True)


@pytest.mark.parametrize("scale", [0.75, 1.0, 1.5, 2.0])
@pytest.mark.parametrize("palette", ["default", "colorblind"])
def test_layout_fits_at_all_scales(qapp, scale, palette):
    from pilot.overlay.hud import HudWindow

    hud = HudWindow({"scale": scale, "palette": palette})
    hud.set_state(LONG)
    L = hud.bar_layout(LONG)
    W = L["W"]
    assert W == hud.width_px == hud.width()
    # text never exceeds its column and nothing leaves the window
    assert L["name_x"] + hud.m1.horizontalAdvance(L["name"]) <= L["name_right"] + 1
    assert hud.m1.horizontalAdvance(L["name"]) > 0
    assert L["pill_rect"].left() >= L["name_x"] and L["pill_rect"].right() < L["timer_x"]
    assert L["timer_x"] + hud._tab_w(L["timer_txt"], hud.m1) <= W - L["padx"] + 1
    assert L["name_x"] + hud.m2.horizontalAdvance(L["nname"]) <= L["nname_right"] + 1
    assert L["zone_rect"].right() <= W - L["padx"] + 1
    assert L["lv_x"] > L["name_x"]
    assert L["zone"].amber is False
    # a warning (long) is elided inside the bar too
    st = HudState(warn="Предупреждение " * 10, running=True)
    assert hud.m2.horizontalAdvance(hud.bar_layout(st)["warn"]) <= W - L["padx"] - L["name_x"]
    # toasts: single line, within the window
    hud.set_state(HudState(toasts=(T("x" * 60), T("y" * 60, "gear"), T("z", "warn"))))
    _h, _bar, _det, trects = hud._geometry(hud._clock())
    assert trects and all(r.left() >= 0 and r.right() <= W for r in trects)
    assert hud.grab().width() == W


def test_amber_zone_pill_in_layout(qapp):
    from pilot.overlay.hud import HudWindow

    hud = HudWindow({})
    st = HudState(area_level=19, char_level=14, running=True)
    assert hud.bar_layout(st)["zone"].amber is True
    assert hud.bar_layout(HudState(running=True))["zone"] is None
    assert hud.bar_layout(HudState(running=True))["lv"] is None
