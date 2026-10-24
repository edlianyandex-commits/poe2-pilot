"""Entry point: wires LogWatcher -> parser -> RunEngine -> overlay (lead-owned)."""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from pilot.config import load_config, save_config

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def _load_plan(cfg: dict, build_arg: str | None):
    """-> PlanDetail (plan + tree data for the tree window) or None without a build."""
    src = build_arg or cfg.get("build_code_file")
    if not src:
        return None
    from pilot.planner import build_plan_detail
    p = Path(src)
    # a file path lets the planner pick up the X.gear.json sidecar next to X.pob
    return build_plan_detail(p if p.exists() else src)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="poe2-pilot")
    ap.add_argument("--route", help="route id in data/routes or path to a .json")
    ap.add_argument("--build", help="PoB2 export code or a file containing it")
    ap.add_argument("--log", help="path to Client.txt (default: auto-detect)")
    ap.add_argument("--replay", help="replay a Client.txt instead of tailing the live one")
    ap.add_argument("--speed", type=float, default=60.0, help="replay speed multiplier")
    args = ap.parse_args(argv)

    from pilot.core.engine import RunEngine
    from pilot.core.logpath import find_client_log
    from pilot.core.logwatch import LogWatcher, replay
    from pilot.core.parser import parse_line
    from pilot.core.route import load_route
    from pilot.core.splits import SplitStore
    from pilot.overlay import run_overlay

    cfg = load_config()
    cfg["on_save"] = save_config

    route_arg = args.route or cfg["route"]
    route_path = Path(route_arg) if route_arg.endswith(".json") else DATA / "routes" / f"{route_arg}.json"
    route = load_route(route_path)
    detail = _load_plan(cfg, args.build)
    engine = RunEngine(route, plan=detail.plan if detail else None, store=SplitStore())
    cfg["details_provider"] = engine.details
    cfg["gem_provider"] = engine.gem_rows

    def current_level():
        s = engine.snapshot()
        return s.char_level or (1 if s.running else None)
    cfg["level_provider"] = current_level

    if detail is not None:
        from pilot.planner.treeview import TreeViewBuilder
        tree = TreeViewBuilder(detail)
        cfg["tree_provider"] = lambda: tree.view(engine.allocated_nodes(), current_level())

    def on_line(line: str) -> None:
        ev = parse_line(line)
        if ev is not None:
            engine.feed(ev)

    if args.replay:
        cfg["hide_when_unfocused"] = False
        threading.Thread(target=replay, args=(args.replay, on_line, args.speed), daemon=True).start()
        watcher = None
    else:
        log = Path(args.log or cfg["log_path"] or find_client_log() or "")
        if not log.is_file():
            print("Client.txt не найден: укажите --log или log_path в конфиге", file=sys.stderr)
            return 2
        # started mid-run: rebuild step, timer, level and passives from the log first
        from pilot.core.warmstart import warm_start
        warm_start(engine, log)
        watcher = LogWatcher(log, on_line, from_end=True)
        watcher.start()

    try:
        return run_overlay(engine, engine, cfg)
    finally:
        if watcher:
            watcher.stop()


if __name__ == "__main__":
    sys.exit(main())
