"""Replay a Client.txt through a route and report how the engine walked it (lead QA tool).

usage: python -X utf8 tools/replay_check.py [log] [route]
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pilot.core.engine import RunEngine  # noqa: E402
from pilot.core.parser import parse_line  # noqa: E402
from pilot.core.route import load_route  # noqa: E402
from pilot.core.splits import SplitStore  # noqa: E402

log = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/campaign_ru.log"
route = load_route(Path(sys.argv[2] if len(sys.argv) > 2 else "data/routes/campaign-0.5.json"))
engine = RunEngine(route, store=SplitStore(Path(tempfile.mkdtemp())))

seen, last = [], None
with open(log, encoding="utf-8", errors="replace") as f:
    for line in f:
        ev = parse_line(line)
        if ev:
            engine.feed(ev)
        idx = engine.snapshot().step_index
        if idx != last:
            seen.append(idx)
            last = idx

jumps = [(a, b) for a, b in zip(seen, seen[1:]) if b - a > 1 or b < a]
skipped = sorted(set(range(len(route.steps))) - set(seen))
s = engine.snapshot()
print(f"visited {len(seen)} of {len(route.steps)} steps; jumps {len(jumps)}")
for a, b in jumps[:25]:
    print(f"  {a}->{b}: {route.steps[min(a, len(route.steps)-1)].id} -> {route.steps[min(b, len(route.steps)-1)].id}")
print("never shown:", [route.steps[i].id for i in skipped][:40])
print(f"final idx {s.step_index}/{s.step_total} running={s.running} finished={engine.finished} "
      f"game_time={s.run_time_s/3600:.2f}h")
print({k: round(v / 60, 1) for k, v in engine.split_times().items()})
