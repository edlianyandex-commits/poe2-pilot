"""Gear hints (PoB uniques + sidecar) and per-level gem setups on the Travic speed-campaign build."""
from __future__ import annotations

import json
import shutil

from pilot.planner import build_plan, build_plan_detail, find_gear_sidecar, load_gear_file, load_pob
from pilot.planner.plan import plan_gear, plan_groups, setup_line

from planner_helpers import FIX

SPEED = FIX / "twister_speed_campaign_0_5_5.pob"
SIDECAR = FIX / "twister_speed_campaign_0_5_5.gear.json"


def _gear(plan):
    return {lvl: h.gear for lvl, h in plan.hints.items() if h.gear}


def test_equipped_items_parsed():
    b = load_pob(SPEED)
    names = {i.name: i for i in b.equipped_items}
    assert names["Skysliver"].rarity == "UNIQUE" and names["Skysliver"].level_req == 16
    assert names["Wake of Destruction"].level_req == 16
    assert "Split Personality" not in names          # tree jewel, not an item slot
    assert all(i.is_jewel for i in b.equipped_items if "Socket" in i.slot)   # body-armour emeralds


def test_gear_from_pob_items_only():
    p = build_plan(SPEED.read_text().strip())        # code string: no sidecar discovery
    g = _gear(p)
    assert "Надеть Skysliver" in g[16] and "Надеть Wake of Destruction" in g[16]
    assert "Надеть Tabula Rasa" in g[1]              # LevelReq 0 -> level 1
    assert "Надеть Hand of Wisdom and Action" in g[33]
    assert "Надеть The Taming" in g[42]
    flat = [x for v in g.values() for x in v]
    assert not any("Split Personality" in x or "Emerald" in x for x in flat)
    assert not any(x.startswith("Надеть") and "Dragon Edge" in x for x in flat)  # rare, skipped


def test_missing_levelreq_is_skipped():
    b = load_pob(SPEED)
    from dataclasses import replace
    b.equipped_items = [replace(i, level_req=None) if i.name == "Skysliver" else i
                        for i in b.equipped_items]
    flat = [x for v in plan_gear(b).values() for x in v]
    assert not any("Skysliver" in x for x in flat)


def test_sidecar_autodiscovered_and_wins():
    assert find_gear_sidecar(SPEED) == SIDECAR
    assert find_gear_sidecar(SPEED.read_text()) is None
    p = build_plan(SPEED)                            # path -> X.gear.json picked up
    g = _gear(p)
    side = load_gear_file(SIDECAR)
    for lvl, lines in side.items():
        for x in lines:
            assert x in g[lvl]
    flat = [x for v in g.values() for x in v]
    # sidecar "Надеть Skysliver (сет 1)" replaces the PoB-derived "Надеть Skysliver"
    assert "Надеть Skysliver (сет 1)" in g[16] and "Надеть Skysliver" not in flat
    assert sum("Tabula Rasa" in x for x in flat) == 1
    # PoB uniques the sidecar does not mention still appear
    assert "Надеть Yoke of Suffering" in g[18]
    assert p.hints[10].gear == ("Новое копьё (макс. DPS)",)   # gear-only level gets a hint


def test_explicit_gear_file_and_underscore_keys(tmp_path):
    f = tmp_path / "g.json"
    f.write_text(json.dumps({"_note": "x", "gear": {"_skip": ["no"], "7": ["Очень длинная строка про снаряжение и копьё"],
                                                    "3": "Сапоги"}}), encoding="utf-8")
    p = build_plan(SPEED.read_text(), gear_file=f)
    assert p.hints[3].gear == ("Сапоги",)
    (line,) = p.hints[7].gear
    assert len(line) <= 32 and line.endswith("…")
    assert not any("no" == x for h in p.hints.values() for x in h.gear)


