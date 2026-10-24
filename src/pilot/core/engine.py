"""RunEngine: turns parsed log events into HudState (SnapshotSource) and handles hotkey Actions."""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Callable

from pilot.contracts import (
    AreaGenerated, Death, Event, FocusChanged, GameClosed, HudState, LevelPlan,
    LevelUp, LoadingScreen, PassiveAllocated, SceneEntered, Toast,
)
from pilot.core.parser import parse_line
from pilot.core.route import Route
from pilot.core.splits import RunRecord, SplitStore

log = logging.getLogger(__name__)

START_AREA = "G1_1"
END_AREA = "G_Endgame_Town"
AFK_GAP_S = 900.0          # gaps between log events longer than this = game was closed/idle
LEVEL_WARN_MARGIN = 3      # warn when char level < area level - 3
MIN_ABANDON_SAVE_S = 30.0  # don't litter history with instantly-reset runs
MAX_TOAST = 40
LOOKAHEAD = 6              # max steps the pointer may jump forward on a zone change
_RE_ACT = re.compile(r"^(?:G(\d)|P(\d))_")


def is_town(area_id: str) -> bool:
    return "town" in area_id.lower()


def is_hideout(area_id: str) -> bool:
    return "hideout" in area_id.lower()


def fmt_time(s: float) -> str:
    """1:12:40 or 12:40."""
    s = int(abs(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def fmt_delta(d: float) -> str:
    """-0:42 (ahead) / +0:42 (behind), with a real minus sign."""
    return ("−" if d < 0 else "+") + fmt_time(d)


def _clip(text: str, n: int = MAX_TOAST) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def area_act(area_id: str) -> int | None:
    """Act number from a zone id: G2_x -> 2, P1_x -> 101."""
    m = _RE_ACT.match(area_id)
    if not m:
        return None
    return int(m[1]) if m[1] else 100 + int(m[2])


class RunEngine:
    """Thread-safe; feed() from the log thread, snapshot()/actions from the UI thread."""

    def __init__(self, route: Route, plan: LevelPlan | None = None,
                 store: SplitStore | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 afk_gap_s: float = AFK_GAP_S) -> None:
        self.route = route
        self.plan = plan
        self.store = store
        self._clock = clock
        self._afk = afk_gap_s
        self._lock = threading.RLock()
        # character / zone
        self._char_name: str | None = None
        self._char_level: int | None = None
        self._area_id = ""
        self._area_name = ""
        self._area_level: int | None = None
        self._awaiting_scene = False
        self._focused = True
        self._closed = False
        # time base
        self._last_ts = None
        self._last_clock = 0.0
        # run
        self._armed = False
        self._finished_before = False
        self._reset_run_state()
        self._toasts: list[tuple[Toast, float]] = []

    # ---------------- public API ----------------

    def feed_line(self, line: str) -> None:
        """Convenience: parse a raw log line and feed the resulting event."""
        ev = parse_line(line)
        if ev is not None:
            self.feed(ev)

    def feed(self, ev: Event) -> None:
        with self._lock:
            self._advance_time(ev)
            if isinstance(ev, AreaGenerated):
                self._on_area(ev)
            elif isinstance(ev, SceneEntered):
                if self._awaiting_scene:
                    self._area_name = ev.name
                    self._awaiting_scene = False
            elif isinstance(ev, LoadingScreen):
                if self._running:
                    self._elapsed = max(0.0, self._elapsed - ev.seconds)
            elif isinstance(ev, LevelUp):
                self._on_level(ev)
            elif isinstance(ev, Death):
                if self._running:
                    self._deaths += 1
            elif isinstance(ev, PassiveAllocated):
                self._on_passive(ev)
            elif isinstance(ev, FocusChanged):
                self._focused = ev.focused
            elif isinstance(ev, GameClosed):
                self._closed = True

    def snapshot(self) -> HudState:
        with self._lock:
            steps = self.route.steps
            i = self._step
            cur = steps[i] if i < len(steps) else None
            nxt = steps[i + 1] if i + 1 < len(steps) else None
            act = cur.act if cur else None
            if act is None or not self._running and not self._finished:
                act = area_act(self._area_id) or act
            return HudState(
                act=act,
                area_name=self._area_name,
                area_level=self._area_level,
                char_level=self._char_level,
                step_short=cur.short if cur else None,
                next_short=nxt.short if nxt else None,
                step_index=i,
                step_total=len(steps),
                run_time_s=self._run_time_now(),
                split_delta_s=self._split_delta,
                toasts=self._active_toasts(),
                warn=self._level_warning(),
                game_focused=self._focused and not self._closed,
                running=self._running,
            )

    def next_step(self) -> None:
        with self._lock:
            last = max(len(self.route.steps) - 1, 0)
            if self._running and self._step < last:
                self._advance_to(self._step + 1)
            else:
                self._step = min(self._step + 1, last)

    def prev_step(self) -> None:
        with self._lock:
            self._step = max(self._step - 1, 0)

    def reset_run(self) -> None:
        """Abandon the current run (saved if it lasted long enough) and wait for the next start."""
        with self._lock:
            if self._running:
                self._save(status="abandoned")
            self._reset_run_state()
            self._armed = True

    def upcoming(self, n: int = 3) -> list[str]:
        """Shorts of the next `n` steps after the current one."""
        with self._lock:
            i = self._step
            return [st.short for st in self.route.steps[i + 1:i + 1 + n]]

    def details(self) -> list[str]:
        """Lines for the details panel: current step detail, reward, then upcoming(3)."""
        with self._lock:
            i = self._step
            lines: list[str] = []
            if i < len(self.route.steps):
                cur = self.route.steps[i]
                if cur.detail:
                    lines.append(cur.detail)
                if cur.reward:
                    lines.append(f"Награда: {cur.reward}")
            return lines + self.upcoming(3)

    # read-only helpers for UI/tests
    @property
    def finished(self) -> bool:
        with self._lock:
            return self._finished

    def split_times(self) -> dict[str, float]:
        """Cumulative game seconds per split id hit so far in the current/last run."""
        with self._lock:
            return dict(self._hits)

    # ---------------- internals ----------------

    def _reset_run_state(self) -> None:
        self._running = False
        self._finished = False
        self._step = 0
        self._elapsed = 0.0
        self._started_iso = ""
        self._hits: dict[str, float] = {}
        self._split_delta: float | None = None
        self._deaths = 0

    def _advance_time(self, ev: Event) -> None:
        """Accumulate in-game time using log timestamps (so replays are exact)."""
        if self._last_ts is not None and self._running:
            dt = (ev.ts - self._last_ts).total_seconds()
            if not self._closed and 0 < dt <= self._afk:
                self._elapsed += dt
        if self._closed:           # first event after the game was closed = restarted
            self._closed = False
            self._focused = True
        self._last_ts = ev.ts
        self._last_clock = self._clock()

    def _run_time_now(self) -> float:
        if not self._running:
            return self._elapsed
        extra = 0.0 if self._closed else max(0.0, self._clock() - self._last_clock)
        return self._elapsed + min(extra, self._afk)

    def _toast(self, text: str, kind: str, ttl: float = 3.0) -> None:
        t = Toast(_clip(text), kind, ttl)
        self._toasts.append((t, self._clock() + ttl))

    def _active_toasts(self) -> tuple[Toast, ...]:
        now = self._clock()
        self._toasts = [(t, exp) for t, exp in self._toasts if exp > now]
        return tuple(t for t, _ in self._toasts)

    def _level_warning(self) -> str | None:
        a = self._area_id
        if (self._char_level is None or self._area_level is None or not a
                or is_town(a) or is_hideout(a)):
            return None
        diff = self._area_level - self._char_level
        if diff > LEVEL_WARN_MARGIN:
            return f"⚠ Ур. ниже зоны −{diff}"
        return None

    # ---- event handlers ----

    def _on_level(self, ev: LevelUp) -> None:
        self._char_name, self._char_level = ev.character, ev.level
        text = f"Ур. {ev.level}"
        hint = self.plan.hint_for(ev.level) if self.plan else None
        if hint is not None:
            parts = [f"+{p}" if not p.startswith(("+", "-")) else p for p in hint.passives]
            parts += list(hint.gems)
            if hint.note:
                parts.append(hint.note)
            if parts:
                text += ": " + " · ".join(parts)
        self._toast(text, "level")

    def _on_passive(self, ev: PassiveAllocated) -> None:
        if self.plan is None or not ev.allocated:
            return
        if ev.node_id not in self.plan.planned_node_ids:
            self._toast("Пассивка не по плану", "warn")

    def _on_area(self, ev: AreaGenerated) -> None:
        z = ev.area_id
        self._area_id, self._area_level = z, ev.area_level
        self._area_name = ""
        self._awaiting_scene = True
        if not self._running:
            if z == START_AREA and (self._armed or self._finished_before
                                    or self._char_level in (None, 1)):
                self._start_run(ev)
            else:
                return
        if is_hideout(z):
            return
        self._on_zone_in_run(z)

    def _start_run(self, ev: AreaGenerated) -> None:
        self._reset_run_state()
        self._running = True
        self._armed = False
        self._started_iso = ev.ts.isoformat(timespec="seconds")
        self._toast("Ран начат", "zone")

    def _on_zone_in_run(self, z: str) -> None:
        steps = self.route.steps
        i = self._step
        new = i
        if i < len(steps):
            cur = steps[i]
            nxt = steps[i + 1] if i + 1 < len(steps) else None
            if (cur.done_on_enter is not None and z == cur.done_on_enter)                     or (nxt is not None and nxt.area == z):
                new = i + 1                           # normal advance (towns included)
            elif not is_town(z):                      # skipped ahead, within the window
                for j in range(i + 2, min(i + LOOKAHEAD, len(steps) - 1) + 1):
                    if steps[j].area == z:
                        new = j
                        break
        self._advance_to(new, toast_idx=new if new < len(steps) and steps[new].area == z else None)
        if z == END_AREA:
            self._finish()

    def _advance_to(self, new: int, toast_idx: int | None = None) -> None:
        """Move the pointer; splits of steps passed over are recorded now (silently)."""
        steps = self.route.steps
        for k in range(self._step, min(new, len(steps))):
            self._hit_split(k, toast=False)
        self._step = new
        if toast_idx is not None:
            self._hit_split(toast_idx, toast=True)

    def _hit_split(self, idx: int, toast: bool) -> None:
        step = self.route.steps[idx]
        if not step.split or step.id in self._hits:
            return
        t = self._elapsed
        self._hits[step.id] = t
        d = None
        if self.store is not None:
            for sid in step.all_ids:
                d = self.store.delta(self.route.id, sid, t)
                if d is not None:
                    break
        self._split_delta = d
        if toast:
            tail = fmt_delta(d) if d is not None else fmt_time(t)
            self._toast(f"{_clip(step.short, MAX_TOAST - len(tail) - 1)} {tail}", "split")

    def _finish(self) -> None:
        total = self._elapsed
        delta = None
        if self.store is not None:
            pb = self.store.pb_total(self.route.id)
            delta = None if pb is None else total - pb
        self._step = len(self.route.steps)
        self._running = False
        self._finished = True
        self._finished_before = True
        self._save(status="finished")
        tail = f" ({fmt_delta(delta)})" if delta is not None else ""
        self._toast(f"Финиш {fmt_time(total)}{tail}", "split", ttl=6.0)

    def _save(self, status: str) -> None:
        if self.store is None:
            return
        if status == "abandoned" and self._elapsed < MIN_ABANDON_SAVE_S:
            return
        rec = RunRecord(self.route.id, status, self._started_iso, self._elapsed,
                        dict(self._hits), self._deaths)
        try:
            self.store.save_run(rec)
        except OSError:
            log.exception("could not save run")
