import time
from pathlib import Path

from pilot.core.engine import RunEngine
from pilot.core.route import load_route
from pilot.core.splits import SplitStore
from pilot.core.warmstart import find_run_start, warm_start

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "campaign_ru.log"
ROUTE = load_route(ROOT / "data" / "routes" / "campaign-0.5.json")
LINES = FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)


def _direct(lines):
    eng = RunEngine(ROUTE)
    for ln in lines:
        eng.feed_line(ln)
    return eng


def _same(a: RunEngine, b: RunEngine):
    sa, sb = a.snapshot(), b.snapshot()
    assert sa.step_index == sb.step_index
    assert sa.char_level == sb.char_level
    assert sa.running == sb.running
    assert abs(sa.run_time_s - sb.run_time_s) < 1.0
    assert a.split_times() == b.split_times()
    assert a.allocated_nodes() == b.allocated_nodes()


def test_warm_start_matches_direct_feed(tmp_path):
    for cut in (30, 400, 900, 1300, 1700, len(LINES)):
        p = tmp_path / f"cut{cut}.log"
        p.write_text("".join(LINES[:cut]), encoding="utf-8")
        eng = RunEngine(ROUTE)
        assert warm_start(eng, p)
        assert eng.snapshot().toasts == ()
        _same(eng, _direct(LINES[:cut]))
    assert eng.finished                                # last cut = whole campaign
    n = eng.allocated_nodes()
    assert n and all(isinstance(x, str) for x in n)


def test_warm_start_picks_last_run_and_saves_nothing(tmp_path):
    # an earlier complete run, then a second run cut in the middle
    cut = 700
    p = tmp_path / "two.log"
    p.write_text("".join(LINES) + "".join(LINES[:cut]), encoding="utf-8")
    store = SplitStore(tmp_path / "runs")
    eng = RunEngine(ROUTE, store=store)
    assert warm_start(eng, p)
    _same(eng, _direct(LINES[:cut]))
    assert not eng.finished and eng.snapshot().running
    assert store.list_runs() == []
    # a complete last run does not create a RunRecord either
    p2 = tmp_path / "full.log"
    p2.write_text("".join(LINES), encoding="utf-8")
    eng2 = RunEngine(ROUTE, store=store)
    assert warm_start(eng2, p2) and eng2.finished
    assert store.list_runs() == []


def test_revisit_of_first_area_is_not_a_run_start(tmp_path):
    # tail of a run ends with a re-entry of G1_1 at char level 5: still the same run
    extra = ('2025/12/12 22:40:00 1 a [DEBUG Client 1] Generating level 1 area "G1_1" with seed 5\n')
    body = "".join(LINES[:80]) + extra
    p = tmp_path / "rev.log"
    p.write_text(body, encoding="utf-8")
    assert find_run_start(p) == 0
    eng = RunEngine(ROUTE)
    assert warm_start(eng, p)
    assert eng.snapshot().char_level is not None and eng.snapshot().char_level >= 7


def test_no_run_returns_false_and_engine_untouched(tmp_path):
    p = tmp_path / "norun.log"
    p.write_text("".join(LINES[0:0]) + "".join(l for l in LINES[200:600]
                                                if 'area "G1_1"' not in l), encoding="utf-8")
    eng = RunEngine(ROUTE)
    before = eng.snapshot()
    assert warm_start(eng, p) is False
    assert eng.snapshot() == before and eng.allocated_nodes() is None
    empty = tmp_path / "empty.log"
    empty.write_bytes(b"")
    assert warm_start(eng, empty) is False
    assert warm_start(eng, tmp_path / "missing.log") is False


def test_warm_start_speed_big_file(tmp_path):
    t = time.perf_counter()
    eng = RunEngine(ROUTE)
    assert warm_start(eng, FIXTURE)
    fixture_s = time.perf_counter() - t
    # ~75 MB of junk lines in front of one run
    junk = ("2025/12/12 20:00:00 1 a [INFO Client 1] Connecting to instance server at 1.2.3.4:6112 "
            "padding padding padding padding padding\n") * 600_000
    p = tmp_path / "big.log"
    with open(p, "w", encoding="utf-8") as f:
        f.write(junk)
        f.write("".join(LINES[:300]))
    assert p.stat().st_size > 60_000_000
    t = time.perf_counter()
    eng = RunEngine(ROUTE)
    assert warm_start(eng, p)
    big_s = time.perf_counter() - t
    print(f"warm start: fixture {fixture_s:.3f}s, {p.stat().st_size / 1e6:.0f}MB {big_s:.3f}s")
    assert big_s < 3.0 and fixture_s < 1.0
    _same(eng, _direct(LINES[:300]))


def test_warm_start_end_offset_lets_the_watcher_continue(tmp_path):
    from pilot.core.logwatch import LogWatcher
    src = Path(__file__).resolve().parents[1] / "fixtures" / "campaign_ru.log"
    lines = src.read_text(encoding="utf-8").splitlines(keepends=True)[:300]
    log = tmp_path / "Client.txt"
    log.write_bytes(("".join(lines) + "2025/12/12 23:59:59 1 2 [INFO Client 1] : Tes").encode("utf-8"))
    eng = RunEngine(ROUTE)
    end: list[int] = []
    assert warm_start(eng, log, end=end)
    assert end and end[0] == len("".join(lines).encode("utf-8"))      # stops before the partial line
    got = []
    w = LogWatcher(log, got.append, start_offset=end[0])
    w.start(); w.stop(); w._stop.clear()       # fix the start position, then poll by hand
    with log.open("ab") as f:
        f.write(b"tExile (Monk) is now level 9\n")
    w.poll_once()
    assert got[-1].endswith(": TestExile (Monk) is now level 9")      # the partial line, whole
