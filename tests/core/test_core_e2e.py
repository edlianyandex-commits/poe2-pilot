"""Replay the real campaign log through parser + engine."""
import re
from datetime import datetime
from pathlib import Path

from pilot.core.engine import RunEngine
from pilot.core.logwatch import replay
from pilot.core.parser import parse_ts
from pilot.core.route import Route, Step
from pilot.core.splits import SplitStore

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "campaign_ru.log"
MARKERS = [
    ("a1", "G1_1", 1), ("a2", "G2_1", 2), ("a3", "G3_1", 3), ("a4", "G4_town", 4),
    ("p1", "P1_1", 101), ("p2", "P2_1", 102), ("p3", "P3_1", 103), ("end", "G_Endgame_Town", 4),
]
ROUTE = Route("e2e", "e2e", tuple(
    Step(i, act, area, f"→ {i}", "move", split=True) for i, area, act in MARKERS
))


def test_full_campaign_replay(tmp_path):
    store = SplitStore(tmp_path)
    eng = RunEngine(ROUTE, store=store)
    n = replay(FIXTURE, eng.feed_line, speed=0)
    assert n == 1824

    snap = eng.snapshot()
    assert eng.finished and not snap.running
    hits = eng.split_times()
    assert list(hits) == [m[0] for m in MARKERS]            # all splits, in order
    times = list(hits.values())
    assert times == sorted(times) and times[0] == 0.0

    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    first, last = parse_ts(lines[0]), parse_ts(lines[-1])
    wall = (last - first).total_seconds()
    assert 0 < snap.run_time_s < wall                        # restarts / closed time excluded
    assert wall - snap.run_time_s > 9 * 3600                 # the 9h overnight gap is gone

    pids = [m[1] for m in (re.search(r"Client (\d+)\]", ln) for ln in lines) if m]
    restarts = sum(1 for a, b in zip(pids, pids[1:]) if a != b)
    assert restarts >= 5                                     # fixture really contains restarts

    runs = store.list_runs("e2e")
    assert len(runs) == 1 and runs[0].status == "finished"
    assert list(runs[0].splits) == list(hits)
    assert store.pb_total("e2e") == runs[0].total_s == snap.run_time_s


def test_second_replay_gives_zero_deltas(tmp_path):
    store = SplitStore(tmp_path)
    replay(FIXTURE, RunEngine(ROUTE, store=store).feed_line, speed=0)
    eng = RunEngine(ROUTE, store=store)
    replay(FIXTURE, eng.feed_line, speed=0)
    assert eng.snapshot().split_delta_s == 0.0
    assert any("Финиш" in t.text and "+0:00" in t.text for t in eng.snapshot().toasts)


def test_real_route_replay_regression(tmp_path):
    from pilot.core.route import load_route
    root = Path(__file__).resolve().parents[2]
    route = load_route(root / "data" / "routes" / "campaign-0.5.json")
    # merging: one displayed step per consecutive same-area run
    assert all(a.area != b.area for a, b in zip(route.steps, route.steps[1:]))
    a1 = next(s for s in route.steps if "a1-011" in s.all_ids)
    assert a1.kind == "boss" and a1.id == "a1-010" and "a1-010" in a1.all_ids

    eng = RunEngine(route, store=SplitStore(tmp_path))
    seen, last = [], None
    with open(FIXTURE, encoding="utf-8") as f:
        for line in f:
            eng.feed_line(line)
            idx = eng.snapshot().step_index
            if idx != last:
                seen.append(idx)
                last = idx
    assert eng.finished
    jumps = [b - a for a, b in zip(seen, seen[1:]) if b < a or b - a > 6]
    assert not jumps
    shown = {i for i in seen if i < len(route.steps)}
    assert len(shown) >= 0.9 * len(route.steps)
    split_ids = [s.id for s in route.steps if s.split]
    assert len(split_ids) == 8
    assert list(eng.split_times()) == split_ids


def test_lookahead_window_town_next_and_details():
    from datetime import datetime
    from pilot.contracts import AreaGenerated
    steps = tuple(Step(f"s{k}", 1, a, f"→ s{k}", "move", detail=f"d{k}", reward="R" if k == 1 else None,
                       split=(a == "G1_town"), done_on_enter="Zdone" if k == 0 else None)
                  for k, a in enumerate(["G1_1", "G1_town", "G1_3", "G1_4", "G1_5", "G1_6", "G1_7", "G1_8", "G1_9"]))
    eng = RunEngine(Route("w", "w", steps))
    t = datetime(2025, 1, 1, 12, 0, 0)
    eng.feed(AreaGenerated(t, "G1_1", 1, 1))
    eng.feed(AreaGenerated(t, "G1_9", 9, 1))          # 8 ahead: outside window
    assert eng.snapshot().step_index == 0
    eng.feed(AreaGenerated(t, "G1_town", 15, 1))      # next step is a town (cur has done_on): advances
    assert eng.snapshot().step_index == 1
    assert eng.details() == ["d1", "Награда: R", "→ s2", "→ s3", "→ s4"]
    eng.feed(AreaGenerated(t, "G1_6", 6, 1))          # 4 ahead: jump, passes the town split
    assert eng.snapshot().step_index == 5 and "s1" in eng.split_times()
    assert eng.upcoming(2) == ["→ s6", "→ s7"]
