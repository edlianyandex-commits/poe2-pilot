"""python -m pilot.planner <code-or-file> [--gear X.gear.json] [--max-level N]

Prints the leveling plan as a table (passives | gems | gear) and the full gem setup at a few
checkpoint levels.
"""
from __future__ import annotations

import argparse
import sys

from . import build_plan_detail
from .plan import passive_points_at

CHECKPOINTS = (1, 5, 10, 16, 30, 45, 60)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pilot.planner")
    ap.add_argument("source", help="PoB export code, file with a code, or PoB .xml file ('-' = stdin)")
    ap.add_argument("--gear", default=None, help="gear sidecar JSON (default: <source>.gear.json)")
    ap.add_argument("--max-level", type=int, default=100)
    ap.add_argument("--ids", action="store_true", help="also print planned node string ids")
    a = ap.parse_args(argv)
    src = sys.stdin.read() if a.source == "-" else a.source
    d = build_plan_detail(src, max_level=a.max_level, gear_file=a.gear)
    p = d.plan
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"{p.title}  [{p.char_class}]  nodes={len(d.main_order)} asc={len(d.asc_order)}")
    print(f"{'Lv':>3} {'Pts':>7}  {'Passives':<60} | {'Gems':<70} | Gear")
    for lvl in sorted(p.hints):
        h = p.hints[lvl]
        pts = f"{d.points_used.get(lvl, 0)}/{passive_points_at(lvl)}"
        line = (f"{lvl:>3} {pts:>7}  {' · '.join(h.passives):<60} | {' · '.join(h.gems):<70}"
                f" | {' · '.join(h.gear)}")
        if h.note:
            line += f"  [{h.note}]"
        print(line.rstrip())
    for area, h in p.ascendancy.items():
        print(f"asc {area}: {' · '.join(h.passives)}")
    print("\nGem setups:")
    for lvl in CHECKPOINTS:
        if lvl > a.max_level:
            break
        print(f"  Lv {lvl}:")
        for s in p.setup_for(lvl) or ("—",):
            print(f"    {s}")
    for w in d.warnings:
        print(f"! {w}")
    if a.ids:
        print(",".join(p.planned_node_ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
