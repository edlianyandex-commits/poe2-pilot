"""Write builds/bloodmage_spark_poevault_0_5.build from the PoE Vault text guide (no PoB exists)."""
import io, json, sys, zipfile
sys.path.insert(0, "src")
from pilot.planner.tree import PassiveTree, steiner_tree

t = PassiveTree.load()
start = t.class_start("Witch")
def path(*names):
    ids = [k for k, v in t.nodes.items() if v.name in names and not v.asc]
    nodes, bad = steiner_tree(t, start, ids)
    assert not bad
    return [{"id": t.nodes[n].sid} for n in nodes if n != start]

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
orb = path("Secrets of the Orb")
ee = orb   # Elemental Equilibrium (~41) is a hint: the author takes many unknown nodes first
stages = [
    ("Level 1-14 (Act 1)", [], [sk("Spark", ("Unleash", "Rapid Casting I")),
                                sk("Frost Bomb", ("Prolonged Duration I",)),
                                sk("Flame Wall", ("Prolonged Duration I",)),
                                sk("Orb of Storms", ("Overabundance I", "Controlled Destruction"), 6),
                                sk("Mana Remnants", (), 10)]),
    ("Level 15-28 (Act 2)", orb, [sk("Spark", ("Considered Casting", "Rapid Casting I")),
                                  sk("Orb of Storms", ("Overabundance I", "Considered Casting", "Unleash")),
                                  sk("Frost Bomb", ("Prolonged Duration I", "Potent Exposure")),
                                  sk("Flame Wall", ("Prolonged Duration I",)),
                                  sk("Mana Remnants", ("Harmonic Remnants I", "Remnant Potency I")),
                                  sk("Life Remnants", ("Harmonic Remnants I", "Remnant Potency I"), 20)]),
    ("Level 29-44 (Act 3)", ee, act3),
    ("Level 45-54 (Act 4)", ee, act4),
    ("Level 55-65 (Interludes)", ee, inter),
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
print(len(orb), len(ee))
