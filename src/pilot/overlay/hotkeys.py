"""Global hotkeys without hooks or injection.

* Toggles: RegisterHotKey (thread-level, delivered as WM_HOTKEY through a Qt native event filter).
* Hold-to-show key: GetAsyncKeyState polled at ~30 Hz.
Hotkeys only call the callbacks given to HotkeyManager (Actions / HUD methods);
nothing is ever sent to the game.
"""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer

from . import winapi

log = logging.getLogger(__name__)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY = 0x0312

DEFAULT_HOTKEYS = {
    "details": "alt+q",   # hold
    "next": "alt+]",
    "prev": "alt+[",
    "reset": "alt+r",
    "edit": "alt+e",
    "hide": "alt+h",
}

_MODS = {
    "alt": MOD_ALT, "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "shift": MOD_SHIFT, "win": MOD_WIN, "super": MOD_WIN, "meta": MOD_WIN,
}
_PUNCT = {
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF,
    "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}
_NAMED = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09,
    "backspace": 0x08, "insert": 0x2D, "delete": 0x2E, "del": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pgup": 0x21, "pagedown": 0x22, "pgdn": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}
# virtual keys of modifiers for GetAsyncKeyState polling
_MOD_VKS = {MOD_ALT: (0x12,), MOD_CONTROL: (0x11,), MOD_SHIFT: (0x10,), MOD_WIN: (0x5B, 0x5C)}


def parse_hotkey(spec: str) -> tuple[int, int]:
    """'alt+q' -> (MOD_ALT, 0x51). Raises ValueError on garbage."""
    tokens = [t.strip().lower() for t in spec.replace(" ", "").split("+")]
    # allow literal '+' key: "alt++" -> tokens ['alt', '', '']
    if len(tokens) >= 3 and tokens[-1] == "" and tokens[-2] == "":
        tokens = tokens[:-2] + ["="]  # '+' is Shift+'=' physically; map to the '=' key
    tokens = [t for t in tokens if t]
    if not tokens:
        raise ValueError(f"empty hotkey: {spec!r}")
    mods, vk = 0, None
    for t in tokens:
        if t in _MODS:
            mods |= _MODS[t]
            continue
        if vk is not None:
            raise ValueError(f"more than one key in hotkey: {spec!r}")
        if len(t) == 1 and "a" <= t <= "z":
            vk = ord(t.upper())
        elif len(t) == 1 and "0" <= t <= "9":
            vk = ord(t)
        elif t in _PUNCT:
            vk = _PUNCT[t]
        elif t in _NAMED:
            vk = _NAMED[t]
        elif t[0] == "f" and t[1:].isdigit() and 1 <= int(t[1:]) <= 24:
            vk = 0x70 + int(t[1:]) - 1
        else:
            raise ValueError(f"unknown key {t!r} in hotkey {spec!r}")
    if vk is None:
        raise ValueError(f"no key in hotkey: {spec!r}")
    return mods, vk


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, manager: "HotkeyManager"):
        super().__init__()
        self._m = manager

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt API)
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                import ctypes
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    self._m.dispatch_id(int(msg.wParam))
                    return True, 0
        except Exception:  # never let a hotkey bug break the Qt loop
            log.exception("native event filter")
        return False, 0


class HotkeyManager:
    """callbacks: next, prev, reset, edit, hide -> fn();  details -> fn(bool down)."""

    POLL_MS = 33

    def __init__(self, callbacks: dict[str, Callable], hotkeys: dict[str, str] | None = None,
                 key_state: Callable[[int], bool] | None = None):
        self.callbacks = callbacks
        spec = dict(DEFAULT_HOTKEYS)
        for name, s in (hotkeys or {}).items():
            if name in DEFAULT_HOTKEYS:
                spec[name] = s
            else:
                log.warning("unknown hotkey name %r (known: %s)", name, ", ".join(DEFAULT_HOTKEYS))
        self.specs = spec
        self.parsed: dict[str, tuple[int, int]] = {}
        for name, s in spec.items():
            try:
                self.parsed[name] = parse_hotkey(s)
            except ValueError as e:
                log.warning("bad hotkey %s: %s", name, e)
        self._key_state = key_state or winapi.key_down
        self._ids: dict[int, str] = {}
        self.failed: list[str] = []
        self._details_down = False
        self._timer: QTimer | None = None
        self._filter: _Filter | None = None

    # ---- lifecycle
    def start(self) -> None:
        from PySide6.QtCore import QCoreApplication
        if winapi.IS_WIN:
            self._filter = _Filter(self)
            QCoreApplication.instance().installNativeEventFilter(self._filter)
            for i, (name, (mods, vk)) in enumerate(self.parsed.items(), start=1):
                if name == "details":
                    continue  # polled, not registered
                if winapi.register_hotkey(0xB000 + i, mods | MOD_NOREPEAT, vk):
                    self._ids[0xB000 + i] = name
                else:
                    self.failed.append(name)
                    log.warning("hotkey %s (%s) is taken by another app", name, self.specs[name])
        self._timer = QTimer()
        self._timer.setInterval(self.POLL_MS)
        self._timer.timeout.connect(self.poll)
        self._timer.start()

    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
        for hk_id in list(self._ids):
            winapi.unregister_hotkey(hk_id)
        self._ids.clear()
        if self._filter is not None:
            from PySide6.QtCore import QCoreApplication
            app = QCoreApplication.instance()
            if app:
                app.removeNativeEventFilter(self._filter)
            self._filter = None

    # ---- dispatch
    def dispatch_id(self, hk_id: int) -> None:
        name = self._ids.get(hk_id)
        if name:
            self.fire(name)

    def fire(self, name: str) -> None:
        cb = self.callbacks.get(name)
        if cb is None:
            return
        try:
            cb()
        except Exception:
            log.exception("hotkey %s callback failed", name)

    def is_combo_down(self, mods: int, vk: int) -> bool:
        if not self._key_state(vk):
            return False
        for flag, vks in _MOD_VKS.items():
            if mods & flag and not any(self._key_state(v) for v in vks):
                return False
        return True

    def poll(self) -> None:
        """Hold-to-show: edge-triggered callbacks('details')(True/False)."""
        combo = self.parsed.get("details")
        if combo is None:
            return
        down = self.is_combo_down(*combo)
        if down != self._details_down:
            self._details_down = down
            cb = self.callbacks.get("details")
            if cb:
                try:
                    cb(down)
                except Exception:
                    log.exception("details callback failed")
