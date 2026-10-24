"""PobBuild -> LevelPlan: passive points per level, ascendancy at trials, gem unlocks."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pilot.contracts import GemCard, GemRow, LevelHint, LevelPlan

from . import data as _data
from .pobcode import GemEntry, PobBuild, SkillGroup
from .tree import NodeValuer, PassiveTree, allocation_order, steiner_tree

MAX_LEN = 32
MAX_ITEMS = 3
MAX_LEVEL = 100
ATTR_RU = {"str": "+5 Сила", "dex": "+5 Ловкость", "int": "+5 Интеллект"}
TYPE_RANK = {"keystone": 0, "notable": 1, "jewel": 2, "small": 3, "attribute": 4}


def clip(s: str, n: int = MAX_LEN) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


# ----------------------------------------------------------------------------- points timeline

def passive_points_at(level: int, qp: dict | None = None) -> int:
    qp = qp or _data.quest_points()
    quest = sum(r["points"] for r in qp["passive_rewards"] if r["typical_char_level"] <= level)
    return max(0, level - 1) + quest


def asc_points_at(level: int, qp: dict | None = None) -> int:
    qp = qp or _data.quest_points()
    return sum(t["points"] for t in qp["ascendancy_trials"] if t["typical_char_level"] <= level)


# ----------------------------------------------------------------------------- gems

@dataclass
class GemInfo:
    name: str
    kind: str          # skill | spirit | support
    tier: int
    tags: tuple[str, ...]
    known: bool = True
    weapon: str = ""        # weapon requirement; tier-0 skills with one are granted by the weapon
    color: str = "none"     # str | dex | int | none
    description: str = ""
    icon: str | None = None


def gem_info(g: GemEntry) -> GemInfo:
    gems = _data.gems_data()
    rec = None
    for key in (g.gem_id, g.gem_id.replace("/Items/Gem/", "/Items/Gems/")):
        if key and key in gems:
            rec = gems[key]
            break
    if rec is None:
        for r in gems.values():
            if (g.variant_id and r.get("v") == g.variant_id) or r["n"] == g.name:
                rec = r
                break
    if rec is None:
        support = "support" in g.skill_id.lower() or "support" in g.gem_id.lower()
        return GemInfo(g.name, "support" if support else "skill", 0, (), known=False,
                       icon=_data.gem_icons().get(g.name))
    # poe2db listing map first (checked), PoB-derived skill icon as fallback
    icon = _data.gem_icons().get(rec["n"]) or rec.get("i")
    return GemInfo(rec["n"], rec["k"], int(rec.get("tier") or 0), tuple(rec.get("tags", ())),
                   weapon=rec.get("w", ""), color=rec.get("c", "none"),
                   description=rec.get("d", ""), icon=icon)


def gem_card(info: GemInfo) -> GemCard:
    """GemCard for the gem window; ``name`` is the exact English in-game name."""
    desc = info.description
    if len(desc) > 400:
        desc = desc[:399].rstrip() + "…"
    return GemCard(name=info.name, kind=info.kind,
                   color=info.color if info.color in ("str", "dex", "int") else "none",
                   description=desc, icon_url=info.icon)


def weapon_granted(info: GemInfo) -> bool:
    return info.tier <= 0 and info.kind == "skill" and bool(info.weapon)


def earliest_level(info: GemInfo, rules: dict | None = None) -> int | None:
    """Earliest character level a gem can be cut and used; None = not obtainable from uncut gems."""
    rules = rules or _data.gem_rules()
    if weapon_granted(info):
        return 1  # base skill of the weapon (e.g. talisman / shield), usable from the start
    if info.tier <= 0:
        return None
    if info.kind == "support":
        table = {int(k): v for k, v in rules["support_tier_min_char_level"].items()}
        return table.get(info.tier, max(table.values()))
    req = rules["skill_level_requirement"]
    t = info.tier
    if info.kind == "spirit":
        t = max(t, int(rules.get("spirit_min_uncut_level", 1)))
    return max(1, req[min(t, len(req)) - 1])


def support_slot_level(n_support: int, rules: dict | None = None) -> int:
    """Character level from which a skill typically has room for its n-th support (1-based)."""
    rules = rules or _data.gem_rules()
    table = sorted((int(k), v) for k, v in rules["support_slots_by_char_level"].items())
    for lvl, slots in table:
        if slots >= n_support:
            return lvl
    return table[-1][0]


@dataclass(order=True)
class GemEvent:
    level: int
    prio: int
    seq: int
    text: str = field(compare=False)
    is_main: bool = field(default=False, compare=False)


@dataclass
class GroupPlan:
    """One socketed skill group: its lead skill and when each support can join it."""
    lead: GemInfo
    lead_level: int
    is_main: bool
    prio: int
    actives: list[tuple[int, GemInfo]]          # (earliest level, gem), PoB order
    supports: list[tuple[int, GemInfo]]         # (level it can be socketed, gem), PoB order


def plan_groups(build: PobBuild, warnings: list[str]) -> list[GroupPlan]:
    """Main group first; groups without an obtainable active skill are dropped."""
    groups: list[SkillGroup] = [g for g in build.skill_groups if g.enabled and not g.source and g.gems]
    main = build.main_group
    if main is None or main not in groups:
        main = groups[0] if groups else None
    ordered = ([main] if main else []) + [g for g in groups if g is not main]
    out: list[GroupPlan] = []
    have_main = False
    for grp in ordered:
        infos = [(g, gem_info(g)) for g in grp.gems if g.enabled]
        for g, inf in infos:
            if not inf.known:
                warnings.append(f"gem not in data: {g.name}")
        actives = [inf for _, inf in infos if inf.kind != "support"]
        if not actives:
            continue
        obtainable = [(earliest_level(a), i, a) for i, a in enumerate(actives)]
        obtainable = [x for x in obtainable if x[0] is not None]
        if not obtainable:
            continue
        # the group's leading active is what supports are linked to
        lead_lvl, _, lead = min(obtainable, key=lambda x: (x[1] if grp is main else 0, x[0], x[1]))
        is_main = not have_main and lead.kind == "skill"  # main group, or first usable fallback
        have_main |= is_main
        sup_infos = [inf for _, inf in infos if inf.kind == "support"]
        sup = [(earliest_level(x), i, x) for i, x in enumerate(sup_infos)]
        sup = [x for x in sup if x[0] is not None]       # lineage / unique-only supports dropped
        by_avail = sorted(sup, key=lambda x: (x[0], x[1]))
        when = {i: max(lv, lead_lvl, support_slot_level(k))
                for k, (lv, i, _) in enumerate(by_avail, 1)}
        out.append(GroupPlan(
            lead=lead, lead_level=lead_lvl, is_main=is_main,
            prio=0 if is_main else (2 if lead.kind == "spirit" else 4),
            actives=[(lv, a) for lv, _, a in obtainable],
            supports=[(when[i], x) for _, i, x in sup]))
    return out


def plan_gems(build: PobBuild, warnings: list[str],
              groups: list[GroupPlan] | None = None) -> tuple[list[GemEvent], str | None]:
    groups = plan_groups(build, warnings) if groups is None else groups
    events: list[GemEvent] = []
    seen_skill: set[str] = set()
    seen_pair: set[tuple[str, str]] = set()
    main_name = next((g.lead.name for g in groups if g.is_main), None)
    seq = 0
    for gp in groups:
        for lvl, a in gp.actives:
            if a.name in seen_skill:
                continue
            seen_skill.add(a.name)
            seq += 1
            text = f"+ {a.name} (оружие)" if weapon_granted(a) else f"+ {a.name}"
            events.append(GemEvent(lvl, gp.prio, seq, clip(text),
                                   is_main=(a is gp.lead and gp.is_main)))
        for when, x in sorted(gp.supports, key=lambda t: t[0]):
            if (x.name, gp.lead.name) in seen_pair:
                continue
            seen_pair.add((x.name, gp.lead.name))
            text = f"+ {x.name} → {gp.lead.name}"
            if len(text) > MAX_LEN:
                text = f"+ {x.name}"
            seq += 1
            events.append(GemEvent(when, gp.prio + 1, seq, clip(text)))
    events.sort()
    return events, main_name


SETUP_LEN = 40


def setup_line(skill: str, supports: list[str], n: int = SETUP_LEN) -> str:
    """'Skill: Sup1, Sup2' <= n chars; overflow keeps the first supports (PoB order) + '+N'."""
    if not supports:
        return clip(skill, n)
    full = f"{skill}: {', '.join(supports)}"
    if len(full) <= n:
        return full
    for k in range(len(supports) - 1, -1, -1):
        cand = f"{skill}: {', '.join(supports[:k] + ['+' + str(len(supports) - k)])}"
        if len(cand) <= n:
            return cand
    return clip(skill, n)


def socketed_at(groups: list[GroupPlan], lvl: int) -> list[tuple[GemInfo, list[GemInfo]]]:
    """(skill, supports) socketed at ``lvl``: main group first, supports in PoB order."""
    rows: list[tuple[GemInfo, list[GemInfo]]] = []
    seen: set[str] = set()
    for gp in groups:
        if gp.lead_level > lvl or gp.lead.name in seen:
            continue
        sups = [x for when, x in gp.supports if when <= lvl]
        if weapon_granted(gp.lead) and not sups:
            continue
        seen.add(gp.lead.name)
        rows.append((gp.lead, sups))
    return rows


def plan_setups(groups: list[GroupPlan], max_level: int = MAX_LEVEL) -> dict[int, tuple[str, ...]]:
    """Full socketed setup at every level where it changes (main group first)."""
    return plan_setups_and_rows(groups, max_level)[0]


def plan_setups_and_rows(groups: list[GroupPlan], max_level: int = MAX_LEVEL
                         ) -> tuple[dict[int, tuple[str, ...]], dict[int, tuple[GemRow, ...]]]:
    """Text setups (<= 40 chars per line) and gem-window rows, at the same levels."""
    setups: dict[int, tuple[str, ...]] = {}
    rows: dict[int, tuple[GemRow, ...]] = {}
    prev: tuple | None = None
    for lvl in range(1, max_level + 1):
        cur_rows = socketed_at(groups, lvl)
        key = tuple((s.name, tuple(x.name for x in sups)) for s, sups in cur_rows)
        if key != prev and (key or prev):
            setups[lvl] = tuple(setup_line(s.name, [x.name for x in sups]) for s, sups in cur_rows)
            rows[lvl] = tuple(GemRow(skill=gem_card(s), supports=tuple(gem_card(x) for x in sups))
                              for s, sups in cur_rows)
        prev = key
    return setups, rows


def spread_gem_events(events: list[GemEvent], per_level: int = MAX_ITEMS) -> dict[int, list[GemEvent]]:
    """At most ``per_level`` gem lines per hint; overflow slides to the next level(s)."""
    out: dict[int, list[GemEvent]] = {}
    queue = sorted(events)
    carry: list[GemEvent] = []
    lvl = 1
    i = 0
    while (i < len(queue) or carry) and lvl <= MAX_LEVEL:
        while i < len(queue) and queue[i].level <= lvl:
            carry.append(queue[i])
            i += 1
        carry.sort()
        if carry:
            out[lvl] = carry[:per_level]
            carry = carry[per_level:]
        lvl += 1
    return out


# ----------------------------------------------------------------------------- gear

class GearLines(dict):
    """level -> lines from a sidecar; ``pob_uniques=False`` drops "Надеть X" hints from the PoB;
    ``zones``: area id -> pickup hints ("Renly: Twister")."""
    pob_uniques: bool = True
    zones: dict[str, tuple[str, ...]] = {}


def load_gear_file(path: str | Path) -> GearLines:
    """Sidecar ``{"gear": {"<level>": [str, ...]}, "pob_uniques": bool}``; "_" keys are ignored.

    ``"pob_uniques": false`` is for self-found play (fresh league, no currency): the PoB's
    equipped uniques are not hinted, only the sidecar's own lines are.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    gear = raw.get("gear", {}) if isinstance(raw, dict) else {}
    out = GearLines()
    if isinstance(raw, dict) and raw.get("pob_uniques") is False:
        out.pob_uniques = False
    zones = raw.get("zones", {}) if isinstance(raw, dict) else {}
    out.zones = {str(a): tuple(clip(str(x), 40) for x in (v if isinstance(v, list) else [v]) if str(x).strip())
                 for a, v in (zones.items() if isinstance(zones, dict) else ()) if not str(a).startswith("_")}
    for k, v in (gear.items() if isinstance(gear, dict) else ()):
        if str(k).startswith("_"):
            continue
        try:
            lvl = int(k)
        except ValueError:
            continue
        items = [v] if isinstance(v, str) else list(v or [])
        lines = [clip(str(x)) for x in items if str(x).strip()]
        if lines:
            out.setdefault(max(1, lvl), []).extend(lines)
    return out


