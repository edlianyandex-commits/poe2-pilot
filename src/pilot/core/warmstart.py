"""Warm start: rebuild RunEngine state when the app starts in the middle of a run.

Scans Client.txt backwards for the start of the last run (the last
`Generating level 1 area "G1_1"` made by a level-1 character), then replays
everything from there to the end of the file into the engine, without sleeping.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from pilot.contracts import LevelUp
from pilot.core.engine import RunEngine
from pilot.core.parser import parse_line, parse_line_or_tick

_CHUNK = 4 << 20
_RE_START = re.compile(rb'area "G1_1" with seed')
_RE_LEVEL = re.compile(
    "(?:достигает \\d+ уровня|is now level \\d+)".encode("utf-8")
)
_PREV_CHAR_LEVEL = 20       # act 1 never takes a character past this: higher = previous character
_MAX_LEVEL_SCAN = 32 << 20  # how far back/forward to look for neighbouring level-ups


def _rfind_all(f, size: int, rx: re.Pattern, lo: int, hi: int) -> Iterator[int]:
    """Absolute offsets of regex matches in [lo, hi), latest first (chunked, overlap-safe)."""
    end = hi
    overlap = 128
    while end > lo:
        start = max(lo, end - _CHUNK)
        f.seek(start)
        data = f.read(min(end + overlap, size) - start)
        limit = end - start
        found = [m.start() for m in rx.finditer(data) if m.start() < limit]
        for off in reversed(found):
            yield start + off
        end = start


def _line_at(f, off: int, size: int) -> tuple[int, bytes]:
    """(start offset, bytes) of the line containing absolute offset `off`."""
    back = max(0, off - 400)
    f.seek(back)
    data = f.read(min(size, off + 400) - back)
    rel = off - back
    s = data.rfind(b"\n", 0, rel) + 1
    e = data.find(b"\n", rel)
    return back + s, data[s:] if e < 0 else data[s:e]


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").rstrip("\r")


def _next_levelup(f, start: int, size: int) -> tuple[int, int] | None:
    """(offset, level) of the first LevelUp at or after `start`."""
    for off in _first_forward(f, start, size):
        _, raw = _line_at(f, off, size)
        ev = parse_line(_decode(raw))
        if isinstance(ev, LevelUp):
            return off, ev.level
    return None


def _first_forward(f, start: int, size: int) -> Iterator[int]:
    hi = min(size, start + _MAX_LEVEL_SCAN)
    pos = start
    while pos < hi:
        f.seek(pos)
        data = f.read(min(_CHUNK, hi - pos) + 128)
        limit = min(_CHUNK, hi - pos)
        for m in _RE_LEVEL.finditer(data):
            if m.start() < limit:
                yield pos + m.start()
        pos += limit


def _prev_levelup_level(f, before: int, size: int) -> int | None:
    for off in _rfind_all(f, size, _RE_LEVEL, max(0, before - _MAX_LEVEL_SCAN), before):
        _, raw = _line_at(f, off, size)
        ev = parse_line(_decode(raw))
        if isinstance(ev, LevelUp):
            return ev.level
    return None


def find_run_start(path: str | Path, max_bytes: int = 200_000_000) -> int | None:
    """Byte offset of the line that started the last run, or None."""
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        lo = max(0, size - max_bytes)
        best: int | None = None
        best_key: object = ()
        for off in _rfind_all(f, size, _RE_START, lo, size):
            line_start, raw = _line_at(f, off, size)
            nxt = _next_levelup(f, line_start, size)
            if nxt is not None:
                ok, key = nxt[1] <= 2, nxt[0]
            else:
                prev = _prev_levelup_level(f, line_start, size)
                ok, key = prev is None or prev >= _PREV_CHAR_LEVEL, None
            if not ok:
                if best is not None:
                    break           # earlier candidates belong to older runs
                continue
            if best is not None and key != best_key:
                break               # same-run revisits share the same next level-up
            best, best_key = line_start, key
        return best


def warm_start(engine: RunEngine, path: str | Path, max_bytes: int = 200_000_000,
               end: list[int] | None = None) -> bool:
    """Feed the last run found in `path` into `engine`. True if a run was found.

    `end`, if given, receives the byte offset just after the last complete line fed, so a
    LogWatcher can continue exactly there (nothing written meanwhile is lost; a line still
    being written is read whole later).
    """
    try:
        start = find_run_start(path, max_bytes)
    except OSError:
        return False
    if start is None:
        return False
    engine.set_quiet(True)
    pos = start
    try:
        with open(path, "rb") as f:
            f.seek(start)
            tail = b""
            while True:
                chunk = f.read(_CHUNK)
                if not chunk:
                    break
                parts = (tail + chunk).split(b"\n")
                tail = parts.pop()
                for raw in parts:
                    pos += len(raw) + 1
                    ev = parse_line_or_tick(_decode(raw))
                    if ev is not None:
                        engine.feed(ev)
    finally:
        engine.set_quiet(False)
        engine.clear_toasts()
        if end is not None:
            end.append(pos)
    return True