def test_sidecar_next_to_copied_build(tmp_path):
    shutil.copy(SPEED, tmp_path / "b.pob")
    assert not any(h.gear and "Новое копьё (макс. DPS)" in h.gear for h in build_plan(tmp_path / "b.pob").hints.values())
    shutil.copy(SIDECAR, tmp_path / "b.gear.json")
    assert build_plan(tmp_path / "b.pob").hints[10].gear


def test_setups_monotonic_complete_and_short():
    d = build_plan_detail(SPEED)
    p = d.plan
    assert p.setups and min(p.setups) == 1
    assert p.setup_for(0) == ()
    prev_supports: dict[str, int] = {}
    prev = None
    for lvl in range(1, 101):
        cur = p.setup_for(lvl)
        if lvl in p.setups:
            assert cur != prev                         # stored only where it changes
        else:
            assert cur == prev
        for line in cur:
            assert 0 < len(line) <= 40, line
        skills = [ln.split(":")[0] for ln in cur]
        assert len(skills) == len(set(skills))
        # monotonic: a skill never disappears and never loses supports
        for ln in cur:
            skill = ln.split(":")[0]
            n = 0
            if ":" in ln:
                parts = ln.split(":", 1)[1].split(", ")
                n = sum(int(x[1:]) if x.startswith("+") and x[1:].isdigit() else 1 for x in parts)
            assert n >= prev_supports.get(skill, 0), (lvl, ln)
            prev_supports[skill] = n
        assert set(skills) >= set(prev_supports)    # no skill disappears
        prev = cur
    # main skill first; weapon-granted Spear Throw without supports is not listed
    assert p.setup_for(1)[0].startswith("Twister")
    assert not any("Spear Throw" in ln for s in p.setups.values() for ln in s)
    final = p.setup_for(100)
    assert any(ln.startswith("Barrage") for ln in final)
    assert any(ln.startswith("Whirling Slash") for ln in final)
    # every planned support is eventually socketed (counting "+N")
    total = sum(len(gp.supports) for gp in plan_groups(d.build, []) if gp.supports or not gp.lead.weapon)
    shown = 0
    for ln in final:
        if ":" in ln:
            parts = ln.split(":", 1)[1].split(", ")
            shown += sum(int(x[1:]) if x.startswith("+") and x[1:].isdigit() else 1 for x in parts)
    assert shown == total


def test_setup_line_overflow():
    assert setup_line("Twister", []) == "Twister"
    assert setup_line("Twister", ["Salvo"]) == "Twister: Salvo"
    s = setup_line("Twister", ["Armour Break III", "Projectile Acceleration III", "Salvo"])
    assert s == "Twister: Armour Break III, +2" and len(s) <= 40
    assert len(setup_line("X" * 60, ["A"])) <= 40


def test_all_strings_lengths():
    p = build_plan(SPEED)
    for h in p.hints.values():
        assert len(h.gear) <= 6
        for x in (*h.passives, *h.gems, *h.gear):
            assert 0 < len(x) <= 32, x
    for lines in p.setups.values():
        assert all(len(x) <= 40 for x in lines)


def test_sidecar_can_drop_pob_unique_hints(tmp_path):
    """Self-found builds: "pob_uniques": false keeps only the sidecar's own lines."""
    import json
    from pathlib import Path
    from pilot.planner import build_plan
    src = Path(__file__).resolve().parents[2] / "builds" / "twister_martial_artist_787prada_0_5_5.pob"
    pob = tmp_path / "ma.pob"
    pob.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    with_uniques = build_plan(pob)                       # no sidecar yet
    assert any(g.startswith("Надеть") for h in with_uniques.hints.values() for g in h.gear)
    (tmp_path / "ma.gear.json").write_text(
        json.dumps({"pob_uniques": False, "gear": {"1": ["Копьё"]}}), encoding="utf-8")
    p = build_plan(pob)
    gear = [g for h in p.hints.values() for g in h.gear]
    assert gear == ["Копьё"]
