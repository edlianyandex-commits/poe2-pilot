"""Validate data/areas/areas.json and data/routes/campaign-0.5.json against docs/ROUTE_SCHEMA.md."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AREAS_PATH = ROOT / "data" / "areas" / "areas.json"
TSV_PATH = ROOT / "data" / "areas" / "seen_areas_ru.tsv"
ROUTE_PATH = ROOT / "data" / "routes" / "campaign-0.5.json"

VALID_ACTS = {1, 2, 3, 4, 101, 102, 103}
KIND_SYMBOLS = {
    "move": "→",
    "wp": "◆",
    "boss": "⚔",
    "quest": "!",
    "town": "⌂",
    "trial": "✦",
    "skip": "✕",
}
REQUIRED_STEP_KEYS = {"id", "act", "area", "short", "kind"}
OPTIONAL_STEP_KEYS = {"detail", "split", "done_on", "reward", "optional"}
SHORT_MAX = 40
DETAIL_MAX = 120
REWARD_MAX = 32


def _load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _tsv_rows():
    with TSV_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _act_of_area(area_id):
    if area_id == "G_Endgame_Town":
        return 103
    return {"G1": 1, "G2": 2, "G3": 3, "G4": 4, "P1": 101, "P2": 102, "P3": 103}[area_id[:2]]


AREAS = _load(AREAS_PATH)
ROUTE = _load(ROUTE_PATH)
STEPS = ROUTE["steps"]


def test_areas_match_tsv_ids_and_names():
    rows = _tsv_rows()
    tsv_ids = [r["area_id"] for r in rows]
    assert len(tsv_ids) == len(set(tsv_ids)), "duplicate ids in TSV"
    assert set(AREAS) == set(tsv_ids)
    for r in rows:
        entry = AREAS[r["area_id"]]
        assert entry["ru"] == r["name_ru"], r["area_id"]
        assert entry["level"] == int(r["area_level"]), r["area_id"]


def test_area_fields_valid():
    for area_id, entry in AREAS.items():
        assert entry["act"] in VALID_ACTS, area_id
        assert entry["act"] == _act_of_area(area_id), area_id
        assert isinstance(entry["level"], int), area_id
        assert isinstance(entry["ru"], str) and entry["ru"], area_id
        assert isinstance(entry["en"], str) and entry["en"], area_id
        assert isinstance(entry["town"], bool), area_id
        assert entry["town"] == ("town" in area_id.lower()), area_id
        if "has_wp" in entry:
            assert isinstance(entry["has_wp"], bool), area_id


def test_route_header():
    assert ROUTE["id"] == "campaign-0.5"
    assert isinstance(ROUTE["patch"], str) and ROUTE["patch"]
    assert isinstance(ROUTE["title"], str) and ROUTE["title"]
    assert STEPS, "route has no steps"


def test_step_ids_unique():
    ids = [s["id"] for s in STEPS]
    assert len(ids) == len(set(ids)), "duplicate step ids"


def test_step_keys_and_limits():
    for s in STEPS:
        keys = set(s)
        assert REQUIRED_STEP_KEYS <= keys, s["id"]
        unknown = {k for k in keys - REQUIRED_STEP_KEYS - OPTIONAL_STEP_KEYS if not k.startswith("_")}
        assert not unknown, (s["id"], unknown)

        assert s["kind"] in KIND_SYMBOLS, s["id"]
        short = s["short"]
        assert isinstance(short, str) and 0 < len(short) <= SHORT_MAX, (s["id"], short)
        assert short.startswith(KIND_SYMBOLS[s["kind"]]), (s["id"], short)
        assert not short.endswith("."), (s["id"], short)

        if "detail" in s:
            assert isinstance(s["detail"], str) and len(s["detail"]) <= DETAIL_MAX, s["id"]
        if "reward" in s:
            assert isinstance(s["reward"], str) and len(s["reward"]) <= REWARD_MAX, s["id"]
        if "split" in s:
            assert isinstance(s["split"], bool), s["id"]

        assert s["act"] in VALID_ACTS, s["id"]
        assert s["area"] in AREAS, (s["id"], s["area"])
        assert s["act"] == AREAS[s["area"]]["act"], (s["id"], s["area"])

        if "done_on" in s:
            done_on = s["done_on"]
            assert set(done_on) == {"enter"}, s["id"]
            assert done_on["enter"] in AREAS, (s["id"], done_on)


def test_steps_follow_act_order():
    acts = [s["act"] for s in STEPS]
    assert acts == sorted(acts), "steps not in non-decreasing act order"
    # interludes (101+) must all come after acts 1-4
    first_interlude = next((i for i, a in enumerate(acts) if a > 4), len(acts))
    assert all(a <= 4 for a in acts[:first_interlude])
    assert all(a > 4 for a in acts[first_interlude:])


def test_split_markers():
    seen = set()
    for i, s in enumerate(STEPS):
        if s["act"] not in seen:
            seen.add(s["act"])
            assert s.get("split") is True, f"first step of act {s['act']} must split ({s['id']})"
    assert STEPS[-1].get("split") is True, "final step must split"


def test_reward_is_stripped_string():
    for s in STEPS:
        if "reward" in s:
            assert s["reward"].strip() == s["reward"], s["id"]
