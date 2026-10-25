"""Tail Client.txt on a daemon thread, and replay old logs by their timestamps."""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

from pilot.core.parser import parse_ts

log = logging.getLogger(__name__)
_CHUNK = 1 << 20


class LogWatcher:
    """Poll `path` and call `on_line(line)` for every new complete line (no newline)."""

    def __init__(self, path: str | Path, on_line: Callable[[str], None],
                 from_end: bool = True, poll_interval: float = 0.2,
                 start_offset: int | None = None) -> None:
        self.path = Path(path)
        self.start_offset = start_offset     # continue a warm start exactly where it stopped
        self.on_line = on_line
        self.from_end = from_end
        self.poll_interval = poll_interval
        self._pos = 0
        self._ident: tuple[int, int] | None = None
        self._buf = b""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Begin tailing (position is fixed synchronously so nothing after start() is lost)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._buf = b""
        self._pos, self._ident = 0, None
        try:
            st = self.path.stat()
            self._ident = (st.st_dev, st.st_ino)
            if self.start_offset is not None and self.start_offset <= st.st_size:
                self._pos = self.start_offset
            elif self.from_end:
                self._pos = st.st_size
        except OSError:
            pass
        self._thread = threading.Thread(target=self._run, name="LogWatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t is not threading.current_thread():
            t.join(timeout=2.0)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:  # keep the thread alive no matter what
                log.exception("LogWatcher poll failed")
            self._stop.wait(self.poll_interval)

    def poll_once(self) -> int:
        """Read whatever was appended; returns number of lines delivered."""
        try:
            st = os.stat(self.path)
        except OSError:
            return 0  # file missing (rotation in progress / game not installed yet)
        ident = (st.st_dev, st.st_ino)
        replaced = (self._ident is not None and ident != self._ident
                    and ident[1] != 0)
        if replaced or st.st_size < self._pos:
            self._pos, self._buf = 0, b""  # rotated or truncated: restart from the top
        self._ident = ident
        if st.st_size == self._pos:
            return 0
        n = 0
        try:
            with open(self.path, "rb") as f:
                f.seek(self._pos)
                while not self._stop.is_set():
                    chunk = f.read(_CHUNK)
                    if not chunk:
                        break
                    self._pos += len(chunk)
                    n += self._deliver(chunk)
        except OSError:
            pass
        return n

    def _deliver(self, chunk: bytes) -> int:
        data = self._buf + chunk
        parts = data.split(b"\n")
        self._buf = parts.pop()  # incomplete tail (maybe empty)
        for raw in parts:
            line = raw.decode("utf-8", errors="replace").rstrip("\r")
            try:
                self.on_line(line)
            except Exception:
                log.exception("on_line callback failed")
        return len(parts)


def replay(path: str | Path, on_line: Callable[[str], None], speed: float = 50.0,
           max_sleep_s: float = 2.0, stop: threading.Event | None = None,
           sleep: Callable[[float], None] = time.sleep) -> int:
    """Feed a log file line by line, sleeping (timestamp delta / speed) between lines.

    speed <= 0 means no sleeping. Each single sleep is capped at `max_sleep_s`
    so hours-long gaps (game closed) don't stall demos. Returns lines delivered.
    """
    prev = None
    n = 0
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        for raw in f:
            if stop is not None and stop.is_set():
                break
            line = raw.rstrip("\r\n")
            if speed > 0:
                ts = parse_ts(line)
                if ts is not None:
                    if prev is not None:
                        dt = (ts - prev).total_seconds() / speed
                        if dt > 0:
                            sleep(min(dt, max_sleep_s))
                    prev = ts
            on_line(line)
            n += 1
    return n
