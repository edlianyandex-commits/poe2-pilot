"""For every zone entry of the last run(s) in a Client.txt: where was the player, what did the HUD show.

usage: python -X utf8 tools/zone_check.py [Client.txt] [--since "YYYY/MM/DD HH:MM"]
Prints only zone entries where the shown step is for a different area (towns/hideouts skipped).
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pilot.contracts import AreaGenerated  # noqa: E402
from pilot.core.engine import RunEngine, is_hideout, is_town  # noqa: E402
from pilot.core.logpath import find_client_log  # noqa: E402
from pilot.core.parser import parse_line_or_tick as parse_line  # noqa: E402
from pilot.core.route import load_route, route_area  # noqa: E402
from pilot.core.splits import SplitStore  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("log", nargs="?")
ap.add_argument("--since", default="")
a = ap.parse_args()
log = Path(a.log or find_client_log())
route = load_route(Path(__file__).resolve().parents[1] / "data" / "routes" / "campaign-0.5.json")
eng = RunEngine(route, store=SplitStore(Path(tempfile.mkdtemp())))
area_of = {s.area for s in route.steps}

total = bad = off = 0
with open(log, encoding="utf-8", errors="replace") as f:
    for line in f:
        if a.since and line[:16] < a.since:
            continue
        ev = parse_line(line)
        if ev is None:
            continue
        eng.feed(ev)
        if not isinstance(ev, AreaGenerated) or not eng.snapshot().running:
            continue
        z = ev.area_id
        if is_town(z) or is_hideout(z):
            continue
        if route_area(z) not in area_of:          # league mechanics etc.: HUD shows the next goal
            off += 1
            continue
        total += 1
        i = eng.snapshot().step_index
        cur = route.steps[i] if i < len(route.steps) else None
        if cur is None or cur.area != route_area(z):
            bad += 1
            print(f"{ev.ts:%m-%d %H:%M}  в зоне {z:10} lvl{ev.area_level:<3} HUD: {cur.area if cur else '-':10} "
                  f"{(cur.short if cur else '')[:30]:30} шаг {i}")
print(f"\nвходов в зоны: {total}, HUD показывал другую зону: {bad}")
