"""Passive tree window data: PlanDetail + what is allocated -> TreeView.

    b = build_tree_view_builder("builds/x.pob")
    view = b.view(taken=None, level=14)              # assume the plan was followed up to 14
    view = b.view(taken={"spells18", ...}, level=14) # string ids from Client.txt

Node states:
  taken    allocated and part of the plan
  offplan  allocated but not in the plan
  next     the next ``next_n`` planned nodes to take, numbered 1..n. Walked in plan order; each one
           must be reachable when it is its turn (adjacent to the class start, an allocated node,
           an earlier "next" node, or a start opened by a socketed Split Personality jewel)
  planned  the rest of the plan
  other    one ring of neighbours around the shown nodes, for context
Ascendancy nodes are not part of this view.
"""
from __future__ import annotations

from pathlib import Path

from pilot.contracts import TreeNodeView, TreeView

from .plan import PlanDetail, _display, passive_points_at

KIND = {"class_start": "start", "small": "small", "notable": "notable", "keystone": "keystone",
        "attribute": "attribute", "jewel": "jewel"}


class TreeViewBuilder:
    def __init__(self, detail: PlanDetail):
        self.d = detail
        self.tree = detail.tree
        self.root = detail.root
        self.opens: dict[int, int] = dict(getattr(detail, "opens", {}) or {})
        # main-tree plan in chronological order (ascendancy excluded)
        self.plan_order: list[int] = [n for n in detail.main_order if self.tree.nodes[n].asc is None]
        self.planned = set(self.plan_order)
        self.plan_level = {n: detail.alloc_level.get(n) for n in self.plan_order}

    # ------------------------------------------------------------------ helpers
    def _ids(self, taken: set[str]) -> set[int]:
        out = set()
        for sid in taken:
            n = self.tree.by_sid.get(sid)
            if n is not None and n in self.tree.nodes and self.tree.nodes[n].asc is None \
                    and self.tree.nodes[n].type not in ("class_start", "asc_start"):
                out.add(n)
        return out

    def _starts(self, allocated: set[int]) -> set[int]:
        """Roots usable now: own class start plus starts opened by an allocated jewel socket."""
        return {self.root} | {s for sock, s in self.opens.items() if sock in allocated}

    def _reachable(self, n: int, allocated: set[int]) -> bool:
        roots = self._starts(allocated)
        return any(o in allocated or o in roots for o in self.tree.nodes[n].adj)

    def next_nodes(self, taken_ids: set[int], next_n: int = 5) -> list[int]:
        cur = set(taken_ids)
        out: list[int] = []
        while len(out) < next_n:
            pick = next((n for n in self.plan_order if n not in cur and self._reachable(n, cur)), None)
            if pick is None:
                break
            out.append(pick)
            cur.add(pick)
        return out

    # ------------------------------------------------------------------ view
    def view(self, taken: set[str] | None = None, level: int | None = None,
             next_n: int = 5) -> TreeView:
        if taken is None:
            taken_ids = ({n for n in self.plan_order
                          if self.plan_level[n] is not None and self.plan_level[n] <= level}
                         if level is not None else set())
        else:
            taken_ids = self._ids(set(taken))
        nxt = self.next_nodes(taken_ids, next_n)
        order = {n: i for i, n in enumerate(nxt, 1)}

        state: dict[int, str] = {}
        for n in self.plan_order:
            state[n] = "planned"
        for n in taken_ids:
            state[n] = "taken" if n in self.planned else "offplan"
        for n in nxt:
            state[n] = "next"
        starts = {self.root} | set(self.opens.values())
        for s in starts:
            state[s] = "taken" if s in self._starts(taken_ids) else "planned"
        shown = set(state)
        for n in list(shown):
            for o in self.tree.nodes[n].adj:
                on = self.tree.nodes.get(o)
                if (o not in shown and on is not None and on.asc is None
                        and on.type != "asc_start" and (on.type != "class_start" or o in starts)):
                    state[o] = "other"
        shown = {n for n in state if self.tree.nodes[n].x is not None}

        views = []
        for n in sorted(shown, key=lambda k: (self.tree.nodes[k].y, self.tree.nodes[k].x, k)):
            node = self.tree.nodes[n]
            views.append(TreeNodeView(
                sid=node.sid,
                name=node.name if node.type == "class_start" else _display(self.tree, n, self.d.build),
                kind=KIND.get(node.type, "small"),
                x=float(node.x), y=float(node.y),
                stats=tuple(node.stats),
                state=state[n],
                order=order.get(n),
                level=self.plan_level.get(n),
                icon_url=node.icon,
            ))
        edges = sorted({tuple(sorted((self.tree.nodes[a].sid, self.tree.nodes[b].sid)))
                        for a in shown for b in self.tree.nodes[a].adj if b in shown and a != b})
        points_free = None
        if level is not None:
            points_free = max(0, passive_points_at(level) - len(taken_ids))
        return TreeView(nodes=tuple(views), edges=tuple(edges), level=level, points_free=points_free)


def build_tree_view_builder(path_or_code: str | Path) -> TreeViewBuilder:
    from . import build_plan_detail
    return TreeViewBuilder(build_plan_detail(path_or_code))
