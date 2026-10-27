"""Write builds/warbringer_bone_spells_0_5_5.build from the user's own plan ("Bone Warbringer").

Warrior -> Warbringer casting physical bone spells (Bone Cage, Bonestorm) with a shield.
The plan was checked against poe2-pilot's gem and tree data; the tree is its notable order.
Weapon set passives are not modelled by the planner, so their notables are HUD hints
(builds/warbringer_bone_spells_0_5_5.gear.json), not part of this tree.
Run from the repo root: python tools/make_warbringer_bone.py
"""
import io, json, sys, zipfile
sys.path.insert(0, "src")
from pilot.planner import data
from pilot.planner.tree import PassiveTree
from stage_tree import stage_trees

t = PassiveTree.load()
start = t.class_start("Warrior")

# the plan's order: early block, armour break and Pin in Act 1; spell damage and Fully Broken
# Armour in Act 2-3; out to the Witch side for more spell damage, block and spell crit last.
# The plan's Powerful Casting and Deadly Thorns (and Shelter from the Rain) are Oracle-only
# nodes, so Defensive Reflexes takes their points. Potent Incantation is the costliest detour (7
# points). Defensive Stance, Sudden Escalation, Draiocht Cleansing, Constricting (set 1) and
# Radial Force, Roil (set 2) go on weapon set points.
BUDGETS = [15, 31, 50, 63, 80]
PRIORITY = [
    ("Defender's Resolve", 0), ("Unstoppable Barrier", 0), ("Cruel Methods", 0), ("Eroding Chains", 0),
    ("Vigilance", 1), ("Lasting Incantations", 1), ("Pile On", 1), ("Irreparable", 1),
    ("Raw Power", 2), ("Potent Incantation", 2), ("Critical Overload", 3),
    ("Core of the Guardian", 3), ("Defensive Reflexes", 3),
]

_BY_NAME = {}
for k, r in data.gems_data().items():
    _BY_NAME.setdefault(r["n"], r.get("gid") or k)


def sk(name, sups=(), frm=1, to=100):
    """sups: names, or (name, first level) for a support that comes later than the skill."""
    sups = [(s, frm) if isinstance(s, str) else s for s in sups]
    return {"id": _BY_NAME[name], "level_interval": [frm, to],
            "support_skills": [{"id": _BY_NAME[s], "level_interval": [lv, to]} for s, lv in sups]}


act1 = [sk("Rolling Slam", (), 1, 8), sk("Boneshatter", (), 1, 8),
        sk("Bone Cage", ("Astral Projection", "Brutality I"), 6)]
act2 = [sk("Bone Cage", ("Astral Projection", "Brutality I", ("Bone Shrapnel", 18))),
        sk("Bonestorm", ("Brutality I", "Rapid Casting I")),
        sk("Scavenged Plating", ("Prolonged Duration I",))]
act3 = [sk("Bonestorm", ("Brutality II", "Rapid Casting I", "Concentrated Area")),
        sk("Bone Cage", ("Brutality II", "Astral Projection", "Bone Shrapnel", "Magnified Area I")),
        sk("Vulnerability", ("Heightened Curse", "Prolonged Duration II")),
        sk("Detonate Dead", ("Corpse Conservation", "Magnified Area I")),
        sk("Scavenged Plating", ("Prolonged Duration I",))]
# Detonate Dead deals fire as well as physical damage, and Brutality drops all non-physical
# damage, so it gets area and corpse supports instead (Brutality II only if testing shows it pays)
act4 = [sk("Bonestorm", ("Brutality II", "Rapid Casting I", "Concentrated Area", "Physical Mastery")),
        sk("Bone Cage", ("Brutality II", "Astral Projection", "Bone Shrapnel", "Magnified Area II")),
        sk("Vulnerability", ("Heightened Curse", "Prolonged Duration II", "Focused Curse")),
        sk("Detonate Dead", ("Corpse Conservation", "Magnified Area II", "Heft")),
        sk("Scavenged Plating", ("Prolonged Duration I",))]

trees = stage_trees(t, start, PRIORITY, BUDGETS)
stages = [("Level 1-14 (Act 1)", trees[0], act1), ("Level 15-28 (Act 2)", trees[1], act2),
          ("Level 29-44 (Act 3)", trees[2], act3), ("Level 45-54 (Act 4)", trees[3], act4),
          ("Level 55-65 (Interludes)", trees[4], act4)]
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for name, passives, skills in stages:
        st = {"author": "the user's own plan (checked by poe2-pilot)", "link": "",
              "ascendancy": "Warrior2", "name": f"{name} - Bone Spells Warbringer Warrior",
              "passives": passives, "skills": skills, "inventory_slots": []}
        z.writestr(f"{name}.build", json.dumps(st, ensure_ascii=False, indent=1))
open("builds/warbringer_bone_spells_0_5_5.build", "wb").write(buf.getvalue())
