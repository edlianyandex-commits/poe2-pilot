"""Write builds/witch_minions_mattjestic_0_5.build from the Mobalytics download.

usage: python tools/prep_minion_witch.py <downloaded .zip>

Mattjestic's "0.5 FASTEST Minions Leveling & Mapping Witch Build!" holds seven variants; the
campaign uses the first three, in the file's order (the later mapping ones carry only a few
passives, so sorting by passive count would put them first):
- "Early lvl 1-10" and "Early lvl 10-30" as they are, "After Act 3 With Vaal Guard" from 45
  (Act 4) with the 10-30 tree plus its ascendancy nodes, since its own tree is a smaller copy;
- only Infernalist ascendancy nodes stay (the page was copied from a Druid build and still
  holds Shaman nodes);
- Raise Shield and the default unarmed attack come with the items, not as gems;
- new gems come at most two a level and a new skill at most every two levels (the player has
  few gems early); the Infernal Hound waits for the first ascendancy (Sekhemas).
"""
import io, json, sys, zipfile
sys.path.insert(0, "src")
from pilot.planner.tree import PassiveTree
from build_prep import stagger

STAGES = [("Level 1-9 (Act 1)", 0), ("Level 10-44 (Acts 1-3)", 1), ("Level 45 (Act 4+, Vaal Guard)", 2)]
ITEM_SKILLS = {"Metadata/Items/Gem/SkillGemShieldBlock", "Metadata/Items/Gem/SkillGemPlayerDefaultUnarmed"}
AFTER_TRIAL = {"Metadata/Items/Gem/SkillGemAscendancySummonInfernalHound": 25}

t = PassiveTree.load()
src = zipfile.ZipFile(sys.argv[1])
files = [json.loads(src.read(i).decode("utf-8")) for i in src.infolist()]


def keep(p: dict) -> bool:
    n = t.nodes.get(t.by_sid.get(p["id"], -1))
    return n is not None and n.asc in (None, "Infernalist")


stages = []
for i, (name, k) in enumerate(STAGES):
    st = dict(files[k], name=f'{name} - {files[k]["name"]}')
    tree = files[min(k, 1)]["passives"]
    extra = [p for p in files[k]["passives"] if t.nodes[t.by_sid[p["id"]]].asc and p not in tree]
    st["passives"] = [p for p in tree + extra if keep(p)]      # later ascendancy nodes kept
    st["skills"] = [json.loads(json.dumps(s)) for s in st["skills"] if s["id"] not in ITEM_SKILLS]
    stagger(st, int(name.split()[1].split("-")[0]), stages[-1] if stages else None,
            per_level=2, skill_gap=2, not_before=AFTER_TRIAL)
    stages.append(st)
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
    for st in stages:
        out.writestr(st["name"].split(" - ")[0] + ".build", json.dumps(st, ensure_ascii=False, indent=1))
open("builds/witch_minions_mattjestic_0_5.build", "wb").write(buf.getvalue())
