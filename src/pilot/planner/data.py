"""Load planner data from data/planner (produced by tools/planner/extract.py + hand-curated JSON)."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_TREE_VERSION = "0_5"


def data_dir() -> Path:
    env = os.environ.get("POE2_PILOT_PLANNER_DATA")
    if env:
        return Path(env)
    # src/pilot/planner/data.py -> repo root
    return Path(__file__).resolve().parents[3] / "data" / "planner"


def _load(name: str) -> dict:
    p = data_dir() / name
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def available_tree_versions() -> list[str]:
    return sorted(p.stem.removeprefix("tree_") for p in data_dir().glob("tree_*.json"))


@lru_cache(maxsize=4)
def tree_data(version: str | None = None) -> dict:
    versions = available_tree_versions()
    if not versions:
        raise FileNotFoundError(f"no tree_*.json in {data_dir()} - run tools/planner/extract.py")
    v = version if version in versions else versions[-1]
    return _load(f"tree_{v}.json")


@lru_cache(maxsize=1)
def gems_data() -> dict:
    return _load("gems.json")["gems"]


@lru_cache(maxsize=1)
def gem_rules() -> dict:
    return _load("gem_rules.json")


@lru_cache(maxsize=1)
def quest_points() -> dict:
    return _load("quest_points.json")
