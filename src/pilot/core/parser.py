"""Client.txt line parser: `parse_line(line) -> Event | None` (ru + en clients).

Hot path: the real log is 70MB+, so most lines must be rejected by a couple of
cheap string checks before any regex runs.
"""
from __future__ import annotations

import re
from datetime import datetime

from pilot.contracts import (
    AreaGenerated, Death, Event, FocusChanged, GameClosed, LevelUp,
    LoadingScreen, PassiveAllocated, SceneEntered,
)

_RE_AREA = re.compile(r'Generating level (\d+) area "([^"]+)" with seed (\d+)')
_RE_LOADING = re.compile(r"\[LOADING SCREEN\] \((.*)\) Duration = ([\d.,]+) seconds")
_RE_LEVEL = re.compile(
    r": (\S+) \(([^)]+)\) (?:достигает (\d+) уровня|is now level (\d+))"
)
_RE_DEATH = re.compile(r": (\S+) (?:был[аио]? повержен[аоы]?\.|has been slain\.)")
_RE_PASSIVE = re.compile(
    r"Successfully (allocated|unallocated) passive skill id: (.+?), name: (.*)"
)

_SCENE_PREFIX = "[SCENE] Set Source ["
_SCENE_IGNORED = frozenset(("(null)", "(unknown)", ""))
_FIRST_CHARS = frozenset("G[S:C")


def parse_ts(line: str) -> datetime | None:
    """Parse the leading `YYYY/MM/DD HH:MM:SS` (naive local time); None if absent."""
    if len(line) < 19 or line[4] != "/" or line[7] != "/" or line[13] != ":":
        return None
    try:
        return datetime(
            int(line[0:4]), int(line[5:7]), int(line[8:10]),
            int(line[11:13]), int(line[14:16]), int(line[17:19]),
        )
    except ValueError:
        return None


def parse_line(line: str) -> Event | None:
    """Return the Event encoded by one log line, or None if irrelevant."""
    end = line.find("] ", 20)
    if end < 0:
        return None
    msg = line[end + 2:]
    if not msg or msg[0] not in _FIRST_CHARS:
        return None
    ev = _classify(msg)
    if ev is None:
        return None
    ts = parse_ts(line)
    if ts is None:
        return None
    return ev(ts)


def _classify(msg: str):
    """Return a factory ts -> Event for `msg`, or None."""
    c = msg[0]
    if c == "G":
        if msg.startswith("Generating level"):
            m = _RE_AREA.match(msg)
            if m:
                lvl, area, seed = int(m[1]), m[2], int(m[3])
                return lambda ts: AreaGenerated(ts, area, lvl, seed)
        return None
    if c == "[":
        if msg.startswith(_SCENE_PREFIX):
            name = msg[len(_SCENE_PREFIX):].rstrip("\r\n")
            if name.endswith("]"):
                name = name[:-1]
            if name in _SCENE_IGNORED:
                return None
            return lambda ts: SceneEntered(ts, name)
        if msg.startswith("[LOADING SCREEN]"):
            m = _RE_LOADING.match(msg)
            if m:
                name, secs = m[1], float(m[2].replace(",", "."))
                return lambda ts: LoadingScreen(ts, name, secs)
            return None
        if msg.startswith("[WINDOW] "):
            if msg.startswith("[WINDOW] Lost focus"):
                return lambda ts: FocusChanged(ts, False)
            if msg.startswith("[WINDOW] Gained focus"):
                return lambda ts: FocusChanged(ts, True)
        return None
    if c == ":":
        m = _RE_LEVEL.match(msg)
        if m:
            name, cls, lvl = m[1], m[2], int(m[3] or m[4])
            return lambda ts: LevelUp(ts, name, cls, lvl)
        m = _RE_DEATH.match(msg)
        if m:
            name = m[1]
            return lambda ts: Death(ts, name)
        return None
    if c == "S":
        m = _RE_PASSIVE.match(msg)
        if m:
            alloc, nid, nm = m[1] == "allocated", m[2], m[3].rstrip("\r\n")
            return lambda ts: PassiveAllocated(ts, nid, nm, alloc)
        return None
    if c == "C" and msg.startswith("Closing game gracefully"):
        return lambda ts: GameClosed(ts)
    return None
