"""Split Personality: part of the tree grows from another class start once its socket is taken."""
from __future__ import annotations

from pilot.planner import load_pob
from pilot.planner.plan import build_level_plan, passive_points_at

from planner_helpers import FIX

SPEED = FIX / "twister_speed_campaign_0_5_5.pob"   # Travic speed campaign, Mercenary + Ranger start


def test_start_jewel_parsed():
    b = load_pob(SPEED.read_text(encoding="utf-8").strip())
    assert b.spec.start_jewels == {54127: "Ranger"}


def test_socket_path_first_then_other_start():
    b = load_pob(SPEED.read_text(encoding="utf-8").strip())
    d = build_level_plan(b)
    tree = d.tree
    ranger = tree.start_for("Ranger")
    sock = 54127

    # no invented filler: every planned node is from the PoB tree
    assert set(d.main_order) <= set(b.spec.nodes)
    assert not any("filler" in w for w in d.plan.warnings)

    # adjacency holds once the jewel opens the Ranger start
    alloc = {d.root}
    for n in d.main_order:
        assert any(o in alloc for o in tree.nodes[n].adj), tree.nodes[n].sid
        alloc.add(n)
        if n == sock:
            alloc.add(ranger)

    # the socket comes right after the Mercenary-side path, early in the campaign
    i = d.main_order.index(sock)
    assert all(ranger not in tree.nodes[n].adj for n in d.main_order[:i])
    assert d.alloc_level[sock] <= 15
    assert d.points_used[d.alloc_level[sock]] <= passive_points_at(d.alloc_level[sock])
    assert d.plan.hints[d.alloc_level[sock]].note == "Самоцвет в гнездо"


def test_unusable_start_jewel_falls_back():
    """A start jewel in a socket the own start can't reach is ignored, not fatal."""
    from planner_helpers import GEMLING  # endgame tree without a start jewel
    b = load_pob(GEMLING.read_text(encoding="utf-8").strip())
    b.spec.start_jewels[next(iter(b.spec.nodes))] = "Nobody"
    d = build_level_plan(b)
    assert any("ignored" in w for w in d.plan.warnings)
    assert d.main_order
