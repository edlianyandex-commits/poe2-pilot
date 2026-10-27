"""Write builds/witch_ice_nova_contagion_0_5_5.build from docs/run-reviews/build-witch-ice-nova-contagion.md.

No guide combines the two skills, so gems per act follow that write-up (pieced together from PoE
Vault's Ice Nova and Chaos Witch guides) and the tree is poe2-pilot's own pick.
Run from the repo root: python tools/make_icenova_contagion.py
"""
import io, json, sys, zipfile
sys.path.insert(0, "src")
from pilot.planner import data
from pilot.planner.tree import PassiveTree
from stage_tree import stage_trees

t = PassiveTree.load()
start = t.class_start("Witch")

# Our own tree for Ice Nova + Contagion on Blood Mage: spell damage and cast speed first, cold
# penetration and life on kill in Act 1-2, +1 cold skill level and chaos damage in Act 3, then
# freeze, chaos levels and more cold. Same placement rule as the Spark build.
BUDGETS = [15, 31, 50, 63, 80]
PRIORITY = [
    ("Raw Power", 0), ("Practiced Signs", 0), ("Breath of Ice", 0), ("Life from Death", 1),
    ("Echoing Frost", 1), ("Vigorous Remnants", 1), ("Endless Blizzard", 2), ("Glaciation", 2),
    ("Spiral into Insanity", 2), ("Lingering Horror", 2), ("Dark Entries", 3), ("Brain Freeze", 3),
    ("Thin Ice", 3), ("Night's Bite", 3), ("Inescapable Cold", 4), ("Rhythm of Ice", 4),
    ("Critical Overload", 4), ("Void", 4),
]

_BY_NAME = {}
for k, r in data.gems_data().items():
    _BY_NAME.setdefault(r["n"], r.get("gid") or k)       # first hit is the support Unleash
_BY_NAME["Life Remnants"] = "Metadata/Items/Gem/SkillGemAscendancyLifeRemnants"


def sk(name, sups=(), frm=1):
    """sups: names, or (name, first level) for a support that comes later than the skill."""
    sups = [(s, frm) if isinstance(s, str) else s for s in sups]
    return {"id": _BY_NAME[name], "level_interval": [frm, 100],
            "support_skills": [{"id": _BY_NAME[s], "level_interval": [lv, 100]} for s, lv in sups]}


act1 = [sk("Ice Nova", ("Magnified Area I", ("Rapid Casting I", 5), ("Unleash", 7))),  # Unleash: Areagne
        sk("Frost Bomb", ("Prolonged Duration I",)),
        sk("Frost Darts", (("Deep Freeze", 10),), 3),
        sk("Contagion", ("Magnified Area I", "Profanity I"), 6),
        sk("Mana Remnants", (), 10)]
act2 = [sk("Ice Nova", ("Considered Casting", "Magnified Area I", "Unleash")),
        sk("Frost Darts", ("Deep Freeze", "Rapid Casting I")),
        sk("Contagion", ("Profanity I", "Intense Agony")),
        sk("Frost Bomb", ("Prolonged Duration I", "Potent Exposure")),
        sk("Elemental Weakness"), sk("Mana Remnants"), sk("Life Remnants", (), 20)]
act3 = [sk("Ice Nova", ("Considered Casting", "Unleash", "Encroaching Ground")),
        sk("Frost Darts", ("Deep Freeze", "Rapid Casting I")),
        sk("Contagion", ("Chaotic Freeze", "Profanity I", "Intense Agony")),
        sk("Frost Bomb", ("Prolonged Duration II", "Cooldown Recovery I")),
        sk("Elemental Weakness"), sk("Blasphemy"), sk("Life Remnants")]
act4 = [sk("Ice Nova", ("Considered Casting", "Unleash", "Encroaching Ground", "Magnified Area I")),
        act3[1],
        sk("Contagion", ("Chaotic Freeze", "Profanity I", "Intense Agony", "Prolonged Duration II")),
        sk("Frost Bomb", ("Prolonged Duration II", "Cooldown Recovery II")),
        sk("Elemental Weakness"), sk("Blasphemy"), sk("Siphon Elements", ("Clarity I",)),
        sk("Life Remnants")]

trees = stage_trees(t, start, PRIORITY, BUDGETS)
stages = [("Level 1-14 (Act 1)", trees[0], act1), ("Level 15-28 (Act 2)", trees[1], act2),
          ("Level 29-44 (Act 3)", trees[2], act3), ("Level 45-54 (Act 4)", trees[3], act4),
          ("Level 55-65 (Interludes)", trees[4], act4)]
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for name, passives, skills in stages:
        st = {"author": "poe2-pilot (from PoE Vault Ice Nova and Chaos Witch guides)",
              "link": "docs/run-reviews/build-witch-ice-nova-contagion.md",
              "ascendancy": "Witch2", "name": f"{name} - Ice Nova Contagion Blood Mage Witch",
              "passives": passives, "skills": skills, "inventory_slots": []}
        z.writestr(f"{name}.build", json.dumps(st, ensure_ascii=False, indent=1))
open("builds/witch_ice_nova_contagion_0_5_5.build", "wb").write(buf.getvalue())
