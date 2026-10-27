"""Stage trees for build files written from text guides (shared by tools/make_*.py).

Each notable, in priority order, goes into the earliest stage (not before its own) where the
stage's tree still fits its passive points; stages are nested, so nothing is ever refunded.
"""
from pilot.planner.tree import steiner_tree


def _dist(t, start):
    nb = t.walker(start, lambda n: True)
    d, q = {start: 0}, [start]
    for c in q:
        for o in nb(c):
            if o not in d and not t.nodes[o].asc:
                d[o] = d[c] + 1
                q.append(o)
    return d


def stage_trees(t, start, priority, budgets):
    d = _dist(t, start)
    node = lambda nm: min((n for n in d if t.nodes[n].name == nm), key=d.get)  # noqa: E731
    stage_of: dict[int, int] = {}
    size = lambda k, extra=(): len(steiner_tree(  # noqa: E731
        t, start, [n for n, s in stage_of.items() if s <= k] + list(extra))[0]) - 1
    for nm, first in priority:
        n = node(nm)
        for k in range(first, len(budgets)):
            if all(size(j, [n]) <= budgets[j] for j in range(k, len(budgets))):
                stage_of[n] = k
                break
        else:
            print("  does not fit:", nm)
    out = []
    for k, budget in enumerate(budgets):
        nodes = steiner_tree(t, start, [n for n, s in stage_of.items() if s <= k])[0]
        print(k, len(nodes) - 1, "/", budget, [t.nodes[n].name for n, s in stage_of.items() if s == k])
        out.append([{"id": t.nodes[n].sid} for n in sorted(nodes) if n != start])
    return out
