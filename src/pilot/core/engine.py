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
from pilot.core.parser import parse_line_or_tick
from pilot.core.route import Route, route_area
from pilot.core.splits import RunRecord, SplitStore, ZoneSegment

log = logging.getLogger(__name__)

START_AREA = "G1_1"
END_AREA = "G_Endgame_Town"
AFK_GAP_S = 900.0          # gaps between log events longer than this = game was closed/idle
LEVEL_WARN_MARGIN = 3      # warn when char level < area level - 3
MIN_ABANDON_SAVE_S = 30.0  # don't litter history with instantly-reset runs
MAX_TOAST = 40
OFF_PLAN_TOAST_GAP_S = 60.0  # min gap between "off plan" toasts
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
                 afk_gap_s: float = AFK_GAP_S, pause_when_unfocused: bool = True) -> None:
        self.route = route
        self.plan = plan
        self.store = store
        self._clock = clock
        self._afk = afk_gap_s
        self._pause_unfocused = pause_when_unfocused
        # manual pause (Alt+P): intervals on self._clock, since the log never records it
        self._mpause_start: float | None = None
        self._mpauses: list[tuple[float, float]] = []
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
        self._counted_since_zone = 0.0       # timer seconds added since the last zone generation
        # run
        self._armed = False
        self._finished_before = False
        self._tentative = False
        self._pending_new: tuple | None = None   # (Riverbank AreaGenerated, game time then)
        self._riverbank: tuple | None = None     # the last Riverbank entry, same shape
        n = len(route.steps)
        self._marks = tuple(k / n for k, st in enumerate(route.steps) if st.split) if n else ()
        self._reset_run_state()
        self._toasts: list[tuple[Toast, float]] = []
        self._off_plan = 0
        self._quiet = False
        self._allocated: set[str] | None = None   # None = state unknown (no run start seen)
        self._off_plan_toast_at: float | None = None

    # ---------------- public API ----------------

    def feed_line(self, line: str) -> None:
        """Convenience: parse a raw log line and feed the resulting event."""
        ev = parse_line_or_tick(line)
        if ev is not None:
            self.feed(ev)

    def feed(self, ev: Event) -> None:
        with self._lock:
            self._advance_time(ev)
            self._account()
            if isinstance(ev, AreaGenerated):
                # the load runs from this line to the [LOADING SCREEN] line that ends it
                self._counted_since_zone = 0.0
                self._on_area(ev)
            elif isinstance(ev, SceneEntered):
                if self._awaiting_scene:
                    self._area_name = ev.name
                    self._awaiting_scene = False
                    if self._seg is not None and not self._seg.area_name:
                        self._seg.area_name = ev.name
            elif isinstance(ev, LoadingScreen):
                if self._running:
                    # only take back what the timer really counted (not paused / AFK / closed)
                    took = min(ev.seconds, self._counted_since_zone)
                    self._elapsed = max(0.0, self._elapsed - took)
                    self._counted_since_zone = 0.0
                    if self._seg is not None:
                        self._seg.loading_s += ev.seconds
                    self._account()
            elif isinstance(ev, LevelUp):
                self._on_level(ev)
            elif isinstance(ev, Death):
                if self._running:
                    self._deaths += 1
                    if self._seg is not None:
                        self._seg.deaths += 1
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
            j = None
            if cur:                           # next open after this one, else a skipped leftover
                j = self._first_open(i, exclude_area=cur.area)
                if j is None:
                    j = self._first_open(exclude_area=cur.area)
            nxt = steps[j] if j is not None else None
            act = cur.act if cur else None
            if act is None or not self._running and not self._finished:
                act = area_act(self._area_id) or act
            total = len(steps)
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
                paused=self._running and self._paused(),
                step_kind=cur.display_kind if cur else None,
                next_kind=nxt.display_kind if nxt else None,
                progress=(1.0 if self._finished else min(len(self._done) / total, 1.0)) if total else 0.0,
                split_marks=self._marks,
            )

    def next_step(self) -> None:
        with self._lock:
            if self._step < len(self.route.steps):          # manual fix-up: this step is done
                if self._running:
                    self._complete(self._step, toast=False)
                else:
                    self._done.add(self._step)
            nxt = self._first_open()
            if nxt is not None:
                self._step = nxt

    def prev_step(self) -> None:
        with self._lock:
            self._step = max(self._step - 1, 0)
            self._done.discard(self._step)

    def reset_run(self) -> None:
        """Abandon the current run (saved if it lasted long enough) and wait for the next start.

        Pressed in the Riverbank, the new run starts from that entry at once: a character
        already standing there would never generate the Riverbank again.
        """
        with self._lock:
            entry = self._riverbank if self._running and self._area_id == START_AREA else None
            since = max(0.0, self._elapsed - entry[1]) if entry else 0.0
            if self._running:
                self._save(status="abandoned")
            self._reset_run_state()
            self._armed = True
            if entry:
                self._restart_from(entry[0], since)
                log.info("run reset (Alt+R): restarted from Riverbank at %s", entry[0].ts)
            else:
                self._toast("Сброс: забег начнётся в Riverbank", "zone", 5.0)
                log.info("run reset (Alt+R): waiting for the Riverbank")

    def allocated_nodes(self) -> set[str] | None:
        """Passive node ids allocated since the run start; None if no run start was seen."""
        with self._lock:
            return None if self._allocated is None else set(self._allocated)

    def set_quiet(self, on: bool) -> None:
        """While quiet (warm start) finished/abandoned runs are not saved to the store."""
        with self._lock:
            self._quiet = on

    def clear_toasts(self) -> None:
        with self._lock:
            self._toasts.clear()
            self._off_plan_toast_at = None

    def upcoming(self, n: int = 3) -> list[str]:
        """Shorts of the next `n` steps after the current one."""
        with self._lock:
            out, k = [], self._step
            cur_area = self.route.steps[k].area if k < len(self.route.steps) else None
            while len(out) < n:
                k = self._first_open(k, exclude_area=cur_area)
                if k is None:
                    break
                out.append(self.route.steps[k].short)
            return out

    def details(self) -> list[str]:
        """Details panel lines: step detail, reward, gem setup for the char level (<=4), upcoming(3); <=10."""
        with self._lock:
            i = self._step
            lines: list[str] = []
            if self.plan is not None and self._area_id:
                lines.extend(self.plan.zone_hints.get(self._area_id, ())[:3])
            if i < len(self.route.steps):
                cur = self.route.steps[i]
                if cur.detail:
                    lines.append(cur.detail)
                if cur.reward:
                    lines.append(f"Награда: {cur.reward}")
            # no LevelUp line is logged for level 1, so a running run starts at 1
            level = self._char_level or (1 if self._running else None)
            if self.plan is not None and level is not None:
                gear_lv = max((lv for lv, h in self.plan.hints.items() if h.gear and lv <= level),
                              default=None)
                if gear_lv is not None:
                    lines.extend(self.plan.hints[gear_lv].gear[:2])
                lines.extend(self.plan.setup_for(level)[:3])
            return (lines + self.upcoming(3))[:10]

    def gem_rows(self) -> tuple:
        """Gem window content: the plan's GemRows for the current character level."""
        with self._lock:
            level = self._char_level or (1 if self._running else None)
            if self.plan is None or level is None:
                return ()
            return self.plan.gem_rows_for(level)

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
        self._pending_new = None
        self._step = 0
        self._done: set[int] = set()
        self._elapsed = 0.0
        self._started_iso = ""
        self._hits: dict[str, float] = {}
        self._split_delta: float | None = None
        self._deaths = 0
        self._segs: dict[str, ZoneSegment] = {}
        self._seg: ZoneSegment | None = None
        self._seg_mark = 0.0

    def _account(self) -> None:
        """Attribute game time elapsed since the last call to the current zone segment."""
        if self._running and self._seg is not None:
            self._seg.seconds += self._elapsed - self._seg_mark
        self._seg_mark = self._elapsed

    def _enter_zone(self, z: str) -> None:
        seg = self._segs.get(z)
        if seg is None:
            seg = self._segs[z] = ZoneSegment(z, "", self._elapsed, is_town=is_town(z) or is_hideout(z))
        seg.visits += 1
        self._seg = seg

    def _record(self, status: str) -> RunRecord:
        segs = [sg.to_dict() for sg in self._segs.values()]
        return RunRecord(self.route.id, status, self._started_iso, self._elapsed,
                         dict(self._hits), self._deaths, segs)

    def current_record(self, status: str = "incomplete") -> RunRecord | None:
        """Snapshot of the run in progress (None when no run was started)."""
        with self._lock:
            return self._record(status) if self._segs else None

    def _advance_time(self, ev: Event) -> None:
        """Accumulate in-game time using log timestamps (so replays are exact)."""
        now = self._clock()
        if self._last_ts is not None and self._running:
            dt = (ev.ts - self._last_ts).total_seconds()
            if not self._closed and not self._focus_paused() and 0 < dt <= self._afk:
                added = max(0.0, dt - self._manual_overlap(self._last_clock, now))
                self._elapsed += added
                self._counted_since_zone += added
        if self._closed:           # first event after the game was closed = restarted
            self._closed = False
            self._focused = True
        self._last_ts = ev.ts
        self._last_clock = now
        self._mpauses = [p for p in self._mpauses if p[1] > now - 2 * self._afk]   # keep it short

    def _focus_paused(self) -> bool:
        return self._pause_unfocused and not self._focused

    def _manual_overlap(self, a: float, b: float) -> float:
        """Seconds of manual pause inside [a, b] on self._clock."""
        spans = list(self._mpauses)
        if self._mpause_start is not None:
            spans.append((self._mpause_start, b))
        return sum(max(0.0, min(b, y) - max(a, x)) for x, y in spans)

    def _paused(self) -> bool:
        return self._mpause_start is not None or self._focus_paused()

    def _run_time_now(self) -> float:
        if not self._running:
            return self._elapsed
        if self._closed or self._focus_paused():
            return self._elapsed
        now = self._clock()
        extra = max(0.0, now - self._last_clock - self._manual_overlap(self._last_clock, now))
        return self._elapsed + min(extra, self._afk)

    def toggle_pause(self) -> None:
        """Alt+P: stop / resume the run timer (for the game's own pause menu)."""
        with self._lock:
            now = self._clock()
            if self._mpause_start is None:
                self._mpause_start = now
            else:
                self._mpauses.append((self._mpause_start, now))
                self._mpause_start = None
            log.info("timer %s (Alt+P)", "paused" if self._mpause_start is not None else "resumed")

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
        if self._running and self._tentative:
            self._tentative = False
            if ev.level > 2:                      # not a fresh character: there was no run
                self._reset_run_state()
                self._toasts.clear()
                self._allocated = None            # the old character's passives are unknown
                log.info("tentative run cancelled: %s is level %s", ev.character, ev.level)
        if self._pending_new is not None:
            entry_ev, entry_elapsed = self._pending_new
            self._pending_new = None
            if ev.level <= 2 and self._running:   # a new character took over mid-run
                self._restart_from(entry_ev, max(0.0, self._elapsed - entry_elapsed))
                log.info("new character %s: run restarted from Riverbank at %s", ev.character, entry_ev.ts)
        self._char_name, self._char_level = ev.character, ev.level
        hint = self.plan.hint_for(ev.level) if self.plan else None
        if hint is None:
            self._toast(f"Ур. {ev.level}", "level")
            return
        # passives and gems as separate toasts so neither gets clipped away
        passives = [f"+{p}" if not p.startswith(("+", "-")) else p for p in hint.passives]
        self._toast(f"Ур. {ev.level}: " + " · ".join(passives) if passives else f"Ур. {ev.level}",
                    "level", 4.0)
        extra = list(hint.gems) + ([hint.note] if hint.note else [])
        if extra:
            self._toast(" · ".join(extra), "level", 4.0)
        self._gear_toast(hint.gear)

    def _gear_toast(self, gear: tuple[str, ...]) -> None:
        """At most two items per toast; the rest are in the details panel."""
        if not gear:
            return
        text = " · ".join(gear[:2])
        if len(gear) > 2:
            text = f"{gear[0]} · +{len(gear) - 1} (Alt+Q)"
        self._toast(text, "gear", 5.0)

    def _zone_hint(self, z: str) -> None:
        """What to pick up in this zone (gems from NPCs and bosses): up to 2 toasts, rest in details."""
        lines = self.plan.zone_hints.get(z, ()) if self.plan else ()
        for text in lines[:2]:
            self._toast(text, "zone", 6.0)
        if len(lines) > 2:
            self._toast(f"+{len(lines) - 2} здесь (Alt+Q)", "zone", 6.0)

    def _ascendancy_hint(self, z: str) -> None:
        hint = self.plan.ascendancy.get(z) if self.plan else None
        if hint is not None and hint.passives:
            names = [p if p.startswith("★") else f"★ {p}" for p in hint.passives]
            self._toast(" · ".join(names), "level", 8.0)

    def _on_passive(self, ev: PassiveAllocated) -> None:
        if self._allocated is not None:
            if ev.allocated:
                self._allocated.add(ev.node_id)
            else:
                self._allocated.discard(ev.node_id)
        if self.plan is None or not ev.allocated:
            return
        if ev.node_id in self.plan.planned_node_ids:
            return
        # one toast per respec burst, not one per node
        self._off_plan += 1
        now = self._clock()
        if self._off_plan_toast_at is None or now - self._off_plan_toast_at >= OFF_PLAN_TOAST_GAP_S:
            self._off_plan_toast_at = now
            self._toast(f"Пассивки не по плану: {self._off_plan}", "warn")

    def _on_area(self, ev: AreaGenerated) -> None:
        z = ev.area_id
        self._area_id, self._area_level = z, ev.area_level
        self._area_name = ""
        self._awaiting_scene = True
        if not self._running:
            if z != START_AREA:
                return
            # a new character may be created while the app runs: the level we remember then
            # belongs to the previous character. Start anyway, but only tentatively; the next
            # LevelUp confirms (level <= 2) or cancels (an old character revisiting Riverbank).
            sure = self._armed or self._finished_before or self._char_level in (None, 1)
            self._start_run(ev)
            self._tentative = not sure
            log.info("run started at %s%s", ev.ts, "" if sure else " (tentative: last level %s)" % self._char_level)
        elif z == START_AREA and len(self._done) > 1 and self._pending_new is None:
            # Riverbank deep into a run: maybe a new character; the next LevelUp decides
            self._pending_new = (ev, self._elapsed)
            self._toast("Новый персонаж? Забег — с ур. 2", "zone", 8.0)
            log.info("Riverbank at %s during a run: waiting for level-up to decide", ev.ts)
        if z == START_AREA:
            self._riverbank = (ev, self._elapsed)
        self._enter_zone(z)
        if is_hideout(z):
            return
        self._on_zone_in_run(z)

    def _restart_from(self, entry_ev: AreaGenerated, since: float) -> None:
        """Start a new run at an earlier Riverbank entry, `since` game seconds ago."""
        area, level, name = self._area_id, self._area_level, self._area_name
        self._start_run(entry_ev)
        # replay the new run's zones: Riverbank (its step and split at 0:00) ...
        self._enter_zone(START_AREA)
        self._on_zone_in_run(START_AREA)
        self._elapsed = since                 # the new run's clock starts at its Riverbank
        self._riverbank = (entry_ev, 0.0)
        if area and area != START_AREA:       # ... then the zone we are in now
            self._account()                   # Riverbank segment gets its seconds
            self._enter_zone(area)
            self._on_zone_in_run(area)
        self._area_id, self._area_level, self._area_name = area, level, name

    def _start_run(self, ev: AreaGenerated) -> None:
        self._reset_run_state()
        self._allocated = set()
        self._running = True
        self._armed = False
        self._tentative = False
        self._char_level = 1                      # a run always starts with a level-1 character
        self._started_iso = ev.ts.isoformat(timespec="seconds")
        self._seg_mark = 0.0
        self._toast("Ран начат", "zone")
        hint = self.plan.hint_for(1) if self.plan else None   # level 1 has no LevelUp line
        if hint is not None:
            if hint.gems:
                self._toast(" · ".join(hint.gems), "level", 5.0)
            self._gear_toast(hint.gear)

    def _first_open(self, after: int = -1, exclude_area: str | None = None) -> int | None:
        for k in range(after + 1, len(self.route.steps)):
            if k not in self._done and self.route.steps[k].area != exclude_area:
                return k
        return None

    def _complete(self, k: int, toast: bool) -> None:
        """Mark step k done, plus skipped pass-through steps before it in the same act."""
        steps = self.route.steps
        newly = [k] if k not in self._done else []
        for j in range(k):
            if j not in self._done and steps[j].act == steps[k].act \
                    and steps[j].skippable:
                newly.append(j)
        for j in sorted(newly):
            self._done.add(j)
            self._hit_split(j, toast=toast and j == k)

    def _on_zone_in_run(self, z: str) -> None:
        """Show the step of the zone the player is in, in any order; elsewhere the next open one.

        Entering a route zone completes its step (kills aren't logged) and the skippable steps
        (move/wp/town/skip, anything marked optional) passed before it in the same act; skipped
        required bosses, quests and trials stay open as reminders.
        """
        steps = self.route.steps
        rz = route_area(z)
        here = [k for k, s in enumerate(steps) if s.area == rz]
        open_here = [k for k in here if k not in self._done]
        shown = None
        if is_town(z):
            # a town step only when it is due: nothing but required leftovers before it
            if open_here:
                k = open_here[0]
                due = all(not steps[j].skippable
                          for j in range(k) if j not in self._done and steps[j].act == steps[k].act)
                if due:
                    self._complete(k, toast=True)
                    shown = k
        elif open_here:
            shown = open_here[0]
            self._complete(shown, toast=True)
        elif here:
            shown = here[-1]                          # revisit: this zone's (done) step
        if shown is None:
            shown = self._first_open()
        self._step = len(steps) if shown is None else shown
        self._ascendancy_hint(z)
        seg = self._segs.get(z)
        if seg is not None and seg.visits == 1:     # pickup hints only on the first visit
            self._zone_hint(z)
        if z == END_AREA:
            self._finish()

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
        if self.store is None or self._quiet:
            return
        if status == "abandoned" and self._elapsed < MIN_ABANDON_SAVE_S:
            return
        rec = self._record(status)
        try:
            self.store.save_run(rec)
        except OSError:
            log.exception("could not save run")
