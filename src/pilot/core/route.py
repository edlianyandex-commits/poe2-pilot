"""Route model and loader with validation (see docs/ROUTE_SCHEMA.md)."""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

KINDS = frozenset({"move", "wp", "boss", "quest", "town", "trial", "skip"})
MAX_SHORT, MAX_DETAIL, MAX_REWARD = 40, 120, 32
VALID_ACTS = frozenset({1, 2, 3, 4, 101, 102, 103})
_ROUTE_KEYS = {"id", "patch", "title", "steps"}
_STEP_KEYS = {"id", "act", "area", "short", "detail", "kind", "split", "done_on", "reward", "optional"}


class RouteError(ValueError):
    """Invalid route file; `.violations` lists every problem found."""

    def __init__(self, source: str, violations: list[str]) -> None:
        self.violations = violations
        super().__init__(
            f"Invalid route {source}: {len(violations)} problem(s):\n  - "
            + "\n  - ".join(violations)
        )


@dataclass(frozen=True)
class Step:
    id: str
    act: int
    area: str
    short: str
    kind: str
    detail: str = ""
    split: bool = False
    done_on_enter: str | None = None
    reward: str | None = None
    merged_ids: tuple[str, ...] = ()   # original step ids folded into this one (first == id)
    optional: bool = False             # not needed to progress (optional bosses keep a dim icon)

    @property
    def display_kind(self) -> str:
        """Kind for the HUD icon: an optional boss is "boss_opt", not a must-kill "boss"."""
        return "boss_opt" if self.kind == "boss" and self.optional else self.kind

    @property
    def all_ids(self) -> tuple[str, ...]:
        return self.merged_ids or (self.id,)


@dataclass(frozen=True)
class Route:
    id: str
    title: str
    steps: tuple[Step, ...]
    patch: str = ""


def load_route(path: str | Path) -> Route:
    """Load and validate a route JSON file; raises RouteError listing all violations."""
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        raise RouteError(str(p), [f"cannot read/parse: {e}"]) from e
    return parse_route(data, source=str(p))


def parse_route(data: object, source: str = "<dict>") -> Route:
    """Validate an already-decoded route object."""
    errs: list[str] = []
    if not isinstance(data, dict):
        raise RouteError(source, ["top level must be an object"])
    _check_keys(data, _ROUTE_KEYS, "route", errs)
    rid = data.get("id")
    if not isinstance(rid, str) or not rid:
        errs.append("route.id: required non-empty string")
    for key in ("patch", "title"):
        if key in data and not isinstance(data[key], str):
            errs.append(f"route.{key}: must be a string")
    raw_steps = data.get("steps")
    steps: list[Step] = []
    if not isinstance(raw_steps, list) or not raw_steps:
        errs.append("route.steps: required non-empty list")
        raw_steps = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_steps):
        step = _parse_step(raw, i, seen, errs)
        if step is not None:
            steps.append(step)
    if errs:
        raise RouteError(source, errs)
    return Route(rid, data.get("title", ""), merge_same_area(steps), data.get("patch", ""))


# the game logs some zones under another id than the route uses (layout versions, patches)
AREA_ALIASES = {
    "G2_3": "G2_3a",       # The Halani Gates, second version
    "G2_12": "G2_12_1",    # The Dreadnought (0.5 id)
}


def route_area(area_id: str) -> str:
    """Area id as the route knows it."""
    return AREA_ALIASES.get(area_id, area_id)


# a must-kill boss leads its zone; an optional one only when nothing else happens there
_KIND_PRIORITY = {"boss": 7, "trial": 6, "quest": 5, "town": 4, "wp": 3, "move": 2, "boss_opt": 1, "skip": 0}


