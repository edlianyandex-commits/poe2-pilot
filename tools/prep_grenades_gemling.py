"""Write builds/grenades_gemling_0_5_5.build from the Mobalytics download.

usage: python tools/prep_grenades_gemling.py <downloaded .zip>

DEADRABB1T's "[0.5.5] Grenades Gemling League Starter (Level 1 to Endgame)" holds seven
stages; the campaign uses the first four (Act 1, Act 2, Act 3/4, Interludes) as they are,
except:
- the stage names carry no level, so each gets the level its act starts at;
- new gems come at most two a level and a new skill at most every two levels;
- Virtuous Barrier waits for the first ascendancy (Sekhemas) and Attrition for Ignagduk's
  Spirit (Azak Bog, Act 3).
"""
import io, json, sys, zipfile
from build_prep import stagger

START = {"ACT 1 ": "Level 1-14 (Act 1)", "ACT 2 ": "Level 15-30 (Act 2)",
         "ACT 3/4": "Level 31-54 (Acts 3-4)", "Interludes": "Level 55 (Interludes)"}
GATED = {"Metadata/Items/Gem/SkillGemAscendancyVirtuousBarrier": 22,
         "Metadata/Items/Gems/SkillGemAscendancyVirtuousBarrier": 22,
         "Metadata/Items/Gems/SkillGemAttrition": 36, "Metadata/Items/Gem/SkillGemAttrition": 36}

src = zipfile.ZipFile(sys.argv[1])
stages = []
for info in src.infolist():
    st = json.loads(src.read(info).decode("utf-8"))
    key = next((k for k in START if st["name"].startswith(k)), None)
    if key is None:                       # the endgame stages
        continue
    st["name"] = f'{START[key]} - {st["name"]}'
    stagger(st, int(START[key].split()[1].split("-")[0]), stages[-1] if stages else None,
            per_level=2, skill_gap=2, not_before=GATED)
    stages.append(st)
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
    for st in stages:
        out.writestr(st["name"].split(" - ")[0] + ".build", json.dumps(st, ensure_ascii=False, indent=1))
open("builds/grenades_gemling_0_5_5.build", "wb").write(buf.getvalue())
