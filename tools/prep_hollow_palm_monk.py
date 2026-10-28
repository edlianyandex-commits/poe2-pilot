"""Write builds/monk_hollow_palm_storm_wave_0_5_5.build from the Mobalytics download.

usage: python tools/prep_hollow_palm_monk.py <downloaded .zip>

DEADRABB1T's file is used as is except for two things the planner cannot read:
- stage names "ACT 3" / "ACT 4 - Endgame" carry no level, so each name gets the level the
  stage starts at (Act 3 zones open at 33, Act 4 at ~45; the first two already say LVL 1, 22);
- the player uses one weapon set, so weapon set 2 passives (Tempest Flurry's) are dropped and
  set 1 (Storm Wave's) stays in the tree;
- the guide takes Hollow Palm Technique as early as possible (~13), so an extra first stage
  holds just the author's own path to it, and the planner fills that path first;
- a stage swaps up to a dozen gems at once (22, 31), so its new gems come at most three a
  level, in the file's order (each skill before its supports).
"""
import io, json, sys, zipfile
sys.path.insert(0, "src")
from pilot.planner.tree import PassiveTree

HOLLOW_PALM = "passive_keystone_hollow_palm_technique"
PER_LEVEL = 3

START = {"ACT 1/2": "Level 1-21 (Act 1-2)", "ACT 2 (LVL 22)": "Level 22 (Act 2)",
         "ACT 3": "Level 31 (Act 3)", "ACT 4": "Level 45 (Act 4 - Endgame)"}



def path_in(t: PassiveTree, sids: set[str], goal: str) -> list[str]:
    """Shortest path from the Monk start to `goal` through the stage's own nodes."""
    start = t.class_start("Monk")
    own = {t.by_sid[x] for x in sids if x in t.by_sid}
    prev, q = {start: None}, [start]
    for c in q:
        for o in t.nodes[c].adj:
            if o in own and o not in prev:
                prev[o] = c
                q.append(o)
    n, out = t.by_sid[goal], []
    while n != start:
        out.append(t.nodes[n].sid)
        n = prev[n]
    return out[::-1]


def stagger(st: dict, start: int, prev: dict | None) -> None:
    """Delay the stage's new skills and supports so at most PER_LEVEL start on one level."""
    old = {sk["id"]: {x["id"] for x in sk.get("support_skills") or ()} for sk in (prev or {}).get("skills") or ()}
    used: dict[int, int] = {}

    def place(item: dict, earliest: int) -> int:
        lv = max(earliest, item["level_interval"][0])
        while used.get(lv, 0) >= PER_LEVEL:
            lv += 1
        used[lv] = used.get(lv, 0) + 1
        item["level_interval"] = [lv, item["level_interval"][1]]
        return lv

    for sk in st["skills"]:
        lv = place(sk, start) if sk["id"] not in old else start
        for sup in sk.get("support_skills") or ():
            if sup["id"] not in old.get(sk["id"], ()):
                place(sup, lv)


src = zipfile.ZipFile(sys.argv[1])
stages = []
for info in src.infolist():
    st = json.loads(src.read(info).decode("utf-8"))
    key = next(k for k in START if st["name"].startswith(k))
    st["name"] = f'{START[key]} - {st["name"]}'
    st["passives"] = [p for p in st["passives"] if p.get("weapon_set") != 2]
    stages.append((info.filename, st))
stages.sort(key=lambda x: len(x[1]["passives"]))
for i, (_, st) in enumerate(stages):
    stagger(st, int(st["name"].split()[1].split("-")[0]), stages[i - 1][1] if i else None)
first = min(stages, key=lambda x: len(x[1]["passives"]))[1]
early = dict(first, name="Level 1-13 (Hollow Palm first) - " + first["name"].split(" - ", 1)[1],
             passives=[{"id": x} for x in path_in(PassiveTree.load(), {p["id"] for p in first["passives"]},
                                                  HOLLOW_PALM)])
stages.insert(0, ("00 Hollow Palm first.build", early))
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
    for name, st in stages:
        out.writestr(name, json.dumps(st, ensure_ascii=False, indent=1))
open("builds/monk_hollow_palm_storm_wave_0_5_5.build", "wb").write(buf.getvalue())
