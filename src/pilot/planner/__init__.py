"""Autobuilder: Path of Building (PoE2) export code -> per-level LevelPlan.

    from pilot.planner import build_plan
    plan = build_plan(code_or_path)

Data comes from data/planner (see tools/planner/extract.py and data/planner/ATTRIBUTION.md).
"""
from __future__ import annotations

from pathlib import Path

from pilot.contracts import LevelPlan

from .plan import PlanDetail, build_level_plan
from .pobcode import PobBuild, PobDecodeError, decode_pob_code, load_pob, parse_pob_xml

__all__ = ["build_plan", "build_plan_detail", "load_pob", "decode_pob_code", "parse_pob_xml",
           "PobBuild", "PobDecodeError", "PlanDetail"]


def build_plan_detail(pob_code: str | Path, max_level: int = 100) -> PlanDetail:
    return build_level_plan(load_pob(pob_code), max_level=max_level)


def build_plan(pob_code: str) -> LevelPlan:
    """PoB export code (or path to a code/.xml file, or raw XML) -> LevelPlan."""
    return build_plan_detail(pob_code).plan
