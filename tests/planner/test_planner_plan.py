from __future__ import annotations

import subprocess
import sys

import pytest

from pilot.contracts import LevelHint, LevelPlan
from pilot.planner import build_plan, build_plan_detail, data, load_pob
from pilot.planner.plan import (asc_points_at, earliest_level, gem_info, passive_points_at,
                                spread_gem_events, GemEvent)
from pilot.planner.pobcode import GemEntry, parse_pob_xml
from pilot.planner.plan import build_level_plan

from planner_helpers import AMAZON, GEMLING, ROOT, log_allocations, make_xml


# ----------------------------------------------------------------------------- quest points

def test_quest_point_table():
    q = data.quest_points()
    pts = sum(r["points"] for r in q["passive_rewards"])
    assert pts == 24                       # PoB: 99 level points + 24 quest points
    assert passive_points_at(1) == 0
    assert passive_points_at(11) == 10
    assert passive_points_at(13) == 16     # Crowbell + Una's Lute
    assert passive_points_at(100) == 99 + 24
    assert asc_points_at(23) == 0 and asc_points_at(41) == 4 and asc_points_at(100) == 8
    assert all(r.get("area_id") or r.get("note") for r in q["passive_rewards"])


def test_quest_points_match_real_log():
    """The real run never spends more regular points than our table allows +- 2 (timing drift)."""
    import re
    from planner_helpers import CAMPAIGN_LOG
    level, alloc, worst = 1, set(), 0
    for line in CAMPAIGN_LOG.read_text(encoding="utf-8").splitlines():
        m = re.search(r"достигает (\d+) уровня", line)
        if m:
            level = int(m.group(1))
        m = re.search(r"Successfully (un)?allocated passive skill id: ([^,]+),", line)
        if m:
            (alloc.discard if m.group(1) else alloc.add)(m.group(2))
            regular = sum(1 for s in alloc if not s.startswith("Ascendancy"))
            worst = max(worst, regular - passive_points_at(level))
    assert worst <= 2


# ----------------------------------------------------------------------------- gems

def test_gem_earliest_levels():
    rules = data.gem_rules()
    req = rules["skill_level_requirement"]
    assert req[:5] == [0, 3, 6, 10, 14]
    spark = gem_info(GemEntry("Spark"))
    assert spark.kind == "skill" and earliest_level(spark) == 1
    frost = gem_info(GemEntry("Frostbolt"))
    assert earliest_level(frost) == max(1, req[frost.tier - 1])
    herald = gem_info(GemEntry("Herald of Ice"))
    assert herald.kind == "spirit" and earliest_level(herald) >= req[3]
    sup = gem_info(GemEntry("Ice Bite II"))
    assert sup.kind == "support" and earliest_level(sup) > earliest_level(gem_info(GemEntry("Ice Bite I")))
    # gem ids with the singular "Items/Gem/" path still resolve
    g = gem_info(GemEntry("x", gem_id="Metadata/Items/Gem/SkillGemWolfShred"))
    assert g.name == "Shred" and earliest_level(g) == 1   # talisman-granted
    assert earliest_level(gem_info(GemEntry("Virtuous Barrier"))) is None  # ascendancy gem


def test_spread_gem_events_caps_per_level():
    ev = [GemEvent(5, 0, i, f"+ g{i}") for i in range(7)]
    out = spread_gem_events(ev)
    assert [len(out[k]) for k in sorted(out)] == [3, 3, 1]
    assert sorted(out) == [5, 6, 7]


# ----------------------------------------------------------------------------- plan validity

def assert_plan_valid(detail):
    plan: LevelPlan = detail.plan
    tree = detail.tree
    assert isinstance(plan, LevelPlan)
    # 1. every node adjacent to start / earlier node of the same sub-graph, in plan order
    alloc = {detail.root}
    for n in detail.main_order:
        assert any(o in alloc for o in tree.nodes[n].adj), tree.nodes[n].sid
        assert tree.nodes[n].asc is None
        alloc.add(n)
    if detail.asc_order:
        a_alloc = {detail.asc_root}
        for n in detail.asc_order:
            assert any(o in a_alloc for o in tree.nodes[n].adj), tree.nodes[n].sid
            a_alloc.add(n)
    # 2. points never exceed what the level gives
    for lvl, used in detail.points_used.items():
        assert used <= passive_points_at(lvl), lvl
    asc_by_level: dict[int, int] = {}
    for n in detail.asc_order:
        if n in detail.alloc_level and not tree.nodes[n].free:
            asc_by_level[detail.alloc_level[n]] = asc_by_level.get(detail.alloc_level[n], 0) + 1
    spent = 0
    for lvl in sorted(asc_by_level):
        spent += asc_by_level[lvl]
        assert spent <= asc_points_at(lvl)
    # 3. allocation levels are monotone along main order
    lv = [detail.alloc_level[n] for n in detail.main_order if n in detail.alloc_level]
    assert lv == sorted(lv)
    # 4. strings
    for lvl, h in plan.hints.items():
        assert isinstance(h, LevelHint) and h.level == lvl
        assert h.passives or h.gems or h.note
        assert len(h.passives) <= 3 and len(h.gems) <= 3
        for s in (*h.passives, *h.gems, *(h.note,) * bool(h.note)):
            assert 0 < len(s) <= 32, s
    assert len(plan.title) <= 32
    # 5. planned ids are string ids, unique, chronological
    assert len(set(plan.planned_node_ids)) == len(plan.planned_node_ids)
    assert all(s in tree.by_sid for s in plan.planned_node_ids)
    levels = [detail.alloc_level[tree.by_sid[s]] for s in plan.planned_node_ids]
    assert levels == sorted(levels)


