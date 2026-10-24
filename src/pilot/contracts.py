"""Shared contracts between teams. Changing anything here = tell the lead.

core     -> produces Events from Client.txt, owns RunEngine -> HudState
planner  -> produces LevelPlan (what to take at each character level)
overlay  -> renders HudState, calls Actions
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


# ---------- raw events parsed from Client.txt (core/parser.py) ----------

@dataclass(frozen=True)
class Event:
    ts: datetime


@dataclass(frozen=True)
class AreaGenerated(Event):
    """`Generating level 1 area "G1_1" with seed 3976951634` — language independent."""
    area_id: str
    area_level: int
    seed: int


@dataclass(frozen=True)
class SceneEntered(Event):
    """`[SCENE] Set Source [Клирфелл]` — localized name; (null)/(unknown) are dropped."""
    name: str


@dataclass(frozen=True)
class LoadingScreen(Event):
    """`[LOADING SCREEN] (Сборочный цех) Duration = 3.33666 seconds`"""
    name: str
    seconds: float


@dataclass(frozen=True)
class LevelUp(Event):
    """ru: `: Name (Чародейка) достигает 2 уровня`  en: `: Name (Sorceress) is now level 2`"""
    character: str
    char_class: str
    level: int


@dataclass(frozen=True)
class Death(Event):
    """ru: `: Name был повержен.`  en: `: Name has been slain.`"""
    character: str


@dataclass(frozen=True)
class PassiveAllocated(Event):
    """`Successfully allocated passive skill id: X, name: Y`; unallocated -> allocated=False"""
    node_id: str
    name: str
    allocated: bool = True


@dataclass(frozen=True)
class FocusChanged(Event):
    """`[WINDOW] Lost focus` / `[WINDOW] Gained focus`"""
    focused: bool


@dataclass(frozen=True)
class GameClosed(Event):
    pass


# ---------- planner output (planner/) ----------

@dataclass(frozen=True)
class GemCard:
    """One gem as the gem window shows it. `name` is English: it is what a click copies."""
    name: str
    kind: str                     # "skill" | "support" | "spirit"
    color: str                    # "str" | "dex" | "int" | "none" -> fallback icon colour
    description: str = ""         # tooltip text, <= 400 chars
    icon_url: str | None = None   # remote image; the app caches it locally


@dataclass(frozen=True)
class GemRow:
    """A socketed skill and the supports that go into it at a given level."""
    skill: GemCard
    supports: tuple[GemCard, ...] = ()

@dataclass(frozen=True)
class LevelHint:
    """What to do when the character reaches `level`. Every string <= 32 chars."""
    level: int
    passives: tuple[str, ...] = ()      # display names of nodes to allocate now
    gems: tuple[str, ...] = ()          # "+ Ледяная стрела", "Support: X -> Y"
    note: str | None = None             # e.g. "Сменить скилл"
    gear: tuple[str, ...] = ()          # "Надеть Skysliver", "Новое копьё"


@dataclass
class LevelPlan:
    title: str
    char_class: str
    hints: dict[int, LevelHint] = field(default_factory=dict)
    planned_node_ids: tuple[str, ...] = ()   # allocation order, used to flag deviations
    ascendancy: dict[str, LevelHint] = field(default_factory=dict)   # trial area id -> nodes to take
    warnings: tuple[str, ...] = ()           # planner diagnostics, never shown on the HUD
    # full gem setup from this level on: level -> ("Twister: Salvo, Retreat II", ...), each <= 40
    setups: dict[int, tuple[str, ...]] = field(default_factory=dict)

    def hint_for(self, level: int) -> LevelHint | None:
        return self.hints.get(level)

    # same setups as structured rows for the gem window: level -> rows, main skill first
    gem_rows: dict[int, tuple[GemRow, ...]] = field(default_factory=dict)
    # area id -> what to pick up there ("Renly: Twister"), each <= 40 chars; shown on first entry
    zone_hints: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def setup_for(self, level: int) -> tuple[str, ...]:
        """Gem setup that should be socketed at `level` (latest entry at or below it)."""
        best = max((lv for lv in self.setups if lv <= level), default=None)
        return self.setups[best] if best is not None else ()

    def gem_rows_for(self, level: int) -> tuple[GemRow, ...]:
        best = max((lv for lv in self.gem_rows if lv <= level), default=None)
        return self.gem_rows[best] if best is not None else ()


# ---------- passive tree window (planner builds it, overlay renders it) ----------

@dataclass(frozen=True)
class TreeNodeView:
    sid: str                      # string id, as in Client.txt
    name: str
    kind: str                     # small | notable | keystone | attribute | jewel | start
    x: float                      # tree coordinates (PoB units, y grows downwards)
    y: float
    stats: tuple[str, ...] = ()
    state: str = "other"          # taken | next | planned | offplan | other
    order: int | None = None      # 1, 2, 3... for the next nodes to take
    level: int | None = None      # character level the plan takes it at
    icon_url: str | None = None


@dataclass(frozen=True)
class TreeView:
    nodes: tuple[TreeNodeView, ...]
    edges: tuple[tuple[str, str], ...]       # pairs of sids, only between shown nodes
    level: int | None = None
    points_free: int | None = None           # points the plan says should be spent but aren't


# ---------- what the overlay renders (core/engine.py -> overlay/) ----------

@dataclass(frozen=True)
class Toast:
    text: str            # <= 40 chars
    kind: str            # "level" | "zone" | "split" | "warn" | "gear"
    ttl_s: float = 3.0


@dataclass(frozen=True)
class HudState:
    act: int | None = None
    area_name: str = ""
    area_level: int | None = None
    char_level: int | None = None
    step_short: str | None = None        # current route step, <= 40 chars
    next_short: str | None = None        # following step, <= 40 chars
    step_index: int = 0
    step_total: int = 0
    run_time_s: float = 0.0              # in-game time, loading screens excluded
    split_delta_s: float | None = None   # vs personal best at the same split; <0 = ahead
    toasts: tuple[Toast, ...] = ()       # active transient messages, newest last
    warn: str | None = None              # one persistent warning max, e.g. "Уровень < зоны −4"
    game_focused: bool = True
    running: bool = False
    paused: bool = False                 # timer stopped: Alt+P, or the game window lost focus
    step_kind: str | None = None         # route kind of step_short ("boss", "wp", ...) -> icon
    next_kind: str | None = None
    progress: float = 0.0                # 0..1 through the whole route
    split_marks: tuple[float, ...] = ()  # progress positions of split steps, ascending


class Actions(Protocol):
    """Hotkey-triggered actions the overlay may call. Never sends input to the game."""
    def next_step(self) -> None: ...
    def prev_step(self) -> None: ...
    def reset_run(self) -> None: ...
    def toggle_pause(self) -> None: ...


class SnapshotSource(Protocol):
    """Thread-safe; overlay polls ~10 Hz."""
    def snapshot(self) -> HudState: ...
