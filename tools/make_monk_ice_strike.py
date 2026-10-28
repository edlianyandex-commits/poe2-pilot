"""Write builds/monk_ice_strike_0_5.build from PoE Vault's Ice Strike Monk levelling guide.

Lollash, "Ice Strike Monk Leveling Build (Martial Artist)", patch 0.5, updated 2026-05-27.
Gems per stage follow the guide's planner (docs/run-reviews/guide-monk-ice-strike-acts.md),
spread to at most three new gems a level; the page shows the tree only as an image, so the
tree is poe2-pilot's own pick around the guide's named nodes. One tree, no weapon sets.
Run from the repo root: python tools/make_monk_ice_strike.py
"""
import io, json, sys, zipfile
sys.path.insert(0, "src")
from pilot.planner import data
from pilot.planner.tree import PassiveTree
from stage_tree import stage_trees

t = PassiveTree.load()
start = t.class_start("Monk")

# Hollow Palm Technique as early as possible (the guide), then cold, freeze, attack speed and
# life on kill; Resonance (charges from freezing, with Combat Frenzy) in Act 3; Heavy Frost late
# in Act 4 (frozen enemies lose their elemental resistances, so Frost Bomb and Elemental Weakness
# can go); evasion and crit to finish.
BUDGETS = [15, 31, 50, 63, 80]
PRIORITY = [
    ("Hollow Palm Technique", 0), ("Essence of the Mountain", 0), ("Life from Death", 1),
    ("Shattering", 1), ("Agile Succession", 1), ("Echoing Frost", 1), ("Resonance", 2),
    ("Snowpiercer", 2), ("Infused Flesh", 2), ("True Strike", 2), ("Heavy Frost", 3),
    ("Biting Frost", 3), ("Deep Trance", 3), ("Elemental Force", 4), ("Escape Velocity", 4),
    ("Critical Exploit", 4),
]

_BY_NAME = {}
for k, r in data.gems_data().items():
    _BY_NAME.setdefault(r["n"], r.get("gid") or k)


def sk(name, frm=1, to=100, sups=()):
    """sups: (name, first level) or (name, first level, last level)."""
    return {"id": _BY_NAME[name], "level_interval": [frm, to],
            "support_skills": [{"id": _BY_NAME[x[0]], "level_interval": [x[1], x[2] if len(x) > 2 else to]}
                               for x in sups]}


# Act 1 before Ice Strike: Quarterstaff Strike + Tempest Bell for single targets, Killing Palm
# builds Power Charges and Falling Thunder spends them on packs; they stay until Ice Strike is
# usable. Ice Strike is tier 5: the Executioner's reward (Leitis, char ~13) is usable from 14
# (data/planner/gem_rules.json); then it carries the rest with Frost Bomb and Tempest Bell on
# bosses. Shattering Palm is tier 11, usable from 41.
# Frost Bomb, Elemental Weakness and Freezing Mark go once Heavy Frost is in (47 in this tree).
GEMS = [
    sk("Quarterstaff Strike", 1, 13, [("Rapid Attacks I", 2), ("Rage I", 3)]),
    sk("Falling Thunder", 3, 13, [("Elemental Armament I", 4), ("Perpetual Charge", 5)]),
    sk("Killing Palm", 4, 13, [("Charge Profusion I", 5)]),
    sk("Tempest Bell", 6, sups=[("Overabundance I", 6, 44), ("Rage I", 7, 44), ("Heavy Swing", 32),
                                ("Rageforged I", 46, 54), ("Ancestral Call I", 47, 54),
                                ("Close Combat I", 47, 54), ("Rageforged II", 55), ("Ancestral Call II", 56)]),
    sk("Herald of Ice", 10, sups=[("Magnified Area I", 10, 30), ("Cold Attunement", 20),
                                  ("Magnified Area II", 31)]),
    sk("Ice Strike", 14, sups=[("Rapid Attacks I", 14, 44), ("Elemental Armament I", 14, 15),
                               ("Elemental Armament II", 16), ("Ice Bite II", 31, 44),
                               ("Rapid Attacks II", 45), ("Rage II", 45), ("Crescendo II", 46),
                               ("Close Combat II", 55)]),
    sk("Frost Bomb", 15, 47, [("Overabundance I", 15), ("Potent Exposure", 18), ("Spell Echo", 32)]),
    sk("Elemental Weakness", 23, 47, [("Heightened Curse", 23)]),
    sk("Freezing Mark", 25, 47, [("Mark of Siphoning", 25), ("Prolonged Duration I", 26)]),
    sk("Combat Frenzy", 28, sups=[("Charge Profusion I", 34)]),
    sk("Charged Staff", 33, sups=[("Prolonged Duration II", 33), ("Perpetual Charge", 33),
                                  ("Heightened Charges", 34)]),
    sk("Wind Dancer", 37, sups=[("Maim", 37), ("Blind I", 37), ("Pin I", 48)]),
    sk("Shattering Palm", 41, sups=[("Ice Bite II", 41, 47), ("Freeze", 41), ("Ancestral Call I", 42, 55),
                                    ("Magnified Area II", 48, 55), ("Ice Bite II", 56),
                                    ("Ancestral Call II", 56), ("Elemental Armament II", 57)]),
]

trees = stage_trees(t, start, PRIORITY, BUDGETS)
stages = [(name, tree, GEMS) for name, tree in zip(
    ("Level 1-14 (Act 1)", "Level 15-28 (Act 2)", "Level 29-44 (Act 3)", "Level 45-54 (Act 4)",
     "Level 55-65 (Interludes)"), trees)]
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for name, passives, skills in stages:
        st = {"author": "Lollash, PoE Vault (written by poe2-pilot from the guide's planner)",
              "link": "https://www.poe-vault.com/poe2/monk/martial-artist/ice-strike-leveling-build",
              "ascendancy": "Monk1", "name": f"{name} - Ice Strike Monk",
              "passives": passives, "skills": skills, "inventory_slots": []}
        z.writestr(f"{name}.build", json.dumps(st, ensure_ascii=False, indent=1))
open("builds/monk_ice_strike_0_5.build", "wb").write(buf.getvalue())
