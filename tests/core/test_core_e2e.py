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

    from pilot.contracts import AreaGenerated
    from pilot.core.engine import is_hideout, is_town
    from pilot.core.parser import parse_line
    from pilot.core.route import route_area
    eng = RunEngine(route, store=SplitStore(tmp_path))
    areas = {s.area for s in route.steps}
    entries = wrong = 0
    shown = set()
    with open(FIXTURE, encoding="utf-8") as f:
        for line in f:
            ev = parse_line(line)
            if ev is None:
                continue
            eng.feed(ev)
            s = eng.snapshot()
            shown.add(s.step_index)
            z = getattr(ev, "area_id", None)
            if isinstance(ev, AreaGenerated) and s.running and route_area(z) in areas                     and not is_town(z) and not is_hideout(z):
                entries += 1
                wrong += route.steps[s.step_index].area != route_area(z)
    assert eng.finished
    assert entries > 50 and wrong == 0          # every route zone shows its own step
    assert len(shown & set(range(len(route.steps)))) >= 0.9 * len(route.steps)
    split_ids = [s.id for s in route.steps if s.split]
    assert len(split_ids) == 8
    assert list(eng.split_times()) == split_ids


def test_any_order_skipped_steps_and_reminders():
    from datetime import datetime
    from pilot.contracts import AreaGenerated
    kinds = ["move", "town", "boss", "move", "move"]
    steps = tuple(Step(f"s{k}", 1, a, f"→ s{k}", kinds[k], detail=f"d{k}", reward="R" if k == 2 else None,
                       split=(a == "G1_town"))
                  for k, a in enumerate(["G1_1", "G1_town", "G1_3", "G1_4", "G1_5"]))
    eng = RunEngine(Route("w", "w", steps))
    t = datetime(2025, 1, 1, 12, 0, 0)
    eng.feed(AreaGenerated(t, "G1_1", 1, 1))
    eng.feed(AreaGenerated(t, "G1_5", 5, 1))           # far ahead: shown, skips the pass-throughs
    s = eng.snapshot()
    assert s.step_short == "→ s4" and "s1" in eng.split_times()   # town split passed silently
    assert s.next_short == "→ s2"                       # skipped must-kill boss stays a reminder
    eng.feed(AreaGenerated(t, "G1_3", 3, 1))           # back for the boss
    assert eng.snapshot().step_short == "→ s2"
    assert eng.details()[:2] == ["d2", "Награда: R"]
    eng.feed(AreaGenerated(t, "G1_4", 4, 1))           # revisit: that zone's (done) step
    assert eng.snapshot().step_short == "→ s3"
