import pytest

from pilot.contracts import HudState, Toast
from pilot.overlay import hotkeys, winapi
from pilot.overlay.fmt import (act_label, delta_kind, details_lines, elide, format_delta,
                               format_time, warn_text)
from pilot.overlay.toasts import ToastStack


# ---------------------------------------------------------------- formatting
def test_format_time():
    assert format_time(0) == "0:00:00"
    assert format_time(4360) == "1:12:40"
    assert format_time(59.9) == "0:00:59"
    assert format_time(-5) == "0:00:00"
    assert format_time(36000 + 61) == "10:01:01"


def test_format_delta():
    assert format_delta(None) is None
    assert format_delta(-42) == "−0:42"
    assert format_delta(65) == "+1:05"
    assert format_delta(-3723) == "−1:02:03"
    assert format_delta(0.2) == "0:00"


def test_delta_kind():
    assert delta_kind(-1) == "ahead"
    assert delta_kind(1) == "behind"
    assert delta_kind(0) is None
    assert delta_kind(None) is None


def test_act_label():
    assert act_label(2, 19) == "A2 · 19"
    assert act_label(101, 40) == "И1 · 40"
    assert act_label(103, None) == "И3"
    assert act_label(None, 5) == "5"
    assert act_label(None, None) == ""


def test_warn_text():
    assert warn_text("x") == "⚠ x"
    assert warn_text("⚠ x") == "⚠ x"


def test_elide(qapp):
    from PySide6.QtGui import QFont, QFontMetrics

    f = QFont("Segoe UI")
    f.setPixelSize(18)
    fm = QFontMetrics(f)
    long = "Очень длинное название шага которое не помещается" * 2
    out = elide(long, fm, 150)
    assert out.endswith("…")
    assert fm.horizontalAdvance(out) <= 150
    assert elide("WP", fm, 150) == "WP"
    assert elide("abc", fm, 0) == ""


def test_details_lines():
    st = HudState(step_short="→ A", next_short="B", step_index=3, step_total=10, char_level=7,
                  area_name="Z")
    lines = details_lines(st, ["x", "B", "y"])
    assert lines == ["4/10 · ур. 7 · Z", "x", "y"]      # bar's step/next not repeated
    assert "→ A" in details_lines(st)                   # no provider -> fall back to state
    assert len(details_lines(HudState(), ["q"] * 30)) == 10


# ---------------------------------------------------------------- toasts
def T(text, ttl=3.0, kind="level"):
    return Toast(text, kind, ttl)


def test_toast_expiry_and_fade():
    s = ToastStack()
    s.update([T("a")], now=10.0)
    (t, alpha), = s.visible(10.0)
    assert alpha == 0.0
    assert s.visible(10.075)[0][1] == pytest.approx(0.5)
    assert s.visible(11.0)[0][1] == 1.0
    assert s.visible(12.925)[0][1] == pytest.approx(0.5)
    assert s.visible(13.0) == []
    assert not s.active()


def test_toast_stack_max_two_newest_last():
    s = ToastStack()
    s.update([T("a"), T("b"), T("c")], now=0.0)
    assert [t.text for t, _ in s.visible(1.0)] == ["b", "c"]


def test_toast_not_reshown_while_source_repeats():
    s = ToastStack()
    s.update([T("a")], 0.0)
    s.update([T("a")], 3.5)       # source still reports it after our TTL
    assert s.visible(3.6) == []
    s.update([], 4.0)             # gone ...
    s.update([T("a")], 5.0)       # ... and back: shown again
    assert len(s.visible(5.5)) == 1


def test_toast_own_ttl_survives_source_dropping_it():
    s = ToastStack()
    s.update([T("a")], 0.0)
    s.update([], 0.5)
    assert len(s.visible(1.0)) == 1


def test_toast_zero_ttl_ignored():
    s = ToastStack()
    s.update([T("a", ttl=0)], 0.0)
    assert not s.active()


# ---------------------------------------------------------------- hotkeys
def test_parse_hotkey():
    assert hotkeys.parse_hotkey("alt+q") == (hotkeys.MOD_ALT, 0x51)
    assert hotkeys.parse_hotkey("Alt+]") == (hotkeys.MOD_ALT, 0xDD)
    assert hotkeys.parse_hotkey("alt+[") == (hotkeys.MOD_ALT, 0xDB)
    assert hotkeys.parse_hotkey("Ctrl + Shift + F5") == (hotkeys.MOD_CONTROL | hotkeys.MOD_SHIFT, 0x74)
    assert hotkeys.parse_hotkey("win+1") == (hotkeys.MOD_WIN, 0x31)
    assert hotkeys.parse_hotkey("f12") == (0, 0x7B)
    assert hotkeys.parse_hotkey("alt+space") == (hotkeys.MOD_ALT, 0x20)


@pytest.mark.parametrize("bad", ["", "alt", "alt+q+w", "alt+nope", "ctrl+f25", "+"])
def test_parse_hotkey_errors(bad):
    with pytest.raises(ValueError):
        hotkeys.parse_hotkey(bad)


