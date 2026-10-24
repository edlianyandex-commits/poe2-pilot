# PoE2 Pilot

Glanceable overlay for the Path of Exile 2 campaign: current route step, run timer with splits vs your PB,
and a per-level plan (passives, gems, ascendancy) generated from a Path of Building PoE2 build.

Reads only `Client.txt`. Never sends input to the game or reads its memory.
Requires the game in **borderless windowed** mode.

## Run
```
pip install -e .[dev]
poe2-pilot                                   # tails the live Client.txt (auto-detected)
poe2-pilot --build build.txt                 # + leveling plan from a PoB2 export code
poe2-pilot --replay tests/fixtures/campaign_ru.log --speed 400   # demo on a recorded run
python -m pilot.overlay.demo                 # HUD only, scripted states
python -m pilot.planner build.txt            # print the leveling plan
```

## Hotkeys
| Key | Action |
|---|---|
| `Alt+Q` (hold) | details panel |
| `Alt+]` / `Alt+[` | step forward / back |
| `Alt+R` | reset run |
| `Alt+E` | edit mode: drag to move, wheel to scale; again to save |
| `Alt+H` | hide / show |

Config: `%APPDATA%\poe2-pilot\config.json`. Runs and PBs: `%APPDATA%\poe2-pilot\runs\`.

## Docs
`docs/ARCHITECTURE.md` · `docs/UX.md` · `docs/ROUTE_SCHEMA.md` · screenshots in `docs/screens/`.

Passive tree and gem data: extracted from Path of Building Community PoE2 (MIT), see `data/planner/ATTRIBUTION.md`.
