"""Passive tree window: node geometry and TreeView states for the Travic speed-campaign build."""
from __future__ import annotations

import math

import pytest

from pilot.contracts import TreeView
from pilot.planner import build_plan_detail
from pilot.planner.plan import _component, passive_points_at
from pilot.planner.treeview import TreeViewBuilder, build_tree_view_builder

from planner_helpers import FIX

SPEED = FIX / "twister_speed_campaign_0_5_5.pob"
SOCKET = 54127  # holds Split Personality (Ranger start)


@pytest.fixture(scope="module")
def builder() -> TreeViewBuilder:
    return build_tree_view_builder(SPEED)


def test_positions_plausible(tree):
    starts = {c: tree.nodes[cd["start"]] for c, cd in tree.classes.items()}
    for n in starts.values():                       # six starts on a ring around the centre
        assert 1300 < math.hypot(n.x, n.y) < 1600, (n.name, n.x, n.y)
    assert starts["Witch"].y < -1300 and abs(starts["Witch"].x) < 50      # top
    assert starts["Mercenary"].y > 1300 and abs(starts["Mercenary"].x) < 50  # bottom
    assert all(n.x is not None for n in tree.nodes.values())
    # adjacent main-tree nodes are close (start-node spokes excluded)
    dists = [math.dist((n.x, n.y), (tree.nodes[o].x, tree.nodes[o].y))
             for n in tree.nodes.values() if n.asc is None and n.type != "class_start"
             for o in n.adj if tree.nodes[o].asc is None and tree.nodes[o].type != "class_start"]
    dists.sort()
    assert dists[len(dists) // 2] < 600
    assert sum(d < 1500 for d in dists) / len(dists) > 0.99
    witch = tree.class_start("Witch")
    assert all(math.dist((tree.nodes[o].x, tree.nodes[o].y), (starts["Witch"].x, starts["Witch"].y)) < 1500
               for o in tree.nodes[witch].adj if tree.nodes[o].asc is None)


def test_notable_icons(tree):
    nots = [n for n in tree.nodes.values() if n.type in ("notable", "keystone") and n.asc is None]
    with_icon = [n for n in nots if n.icon]
    assert len(with_icon) > 0.95 * len(nots)
    assert all(n.icon.startswith("https://cdn.poe2db.tw/image/") and n.icon.endswith(".webp")
               for n in with_icon)
    assert not any(n.icon for n in tree.nodes.values() if n.type == "small")


def _by_state(view: TreeView) -> dict[str, list]:
    out: dict[str, list] = {}
    for n in view.nodes:
        out.setdefault(n.state, []).append(n)
    return out


def _check_view(view: TreeView, b: TreeViewBuilder):
    sids = {n.sid for n in view.nodes}
    assert len(sids) == len(view.nodes)
    assert all(a in sids and c in sids and a < c for a, c in view.edges)
    assert all(b.tree.nodes[b.tree.by_sid[n.sid]].asc is None for n in view.nodes)
    nxt = sorted((n for n in view.nodes if n.state == "next"), key=lambda n: n.order)
    assert [n.order for n in nxt] == list(range(1, len(nxt) + 1))
    assert all(n.order is None for n in view.nodes if n.state != "next")
    # next nodes are reachable in order from start / taken / earlier next / opened start
    alloc = {b.tree.by_sid[n.sid] for n in view.nodes if n.state in ("taken", "offplan")}
    for n in nxt:
        nid = b.tree.by_sid[n.sid]
        assert b._reachable(nid, alloc), n.sid
        alloc.add(nid)
    kinds = {n.kind for n in view.nodes}
    assert kinds <= {"small", "notable", "keystone", "attribute", "jewel", "start"}
    assert any(n.kind == "start" and n.sid == b.tree.nodes[b.root].sid for n in view.nodes)


@pytest.mark.parametrize("level", [1, 13, 14, 30])
def test_states_follow_plan(builder, level):
    v = builder.view(taken=None, level=level)
    _check_view(v, builder)
    st = _by_state(v)
    taken_main = [n for n in st.get("taken", []) if n.kind != "start"]
    assert len(taken_main) == builder.d.points_used[level] <= passive_points_at(level)
    assert v.points_free == passive_points_at(level) - len(taken_main) == 0
    assert all(n.level is not None and n.level <= level for n in taken_main)
    assert len(st["next"]) == 5
    assert all(n.level > level for n in st["next"])
    assert "offplan" not in st
    assert st.get("other")                               # context ring
    shown_planned = {n.sid for n in v.nodes if n.state in ("taken", "next", "planned") and n.kind != "start"}
    assert shown_planned == {builder.tree.nodes[n].sid for n in builder.plan_order}
    ranger = builder.tree.nodes[builder.opens[SOCKET]].sid
    assert any(n.sid == ranger and n.kind == "start" for n in v.nodes)


def test_split_personality_socket_comes_first(builder):
    tree = builder.tree
    sock_sid = tree.nodes[SOCKET].sid
    own = _component(tree, builder.root, builder.planned)
    ranger_side = {tree.nodes[n].sid for n in builder.planned - own}
    assert ranger_side
    sock_level = builder.plan_level[SOCKET]
    assert sock_level <= 13
    for lvl in range(1, sock_level):
        v = builder.view(level=lvl, next_n=8)
        nxt = sorted((n for n in v.nodes if n.state == "next"), key=lambda n: n.order)
        ranger_orders = [n.order for n in nxt if n.sid in ranger_side]
        sock = [n.order for n in nxt if n.sid == sock_sid]
        if ranger_orders:
            assert sock and sock[0] < min(ranger_orders)
    v = builder.view(level=sock_level - 1, next_n=1 + sum(
        1 for n in builder.plan_order if builder.plan_level[n] == sock_level))
    assert any(n.sid == sock_sid and n.state == "next" for n in v.nodes)
    # before the socket the Ranger start is not usable, afterwards it is
    ranger = tree.nodes[builder.opens[SOCKET]].sid
    st = {n.sid: n.state for n in builder.view(level=sock_level - 1).nodes}
    assert st[ranger] == "planned"
    assert {n.sid: n.state for n in builder.view(level=sock_level).nodes}[ranger] == "taken"


def test_offplan_and_real_taken(builder):
    tree = builder.tree
    plan10 = {tree.nodes[n].sid for n in builder.plan_order if builder.plan_level[n] <= 10}
    # one off-plan node adjacent to the class start, plus junk / ascendancy ids ignored
    off = next(tree.nodes[o] for o in tree.nodes[builder.root].adj
               if o not in builder.planned and tree.nodes[o].asc is None
               and tree.nodes[o].type not in ("class_start", "asc_start"))
    v = builder.view(taken=plan10 | {off.sid, "no_such_node", "AscendancyMercenary3Notable1"}, level=12)
    _check_view(v, builder)
    st = {n.sid: n for n in v.nodes}
    assert st[off.sid].state == "offplan" and st[off.sid].level is None
    assert all(st[s].state == "taken" for s in plan10)
    assert v.points_free == passive_points_at(12) - len(plan10) - 1
    # empty allocation, no level
    v0 = builder.view(taken=set(), level=None)
    assert v0.points_free is None and v0.level is None
    assert not any(n.state == "taken" and n.kind != "start" for n in v0.nodes)
    first = next(n for n in v0.nodes if n.order == 1)
    assert first.sid == tree.nodes[builder.plan_order[0]].sid


def test_builder_from_detail_and_code():
    d = build_plan_detail(SPEED.read_text().strip())
    b = TreeViewBuilder(d)
    v = b.view(level=14)
    assert v.level == 14 and v.nodes and v.edges
    assert any(n.icon_url for n in v.nodes if n.kind == "notable")
