"""In-game build planner files (.build, as exported by mobalytics "Download Build File") -> PobBuild.

A download is either one JSON build or a zip of several (one per level range, e.g. Act 1 /
Act 2 / Act 3+). Each JSON has ``passives`` (string ids, the same ids Client.txt logs),
``skills`` (gem metadata ids with supports) and ``inventory_slots`` (base types by level range).
Stages become PoB-like specs, so the planner finishes the smaller (earlier) trees first.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

from . import data as _data
from .pobcode import GemEntry, PobBuild, SkillGroup, TreeSpec
from .tree import PassiveTree

MAX_FILE = 2_000_000
_NUM = ("One", "Two", "Three", "Four", "Five")


def read_build_files(path: str | Path) -> list[dict]:
    """Stages in file order (zip members sorted by passive count = earlier stage first)."""
    raw = Path(path).read_bytes()
    if raw[:2] == b"PK":
        out = []
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for info in z.infolist():
                if info.is_dir() or info.file_size > MAX_FILE or ".." in info.filename:
                    continue
                out.append(json.loads(z.read(info).decode("utf-8")))
        return sorted(out, key=lambda d: len(d.get("passives") or ()))
    return [json.loads(raw.decode("utf-8"))]


_GID: dict[str, str] | None = None


def _gem_key(game_id: str) -> str | None:
    """In-game id ('Metadata/Items/Gems/SupportGemMartialTempo') -> planner data key
    ('Metadata/Items/Gems/SkillGemRapidAttacksSupport', i.e. Rapid Attacks I), via PoB's gameId."""
    global _GID
    gems = _data.gems_data()
    if _GID is None:
        _GID = {r["gid"].replace("/Items/Gem/", "/Items/Gems/"): k for k, r in gems.items() if r.get("gid")}
    gid = game_id.replace("/Items/Gem/", "/Items/Gems/")
    if gid in _GID:
        return _GID[gid]
    return gid if gid in gems else None


def _gem_name(game_id: str) -> str:
    key = _gem_key(game_id)
    if key:
        return _data.gems_data()[key]["n"]
    tail = game_id.rsplit("/", 1)[-1].removeprefix("SkillGem").removeprefix("SupportGem")
    return re.sub(r"(?<!^)(?=[A-Z])", " ", tail)          # best effort for unknown gems


def stage_starts(stages: list[dict]) -> list[int]:
    """First character level of each stage, from names like 'Level 15-28 (Act 2)'."""
    out = []
    for i, st in enumerate(stages):
        m = re.search(r"Level\s+(\d+)", st.get("name", ""))
        out.append(int(m.group(1)) if m else (1 if i == 0 else out[-1] + 1))
    out[0] = 1
    return out


def _in(interval, lvl: int) -> bool:
    a, b = (list(interval or [1, 100]) + [100])[:2]
    return a <= lvl <= b


def stage_gem_plan(stages: list[dict], max_level: int = 100):
    """Gems exactly as the guide's stages list them -> (setups, gem_rows, gem_hints) by level.

    A stage applies from its first level until the next stage; inside it each skill and
    support follows its own level_interval. Hints name what changed: "+ X", "Sup → Skill".
    """
    from pilot.contracts import GemRow
    from .plan import gem_card, gem_info, setup_line

    starts = stage_starts(stages)
    cards: dict[str, object] = {}

    def info(gid: str):
        if gid not in cards:
            cards[gid] = gem_info(GemEntry(name=_gem_name(gid), gem_id=_gem_key(gid) or gid))
        return cards[gid]

    setups, rows, hints = {}, {}, {}
    prev: dict[str, tuple[str, ...]] = {}
    for lvl in range(1, max_level + 1):
        st = stages[max(i for i, s in enumerate(starts) if s <= lvl)]
        cur: dict[str, tuple[str, ...]] = {}
        for sk in st.get("skills") or ():
            if _in(sk.get("level_interval"), lvl):
                cur[sk["id"]] = tuple(s["id"] for s in sk.get("support_skills") or ()
                                      if _in(s.get("level_interval"), lvl))
        if cur == prev:
            continue
        rows[lvl] = tuple(GemRow(skill=gem_card(info(k)), supports=tuple(gem_card(info(s)) for s in sups))
                          for k, sups in cur.items())
        setups[lvl] = tuple(setup_line(info(k).name, [info(s).name for s in sups]) for k, sups in cur.items())
        change = [f"+ {info(k).name}" for k in cur if k not in prev]
        for k, sups in cur.items():
            change += [f"{info(s).name} → {info(k).name}" for s in sups if s not in prev.get(k, ())]
        if change:
            hints[lvl] = tuple(change)
        prev = cur
    return setups, rows, hints


