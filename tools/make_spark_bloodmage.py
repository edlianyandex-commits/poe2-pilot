"""Write builds/bloodmage_spark_poevault_0_5.build from the PoE Vault text guide (no PoB exists).

Run from the repo root: python tools/make_spark_bloodmage.py
"""
import io, json, sys, zipfile
sys.path.insert(0, "src")
from pilot.planner.tree import PassiveTree, steiner_tree

t = PassiveTree.load()
start = t.class_start("Witch")

# The guide's tree is an image, so this tree is our own pick for Spark / Orb of Storms:
# spell damage and cast speed first, Secrets of the Orb in Act 2 (third orb, the guide's ~23),
# spell crit, extra Spark projectiles and Elemental Equilibrium in Act 3 (the guide's ~41),
# life on kill / from remnants (Blood Mage pays skills with life), then crit and lightning.
# Each notable, in priority order, goes into the earliest stage (not before its own) where the
# stage's tree still fits its passive points; stages are nested, so nothing is ever refunded.
BUDGETS = [15, 31, 50, 63, 80]          # points by the end of Act 1, 2, 3, 4, Interludes
PRIORITY = [                             # (notable, earliest stage index)
    ("Raw Power", 0), ("Practiced Signs", 0), ("Secrets of the Orb", 1),
    ("Critical Overload", 1), ("Psychic Fragmentation", 2), ("Elemental Equilibrium", 2),
    ("Vigorous Remnants", 2), ("Life from Death", 0), ("Essence of the Storm", 2),
    ("Breath of Lightning", 2), ("Sudden Escalation", 3), ("Crashing Wave", 3),
    ("Critical Exploit", 3), ("Echoing Thunder", 3), ("All Natural", 3),
    ("Lightning Storm", 4), ("Flow Like Water", 4), ("Moment of Truth", 4), ("Cruel Fate", 4),
]


def _dist():
    nb = t.walker(start, lambda n: True)
    d, q = {start: 0}, [start]
    for c in q:
        for o in nb(c):
            if o not in d and not t.nodes[o].asc:
                d[o] = d[c] + 1
                q.append(o)
    return d


def stage_trees():
    d = _dist()
    node = lambda nm: min((n for n in d if t.nodes[n].name == nm), key=d.get)  # noqa: E731
    stage_of: dict[int, int] = {}
    size = lambda k, extra=(): len(steiner_tree(  # noqa: E731
        t, start, [n for n, s in stage_of.items() if s <= k] + list(extra))[0]) - 1
    for nm, first in PRIORITY:
        n = node(nm)
        for k in range(first, len(BUDGETS)):
            if all(size(j, [n]) <= BUDGETS[j] for j in range(k, len(BUDGETS))):
                stage_of[n] = k
                break
        else:
            print("  does not fit:", nm)
    out = []
    for k, budget in enumerate(BUDGETS):
        nodes = steiner_tree(t, start, [n for n, s in stage_of.items() if s <= k])[0]
        print(k, len(nodes) - 1, "/", budget, [t.nodes[n].name for n, s in stage_of.items() if s == k])
        out.append([{"id": t.nodes[n].sid} for n in sorted(nodes) if n != start])
    return out


G = "Metadata/Items/Gems/"
SK = {"Spark": G + "SkillGemSpark", "Orb of Storms": G + "SkillGemOrbOfStorms",
      "Frost Bomb": G + "SkillGemFrostBomb", "Flame Wall": G + "SkillGemFlameWall",
      "Mana Remnants": "Metadata/Items/Gem/SkillGemManaRemnants",
      "Life Remnants": "Metadata/Items/Gem/SkillGemAscendancyLifeRemnants",
      "Arctic Armour": G + "SkillGemArcticArmour"}
