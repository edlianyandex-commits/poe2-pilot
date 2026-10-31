"""Entry point: wires LogWatcher -> parser -> RunEngine -> overlay (lead-owned)."""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from pilot.config import load_config, save_config
from pilot.i18n import tr

from pilot.paths import BUILDS, DATA

# replay demos without --build and no build chosen yet
DEFAULT_BUILD = "twister_monk_guythatdies_0_5_5.build"


def _load_plan(cfg: dict, build_arg: str | None):
    """-> PlanDetail (plan + tree data for the tree window) or None without a build."""
    src = build_arg or cfg.get("build_code_file") or DEFAULT_BUILD
    from pilot.planner import build_plan_detail
    p = Path(src)
    if not p.exists() and (BUILDS / src).exists():     # a bundled build by file name
        p = BUILDS / src
    if not p.exists() and len(src) < 260 and src.endswith((".pob", ".build")):
        print(tr("Билд не найден: {src}", src=src), file=sys.stderr)
        return None
    # a file path lets the planner pick up the X.gear.json sidecar next to X.pob
    return build_plan_detail(p if p.exists() else src)


def _setup_logging() -> None:
    """Console + %APPDATA%/poe2-pilot/pilot.log (the previous run's kept as pilot.prev.log)."""
    import logging
    from pilot.config import config_dir
    from pilot.startup import rotate_log
    config_dir().mkdir(parents=True, exist_ok=True)
    rotate_log(config_dir() / "pilot.log")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(config_dir() / "pilot.log", mode="w", encoding="utf-8")])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="poe2-pilot")
    ap.add_argument("--route", help="route id in data/routes or path to a .json (default: the catalog's)")
    ap.add_argument("--build", help="PoB2 export code or a file containing it (skips the start window)")
    ap.add_argument("--log", help="path to Client.txt (default: auto-detect)")
    ap.add_argument("--replay", help="replay a Client.txt instead of tailing the live one")
    ap.add_argument("--speed", type=float, default=60.0, help="replay speed multiplier")
    ap.add_argument("--wait-lock", action="store_true", help=argparse.SUPPRESS)   # set by relaunch()
    args = ap.parse_args(argv)

    from pilot.core.engine import RunEngine
    from pilot.core.logpath import find_client_log
    from pilot.core.logwatch import LogWatcher, replay
    from pilot.core.parser import parse_line_or_tick
    from pilot.core.route import load_route, require_steps
    from pilot.core.splits import SplitStore
    from pilot.overlay import run_overlay

    from pilot.config import config_dir
    from pilot.startup import already_running, ask_client_log, instance_lock, resolve_log

    # one copy at a time; a restart (change of build, update) waits for the old copy to quit
    from pilot.i18n import set_lang
    set_lang(load_config().get("language"))
    lock = None
    if not args.replay:
        lock = instance_lock(config_dir() / "pilot.lock", 15000 if args.wait_lock else 0)
        if lock is None:
            already_running()
            return 1

    cfg = load_config()
    cfg["on_save"] = save_config
    _setup_logging()

    log = None
    if not args.replay:                      # before the start window: no point picking a build without it
        log = resolve_log(args.log, cfg, find_client_log, ask_client_log)
        if log is None:
            print(tr("Client.txt не найден: укажите --log или log_path в конфиге"), file=sys.stderr)
            return 2
        if cfg.get("log_path") == str(log):
            save_config(cfg)

    build = args.build
    if build is None and not args.replay:
        from pilot.launcher import pick_build
        build = pick_build(cfg)
        if build is None:
            return 0
        cfg["build_code_file"] = build
        save_config(cfg)

    from pilot.catalog import load_catalog
    route_arg = args.route or load_catalog().route or "campaign-0.5"
    route_path = Path(route_arg) if route_arg.endswith(".json") else DATA / "routes" / f"{route_arg}.json"
    route = load_route(route_path)
    detail = _load_plan(cfg, build)
    if detail is not None:
        route = require_steps(route, detail.plan.route_require)   # the build's must-do steps
    engine = RunEngine(route, plan=detail.plan if detail else None, store=SplitStore(),
                       afk_gap_s=float(cfg.get("afk_pause_s", 300)),
                       pause_when_unfocused=cfg.get("pause_when_unfocused", True))
    cfg["details_provider"] = engine.details
    cfg["gem_provider"] = engine.gem_rows

    def current_level():
        s = engine.snapshot()
        return s.char_level or (1 if s.running else None)
    cfg["level_provider"] = current_level
    if not args.replay:
        from pilot.launcher import relaunch
        cfg["on_switch_build"] = relaunch
        if not cfg.get("seen_help"):         # the hotkeys cheat sheet once, on the first take-off
            cfg["_show_help"] = True        # "_" keys are never saved
            cfg["seen_help"] = True
            save_config(cfg)

    if detail is not None:
        from pilot.planner.treeview import TreeViewBuilder
        tree = TreeViewBuilder(detail)
        cfg["tree_provider"] = lambda: tree.view(engine.allocated_nodes(), current_level())

    def on_line(line: str) -> None:
        ev = parse_line_or_tick(line)
        if ev is not None:
            engine.feed(ev)

    if args.replay:
        # demo only: keep the HUD visible, but never write that into the user's config
        saved_hide = cfg.get("hide_when_unfocused", True)
        cfg["hide_when_unfocused"] = False
        cfg["on_save"] = lambda c: save_config({**c, "hide_when_unfocused": saved_hide})
        threading.Thread(target=replay, args=(args.replay, on_line, args.speed), daemon=True).start()
        watcher = None
    else:
        # started mid-run: rebuild step, timer, level and passives from the log first
        from pilot.core.warmstart import warm_start
        end: list[int] = []
        warm_start(engine, log, end=end)
        watcher = LogWatcher(log, on_line, from_end=True, start_offset=end[0] if end else None)
        watcher.start()

    try:
        return run_overlay(engine, engine, cfg)
    finally:
        if watcher:
            watcher.stop()
        if lock is not None:
            lock.unlock()


if __name__ == "__main__":
    sys.exit(main())
