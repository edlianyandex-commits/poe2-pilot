"""Extract the data the PoE2 Pilot planner needs from a Path of Building (PoE2) checkout.

Usage (run isolated, the checkout is untrusted data and is only *parsed*, never executed):

    python -I tools/planner/extract.py --pob vendor/pob2 --out data/planner

Inputs (PathOfBuilding-PoE2, MIT licence, https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2):
  src/TreeData/<ver>/tree.json   passive tree graph
  src/Data/Gems.lua              gem list (name, type, tier, tags)
  src/Data/Skills/act_*.lua      per-gem-level character level requirements
  src/Data/QuestRewards.lua      campaign quest rewards (passive points)

Outputs (compact JSON, < 5 MB total):
  tree_<ver>.json   nodes + undirected adjacency + class/ascendancy start nodes
  gems.json         gems keyed by gameId with name/kind/tier
  gem_rules.json    level requirement per gem level (skills/spirit) + support tier table
  pob_quest_rewards.json  raw PoB quest-reward table (quest_points.json is curated by hand)
  ATTRIBUTION.md    licence/attribution note
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import re
import subprocess
import sys
from pathlib import Path

# ----------------------------------------------------------------------------- Lua literal parser
# PoB data files are generated Lua *table literals*. We parse them with a tiny tokenizer
# (no Lua runtime, nothing is executed).

_TOKEN = re.compile(
    r"""
    (?P<ws>\s+|--\[\[.*?\]\]|--[^\n]*)
  | (?P<str>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
  | (?P<lstr>\[(?P<eq>=*)\[.*?\](?P=eq)\])
  | (?P<num>-?0x[0-9a-fA-F]+|-?\d+\.?\d*(?:[eE][-+]?\d+)?)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<sym>[{}\[\]=,;])
    """,
    re.S | re.X,
)

_ESC = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "\n": "\n"}


def _unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n.isdigit():
                m = re.match(r"\d{1,3}", s[i + 1:])
                out.append(chr(int(m.group(0))))
                i += 1 + len(m.group(0))
                continue
            out.append(_ESC.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _tokens(text: str):
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise ValueError(f"lua parse error at {pos}: {text[pos:pos + 40]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        if kind == "eq":
            kind = "lstr"
        yield kind, m.group(0)


class _LuaParser:
    def __init__(self, text: str):
        self.toks = list(_tokens(text))
        self.i = 0

    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else (None, None)

    def take(self, expect=None):
        t = self.toks[self.i]
        if expect is not None and t[1] != expect:
            raise ValueError(f"expected {expect!r}, got {t!r}")
        self.i += 1
        return t

    def value(self):
        kind, v = self.peek()
        if v == "{":
            return self.table()
        self.i += 1
        if kind == "str":
            return _unescape(v[1:-1])
        if kind == "lstr":
            eq = re.match(r"\[(=*)\[", v).group(1)
            return v[len(eq) + 2: -(len(eq) + 2)]
        if kind == "num":
            return int(v, 16) if "x" in v.lower() else (float(v) if any(c in v for c in ".eE") else int(v))
        if kind == "name":
            if v == "true":
                return True
            if v == "false":
                return False
            if v == "nil":
                return None
        raise ValueError(f"unsupported lua value {v!r}")

    def table(self):
        self.take("{")
        arr, obj = [], {}
        while self.peek()[1] != "}":
            k, v = self.peek()
            if v == "[":
                self.take("[")
                key = self.value()
                self.take("]")
                self.take("=")
                obj[key] = self.value()
            elif k == "name" and self.peek(1)[1] == "=":
                self.i += 2
                obj[v] = self.value()
            else:
                arr.append(self.value())
            if self.peek()[1] in (",", ";"):
                self.i += 1
        self.take("}")
        if obj and arr:
            for n, a in enumerate(arr, 1):
                obj.setdefault(n, a)
            return obj
        if obj and all(isinstance(k, int) for k in obj):  # [1]=..,[2]=.. -> list
            keys = sorted(obj)
            if keys == list(range(1, len(keys) + 1)):
                return [obj[k] for k in keys]
        return obj if obj else arr


def parse_lua_return(text: str):
    text = text.lstrip("﻿")
    m = re.search(r"\breturn\s*\{", text)
    if not m:
        raise ValueError("no 'return {' found")
    p = _LuaParser(text[m.end() - 1:])
    return p.table()


# ----------------------------------------------------------------------------- tree

def node_type(n: dict) -> str:
    if n.get("classesStart"):
        return "class_start"
    if n.get("isAscendancyStart"):
        return "asc_start"
    if n.get("isJewelSocket"):
        return "jewel"
    if n.get("isKeystone"):
        return "keystone"
    if n.get("isNotable"):
        return "notable"
    if n.get("isAttribute"):
        return "attribute"
    return "small"


def extract_tree(tree_json: Path, version: str) -> dict:
    t = json.loads(tree_json.read_text(encoding="utf-8"))
    raw = t["nodes"]
    keep = {}
    for k, n in raw.items():
        if not k.isdigit() or n.get("isOnlyImage"):
            continue
        keep[int(k)] = n
    adj: dict[int, set[int]] = collections.defaultdict(set)
    for nid, n in keep.items():
        for c in n.get("connections", []):
            o = c["id"]
            if o == nid or o not in keep:
                continue
            adj[nid].add(o)
            adj[o].add(nid)

    # node position, as PoB's PassiveTree:ProcessNode (Lua tables are 1-based: node.group indexes
    # the JSON groups list with an offset of 1):
    #   angle = orbitAnglesByOrbit[orbit][orbitIndex]; r = orbitRadii[orbit]
    #   x = group.x + r*sin(angle);  y = group.y - r*cos(angle)
    groups = t["groups"]
    radii = t["constants"]["orbitRadii"]
    angles = t["constants"]["orbitAnglesByOrbit"]

    def position(n: dict) -> tuple[float, float] | None:
        g = n.get("group")
        if not isinstance(g, int) or not (1 <= g <= len(groups)) or not groups[g - 1]:
            return None
        grp = groups[g - 1]
        o, oi = n.get("orbit", 0), n.get("orbitIndex", 0)
        try:
            a, r = angles[o][oi], radii[o]
        except (IndexError, TypeError):
            return None
        return round(grp["x"] + r * math.sin(a), 1), round(grp["y"] - r * math.cos(a), 1)

    nodes = {}
    for nid, n in sorted(keep.items()):
        rec = {
            "s": n.get("stringId", ""),
            "n": n.get("name", ""),
            "t": node_type(n),
            "e": sorted(adj.get(nid, ())),
        }
        pos = position(n)
        if pos:
            rec["x"], rec["y"] = pos
        if rec["t"] in ("notable", "keystone") and n.get("icon"):
            rec["ic"] = ICON_CDN + re.sub(r"\.dds$", ".webp", n["icon"], flags=re.I)
        if n.get("ascendancyName"):
            rec["a"] = n["ascendancyName"]
        if n.get("stats"):
            rec["st"] = n["stats"]
        if n.get("unlockConstraint"):
            rec["uc"] = n["unlockConstraint"].get("nodes", [])
        if n.get("classesStart"):
            rec["cs"] = n["classesStart"]
        if n.get("isFreeAllocate"):
            rec["free"] = True
        if n.get("isMultipleChoiceOption"):
            rec["mco"] = True
        if "group" in n:
            rec["g"] = n["group"]
        if n.get("isSwitchable") and isinstance(n.get("options"), dict):
            # class/ascendancy-specific variant of this node (e.g. Huntress sees "Attack Damage"
            # where Ranger sees "Projectile Damage"; Abyssal Lich re-skins Lich nodes)
            sw = {}
            for key, opt in n["options"].items():
                v = {}
                if opt.get("name"):
                    v["n"] = opt["name"]
                if opt.get("stats"):
                    v["st"] = opt["stats"]
                if opt.get("ascendancyName"):
                    v["a"] = opt["ascendancyName"]
                sw[key] = v
            rec["sw"] = sw
        nodes[str(nid)] = rec

    classes = {}
    class_start = {}
    for nid, n in keep.items():
        for cname in n.get("classesStart", []) or []:
            class_start[cname] = nid
    asc_start = {n["ascendancyName"]: nid for nid, n in keep.items() if n.get("isAscendancyStart")}
    for cl in t["classes"]:
        classes[cl["name"]] = {
            "integerId": cl.get("integerId"),
            "start": class_start.get(cl["name"]),
            "ascendancies": {
                a["id"]: {"name": a.get("name", a["id"]), "internalId": a.get("internalId"),
                          "start": asc_start.get(a["id"])}
                for a in cl.get("ascendancies", [])
            },
        }
    return {"version": version, "classes": classes, "nodes": nodes}


# ----------------------------------------------------------------------------- gems

def gem_kind(g: dict) -> str:
    tags = g.get("tags") or {}
    if g.get("gemType") == "Support" or tags.get("support"):
        return "support"
    if tags.get("persistent"):
        return "spirit"
    return "skill"


def extract_gems(gems_lua: Path, cards: dict[str, dict] | None = None) -> dict:
    data = parse_lua_return(gems_lua.read_text(encoding="utf-8"))
    cards = cards or {}
    out = {}
    for game_id, g in data.items():
        if not isinstance(g, dict) or not g.get("name"):
            continue
        rec = {
            "n": g["name"],
            "k": gem_kind(g),
            "tier": int(g.get("Tier") or 0),
            "type": g.get("gemType", ""),
            "v": g.get("variantId", ""),
            "ge": g.get("grantedEffectId", ""),
            "tags": sorted(k for k, v in (g.get("tags") or {}).items() if v is True),
        }
        if g.get("gemFamily"):
            rec["fam"] = g["gemFamily"]
        if g.get("weaponRequirements"):
            rec["w"] = g["weaponRequirements"]
        card = cards.get(g.get("grantedEffectId", ""), {})
        rec["c"] = card.get("c", "none")
        if card.get("d"):
            rec["d"] = card["d"]
        if card.get("i"):
            rec["i"] = card["i"]
        out[game_id] = rec
    return out


_SKILL_HEAD = re.compile(r'^skills\["([^"]+)"\] = \{', re.M)
_STR_FIELD = r'^\t{field} = "((?:\\.|[^"\\])*)"'
COLORS = {1: "str", 2: "dex", 3: "int"}
ICON_CDN = "https://cdn.poe2db.tw/image/"
DESC_MAX = 400


def _field(block: str, name: str) -> str | None:
    m = re.search(_STR_FIELD.format(field=name), block, re.M)
    return _unescape(m.group(1)) if m else None


def extract_skill_cards(skills_dir: Path) -> dict[str, dict]:
    """grantedEffectId -> {desc, color, icon} from Data/Skills/*.lua (top-level fields only)."""
    out: dict[str, dict] = {}
    for f in sorted(skills_dir.glob("*.lua")):
        s = f.read_text(encoding="utf-8")
        heads = list(_SKILL_HEAD.finditer(s))
        for i, m in enumerate(heads):
            block = s[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(s)]
            rec: dict = {}
            desc = _field(block, "description")
            if desc:
                desc = " ".join(desc.split())
                rec["d"] = desc if len(desc) <= DESC_MAX else desc[: DESC_MAX - 1].rstrip() + "…"
            cm = re.search(r"^\tcolor = (\d+)", block, re.M)
            if cm:
                rec["c"] = COLORS.get(int(cm.group(1)), "none")
            icon = _field(block, "icon")
            if icon:
                rec["i"] = ICON_CDN + re.sub(r"\.dds$", ".webp", icon, flags=re.I)
            out.setdefault(m.group(1), rec)
    return out


def extract_level_reqs(skills_dir: Path) -> list[int]:
    c = collections.Counter()
    for f in sorted(skills_dir.glob("act_*.lua")):
        s = f.read_text(encoding="utf-8")
        for m in re.finditer(r'skills\["([^"]+)"\] = \{(.*?)\n\}', s, re.S):
            reqs = tuple(int(x) for x in re.findall(
                r"\[\d+\] = \{[^\n]*?levelRequirement = (\d+)", m.group(2)))
            if len(reqs) >= 20 and any(reqs):
                c[reqs[:20]] += 1
    table, _ = c.most_common(1)[0]
    return list(table)


# ----------------------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pob", default="vendor/pob2", type=Path)
    ap.add_argument("--out", default="data/planner", type=Path)
    ap.add_argument("--tree-version", default=None, help="e.g. 0_5 (default: latest)")
    a = ap.parse_args(argv)
    src = a.pob / "src"
    a.out.mkdir(parents=True, exist_ok=True)

    versions = sorted(p.name for p in (src / "TreeData").iterdir()
                      if re.fullmatch(r"\d+_\d+", p.name) and (p / "tree.json").exists())
    ver = a.tree_version or versions[-1]
    commit = ""
    try:  # read-only git query about the checkout (does not run any of its code)
        commit = subprocess.run(["git", "-C", str(a.pob), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        pass

    tree = extract_tree(src / "TreeData" / ver / "tree.json", ver)
    tree["source_commit"] = commit
    (a.out / f"tree_{ver}.json").write_text(json.dumps(tree, ensure_ascii=False, separators=(",", ":")),
                                            encoding="utf-8")

    gems = extract_gems(src / "Data" / "Gems.lua", extract_skill_cards(src / "Data" / "Skills"))
    (a.out / "gems.json").write_text(json.dumps({"source_commit": commit, "gems": gems},
                                                ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    rules_path = a.out / "gem_rules.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8")) if rules_path.exists() else {}
    rules["skill_level_requirement"] = extract_level_reqs(src / "Data" / "Skills")
    rules["source_commit"] = commit
    rules_path.write_text(json.dumps(rules, ensure_ascii=False, indent=1), encoding="utf-8")

    quests = parse_lua_return((src / "Data" / "QuestRewards.lua").read_text(encoding="utf-8"))
    (a.out / "pob_quest_rewards.json").write_text(
        json.dumps({"source_commit": commit, "quests": quests}, ensure_ascii=False, indent=1), encoding="utf-8")

    (a.out / "ATTRIBUTION.md").write_text(
        "# Attribution\n\n"
        "Files `tree_*.json`, `gems.json`, `gem_rules.json` (skill_level_requirement) and "
        "`pob_quest_rewards.json` are derived from **Path of Building Community (PoE2)**\n"
        "https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2 "
        f"(commit `{commit or 'unknown'}`), licensed under the MIT License,\n"
        "Copyright (c) Path of Building Community contributors.\n\n"
        "Underlying game data (passive tree, gem data) (c) Grinding Gear Games.\n"
        "This project is not affiliated with or endorsed by Grinding Gear Games.\n\n"
        "Regenerate with: `python -I tools/planner/extract.py --pob vendor/pob2 --out data/planner`.\n"
        "`quest_points.json` and the support/socket parts of `gem_rules.json` are curated by hand "
        "(sources listed inside).\n\n"
        "Gem descriptions/colours/skill icons come from PoB `src/Data/Skills/*.lua`. Icon URLs\n"
        "(`gems.json` field `i`, `gem_icons.json`) point to the https://poe2db.tw image CDN\n"
        "(cdn.poe2db.tw); `gem_icons.json` is a name -> URL map parsed from poe2db gem listing pages\n"
        "by `tools/planner/poe2db_icons.py`. No images are stored in this repository.\n",
        encoding="utf-8")

    total = sum(p.stat().st_size for p in a.out.glob("*.json"))
    print(f"tree {ver}: {len(tree['nodes'])} nodes; gems: {len(gems)}; total json {total / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