SUP = {"Unleash": G + "SupportGemUnleash", "Rapid Casting I": G + "SupportGemArcaneTempo",
       "Overabundance I": G + "SupportGemOverabundance",
       "Controlled Destruction": G + "SupportGemControlledDestruction",
       "Prolonged Duration I": G + "SupportGemPersistence", "Prolonged Duration II": G + "SupportGemPersistenceTwo",
       "Considered Casting": "Metadata/Items/Gem/SupportGemConsideredCasting",
       "Potent Exposure": "Metadata/Items/Gem/SupportGemStripAway",
       "Harmonic Remnants I": "Metadata/Items/Gem/SupportGemDissipate",
       "Harmonic Remnants II": "Metadata/Items/Gem/SupportGemDissipateTwo",
       "Remnant Potency I": "Metadata/Items/Gem/SupportGemInterlude",
       "Remnant Potency II": "Metadata/Items/Gem/SupportGemInterludeTwo",
       "Freeze": G + "SupportGemGlaciation", "Knockback": G + "SupportGemBludgeon",
       "Projectile Acceleration I": G + "SupportGemAcceleration",
       "Projectile Acceleration II": G + "SupportGemAccelerationTwo"}
def sk(name, sups=(), frm=1):
    return {"id": SK[name], "level_interval": [frm, 100],
            "support_skills": [{"id": SUP[s], "level_interval": [frm, 100]} for s in sups]}

act3 = [sk("Spark", ("Considered Casting", "Rapid Casting I", "Unleash")),
        sk("Orb of Storms", ("Overabundance I", "Considered Casting", "Unleash")),
        sk("Frost Bomb", ("Prolonged Duration II", "Potent Exposure")),
        sk("Flame Wall", ("Prolonged Duration II",)),
        sk("Mana Remnants", ("Harmonic Remnants II", "Remnant Potency II")),
        sk("Life Remnants", ("Harmonic Remnants II", "Remnant Potency II")),
        sk("Arctic Armour", ("Freeze", "Knockback"))]
act4 = [dict(act3[0], support_skills=act3[0]["support_skills"] + [{"id": SUP["Projectile Acceleration I"], "level_interval": [1, 100]}])] + [s for s in act3[1:] if s["id"] != SK["Flame Wall"]]
inter = [dict(act4[0], support_skills=act4[0]["support_skills"][:3] + [{"id": SUP["Projectile Acceleration II"], "level_interval": [1, 100]}])] + act4[1:]
trees = stage_trees()
stages = [
    ("Level 1-14 (Act 1)", trees[0], [sk("Spark", ("Unleash", "Rapid Casting I")),
                                sk("Frost Bomb", ("Prolonged Duration I",)),
                                sk("Flame Wall", ("Prolonged Duration I",)),
                                sk("Orb of Storms", ("Overabundance I", "Controlled Destruction"), 6),
                                sk("Mana Remnants", (), 10)]),
    ("Level 15-28 (Act 2)", trees[1], [sk("Spark", ("Considered Casting", "Rapid Casting I")),
                                  sk("Orb of Storms", ("Overabundance I", "Considered Casting", "Unleash")),
                                  sk("Frost Bomb", ("Prolonged Duration I", "Potent Exposure")),
                                  sk("Flame Wall", ("Prolonged Duration I",)),
                                  sk("Mana Remnants", ("Harmonic Remnants I", "Remnant Potency I")),
                                  sk("Life Remnants", ("Harmonic Remnants I", "Remnant Potency I"), 20)]),
    ("Level 29-44 (Act 3)", trees[2], act3),
    ("Level 45-54 (Act 4)", trees[3], act4),
    ("Level 55-65 (Interludes)", trees[4], inter),
]
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for name, passives, skills in stages:
        st = {"author": "PoE Vault (written by poe2-pilot from the text guide)",
              "link": "https://www.poe-vault.com/poe2/witch/blood-mage/crit-spark-leveling-build",
              "ascendancy": "Witch2", "name": f"{name} - Spark Blood Mage Witch",
              "passives": passives, "skills": skills, "inventory_slots": []}
        z.writestr(f"{name}.build", json.dumps(st, ensure_ascii=False, indent=1))
open("builds/bloodmage_spark_poevault_0_5.build", "wb").write(buf.getvalue())

