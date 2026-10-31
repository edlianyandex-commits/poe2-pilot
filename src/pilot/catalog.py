"""The build list of the start window: builds/catalog.json plus what the board shows per build.

Kept free of the planner so the start window opens fast; the plan is built only after take-off.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pilot.paths import BUILDS, DATA, version_key

CATALOG = "catalog.json"
STATUSES = ("verified", "guide", "custom")


@dataclass(frozen=True)
class Entry:
    code: str                       # flight number on the board, "MR 202"
    file: str                       # file name in builds/
    rev: int
    title: str
    cls: str
    ascendancy: str
    skills: tuple[str, ...]
    author: str
    patch: str
    status: str                     # one of STATUSES
    source: str = ""
    note: str = ""
    musts: tuple[str, ...] = ()     # route steps the build makes required, as the route names them
    outdated: bool = False          # made for an older game patch than the catalog's

    @property
    def role(self) -> str:
        return self.ascendancy or self.cls


@dataclass(frozen=True)
class Catalog:
    game: str
    route: str
    entries: tuple[Entry, ...] = field(default_factory=tuple)
    start: str = ""                 # first and last route step, for the boarding pass
    finish: str = ""

    def find(self, file: str | None) -> Entry | None:
        name = Path(file).name if file else None
        return next((e for e in self.entries if e.file == name), None)


def _route_names(route: str) -> dict[str, str]:
    """step id -> its short name without the leading marker ('✦ Испытание Сехем' -> 'Испытание Сехем'),
    in route order."""
    try:
        steps = json.loads((DATA / "routes" / f"{route}.json").read_text(encoding="utf-8"))["steps"]
    except (OSError, ValueError, KeyError):
        return {}
    return {s["id"]: s.get("short", s["id"]).lstrip("✦✕⚔→⌂ ").strip() for s in steps if "id" in s}


def _musts(build: Path, names: dict[str, str]) -> tuple[str, ...]:
    try:
        gear = json.loads(build.with_name(build.stem + ".gear.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(names.get(i, i) for i in gear.get("route", {}).get("require", []))


def _minor(v: str) -> tuple[int, ...]:
    return version_key(v)[:2]


def load_catalog(base: Path = BUILDS) -> Catalog:
    raw = json.loads((base / CATALOG).read_text(encoding="utf-8"))
    game, route = raw.get("game", ""), raw.get("route", "")
    names = _route_names(route)
    entries = []
    for b in raw.get("builds", []):
        if not (base / b["file"]).is_file():
            continue
        entries.append(Entry(
            code=b["code"], file=b["file"], rev=int(b.get("rev", 1)), title=b["title"],
            cls=b["class"], ascendancy=b.get("ascendancy", ""), skills=tuple(b.get("skills", ())),
            author=b.get("author", ""), patch=b.get("patch", ""),
            status=b.get("status") if b.get("status") in STATUSES else "custom",
            source=b.get("source", ""), note=b.get("note", ""),
            musts=_musts(base / b["file"], names),
            outdated=bool(game) and _minor(b.get("patch", "")) < _minor(game)))
    order = list(names.values())
    return Catalog(game, route, tuple(entries), order[0] if order else "", order[-1] if order else "")