def plan_gear(build: PobBuild, sidecar: dict[int, list[str]] | None = None) -> dict[int, list[str]]:
    """Equipped uniques from PoB ("Надеть X" at max(1, LevelReq)) merged with the sidecar.

    Sidecar lines win: a PoB unique whose name appears in any sidecar line is dropped.
    Uniques without a LevelReq are skipped (no guessing); jewels are handled by the tree.
    """
    sidecar = sidecar or {}
    side_text = " ".join(x for v in sidecar.values() for x in v).lower()
    out: dict[int, list[str]] = {}
    seen: set[str] = set()
    uniques = build.equipped_items if getattr(sidecar, "pob_uniques", True) else ()
    for it in uniques:
        if it.rarity != "UNIQUE" or it.is_jewel or it.level_req is None or it.name in seen:
            continue
        seen.add(it.name)
        if it.name.lower() in side_text:
            continue
        out.setdefault(max(1, it.level_req), []).append(clip(f"Надеть {it.name}"))
    for lvl, lines in sidecar.items():   # guide lines first: they are the author's priorities
        out[lvl] = list(lines) + out.get(lvl, [])
    return {k: out[k] for k in sorted(out)}


# ----------------------------------------------------------------------------- passives

@dataclass
class PlanDetail:
    plan: LevelPlan
    main_order: list[int]
    asc_order: list[int]
    alloc_level: dict[int, int]            # node id -> character level when it is taken
    points_used: dict[int, int]            # level -> main-tree points spent so far
    warnings: list[str]
    tree: PassiveTree
    root: int
    asc_root: int | None
    build: PobBuild
    opens: dict[int, int] = field(default_factory=dict)   # jewel socket -> class start it opens


