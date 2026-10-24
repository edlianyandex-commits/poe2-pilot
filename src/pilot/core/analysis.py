"""Post-run analysis: replay a Client.txt through a route and report where the time went.

CLI: python -m pilot.core.analysis [Client.txt] [--route FILE] [--run N] [--vs pb|N] [--runs-dir DIR]
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pilot.core.engine import RunEngine, fmt_delta, fmt_time
from pilot.core.logpath import find_client_log
from pilot.core.logwatch import replay
from pilot.core.route import Route, load_route
from pilot.core.splits import RunRecord, SplitStore, ZoneSegment

DEFAULT_ROUTE = Path(__file__).resolve().parents[3] / "data" / "routes" / "campaign-0.5.json"

# rooms inside a trial are logged as their own areas; they belong to the trial's route step
_SUBAREA_PREFIX = {"Sanctum_": "G2_13"}


def _route_area(area_id: str) -> str:
    for prefix, parent in _SUBAREA_PREFIX.items():
        if area_id.startswith(prefix):
            return parent
    return area_id


@dataclass
class RunReport:
    route_id: str
    status: str                       # "finished" | "abandoned" | "incomplete"
    started_at: str
    total_s: float
    deaths: int
    splits: dict[str, float] = field(default_factory=dict)
    zones: list[ZoneSegment] = field(default_factory=list)

    @property
    def town_s(self) -> float:
        return sum(z.seconds for z in self.zones if z.is_town)

    @property
    def loading_s(self) -> float:
        return sum(z.loading_s for z in self.zones)

    def top_zones(self, n: int = 8) -> list[ZoneSegment]:
        return sorted(self.zones, key=lambda z: z.seconds, reverse=True)[:n]

    def extra_zones(self, route: Route) -> list[ZoneSegment]:
        """Visited zones that are not part of the route (hideouts excluded)."""
        in_route = {s.area for s in route.steps}
        return [z for z in self.zones
                if _route_area(z.area_id) not in in_route and "hideout" not in z.area_id.lower()]

    @classmethod
    def from_record(cls, rec: RunRecord) -> "RunReport":
        return cls(rec.route_id, rec.status, rec.started_at, rec.total_s, rec.deaths,
                   dict(rec.splits), rec.zone_segments())


@dataclass(frozen=True)
class ZoneDelta:
    area_id: str
    area_name: str
    seconds: float
    base_seconds: float

    @property
    def delta(self) -> float:
        return self.seconds - self.base_seconds


def compare(report: RunReport, baseline: RunReport) -> list[ZoneDelta]:
    """Per-zone time difference vs a baseline, biggest loss first."""
    mine = {z.area_id: z for z in report.zones}
    base = {z.area_id: z for z in baseline.zones}
    out = []
    for aid in list(mine) + [a for a in base if a not in mine]:
        z = mine.get(aid) or base[aid]
        out.append(ZoneDelta(aid, z.area_name or aid,
                             mine[aid].seconds if aid in mine else 0.0,
                             base[aid].seconds if aid in base else 0.0))
    out.sort(key=lambda d: d.delta, reverse=True)
    return out


class _MemoryStore:
    """Minimal SplitStore stand-in that just collects the runs the engine saves."""

    def __init__(self) -> None:
        self.records: list[RunRecord] = []

    def save_run(self, rec: RunRecord) -> None:
        self.records.append(rec)

    def delta(self, route_id: str, split_id: str, t: float) -> None:
        return None

    def pb_total(self, route_id: str) -> None:
        return None


def analyze_log(path: str | Path, route: Route | None = None) -> list[RunReport]:
    """Replay `path` through `route` (default campaign route); one report per run found."""
    route = route or load_route(DEFAULT_ROUTE)
    mem = _MemoryStore()
    eng = RunEngine(route, store=mem)  # type: ignore[arg-type]
    replay(path, eng.feed_line, speed=0)
    reports = [RunReport.from_record(r) for r in mem.records]
    tail = eng.current_record("incomplete") if not eng.finished else None
    if tail is not None and eng.snapshot().running:
        reports.append(RunReport.from_record(tail))
    return reports


# ---------------- CLI ----------------

def _zone_label(z: ZoneSegment, width: int = 26) -> str:
    name = z.area_name or z.area_id
    return name if len(name) <= width else name[: width - 1] + "…"


def format_report(rep: RunReport, route: Route, baseline: RunReport | None = None,
                  title: str = "") -> str:
    tot = rep.total_s or 1.0
    lines = [
        f"{title}Ран: {_status_ru(rep.status)}, старт {rep.started_at}",
        f"  Игровое время : {fmt_time(rep.total_s)}",
        f"  В городах     : {fmt_time(rep.town_s)} ({rep.town_s / tot:.0%})",
        f"  Загрузки      : {fmt_time(rep.loading_s)}",
        f"  Смерти        : {rep.deaths}",
        "",
        "  Топ-8 зон по времени:",
        f"    {'зона':<26}{'время':>9}{'%':>5}{'заходов':>9}{'смертей':>9}",
    ]
    for z in rep.top_zones(8):
        lines.append(f"    {_zone_label(z):<26}{fmt_time(z.seconds):>9}{z.seconds / tot:>5.0%}"
                     f"{z.visits:>9}{z.deaths:>9}")
    extra = sorted(rep.extra_zones(route), key=lambda z: z.seconds, reverse=True)
    lines.append("")
    if extra:
        lines.append("  Лишние заходы (нет в маршруте):")
        for z in extra[:10]:
            lines.append(f"    {_zone_label(z):<26}{fmt_time(z.seconds):>9}{z.visits:>5}x")
        if len(extra) > 10:
            lines.append(f"    … и ещё {len(extra) - 10}")
    else:
        lines.append("  Лишних заходов нет")
    if baseline is not None:
        lines += ["", f"  Где потеряно время (против {fmt_time(baseline.total_s)}):"]
        losses = [d for d in compare(rep, baseline) if d.delta > 0][:5]
        for d in losses:
            lines.append(f"    {(d.area_name or d.area_id)[:26]:<26}{fmt_delta(d.delta):>9}")
        if not losses:
            lines.append("    нигде — быстрее везде")
    return "\n".join(lines)


def _status_ru(status: str) -> str:
    return {"finished": "завершён", "abandoned": "брошен", "incomplete": "не завершён"}.get(status, status)


def _best_saved(store: SplitStore, route_id: str) -> RunReport | None:
    runs = [r for r in store.list_runs(route_id) if r.status == "finished" and r.segments]
    return RunReport.from_record(min(runs, key=lambda r: r.total_s)) if runs else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pilot.core.analysis", description=__doc__)
    ap.add_argument("log", nargs="?", help="Client.txt (default: auto-detected)")
    ap.add_argument("--route", default=str(DEFAULT_ROUTE))
    ap.add_argument("--run", type=int, default=0, help="which run in the log (1-based; default last)")
    ap.add_argument("--vs", default="pb", help="baseline: 'pb' (best saved run) or N = run N of this log")
    ap.add_argument("--runs-dir", default=None, help="SplitStore directory (default %%APPDATA%%)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    log = Path(args.log) if args.log else find_client_log()
    if log is None or not log.is_file():
        print("Client.txt не найден: укажите путь аргументом", file=sys.stderr)
        return 2
    route = load_route(args.route)
    reports = analyze_log(log, route)
    if not reports:
        print("В логе не найдено ни одного рана (нужен вход в G1_1 на 1 уровне)")
        return 1
    idx = (args.run or len(reports)) - 1
    if not 0 <= idx < len(reports):
        print(f"Нет рана №{args.run}: в логе найдено {len(reports)}", file=sys.stderr)
        return 2
    rep = reports[idx]

    base: RunReport | None = None
    if args.vs == "pb":
        store = SplitStore(args.runs_dir) if args.runs_dir else SplitStore()
        base = _best_saved(store, route.id)
    elif args.vs.isdigit() and 1 <= int(args.vs) <= len(reports) and int(args.vs) - 1 != idx:
        base = reports[int(args.vs) - 1]
    print(format_report(rep, route, base, f"[{idx + 1}/{len(reports)}] "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