def test_defaults_parse():
    for s in hotkeys.DEFAULT_HOTKEYS.values():
        hotkeys.parse_hotkey(s)


def test_hold_polling_edges(qapp):
    down = set()
    events = []
    hk = hotkeys.HotkeyManager({"details": events.append}, key_state=lambda vk: vk in down)
    hk.poll()
    assert events == []
    down.add(0x51)                      # q alone: alt missing
    hk.poll()
    assert events == []
    down.add(0x12)                      # alt+q
    hk.poll(); hk.poll()
    assert events == [True]
    down.clear()
    hk.poll()
    assert events == [True, False]


def test_dispatch_calls_callbacks_and_swallows_errors(qapp):
    calls = []

    def boom():
        raise RuntimeError

    hk = hotkeys.HotkeyManager({"next": lambda: calls.append("n"), "prev": boom})
    hk.fire("next")
    hk.fire("prev")     # must not raise
    hk.fire("reset")    # no callback: ignored
    assert calls == ["n"]


# ---------------------------------------------------------------- foreground check
def test_is_game_foreground():
    fg = winapi.Foreground
    assert winapi.is_game_foreground(fg(1, "pathofexile_x64steam.exe"), own_pid=99)
    assert winapi.is_game_foreground(fg(1, "pathofexilesteam.exe"), own_pid=99)
    assert not winapi.is_game_foreground(fg(1, "chrome.exe"), own_pid=99)
    assert not winapi.is_game_foreground(fg(0, None), own_pid=99)
    assert winapi.is_game_foreground(fg(99, "python.exe"), own_pid=99)   # HUD/settings itself
    assert winapi.is_game_foreground(None)                               # unknown platform


# ---------------------------------------------------------------- hud behaviour
def test_hud_visibility_rules(qapp):
    from pilot.overlay.hud import HudWindow

    fg = winapi.Foreground
    hud = HudWindow({"hide_when_unfocused": True})
    assert hud.should_be_visible(fg(1, "pathofexile.exe"))
    assert not hud.should_be_visible(fg(1, "notepad.exe"))
    hud.config["hide_when_unfocused"] = False
    assert hud.should_be_visible(fg(1, "notepad.exe"))
    hud._user_hidden = True
    assert not hud.should_be_visible(fg(1, "pathofexile.exe"))


def test_hud_edit_mode_saves_config(qapp):
    from pilot.overlay.hud import HudWindow

    saved = []
    cfg = {"on_save": saved.append, "x": 10, "y": 20}
    hud = HudWindow(cfg)
    hud.toggle_edit()
    assert hud.edit_mode
    hud.set_scale(5)
    assert hud.scale == 2.0
    hud.set_scale(0.1)
    assert hud.scale == 0.75
    hud.move(100, 50)
    hud.toggle_edit()
    assert not hud.edit_mode
    assert saved and saved[0] is cfg
    assert (cfg["x"], cfg["y"], cfg["scale"]) == (hud.x(), hud.y(), 0.75)


def test_hud_toasts_resize_and_expire(qapp):
    from pilot.overlay.hud import HudWindow

    t = [0.0]
    hud = HudWindow({}, clock=lambda: t[0])
    h0 = hud.height()
    hud.set_state(HudState(toasts=(T("a"), T("b"), T("c"))))
    h2 = hud.height()
    assert h2 > h0
    t[0] = 1.0
    hud._tick()
    assert hud.height() == h2          # still two
    t[0] = 4.0
    hud._tick()
    assert hud.height() == h0          # expired


def test_hud_details_provider(qapp):
    from pilot.overlay.hud import HudWindow

    hud = HudWindow({"details_provider": lambda: ["l1", "l2"]})
    hud.set_state(HudState(step_short="s", next_short="n"))
    h0 = hud.height()
    hud.set_details_visible(True)
    assert hud.height() > h0
    assert hud._details[-2:] == ["l1", "l2"]
    hud.set_details_visible(False)
    assert hud.height() == h0


def test_hotkeys_released_while_another_app_is_in_front(qapp, monkeypatch):
    calls = []
    monkeypatch.setattr(hotkeys.winapi, "IS_WIN", True)
    monkeypatch.setattr(hotkeys.winapi, "register_hotkey", lambda i, m, vk: calls.append(("reg", i)) or True)
    monkeypatch.setattr(hotkeys.winapi, "unregister_hotkey", lambda i: calls.append(("unreg", i)))
    hk = hotkeys.HotkeyManager({})
    hk.set_active(True)
    n = len(hk._ids)
    assert n and all(c[0] == "reg" for c in calls)
    hk.set_active(False)                       # browser in front: Alt+E / Alt+H are free again
    assert not hk._ids and sum(c[0] == "unreg" for c in calls) == n
    hk.set_active(False)                       # idempotent
    assert sum(c[0] == "unreg" for c in calls) == n
