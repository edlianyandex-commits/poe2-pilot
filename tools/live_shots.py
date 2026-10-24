"""Replay the real log through engine + planner and render the HUD at key moments (lead QA tool).

usage: python -X utf8 tools/live_shots.py [build.pob]
Writes docs/screens/live_*.png.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from pilot.contracts import AreaGenerated, LevelUp  # noqa: E402
from pilot.core.engine import RunEngine  # noqa: E402
from pilot.core.parser import parse_line  # noqa: E402
from pilot.core.route import load_route  # noqa: E402
from pilot.core.splits import SplitStore  # noqa: E402
from pilot.overlay.hud import HudWindow as _Hud  # noqa: E402
from pilot.planner import build_plan  # noqa: E402
from tests.overlay.test_screens import _shot  # noqa: E402

build = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "tests/planner/fixtures/amazon_leveling_0_5.pob")
plan = build_plan(build.read_text(encoding="utf-8").strip())
engine = RunEngine(load_route(ROOT / "data/routes/campaign-0.5.json"), plan=plan,
                   store=SplitStore(Path(tempfile.mkdtemp())), clock=lambda: 0.0)
app = QApplication.instance() or QApplication([])


def HudWindow(cfg, clock=None):  # noqa: N802
    """HUD whose clock moves 1 s after set_state, so toast fade-in has finished at grab time."""
    t = [0.0]
    hud = _Hud(cfg, clock=lambda: t[0])
    orig = hud.set_state

    def set_state(s):
        orig(s)
        t[0] = 1.0
    hud.set_state = set_state
    return hud

# (predicate on event, screenshot name); shot taken after the following SceneEntered line
moments = [
    (lambda e: isinstance(e, LevelUp) and e.level == 6, "live_levelup.png"),
    (lambda e: isinstance(e, AreaGenerated) and e.area_id == "G2_1", "live_act2.png"),
    (lambda e: isinstance(e, AreaGenerated) and e.area_id == "G2_13", "live_trial.png"),
]
pending = None
for line in open(ROOT / "tests/fixtures/campaign_ru.log", encoding="utf-8"):
    ev = parse_line(line)
    if ev is None:
        continue
    engine.feed(ev)
    if pending and type(ev).__name__ in ("SceneEntered", "LevelUp"):
        hud = HudWindow({"details_provider": engine.details}, clock=lambda: 0.0)
        hud.set_state(engine.snapshot())
        print(pending, "->", [t.text for t in engine.snapshot().toasts], _shot(hud, pending))
        if pending == "live_act2.png":
            hud.set_details_visible(True)
            print("details ->", _shot(hud, "live_details.png"))
        pending = None
        engine._toasts.clear()  # QA only: start each moment with a clean toast stack
    for pred, name in moments:
        if pred(ev):
            pending = name
            if isinstance(ev, LevelUp):  # level-up toasts are already there
                hud = HudWindow({}, clock=lambda: 0.0)
                hud.set_state(engine.snapshot())
                print(name, "->", [t.text for t in engine.snapshot().toasts], _shot(hud, name))
                pending = None
print("plan:", plan.title, "| asc trials:", list(plan.ascendancy))