def _linked(tree: PassiveTree, start: int, nodes: set[int]) -> set[int]:
    """Nodes reachable from the class start through `nodes` (ascendancy nodes kept as is)."""
    seen, stack = {start}, [start]
    while stack:
        for o in tree.nodes[stack.pop()].adj:
            if o in nodes and o not in seen:
                seen.add(o)
                stack.append(o)
    return seen | {n for n in nodes if tree.nodes[n].asc}


def _class_of(tree: PassiveTree, sids: list[str], hint: str = "") -> str | None:
    """Class whose start node touches the allocated passives.

    Two classes share each start (Ranger/Huntress, Witch/Sorceress): the ascendancy nodes
    decide, else a class name in the build's name/link (e.g. "Twister Monk"), else the first.
    """
    nodes = {tree.by_sid[s] for s in sids if s in tree.by_sid}
    cands = [cls for cls in tree.classes
             if any(o in nodes for o in tree.nodes[tree.class_start(cls)].adj)]
    if len(cands) <= 1:
        return cands[0] if cands else None
    for n in nodes:
        asc = tree.nodes[n].asc
        cls = tree.class_of_ascendancy(asc) if asc else None
        if cls in cands:
            return cls
    low = hint.lower()
    return next((c for c in cands if c.lower() in low), cands[0])


def load_game_build(path: str | Path, class_name: str | None = None) -> PobBuild:
    stages = read_build_files(path)
    if not stages:
        raise ValueError("empty build file")
    tree = PassiveTree.load()
    final = stages[-1]
    sids = [p["id"] for p in final.get("passives") or () if isinstance(p, dict) and p.get("id")]
    cls = class_name or _class_of(tree, sids, f"{final.get('name', '')} {final.get('link', '')}")
    if cls is None:
        raise ValueError("cannot tell the class from the passives; pass class_name")
    asc = None
    for s in sids:                                   # ascendancy from its nodes, if any
        n = tree.nodes.get(tree.by_sid.get(s, -1))
        if n is not None and n.asc:
            asc = n.asc
            break

    specs = []
    start = tree.class_start(cls)
    for st in stages:
        ids = [tree.by_sid[p["id"]] for p in st.get("passives") or ()
               if isinstance(p, dict) and p.get("id") in tree.by_sid]
        # guides sometimes contain islands not linked to the tree; reaching them would cost
        # many filler points, so they are dropped
        linked = _linked(tree, start, set(ids))
        specs.append(TreeSpec(title=st.get("name", ""), tree_version=tree.version,
                              nodes=[n for n in ids if n in linked]))

    groups = []
    for i, sk in enumerate(final.get("skills") or (), start=1):
        gems = [GemEntry(name=_gem_name(sk["id"]), gem_id=_gem_key(sk["id"]) or sk["id"])]
        for sup in sk.get("support_skills") or ():
            gems.append(GemEntry(name=_gem_name(sup["id"]), gem_id=_gem_key(sup["id"]) or sup["id"]))
        groups.append(SkillGroup(index=i, gems=gems))

    # items are plain base types here (no uniques), so gear hints come from the .gear.json sidecar
    return PobBuild(class_name=cls, ascendancy_name=asc, level=1, main_socket_group=1,
                    specs=specs, active_spec=len(specs) - 1, skill_groups=groups,
                    target_version=tree.version)
