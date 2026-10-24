from __future__ import annotations

import json

from pilot.planner import data
from pilot.planner.tree import NodeValuer, allocation_order, steiner_tree

from planner_helpers import log_allocations


def test_data_files_small_and_attributed():
    d = data.data_dir()
    total = sum(p.stat().st_size for p in d.glob("*.json"))
    assert total < 5_000_000
    assert (d / "ATTRIBUTION.md").read_text(encoding="utf-8").count("MIT") >= 1
    q = json.loads((d / "quest_points.json").read_text(encoding="utf-8"))
    assert q["sources"]


def test_adjacency_symmetric(tree):
    for nid, n in tree.nodes.items():
        for o in n.adj:
            assert nid in tree.nodes[o].adj, (nid, o)


def test_class_and_ascendancy_starts(tree):
    assert len(tree.classes) >= 8
    for cname, c in tree.classes.items():
        assert tree.nodes[c["start"]].type == "class_start"
        for aname in c["ascendancies"]:
            s = tree.asc_start(aname)
            assert s is not None, aname
            assert tree.nodes[s].type == "asc_start"


def test_main_tree_connected_from_class_starts(tree):
    seen = set()
    for c in tree.classes.values():
        r = c["start"]
        nb = tree.walker(r)
        stack = [r]
        seen.add(r)
        while stack:
            x = stack.pop()
            for o in nb(x):
                if o not in seen:
                    seen.add(o)
                    stack.append(o)
    main = [n for n, v in tree.nodes.items() if v.asc is None and v.type != "class_start"]
    unreachable = [n for n in main if n not in seen]
    # only edge-less special nodes (Delirium anoint notables, sinister sockets) are off-graph
    assert all(not tree.nodes[n].adj for n in unreachable)
    assert len(unreachable) < 0.01 * len(main)


def test_each_ascendancy_connected(tree):
    for c in tree.classes.values():
        for aname in c["ascendancies"]:
            dom = tree.asc_domain(aname)
            root = tree.asc_start(aname)
            nb = tree.walker(root)
            seen, stack = {root}, [root]
            while stack:
                x = stack.pop()
                for o in nb(x):
                    if o not in seen:
                        seen.add(o)
                        stack.append(o)
            nodes = [n for n, v in tree.nodes.items() if v.asc == dom and v.adj]
            reach = sum(1 for n in nodes if n in seen)
            assert reach >= 0.8 * len(nodes), (aname, reach, len(nodes))


def test_log_string_ids_map_to_tree(tree):
    """Client.txt node ids are PoB `stringId`s: every one in the real log must resolve."""
    allocs = log_allocations()
    assert len(allocs) > 80
    missing = {sid for _, sid in allocs if sid not in tree.by_sid}
    assert not missing


def test_log_allocations_follow_graph(tree):
    """Replay the real Sorceress run: each allocation must touch the start or an allocated node."""
    root = tree.class_start("Sorceress")
    asc = tree.asc_start("Stormweaver")
    alloc: set[int] = set()
    bad = []
    for added, sid in log_allocations():
        n = tree.by_sid[sid]
        if not added:
            alloc.discard(n)
            continue
        if not any(o in alloc or o in (root, asc) for o in tree.nodes[n].adj):
            bad.append(sid)
        alloc.add(n)
    assert len(bad) <= 2, bad   # log order inside a multi-node click is not always topological


def test_switchable_variants(tree):
    hunt = tree.specialise("Huntress", "Amazon")
    rang = tree.specialise("Ranger", "Deadeye")
    switch = [n for n, v in tree.nodes.items() if v.variants and "Huntress" in v.variants]
    assert switch
    n = switch[0]
    assert hunt.nodes[n].name == tree.nodes[n].variants["Huntress"]["n"]
    assert rang.nodes[n].name == tree.nodes[n].name
    # Abyssal Lich re-uses the Lich ascendancy nodes
    assert tree.asc_domain("Abyssal Lich") == "Lich"
    assert tree.asc_start("Abyssal Lich") == tree.asc_start("Lich")


def _check_order(tree, root, order):
    alloc = {root}
    nb = tree.walker(root, lambda n: True)
    for n in order:
        assert any(o in alloc for o in tree.nodes[n].adj) and n in set(nb_any(tree, alloc, nb)), n
        alloc.add(n)


def nb_any(tree, alloc, nb):
    for a in alloc:
        yield from nb(a)


def test_steiner_connects_sparse_targets(tree):
    root = tree.class_start("Sorceress")
    # pick 3 notables reachable from the Sorceress start, give only them as terminals
    nb = tree.walker(root)
    dist = {root: 0}
    frontier = [root]
    notables = []
    while frontier and len(notables) < 3:
        nxt = []
        for x in frontier:
            for o in nb(x):
                if o not in dist:
                    dist[o] = dist[x] + 1
                    nxt.append(o)
                    if tree.nodes[o].type == "notable" and dist[o] >= 3:
                        notables.append(o)
        frontier = nxt
    st, unreach = steiner_tree(tree, root, notables)
    assert not unreach
    assert set(notables) <= st
    # Steiner tree no bigger than the union of independent shortest paths
    assert len(st) - 1 <= sum(dist[n] for n in notables)
    order = allocation_order(tree, root, st, lambda n: 1.0)
    assert set(order) == st - {root}
    _check_order(tree, root, order)


def test_order_prefers_valuable_and_respects_stages(tree):
    root = tree.class_start("Witch")
    nb = tree.walker(root)
    a, b = list(nb(root))[:2]
    st = {root, a, b}
    order = allocation_order(tree, root, st, lambda n: 5.0 if n == b else 1.0)
    assert order[0] == b
    order = allocation_order(tree, root, st, lambda n: 5.0 if n == b else 1.0, stage={a: 0, b: 1})
    assert order[0] == a


def test_valuer_keywords(tree):
    v = NodeValuer({"spell": 2.0, "cold": 1.0})
    by_name = {}
    for n in tree.nodes.values():
        by_name.setdefault((n.name, n.type), n)
    spell = next(n for n in tree.nodes.values() if n.type == "small" and n.name == "Spell Damage")
    melee = next(n for n in tree.nodes.values() if n.type == "small" and n.name == "Melee Damage")
    assert v.value(spell) > v.value(melee)
    life = next(n for n in tree.nodes.values() if n.type == "small" and any("maximum Life" in s for s in n.stats))
    assert v.value(life) > 1.0
