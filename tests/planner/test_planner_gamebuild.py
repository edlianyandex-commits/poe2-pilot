"""In-game .build files (zip of stages) -> plan with the guide's own gems per stage."""
from pathlib import Path

from pilot.planner import build_plan, load_pob

BUILD = Path(__file__).resolve().parents[2] / "builds" / "twister_monk_guythatdies_0_5_5.build"


def test_stages_class_and_islands_dropped():
    b = load_pob(BUILD)
    assert b.class_name == "Monk"
    assert [len(s.nodes) for s in b.specs] == sorted(len(s.nodes) for s in b.specs)   # early stage first
    p = build_plan(BUILD)
    assert not any("filler" in w for w in p.warnings)


def test_guide_gems_by_stage_and_ingame_names():
    p = build_plan(BUILD)
    lv1 = {r.skill.name: [s.name for s in r.supports] for r in p.gem_rows_for(1)}
    assert lv1["Whirling Slash"] == ["Rage I", "Rapid Attacks I"]       # SupportGemMartialTempo
    assert lv1["Twister"] == ["Retreat I"]
    assert "Barrage" not in lv1 and "Barrage" in {r.skill.name for r in p.gem_rows_for(14)}
    assert all(r.skill.icon_url for r in p.gem_rows_for(1))


def test_zone_hints_from_sidecar():
    p = build_plan(BUILD)
    assert p.zone_hints["G1_town"] == ("Renly: Twister",)
    assert all(len(s) <= 40 for v in p.zone_hints.values() for s in v)


def test_shared_start_class_from_name():
    """Ranger/Huntress share a start: without ascendancy nodes the build name decides."""
    from pilot.planner.gamebuild import _class_of
    from pilot.planner.tree import PassiveTree
    t = PassiveTree.load()
    start = t.class_start("Huntress")
    near = [t.nodes[o].sid for o in t.nodes[start].adj if t.nodes[o].sid and not t.nodes[o].asc][:1]
    asc = [t.nodes[o].sid for o in t.nodes[start].adj if t.nodes[o].asc == "Amazon"]
    assert _class_of(t, near + asc, "Lightning Arrow Ranger") == "Huntress"   # ascendancy wins
    assert _class_of(t, near, "Spear Huntress levelling") == "Huntress"
    assert _class_of(t, near, "Lightning Arrow Ranger") == "Ranger"
