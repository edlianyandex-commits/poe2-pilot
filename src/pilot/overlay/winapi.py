"""Thin ctypes helpers. Everything degrades to a no-op off Windows (tests, offscreen)."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

IS_WIN = sys.platform == "win32"

GAME_EXES = (
    "pathofexilesteam.exe",
    "pathofexile.exe",
    "pathofexile_x64.exe",
    "pathofexile_x64steam.exe",
)

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER = 0x1, 0x2, 0x4
SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x10, 0x20
HWND_TOPMOST = -1

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    _get_long = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
    _set_long = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    _get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_long.restype = ctypes.c_ssize_t
    _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _set_long.restype = ctypes.c_ssize_t


@dataclass(frozen=True)
class Foreground:
    pid: int
    exe: str | None  # lower-case basename, None if it could not be resolved


def foreground_info() -> Foreground | None:
    """Foreground window's process. None = cannot be determined (non-Windows)."""
    if not IS_WIN:
        return None
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return Foreground(0, None)
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = None
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                exe = os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(h)
    return Foreground(int(pid.value), exe)


def is_game_foreground(fg: Foreground | None, game_exes=GAME_EXES, own_pid: int | None = None) -> bool:
    """True if the HUD should be visible: game (or our own process) is in front."""
    if fg is None:
        return True
    if own_pid is None:
        own_pid = os.getpid()
    if fg.pid == own_pid:
        return True
    names = {n.lower() for n in game_exes}
    return fg.exe is not None and fg.exe in names


def make_click_through(hwnd: int, interactive: bool = False) -> None:
    """Layered + toolwindow + no-activate (+ transparent unless interactive)."""
    if not IS_WIN or not hwnd:
        return
    h = wintypes.HWND(hwnd)
    style = _get_long(h, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
    if interactive:
        style &= ~WS_EX_TRANSPARENT
    else:
        style |= WS_EX_TRANSPARENT
    _set_long(h, GWL_EXSTYLE, style)
    user32.SetWindowPos(h, None, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)


def keep_topmost(hwnd: int) -> None:
    if not IS_WIN or not hwnd:
        return
    user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def key_down(vk: int) -> bool:
    if not IS_WIN:
        return False
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def register_hotkey(hk_id: int, mods: int, vk: int) -> bool:
    if not IS_WIN:
        return False
    return bool(user32.RegisterHotKey(None, hk_id, mods, vk))


def unregister_hotkey(hk_id: int) -> None:
    if IS_WIN:
        user32.UnregisterHotKey(None, hk_id)
