"""Write builds/warbringer_bone_spells_0_5_5.build from the user's own plan ("Bone Warbringer").

Warrior -> Warbringer casting physical bone spells (Bone Cage, Bonestorm) with a shield;
levels 1-8 dual-wield two one-handed maces with slams and strikes.
The plan was checked against poe2-pilot's gem and tree data; the tree is its notable order.
The campaign is played with one weapon set (wand + shield). Weapon set passives are not
modelled by the planner, so the notables for those points are HUD hints
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
# points). Defensive Stance, Sudden Escalation, Constricting and Radial Force (20 points) go on
# the weapon set points, all on the one set.
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


def sk(name, frm=1, to=100, sups=()):
    """sups: (name, first level) or (name, first level, last level) - one or two gems a level."""
    return {"id": _BY_NAME[name], "level_interval": [frm, to],
            "support_skills": [{"id": _BY_NAME[x[0]], "level_interval": [x[1], x[2] if len(x) > 2 else to]}
                               for x in sups]}


# One schedule for the whole campaign, at most 2-3 new gems a level, in order of importance:
# Bone Cage carries Act 1, Bonestorm takes bosses from Act 2 and gets its supports first;
# the tier 7 gems (Vulnerability, Detonate Dead) come in Act 3. Detonate Dead deals fire as
# well as physical damage and Brutality drops all non-physical damage, so it gets area and
# corpse supports instead (Brutality II only if testing shows it pays).
GEMS = [
    # levels 1-8 with two one-handed maces: Rolling Slam primes for stun, Boneshatter's Heavy
    # Stun makes a shockwave and Impact Shockwave adds an aftershock; Fist of War boosts a slam
    # every few seconds. Brutality I and Magnified Area I then move to Bone Cage.
    sk("Rolling Slam", 1, 8, sups=[("Magnified Area I", 4, 7), ("Fist of War I", 5)]),
    sk("Boneshatter", 1, 8, sups=[("Brutality I", 2, 5), ("Impact Shockwave", 3)]),
    sk("Bone Cage", 6, sups=[("Brutality I", 6, 19), ("Astral Projection", 7), ("Magnified Area I", 8, 44),
                             ("Rapid Casting I", 10, 15), ("Bone Shrapnel", 18), ("Brutality II", 20),
                             ("Magnified Area II", 45)]),
    sk("Bonestorm", 15, sups=[("Brutality I", 15, 19), ("Rapid Casting I", 16), ("Brutality II", 20),
                              ("Concentrated Area", 22), ("Physical Mastery", 24)]),
    sk("Scavenged Plating", 17, sups=[("Prolonged Duration I", 17)]),
    sk("Vulnerability", 29, sups=[("Heightened Curse", 29), ("Prolonged Duration II", 33),
                                  ("Focused Curse", 40)]),
    sk("Detonate Dead", 31, sups=[("Corpse Conservation", 31), ("Magnified Area I", 33, 44),
                                  ("Heft", 36), ("Magnified Area II", 45)]),
]

trees = stage_trees(t, start, PRIORITY, BUDGETS)
stages = [(name, tree, GEMS) for name, tree in zip(
    ("Level 1-14 (Act 1)", "Level 15-28 (Act 2)", "Level 29-44 (Act 3)", "Level 45-54 (Act 4)",
     "Level 55-65 (Interludes)"), trees)]
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for name, passives, skills in stages:
        st = {"author": "the user's own plan (checked by poe2-pilot)", "link": "",
              "ascendancy": "Warrior2", "name": f"{name} - Bone Spells Warbringer Warrior",
              "passives": passives, "skills": skills, "inventory_slots": []}
        z.writestr(f"{name}.build", json.dumps(st, ensure_ascii=False, indent=1))
open("builds/warbringer_bone_spells_0_5_5.build", "wb").write(buf.getvalue())