@pytest.mark.parametrize("fixture", [AMAZON, GEMLING])
def test_end_to_end_fixtures(fixture):
    d = build_plan_detail(fixture.read_text())
    assert_plan_valid(d)
    assert d.plan.hints[2].passives          # first point spent at level 2
    assert not d.plan.hint_for(1) or not d.plan.hint_for(1).passives


def test_amazon_plan_contents():
    d = build_plan_detail(AMAZON)
    p = d.plan
    assert p.char_class == "Huntress"
    assert p.title.startswith("Amazon")
    b = load_pob(AMAZON)
    spec = {n for n in b.spec.nodes}
    planned = {d.tree.by_sid[s] for s in p.planned_node_ids}
    # the whole PoB tree (minus free start nodes) is planned, nothing more (tree is connected)
    starts = {n for n in spec if d.tree.nodes[n].type in ("class_start", "asc_start")}
    assert planned == spec - starts
    # ascendancy points land at the trials
    asc_levels = sorted({d.alloc_level[n] for n in d.asc_order})
    qp = data.quest_points()["ascendancy_trials"]
    assert asc_levels[0] == qp[0]["typical_char_level"]
    assert p.ascendancy and all(h.note == "Восхождение" for h in p.ascendancy.values())
    # gems: skills appear once; main skill is in the level-1 hint
    all_gems = [g for h in p.hints.values() for g in h.gems]
    assert len(all_gems) == len(set(all_gems))
    assert any("Shred" in g for g in p.hints[1].gems)
    assert any(g.startswith("+ Herald of Ice") for g in all_gems)
    # with 52 levels of content the 73-node tree fits by level ~52
    assert max(d.alloc_level[n] for n in d.main_order) <= 55


def test_gemling_alt_start_uses_filler():
    d = build_plan_detail(GEMLING)
    assert any("Steiner filler" in w for w in d.warnings)
    assert any("start" in w and "Sorceress" in w for w in d.warnings)
    assert d.plan.title.endswith("Ice Nova")


def test_build_plan_api_returns_levelplan():
    p = build_plan(AMAZON.read_text())
    assert isinstance(p, LevelPlan)
    assert p.hint_for(12) is not None


def test_synthetic_from_real_log():
    """Rebuild the user's real Sorceress tree from Client.txt and plan it."""
    from pilot.planner.tree import PassiveTree
    t = PassiveTree.load()
    alloc: dict[str, None] = {}
    for added, sid in log_allocations():
        if added:
            alloc[sid] = None
        else:
            alloc.pop(sid, None)
    nodes = [t.by_sid[s] for s in alloc]
    xml = make_xml("Sorceress", "Stormweaver", nodes, [["Spark", "Arcane Tempo", "Lightning Exposure"],
                                                      ["Orb of Storms"], ["Herald of Thunder"]])
    d = build_level_plan(parse_pob_xml(xml))
    assert_plan_valid(d)
    assert d.plan.char_class == "Sorceress"
    assert set(d.plan.ascendancy) <= {"G2_13", "G3_10"} and d.plan.ascendancy
    assert any(n.startswith("★") for h in d.plan.ascendancy.values() for n in h.passives)
    assert not any(n.startswith("★") for h in d.plan.hints.values() for n in h.passives)
    asc_ids = [s for s in d.plan.planned_node_ids if s.startswith("Ascendancy")]
    assert set(asc_ids) == {s for s in alloc if s.startswith("Ascendancy")}


def test_multi_spec_stages():
    """Nodes of an earlier (smaller) PoB spec are allocated before the rest."""
    from collections import deque
    from pilot.planner.tree import PassiveTree
    t = PassiveTree.load().specialise("Huntress", "Amazon")
    b = load_pob(AMAZON)
    final = b.spec.nodes
    base = build_plan_detail(AMAZON)
    root = base.root
    target = base.main_order[-1]           # normally taken last
    allowed = set(base.main_order)
    nb = t.walker(root)
    prev, dq = {root: None}, deque([root])
    while dq:
        x = dq.popleft()
        for o in nb(x):
            if o in allowed and o not in prev:
                prev[o] = x
                dq.append(o)
    path, c = [], target
    while c is not None and c != root:
        path.append(c)
        c = prev[c]
    xml = make_xml("Huntress", "Amazon", final, [["Lunar Assault"]], extra_specs=[path + [root]])
    d = build_level_plan(parse_pob_xml(xml))
    assert_plan_valid(d)
    assert set(d.main_order[: len(path)]) == set(path)


def test_cli_runs():
    r = subprocess.run([sys.executable, "-m", "pilot.planner", str(AMAZON), "--max-level", "15"],
                       capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
                       env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")})
    assert r.returncode == 0, r.stderr
    assert "Amazon" in r.stdout and " 12 " in r.stdout
