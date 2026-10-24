"""PobBuild -> LevelPlan: passive points per level, ascendancy at trials, gem unlocks."""
from __future__ import annotations

from dataclasses import dataclass, field

from pilot.contracts import LevelHint, LevelPlan

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
        return GemInfo(g.name, "support" if support else "skill", 0, (), known=False)
    return GemInfo(rec["n"], rec["k"], int(rec.get("tier") or 0), tuple(rec.get("tags", ())),
                   weapon=rec.get("w", ""))


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


def plan_gems(build: PobBuild, warnings: list[str]) -> tuple[list[GemEvent], str | None]:
    groups: list[SkillGroup] = [g for g in build.skill_groups if g.enabled and not g.source and g.gems]
    main = build.main_group
    if main is None or main not in groups:
        main = groups[0] if groups else None
    ordered = ([main] if main else []) + [g for g in groups if g is not main]
    events: list[GemEvent] = []
    seen_skill: set[str] = set()
    seen_pair: set[tuple[str, str]] = set()
    main_name = None
    seq = 0
    for grp in ordered:
        infos = [(g, gem_info(g)) for g in grp.gems if g.enabled]
        for g, inf in infos:
            if not inf.known:
                warnings.append(f"gem not in data: {g.name}")
        actives = [inf for _, inf in infos if inf.kind != "support"]
        supports = [inf for _, inf in infos if inf.kind == "support"]
        if not actives:
            continue
        # the group's leading active (first obtainable one) is what supports are linked to
        act_levels = [(earliest_level(a), i, a) for i, a in enumerate(actives)]
        obtainable = [x for x in act_levels if x[0] is not None]
        if not obtainable:
            continue
        lead_lvl, _, lead = min(obtainable, key=lambda x: (x[1] if grp is main else 0, x[0], x[1]))
        is_main = main_name is None and lead.kind == "skill"  # main group, or first usable fallback
        if is_main:
            main_name = lead.name
        prio_base = 0 if is_main else (2 if lead.kind == "spirit" else 4)
        for lvl, _, a in obtainable:
            if a.name in seen_skill:
                continue
            seen_skill.add(a.name)
            seq += 1
            text = f"+ {a.name} (оружие)" if weapon_granted(a) else f"+ {a.name}"
            events.append(GemEvent(lvl, prio_base, seq, clip(text), is_main=(a is lead and is_main)))
        sup_info = []
        for s in supports:
            lv = earliest_level(s)
            if lv is None:
                continue  # lineage / unique-only supports
            sup_info.append((lv, s))
        sup_info.sort(key=lambda x: x[0])
        for k, (lv, s) in enumerate(sup_info, 1):
            if (s.name, lead.name) in seen_pair:
                continue
            seen_pair.add((s.name, lead.name))
            when = max(lv, lead_lvl, support_slot_level(k))
            text = f"+ {s.name} → {lead.name}"
            if len(text) > MAX_LEN:
                text = f"+ {s.name}"
            seq += 1
            events.append(GemEvent(when, prio_base + 1, seq, clip(text)))
    events.sort()
    return events, main_name


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


def build_level_plan(build: PobBuild, tree: PassiveTree | None = None,
                     max_level: int = MAX_LEVEL) -> PlanDetail:
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
    steiner, unreachable = steiner_tree(tree, root, main_targets, unlocked=lambda n: n in all_wanted)
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

    valuer = NodeValuer(damage_profile(build))
    vcache = {n: valuer.value(tree.nodes[n]) for n in steiner | asc_targets}
    main_order = allocation_order(tree, root, steiner, vcache.__getitem__, stage,
                                  extra_unlocked=asc_targets)
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
    events, main_name = plan_gems(build, warnings)
    gem_by_level = spread_gem_events(events)

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
        if not nodes and not gems_ev:
            continue
        note = None
        if any(e.is_main for e in gems_ev) and lvl > 1:
            note = clip(f"Основной скилл: {main_name}") if note is None else note
        hints[lvl] = LevelHint(level=lvl, passives=format_passives(tree, nodes, build),
                               gems=tuple(e.text for e in gems_ev), note=note)

    chrono = sorted((alloc_level[n], i, n) for i, n in enumerate(main_order + asc_order) if n in alloc_level)
    planned = tuple(tree.nodes[n].sid for _, _, n in chrono)
    head = build.ascendancy_name or build.class_name
    title = clip(f"{head}: {main_name}" if main_name else head)
    plan = LevelPlan(title=title, char_class=class_name, hints=hints, planned_node_ids=planned,
                     ascendancy=asc_hints, warnings=tuple(warnings))
    return PlanDetail(plan, main_order, asc_order, alloc_level, points_used, warnings, tree, root,
                      asc_root, build)
