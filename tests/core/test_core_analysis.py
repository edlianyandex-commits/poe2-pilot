import os
import subprocess
import sys
from pathlib import Path

from pilot.contracts import Death
from pilot.core.analysis import RunReport, analyze_log, compare, main
from pilot.core.parser import parse_line
from pilot.core.route import load_route
from pilot.core.splits import RunRecord, SplitStore

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "campaign_ru.log"
ROUTE = ROOT / "data" / "routes" / "campaign-0.5.json"


def test_analyze_fixture_consistency():
    route = load_route(ROUTE)
    reports = analyze_log(FIXTURE, route)
    assert len(reports) == 1
    r = reports[0]
    assert r.status == "finished" and r.total_s > 3600
    assert abs(sum(z.seconds for z in r.zones) - r.total_s) <= 0.01 * r.total_s
    assert all(z.visits >= 1 for z in r.zones)
    assert r.zones[0].area_id == "G1_1" and r.zones[0].first_s == 0.0
    names = [z for z in r.zones if z.area_name]
    assert len(names) > len(r.zones) * 0.8
    # deaths between run start and finish == Death events in that span
    deaths = sum(isinstance(parse_line(ln), Death) for ln in FIXTURE.read_text(encoding="utf-8").splitlines())
    assert r.deaths == deaths == sum(z.deaths for z in r.zones)
    assert any(z.is_town for z in r.zones) and 0 < r.town_s < r.total_s
    assert r.extra_zones(route)                      # Incursion/Abyss etc. are not in the route
    assert all(z.area_id != "G1_1" for z in r.extra_zones(route))


def test_compare():
    from pilot.core.splits import ZoneSegment as Z
    a = RunReport("r", "finished", "", 100, 0, zones=[Z("A", "a", seconds=60), Z("B", "b", seconds=40)])
    b = RunReport("r", "finished", "", 90, 0, zones=[Z("A", "a", seconds=30), Z("C", "c", seconds=60)])
    d = {x.area_id: x.delta for x in compare(a, b)}
    assert d == {"A": 30, "B": 40, "C": -60}
    assert [x.area_id for x in compare(a, b)][0] == "B"


def test_segments_persist_and_old_records_load(tmp_path):
    store = SplitStore(tmp_path)
    rep = analyze_log(FIXTURE, load_route(ROUTE))[0]
    rec = RunRecord("campaign-0.5", "finished", rep.started_at, rep.total_s,
                    rep.splits, rep.deaths, [z.to_dict() for z in rep.zones])
    store.save_run(rec)
    back = SplitStore(tmp_path).list_runs()[0]
    assert back.zone_segments() == rep.zones
    (tmp_path / "run_old_finished.json").write_text(
        '{"route_id":"x","status":"finished","started_at":"","total_s":5.0,"splits":{},"deaths":0}',
        encoding="utf-8")
    old = [r for r in SplitStore(tmp_path).list_runs("x")]
    assert old and old[0].segments == [] and old[0].zone_segments() == []


def test_main_in_process(tmp_path, capsys):
    rc = main([str(FIXTURE), "--route", str(ROUTE), "--runs-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0 and "Игровое время" in out and "Топ-8 зон" in out and "Лишние заходы" in out


def test_cli_smoke_with_baseline(tmp_path):
    # save a faster baseline as PB, then check the "lost time" section appears
    rep = analyze_log(FIXTURE, load_route(ROUTE))[0]
    fast = [z.to_dict() for z in rep.zones]
    for d in fast:
        d["seconds"] *= 0.5
    SplitStore(tmp_path).save_run(RunRecord("campaign-0.5", "finished", "2025-01-01T00:00:00",
                                            rep.total_s / 2, rep.splits, 0, fast))
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-m", "pilot.core.analysis", str(FIXTURE),
                        "--runs-dir", str(tmp_path)],
                       capture_output=True, env=env, cwd=ROOT, timeout=60)
    out = p.stdout.decode("utf-8")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert "Игровое время" in out and "Где потеряно время" in out