def damage_profile(build: PobBuild) -> dict[str, float]:
    tags: dict[str, float] = {}
    main = build.main_group
    for grp in build.skill_groups:
        if not grp.enabled or grp.source:
            continue
        w = 2.0 if grp is main else 1.0
        for g in grp.gems:
            inf = gem_info(g)
            if inf.kind == "support" or not inf.known:
                continue
            for t in inf.tags:
                tags[t] = max(tags.get(t, 0.0), w)
    return tags


def _display(tree: PassiveTree, nid: int, build: PobBuild) -> str:
    n = tree.nodes[nid]
    if n.asc:
        return "★ " + (n.name or n.sid)
    if n.type == "attribute":
        choices = build.spec.attribute_choice
        ch = choices.get(nid)
        if ch is None and choices:  # filler attribute node: use the build's dominant attribute
            vals = list(choices.values())
            ch = max(("int", "dex", "str"), key=vals.count)
        return ATTR_RU.get(ch, "+5 Атрибут")
    return n.name or n.sid


def format_passives(tree: PassiveTree, nids: list[int], build: PobBuild) -> tuple[str, ...]:
    if not nids:
        return ()
    ranked = sorted(nids, key=lambda n: (0 if tree.nodes[n].asc else 1,
                                         TYPE_RANK.get(tree.nodes[n].type, 5), nids.index(n)))
    names: list[str] = []
    counts: dict[str, int] = {}
    for n in ranked:
        d = _display(tree, n, build)
        if d not in counts:
            names.append(d)
        counts[d] = counts.get(d, 0) + 1
    labels = [clip(d if counts[d] == 1 else f"{d} ×{counts[d]}") for d in names]
    if len(labels) <= MAX_ITEMS:
        return tuple(labels)
    shown = labels[: MAX_ITEMS - 1]
    rest = sum(counts[d] for d in names[MAX_ITEMS - 1:])
    return tuple(shown) + (f"+{rest} ещё",)


