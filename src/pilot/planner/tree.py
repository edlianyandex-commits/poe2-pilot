"""Passive tree graph, Steiner approximation and allocation ordering.

Graph rules (mirroring PoB's PassiveSpec pathing):
  * Edges are undirected (tree.json lists each connection on one side only; extract.py symmetrises).
  * The main tree is entered only from the character's class start node. Other class starts and
    every ascendancy start are never walked through.
  * Ascendancy nodes form separate sub-graphs: walking is only allowed between nodes of the same
    ascendancy, starting at that ascendancy's start node (which is free).
  * Nodes with an ``unlockConstraint`` (e.g. Oracle-only tree areas) are walkable only once the
    listed nodes are allocated.

Ordering heuristic (documented, deliberately simple and deterministic):
  1. Steiner tree: the PoB target set is normally already a connected tree that contains the
     class start; then it *is* the minimal Steiner tree (every target must be bought anyway).
     If it is not connected (tree-version drift, hand-written target lists) we use the classic
     shortest-path heuristic: repeatedly attach the cheapest-to-reach remaining terminal via a
     0-1 BFS where already-wanted nodes cost 0 and filler nodes cost 1 (2-approximation).
  2. Value per node from its type and stat text (see ``NodeValuer``):
       base: notable 3.0, keystone 2.0, small 1.0, attribute 0.8, jewel socket 0.3
       x (1 + 1.2*[matches the build's damage keywords] + 0.8*[life/defence keyword]
            + 1.0*[movement speed])
     Damage keywords come from the tags of the build's active gems (main skill counted double),
     so e.g. a cold spell build values "Spell Damage"/"Cold Damage"/"Freeze" nodes.
  3. Greedy "bang for buck": from the allocated set, BFS through not-yet-allocated nodes of the
     Steiner tree; pick the frontier path with the best (sum of path values) / (path length)^0.9,
     allocate that whole path, repeat. Exponent < 1 slightly favours finishing a path to a
     notable over sprinkling cheap smalls. Optional ``stage`` (from earlier PoB specs of a
     multi-tree leveling build) is respected: lower stages are finished first.
"""
from __future__ import annotations

import re
from collections import deque
from functools import lru_cache
from dataclasses import dataclass, field, replace
from typing import Callable, Iterable

from . import data as _data

TYPE_BASE = {"notable": 3.0, "keystone": 2.0, "small": 1.0, "attribute": 0.8, "jewel": 0.3,
             "class_start": 0.0, "asc_start": 0.0}

DEFENCE_RE = re.compile(
    r"maximum life|life regeneration|life recovery|life recoup|life leech|life flask|"
    r"maximum energy shield|energy shield|\barmour\b|evasion|resistance|block chance|chance to block|"
    r"stun threshold|ailment threshold|damage taken|maximum mana|mana regeneration|deflect",
    re.I)
MOVE_RE = re.compile(r"movement speed", re.I)

# gem tag -> stat text patterns that make a node "on-theme" for the build's damage
TAG_PATTERNS: dict[str, str] = {
    "spell": r"spell|cast speed",
    "attack": r"attack",
    "melee": r"melee|strike",
    "projectile": r"projectile",
    "area": r"area of effect",
    "cold": r"cold|freez|chill",
    "fire": r"fire|ignit|burn",
    "lightning": r"lightning|shock|electrocut",
    "chaos": r"chaos|poison|wither",
    "physical": r"physical|bleed",
    "minion": r"minion|companion|allies",
    "totem": r"totem",
    "duration": r"skill effect duration",
    "bow": r"\bbows?\b|arrow",
    "crossbow": r"crossbow|bolt",
    "spear": r"spear",
    "mace": r"mace",
    "quarterstaff": r"quarterstaff",
    "warcry": r"warcr",
    "slam": r"slam",
    "curse": r"curse",
    "herald": r"herald",
    "critical": r"critical",
    "nova": r"area of effect",
    "remnant": r"remnant",
    "shapeshift": r"shapeshift",
    "infusion": r"infus",
}
ELEMENTS = ("cold", "fire", "lightning")


@dataclass(frozen=True)
class Node:
    id: int
    sid: str               # string id, as written in Client.txt ("spells18", "AscendancySorceress1Notable3")
    name: str
    type: str              # small | notable | keystone | attribute | jewel | class_start | asc_start
    asc: str | None
    stats: tuple[str, ...]
    adj: tuple[int, ...]
    unlock: tuple[int, ...] = ()
    free: bool = False
    group: int | None = None
    variants: dict | None = field(default=None, compare=False, hash=False)  # class/asc -> {n, st, a}