def merge_same_area(steps: list[Step]) -> tuple[Step, ...]:
    """Fold runs of consecutive steps in one area into a single display step.

    Primary = highest-priority kind (first wins ties); its short is shown, the
    other shorts go to `detail`. split = any, done_on = last, reward = first non-null.
    """
    out: list[Step] = []
    i = 0
    while i < len(steps):
        j = i
        while j + 1 < len(steps) and steps[j + 1].area == steps[i].area:
            j += 1
        group = steps[i:j + 1]
        i = j + 1
        if len(group) == 1:
            g = group[0]
            out.append(replace(g, merged_ids=(g.id,)))
            continue
        primary = max(group, key=lambda g: _KIND_PRIORITY[g.display_kind])  # max keeps the first on ties
        others = [g.short for g in group if g is not primary]
        details = [g.detail for g in group if g.detail]
        detail = " · ".join(others)
        if details:
            detail = (detail + " — " if detail else "") + " | ".join(details)
        if len(detail) > MAX_DETAIL:
            detail = detail[:MAX_DETAIL - 1] + "…"
        out.append(Step(
            id=group[0].id, act=group[0].act, area=group[0].area,
            short=primary.short, kind=primary.kind, detail=detail,
            split=any(g.split for g in group), done_on_enter=group[-1].done_on_enter,
            reward=next((g.reward for g in group if g.reward), None),
            merged_ids=tuple(g.id for g in group), optional=primary.optional,
        ))
    return tuple(out)


def _check_keys(obj: dict, allowed: set[str], where: str, errs: list[str]) -> None:
    for k in obj:
        if k not in allowed and not str(k).startswith("_"):
            errs.append(f"{where}: unknown key {k!r}")


def _parse_step(raw: object, i: int, seen: set[str], errs: list[str]) -> Step | None:
    if not isinstance(raw, dict):
        errs.append(f"steps[{i}]: must be an object")
        return None
    sid = raw.get("id")
    where = f"steps[{i}]" + (f" ({sid})" if isinstance(sid, str) else "")
    n0 = len(errs)
    _check_keys(raw, _STEP_KEYS, where, errs)
    if not isinstance(sid, str) or not sid:
        errs.append(f"{where}: id required non-empty string")
    elif sid in seen:
        errs.append(f"{where}: duplicate id")
    else:
        seen.add(sid)
    act = raw.get("act")
    if isinstance(act, bool) or act not in VALID_ACTS:
        errs.append(f"{where}: act must be one of 1-4, 101-103 (got {act!r})")
    area = raw.get("area")
    if not isinstance(area, str) or not area:
        errs.append(f"{where}: area required non-empty string")
    short = raw.get("short")
    if not isinstance(short, str) or not short:
        errs.append(f"{where}: short required non-empty string")
    elif len(short) > MAX_SHORT:
        errs.append(f"{where}: short is {len(short)} chars (max {MAX_SHORT})")
    kind = raw.get("kind")
    if kind not in KINDS:
        errs.append(f"{where}: kind {kind!r} not in {sorted(KINDS)}")
    detail = raw.get("detail", "")
    if not isinstance(detail, str):
        errs.append(f"{where}: detail must be a string")
    elif len(detail) > MAX_DETAIL:
        errs.append(f"{where}: detail is {len(detail)} chars (max {MAX_DETAIL})")
    reward = raw.get("reward")
    if reward is not None:
        if not isinstance(reward, str):
            errs.append(f"{where}: reward must be a string")
        elif len(reward) > MAX_REWARD:
            errs.append(f"{where}: reward is {len(reward)} chars (max {MAX_REWARD})")
    split = raw.get("split", False)
    if not isinstance(split, bool):
        errs.append(f"{where}: split must be a boolean")
    enter = None
    if "done_on" in raw:
        d = raw["done_on"]
        if not isinstance(d, dict):
            errs.append(f"{where}: done_on must be an object")
        else:
            _check_keys(d, {"enter"}, f"{where}.done_on", errs)
            enter = d.get("enter")
            if not isinstance(enter, str) or not enter:
                errs.append(f"{where}: done_on.enter required non-empty string")
                enter = None
    optional = raw.get("optional", False)
    if not isinstance(optional, bool):
        errs.append(f"{where}: optional must be a boolean")
    if len(errs) > n0:
        return None
    return Step(sid, act, area, short, kind, detail, split, enter, reward, optional=optional)