def _component(tree: PassiveTree, root: int, nodes: set[int]) -> set[int]:
    """Nodes of ``nodes`` connected to ``root`` through ``nodes`` only."""
    seen = {root}
    stack = [root]
    while stack:
        for o in tree.nodes[stack.pop()].adj:
            if o in nodes and o not in seen:
                seen.add(o)
                stack.append(o)
    return seen - {root}


def build_level_plan(build: PobBuild, tree: PassiveTree | None = None,
                     max_level: int = MAX_LEVEL,
                     gear: dict[int, list[str]] | None = None) -> PlanDetail:
    """``gear``: sidecar gear timeline (level -> lines); it wins over PoB uniques of the same name."""
    warnings: list[str] = []
    spec = build.spec
    base = tree or PassiveTree.load(spec.tree_version)
    if spec.tree_version and spec.tree_version != base.version:
        warnings.append(f"build tree {spec.tree_version}, data tree {base.version}")
    class_name = build.class_name
    if class_name not in base.classes and build.ascendancy_name:
        class_name = base.class_of_ascendancy(build.ascendancy_name) or class_name
    tree = base.specialise(class_name, build.ascendancy_name)
    root = tree.class_start(class_name)

    spec_nodes = [n for n in dict.fromkeys(spec.nodes)]
    unknown = [n for n in spec_nodes if n not in tree.nodes]
    if unknown:
        warnings.append(f"{len(unknown)} nodes not in tree data: {unknown[:5]}")
    known = [n for n in spec_nodes if n in tree.nodes]
    asc_root = tree.asc_start(build.ascendancy_name) if build.ascendancy_name else None
    asc_name = tree.asc_domain(build.ascendancy_name)
    main_targets = {n for n in known if tree.nodes[n].asc is None
                    and tree.nodes[n].type not in ("class_start", "asc_start")}
    asc_targets = {n for n in known if asc_name and tree.nodes[n].asc == asc_name
                   and tree.nodes[n].type != "asc_start"}
    stray = [n for n in known if tree.nodes[n].asc not in (None, asc_name)]
    if stray:
        warnings.append(f"{len(stray)} nodes of another ascendancy ignored")

    all_wanted = main_targets | asc_targets
    # Split Personality-like jewels: the part of the tree grown from another class start is
    # reachable only after the socket holding the jewel is allocated
    opens: dict[int, int] = {}
    own = _component(tree, root, main_targets)
    for sock, cls in spec.start_jewels.items():
        s = tree.start_for(cls)
        if s is None or sock not in own:   # socket must be reachable before the jewel helps
            warnings.append(f"start jewel ({cls}) in socket {sock} ignored")
        else:
            opens[sock] = s
    jewel_stage: dict[int, int] = {}
    if opens:
        steiner, unreachable = steiner_tree(tree, root, own,
                                            unlocked=lambda n: n in all_wanted)
        rest = main_targets - steiner
        for s in dict.fromkeys(opens.values()):
            part, unreachable = steiner_tree(tree, s, rest, unlocked=lambda n: n in all_wanted)
            part.discard(s)
            jewel_stage.update({n: 1 for n in part})
            steiner |= part
            rest = unreachable
        unreachable = rest
        for sock, s in opens.items():
            warnings.append(f"{tree.nodes[s].name.title()} start via jewel in socket {sock}")
    else:
        steiner, unreachable = steiner_tree(tree, root, main_targets,
                                            unlocked=lambda n: n in all_wanted)
    if unreachable:
        warnings.append(f"{len(unreachable)} target nodes unreachable from class start")
    extra = steiner - main_targets - {root}
    if extra:
        warnings.append(f"Steiner filler: +{len(extra)} nodes to connect targets")
        own_hits = [o for o in tree.nodes[root].adj if o in main_targets]
        if not own_hits:
            alt = sorted({c for c, cd in tree.classes.items()
                          if any(o in main_targets for o in tree.nodes[cd["start"]].adj)})
            if alt:
                warnings.append(f"tree starts at {'/'.join(alt)} start (item?); planned from own start")

    # stages from the other (smaller) specs of the same class - multi-tree leveling builds
    stage: dict[int, int] = {}
    others = sorted((s for i, s in enumerate(build.specs) if i != build.target_spec_index()
                     and (s.class_id == spec.class_id)), key=lambda s: len(s.nodes))
    for si, s in enumerate(others):
        for n in s.nodes:
            stage.setdefault(n, si)
    if others:
        last = len(others)
        stage = {n: stage.get(n, last) for n in steiner}
    if jewel_stage:  # the path to the jewel socket always comes first
        stage = {n: jewel_stage.get(n, 0) * 1000 + stage.get(n, 0) for n in steiner}

    valuer = NodeValuer(damage_profile(build))
    vcache = {n: valuer.value(tree.nodes[n]) for n in steiner | asc_targets}
    main_order = allocation_order(tree, root, steiner, vcache.__getitem__, stage,
                                  extra_unlocked=asc_targets, opens=opens)
    leftover = steiner - set(main_order) - {root}
    if leftover:
        warnings.append(f"{len(leftover)} nodes could not be ordered")

    asc_order: list[int] = []
    if asc_root is not None and asc_targets:
        asc_steiner, asc_unreach = steiner_tree(tree, asc_root, asc_targets)
        if asc_unreach:
            warnings.append(f"{len(asc_unreach)} ascendancy nodes unreachable")
        asc_order = allocation_order(tree, asc_root, asc_steiner, lambda n: vcache.get(n, 1.0),
                                     cost=lambda n: 0 if tree.nodes[n].free else 1)

    # ------------------------------------------------------------------ map onto levels
    qp = _data.quest_points()
    alloc_level: dict[int, int] = {}
    per_level_nodes: dict[int, list[int]] = {}
    points_used: dict[int, int] = {}
    mi = ai = 0
    used = 0
    asc_used = 0
    for lvl in range(1, max_level + 1):
        avail = passive_points_at(lvl, qp)
        while mi < len(main_order) and used < avail:
            n = main_order[mi]
            mi += 1
            used += 1
            alloc_level[n] = lvl
            per_level_nodes.setdefault(lvl, []).append(n)
        a_avail = asc_points_at(lvl, qp)
        while ai < len(asc_order):
            n = asc_order[ai]
            c = 0 if tree.nodes[n].free else 1
            if asc_used + c > a_avail:
                break
            ai += 1
            asc_used += c
            alloc_level[n] = lvl
            per_level_nodes.setdefault(lvl, []).append(n)
        points_used[lvl] = used
    if mi < len(main_order):
        warnings.append(f"{len(main_order) - mi} passives beyond level {max_level}")

    # ------------------------------------------------------------------ gems
    groups = plan_groups(build, warnings)
    events, main_name = plan_gems(build, warnings, groups)
    gem_by_level = spread_gem_events(events)
    setups, gem_rows = plan_setups_and_rows(groups, max_level)
    gear_by_level = plan_gear(build, gear)

    # ascendancy nodes are shown on entering the trial area, not on level-up
    asc_hints: dict[str, LevelHint] = {}
    ai = 0
    for t in qp["ascendancy_trials"]:
        if not t.get("area_id"):
            continue
        chunk: list[int] = []
        spent = 0
        while ai < len(asc_order):
            n = asc_order[ai]
            c = 0 if tree.nodes[n].free else 1
            if spent + c > t["points"]:
                break
            chunk.append(n)
            spent += c
            ai += 1
        if chunk:
            asc_hints[t["area_id"]] = LevelHint(level=t["typical_char_level"],
                                                passives=format_passives(tree, chunk, build),
                                                note="Восхождение")
    asc_set = set(asc_order)

    hints: dict[int, LevelHint] = {}
    for lvl in range(1, max_level + 1):
        nodes = [n for n in per_level_nodes.get(lvl, []) if n not in asc_set]
        gems_ev = gem_by_level.get(lvl, [])
        gear_lines = gear_by_level.get(lvl, ())
        if not nodes and not gems_ev and not gear_lines:
            continue
        note = None
        if any(n in opens for n in nodes):
            note = "Самоцвет в гнездо"
        if any(e.is_main for e in gems_ev) and lvl > 1 and note is None:
            note = clip(f"Основной скилл: {main_name}") if note is None else note
        hints[lvl] = LevelHint(level=lvl, passives=format_passives(tree, nodes, build),
                               gems=tuple(e.text for e in gems_ev), note=note,
                               gear=tuple(gear_lines))

    chrono = sorted((alloc_level[n], i, n) for i, n in enumerate(main_order + asc_order) if n in alloc_level)
    planned = tuple(tree.nodes[n].sid for _, _, n in chrono)
    head = build.ascendancy_name or build.class_name
    title = clip(f"{head}: {main_name}" if main_name else head)
    plan = LevelPlan(title=title, char_class=class_name, hints=hints, planned_node_ids=planned,
                     ascendancy=asc_hints, warnings=tuple(warnings), setups=setups,
                     gem_rows=gem_rows)
    return PlanDetail(plan, main_order, asc_order, alloc_level, points_used, warnings, tree, root,
                      asc_root, build, opens)