class PassiveTree:
    def __init__(self, raw: dict | None = None):
        self.class_name: str | None = None
        self.asc_name: str | None = None
        if raw is None:
            return
        self.version: str = raw["version"]
        self.classes: dict = raw["classes"]
        self.nodes: dict[int, Node] = {}
        for k, r in raw["nodes"].items():
            nid = int(k)
            self.nodes[nid] = Node(
                id=nid, sid=r.get("s", ""), name=r.get("n", ""), type=r.get("t", "small"),
                asc=r.get("a"), stats=tuple(r.get("st", ())), adj=tuple(r.get("e", ())),
                unlock=tuple(r.get("uc", ())), free=bool(r.get("free")), group=r.get("g"),
                variants=r.get("sw"))
        self.by_sid = {n.sid: n.id for n in self.nodes.values() if n.sid}

    def specialise(self, class_name: str | None, asc_name: str | None) -> "PassiveTree":
        """Copy with class/ascendancy-specific node variants applied ("switchable" nodes).

        E.g. near the shared Ranger/Huntress start a Huntress sees "Attack Damage" where a Ranger
        sees "Projectile Damage"; Abyssal Lich re-skins the Lich ascendancy nodes.
        """
        t = PassiveTree()
        t.version, t.classes, t.by_sid = self.version, self.classes, self.by_sid
        t.class_name, t.asc_name = class_name, asc_name
        t.nodes = {}
        for nid, n in self.nodes.items():
            v = None
            if n.variants:
                v = n.variants.get(asc_name) if asc_name else None
                if v is None and class_name:
                    v = n.variants.get(class_name)
            if v:
                n = replace(n, name=v.get("n", n.name), stats=tuple(v.get("st", n.stats)))
            t.nodes[nid] = n
        return t

    def asc_domain(self, asc_name: str | None) -> str | None:
        """Node ``asc`` value used by this ascendancy (Abyssal Lich lives on Lich nodes)."""
        if not asc_name:
            return None
        if any(n.asc == asc_name for n in self.nodes.values()):
            return asc_name
        for n in self.nodes.values():
            if n.type == "asc_start" and n.variants and asc_name in n.variants:
                return n.asc
        return asc_name

    @classmethod
    def load(cls, version: str | None = None) -> "PassiveTree":
        return _cached_tree(version or _data.DEFAULT_TREE_VERSION)

    # -- class helpers
    def class_names(self) -> list[str]:
        return list(self.classes)

    def class_start(self, class_name: str) -> int:
        c = self.classes.get(class_name)
        if not c or c.get("start") is None:
            raise KeyError(f"unknown class {class_name!r}")
        return int(c["start"])

    # jewel texts use PoE1 class names for the shared start positions
    _START_ALIASES = {"shadow": "SIX", "marauder": "MARAUDER", "duelist": "DUELIST",
                      "templar": "TEMPLAR", "ranger": "RANGER", "witch": "WITCH"}

    def start_for(self, class_name: str) -> int | None:
        """Start node for a class name as written on an item ("Ranger", "Shadow", ...)."""
        try:
            return self.class_start(class_name)
        except KeyError:
            pass
        alias = self._START_ALIASES.get(class_name.lower())
        for n in self.nodes.values():
            if n.type == "class_start" and n.name == alias:
                return n.id
        return None

    def asc_start(self, asc_name: str) -> int | None:
        for c in self.classes.values():
            a = c["ascendancies"].get(asc_name)
            if a and a.get("start") is not None:
                return int(a["start"])
        for n in self.nodes.values():  # switchable start (Abyssal Lich -> Lich start)
            if n.type == "asc_start" and n.variants and asc_name in n.variants:
                return n.id
        return None

    def class_of_ascendancy(self, asc_name: str) -> str | None:
        for cname, c in self.classes.items():
            if asc_name in c["ascendancies"]:
                return cname
        return None

    # -- walking
    def walker(self, root: int, unlocked: Callable[[int], bool] = lambda _n: True):
        """Return neighbours(nid) honouring the pathing rules for the sub-graph containing root."""
        root_node = self.nodes[root]
        domain = root_node.asc  # None for main tree, ascendancy name for ascendancy sub-graph

        def neighbours(nid: int) -> Iterable[int]:
            for o in self.nodes[nid].adj:
                on = self.nodes.get(o)
                if on is None or o == root:
                    continue
                if on.type in ("class_start", "asc_start"):
                    continue
                if on.asc != domain:
                    continue
                if on.unlock and not all(unlocked(u) for u in on.unlock):
                    continue
                yield o
        return neighbours


@lru_cache(maxsize=4)
def _cached_tree(version: str) -> PassiveTree:
    return PassiveTree(_data.tree_data(version))


# ----------------------------------------------------------------------------- Steiner tree

