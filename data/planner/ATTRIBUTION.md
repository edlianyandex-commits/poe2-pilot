# Attribution

Files `tree_*.json`, `gems.json`, `gem_rules.json` (skill_level_requirement) and `pob_quest_rewards.json` are derived from **Path of Building Community (PoE2)**
https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2 (commit `bb52d6b368307457eb9c54bb13f1829993d390b1`), licensed under the MIT License,
Copyright (c) Path of Building Community contributors.

Underlying game data (passive tree, gem data) (c) Grinding Gear Games.
This project is not affiliated with or endorsed by Grinding Gear Games.

Regenerate with: `python -I tools/planner/extract.py --pob vendor/pob2 --out data/planner`.
`quest_points.json` and the support/socket parts of `gem_rules.json` are curated by hand (sources listed inside).

Gem descriptions/colours/skill icons come from PoB `src/Data/Skills/*.lua`. Icon URLs
(`gems.json` field `i`, `gem_icons.json`) point to the https://poe2db.tw image CDN
(cdn.poe2db.tw); `gem_icons.json` is a name -> URL map parsed from poe2db gem listing pages
by `tools/planner/poe2db_icons.py`. No images are stored in this repository.
