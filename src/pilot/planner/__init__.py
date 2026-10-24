"""Autobuilder: Path of Building (PoE2) export code -> per-level LevelPlan.

    from pilot.planner import build_plan
    plan = build_plan(code_or_path)                 # X.pob auto-loads X.gear.json if present
    plan = build_plan(code, gear_file="x.gear.json")

Data comes from data/planner (see tools/planner/extract.py and data/planner/ATTRIBUTION.md).
"""
from __future__ import annotations

from pathlib import Path

from pilot.contracts import LevelPlan

from .plan import PlanDetail, build_level_plan, load_gear_file
from .pobcode import PobBuild, PobDecodeError, decode_pob_code, load_pob, parse_pob_xml

__all__ = ["build_plan", "build_plan_detail", "load_pob", "decode_pob_code", "parse_pob_xml",
           "load_gear_file", "find_gear_sidecar", "PobBuild", "PobDecodeError", "PlanDetail"]


def find_gear_sidecar(source: str | Path) -> Path | None:
    """X.pob / X.xml / X.txt -> X.gear.json next to it, if the source is an existing file."""
    if isinstance(source, str) and (len(source) >= 1024 or source.lstrip().startswith("<")):
        return None  # a code / XML string, not a path
    try:
        p = Path(source)
        if not p.is_file():
            return None
    except (OSError, ValueError):
        return None
    cand = p.with_name(p.stem + ".gear.json")
    return cand if cand.is_file() else None


def build_plan_detail(pob_code: str | Path, max_level: int = 100,
                      gear_file: str | Path | None = None) -> PlanDetail:
    if gear_file is None:
        gear_file = find_gear_sidecar(pob_code)
    gear = load_gear_file(gear_file) if gear_file else None
    return build_level_plan(load_pob(pob_code), max_level=max_level, gear=gear)


def build_plan(pob_code: str | Path, gear_file: str | Path | None = None) -> LevelPlan:
    """PoB export code (or path to a code/.xml file, or raw XML) -> LevelPlan.

    ``gear_file``: optional sidecar ``{"gear": {"<level>": [...]}}``; when omitted and
    ``pob_code`` is a file path ``X.pob``, ``X.gear.json`` next to it is used if it exists.
    """
    return build_plan_detail(pob_code, gear_file=gear_file).plan