def steiner_tree(tree: PassiveTree, root: int, terminals: Iterable[int],
                 unlocked: Callable[[int], bool] | None = None) -> tuple[set[int], set[int]]:
    """Connect ``terminals`` to ``root``. Returns (node set incl. root, unreachable terminals)."""
    terms = set(terminals) - {root}
    wanted = set(terms)
    if unlocked is None:
        unlocked = lambda n: n in wanted  # noqa: E731 - constraint met if the unlock node is a target
    nb = tree.walker(root, unlocked)
    connected = {root}
    remaining = set(terms)
    unreachable: set[int] = set()
    while remaining:
        # 0-1 BFS from the connected set; wanted nodes are free (they must be bought anyway)
        dist = {n: 0 for n in connected}
        prev: dict[int, int] = {}
        dq = deque(connected)
        hit = None
        while dq:
            cur = dq.popleft()
            if cur in remaining:
                hit = cur
                break
            for o in nb(cur):
                w = 0 if o in wanted else 1
                nd = dist[cur] + w
                if nd < dist.get(o, 1 << 30):
                    dist[o] = nd
                    prev[o] = cur
                    (dq.appendleft if w == 0 else dq.append)(o)
        if hit is None:
            unreachable |= remaining
            break
        cur = hit
        while cur not in connected:
            connected.add(cur)
            remaining.discard(cur)
            cur = prev[cur]
        # absorb terminals that are now adjacent-free (connected through wanted nodes) next round
    return connected, unreachable


# ----------------------------------------------------------------------------- values

@dataclass
class NodeValuer:
    damage_tags: dict[str, float] = field(default_factory=dict)  # tag -> weight (main skill 2.0)

    def __post_init__(self):
        pats = []
        for tag, w in self.damage_tags.items():
            p = TAG_PATTERNS.get(tag)
            if p:
                pats.append((re.compile(p, re.I), w))
        if any(t in self.damage_tags for t in ELEMENTS):
            pats.append((re.compile(r"elemental", re.I), 1.0))
        self._pats = pats
        self._norm = max((w for _, w in pats), default=1.0)

    def damage_match(self, text: str) -> float:
        if not self._pats:
            return 1.0 if re.search(r"damage", text, re.I) else 0.0
        best = max((w for p, w in self._pats if p.search(text)), default=0.0)
        return best / self._norm

    def value(self, node: Node) -> float:
        base = TYPE_BASE.get(node.type, 1.0)
        text = " ".join(node.stats) + " " + node.name
        mult = 1.0
        mult += 1.2 * self.damage_match(text)
        if DEFENCE_RE.search(text):
            mult += 0.8
        if MOVE_RE.search(text):
            mult += 1.0
        return base * mult


# ----------------------------------------------------------------------------- ordering

def allocation_order(tree: PassiveTree, root: int, to_alloc: set[int],
                     value: Callable[[int], float], stage: dict[int, int] | None = None,
                     cost: Callable[[int], int] = lambda _n: 1,
                     extra_unlocked: set[int] | None = None,
                     opens: dict[int, int] | None = None) -> list[int]:
    """Order ``to_alloc`` so every node is adjacent to root/an earlier node (greedy value/cost).

    ``opens`` maps a node to an extra start that becomes allocated once that node is taken
    (a jewel socket holding Split Personality opens another class's starting point).
    """
    stage = stage or {}
    opens = opens or {}
    allocated = {root}
    order: list[int] = []
    remaining = set(to_alloc) - {root}

    extra = extra_unlocked or set()

    def unlocked(n: int) -> bool:
        return n in allocated or n in extra

    nb = tree.walker(root, unlocked)
    while remaining:
        cur_stage = min(stage.get(n, 0) for n in remaining)
        # BFS restricted to remaining nodes
        prev: dict[int, int | None] = {}
        dist: dict[int, int] = {}
        pval: dict[int, float] = {}
        dq = deque()
        for a in sorted(allocated):
            for o in nb(a):
                if o in remaining and o not in prev:
                    prev[o] = None
                    dist[o] = cost(o)
                    pval[o] = value(o)
                    dq.append(o)
        while dq:
            c = dq.popleft()
            for o in nb(c):
                if o in remaining and o not in prev:
                    prev[o] = c
                    dist[o] = dist[c] + cost(o)
                    pval[o] = pval[c] + value(o)
                    dq.append(o)
        if not prev:
            break  # rest unreachable (should not happen for a Steiner tree)
        best, best_score = None, None
        for n in prev:
            if stage.get(n, 0) != cur_stage:
                continue
            d = max(dist[n], 0.5)
            score = (pval[n] / d ** 0.9, -dist[n], -n)
            if best_score is None or score > best_score:
                best, best_score = n, score
        if best is None:  # current-stage nodes not reachable yet: take any reachable node
            best = min(prev, key=lambda n: (stage.get(n, 0), dist[n], n))
        path = []
        c = best
        while c is not None:
            path.append(c)
            c = prev[c]
        for n in reversed(path):
            order.append(n)
            allocated.add(n)
            remaining.discard(n)
            if n in opens:
                allocated.add(opens[n])
    return order
