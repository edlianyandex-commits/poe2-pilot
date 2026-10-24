"""Toast bookkeeping: dedupe, TTL, stacking (max 2) and 150 ms fades. Pure logic."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pilot.contracts import Toast

FADE_S = 0.15
MAX_VISIBLE = 2


@dataclass
class _Entry:
    toast: Toast
    start: float

    @property
    def end(self) -> float:
        return self.start + max(self.toast.ttl_s, 0.0)


class ToastStack:
    def __init__(self, max_visible: int = MAX_VISIBLE, fade_s: float = FADE_S):
        self.max_visible = max_visible
        self.fade_s = fade_s
        self._entries: list[_Entry] = []
        self._seen: set[tuple[str, str]] = set()

    def update(self, toasts: Iterable[Toast], now: float) -> None:
        """Feed the toasts currently present in HudState. New ones start their own TTL;
        a toast the source keeps repeating is not re-shown until it disappears first."""
        current = set()
        for t in toasts:
            key = (t.text, t.kind)
            current.add(key)
            if key not in self._seen:
                self._seen.add(key)
                self.push(t, now)
        self._seen &= current

    def push(self, toast: Toast, now: float) -> None:
        if toast.ttl_s <= 0 or not toast.text:
            return
        self._entries.append(_Entry(toast, now))
        # entries beyond the stack limit can never be shown again (only newest N are)
        if len(self._entries) > self.max_visible:
            del self._entries[: len(self._entries) - self.max_visible]

    def visible(self, now: float) -> list[tuple[Toast, float]]:
        """[(toast, alpha 0..1)], oldest first (top to bottom)."""
        self._entries = [e for e in self._entries if now < e.end]
        out = []
        for e in self._entries[-self.max_visible:]:
            a_in = (now - e.start) / self.fade_s if self.fade_s > 0 else 1.0
            a_out = (e.end - now) / self.fade_s if self.fade_s > 0 else 1.0
            alpha = max(0.0, min(1.0, a_in, a_out))
            out.append((e.toast, alpha))
        return out

    def active(self) -> bool:
        return bool(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self._seen.clear()
