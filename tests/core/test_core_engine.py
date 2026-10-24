from datetime import datetime, timedelta

from pilot.contracts import (
    AreaGenerated, Death, FocusChanged, GameClosed, LevelHint, LevelPlan, LevelUp,
    LoadingScreen, PassiveAllocated, SceneEntered,
)
from pilot.core.engine import RunEngine
from pilot.core.route import Route, Step
from pilot.core.splits import RunRecord, SplitStore

T0 = datetime(2025, 1, 1, 12, 0, 0)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def S(id, area, split=False, done_on=None, kind="move", act=1):
    return Step(id, act, area, f"→ {id}", kind, split=split, done_on_enter=done_on)


ROUTE = Route("r", "T", (
    S("a", "G1_1", split=True),
    S("b", "G1_2"),
    S("c", "G1_3", done_on="G1_town"),
    S("d", "G1_4", split=True),
    S("e", "G_Endgame_Town", split=True, act=4),
))


class Feeder:
    def __init__(self, eng):
        self.eng, self.sec = eng, 0.0

    def at(self, sec):
        self.sec = sec
        return T0 + timedelta(seconds=sec)

    def zone(self, area, sec, level=5, name="Zone"):
        self.eng.feed(AreaGenerated(self.at(sec), area, level, 1))
        self.eng.feed(SceneEntered(self.at(sec + 1), name))

    def feed(self, ev_cls, sec, *a):
        self.eng.feed(ev_cls(self.at(sec), *a))


def make(route=ROUTE, plan=None, store=None):
    clk = Clock()
    eng = RunEngine(route, plan, store, clock=clk)
    return eng, Feeder(eng), clk


def test_idle_until_start():
    eng, f, _ = make()
    f.zone("G1_2", 0)
    s = eng.snapshot()
    assert not s.running and s.run_time_s == 0 and s.step_short == "→ a" and s.step_total == 5


def test_start_requires_level_1():
    eng, f, _ = make()
    f.feed(LevelUp, 0, "X", "Mage", 7)
    f.zone("G1_1", 5)
    assert not eng.snapshot().running
    eng2, f2, _ = make()
    f2.zone("G1_1", 5, level=1, name="Берег")
    s = eng2.snapshot()
    assert s.running and s.area_name == "Берег" and s.act == 1
    assert eng2.split_times() == {"a": 0.0}


def test_steps_progress_skip_and_hideout_and_time():
    eng, f, clk = make()
    f.zone("G1_1", 0, 1)
    f.zone("G1_2", 100, 2)                      # next step area
    assert eng.snapshot().step_index == 1 + 0 and eng.snapshot().step_short == "→ b"
    f.zone("Hideout_X", 150)                    # ignored
    assert eng.snapshot().step_short == "→ b"
    f.zone("G1_town", 200)                      # town: no advance
    assert eng.snapshot().step_short == "→ b"
    f.zone("G1_3", 300, 3)                      # b -> c
    assert eng.snapshot().step_short == "→ c"
    f.zone("G1_2", 310)                         # backwards: ignored
    assert eng.snapshot().step_short == "→ c"
    f.zone("G1_town", 400)                      # done_on of c
    s = eng.snapshot()
    assert s.step_short == "→ d" and s.next_short == "→ e"
    assert eng.split_times() == {"a": 0.0}
    f.zone("G_Endgame_Town", 1000, 65)          # skip ahead + finish
    assert eng.finished and eng.split_times()["e"] == 1000.0
    s = eng.snapshot()
    assert not s.running and s.run_time_s == 1000.0 and s.step_short is None


def test_manual_steps_and_reset():
    eng, f, _ = make()
    f.zone("G1_1", 0, 1)
    eng.next_step(); eng.next_step()
    assert eng.snapshot().step_index == 2
    eng.prev_step()
    assert eng.snapshot().step_index == 1
    for _ in range(10):
        eng.next_step()
    assert eng.snapshot().step_index == 4
    eng.reset_run()
    s = eng.snapshot()
    assert not s.running and s.step_index == 0 and s.run_time_s == 0
    f.zone("G1_1", 100, 1)                      # restarts even if char level was high
    assert eng.snapshot().running


def test_live_clock_extrapolation_and_toast_expiry():
    eng, f, clk = make()
    f.zone("G1_1", 0, 1)
    assert any(t.text == "Ран начат" for t in eng.snapshot().toasts)
    clk.t = 2
    base = eng.snapshot().run_time_s
    clk.t = 2.5
    assert eng.snapshot().run_time_s - base == 0.5
    clk.t = 20
    assert eng.snapshot().toasts == ()


def test_loading_closed_and_afk_excluded():
    eng, f, _ = make()
    f.zone("G1_1", 0, 1)                         # scene at 1s
    f.feed(LoadingScreen, 11, "Z", 4.0)          # 11s wall - 4s loading
    assert eng.snapshot().run_time_s == 7.0
    f.feed(GameClosed, 20)
    assert not eng.snapshot().game_focused
    f.feed(FocusChanged, 100000, False)          # first event after 27h closed
    assert eng.snapshot().run_time_s == 7.0 + 9.0
    f.feed(FocusChanged, 100030, True)
    assert eng.snapshot().run_time_s == 7.0 + 9.0 + 30
    f.feed(FocusChanged, 100030 + 3600, True)    # silent hour = idle, not counted
    assert eng.snapshot().run_time_s == 7.0 + 9.0 + 30


def test_split_delta_and_store(tmp_path):
    store = SplitStore(tmp_path)
    store.save_run(RunRecord("r", "finished", "2025-01-01T00:00:00", 900.0, {"a": 0.0, "d": 450.0, "e": 900.0}))
    eng, f, _ = make(store=store)
    f.zone("G1_1", 0, 1)
    f.zone("G1_2", 100)
    f.zone("G1_3", 200)
    f.zone("G1_4", 400)                           # d split at 400 vs PB 450
    s = eng.snapshot()
    assert s.split_delta_s == -50.0
    assert any(t.kind == "split" and "−0:50" in t.text and len(t.text) <= 40 for t in s.toasts)
    f.feed(Death, 450, "X")
    f.zone("G_Endgame_Town", 800, 65)
    rec = store.list_runs("r")[-1]
    assert rec.status == "finished" and rec.total_s == 800.0 and rec.deaths == 1
    assert store.pb_total("r") == 800.0
    # abandoned runs are saved only after 30s
    f.zone("G1_1", 2000, 1)
    eng.reset_run()
    assert len(store.list_runs("r")) == 2
    f.zone("G1_1", 3000, 1)
    f.zone("G1_2", 3100)
    eng.reset_run()
    assert store.list_runs("r")[-1].status == "abandoned"


def test_level_toasts_and_plan():
    plan = LevelPlan("p", "Mage", {3: LevelHint(3, passives=("Быстрота",), gems=("Ледяная стрела",))},
                     planned_node_ids=("n1",))
    eng, f, _ = make(plan=plan)
    f.feed(LevelUp, 0, "X", "Mage", 3)
    assert eng.snapshot().toasts[-1].text == "Ур. 3: +Быстрота · Ледяная стрела"
    f.feed(LevelUp, 1, "X", "Mage", 4)
    assert eng.snapshot().toasts[-1].text == "Ур. 4"
    assert eng.snapshot().char_level == 4
    f.feed(PassiveAllocated, 2, "n1", "ok", True)
    f.feed(PassiveAllocated, 3, "zzz", "bad", True)
    texts = [t.text for t in eng.snapshot().toasts]
    assert texts.count("Пассивка не по плану") == 1
    eng2, f2, _ = make()                          # no plan: no passive warnings
    f2.feed(PassiveAllocated, 0, "zzz", "bad", True)
    assert eng2.snapshot().toasts == ()
    eng2.feed(LevelUp(T0, "X", "Mage", 9))
    assert eng2.snapshot().toasts[-1].text == "Ур. 9"


def test_level_warning():
    eng, f, _ = make()
    f.feed(LevelUp, 0, "X", "Mage", 10)
    f.zone("G1_2", 1, level=13)
    assert eng.snapshot().warn is None            # 13 - 10 = 3, not > 3
    f.zone("G1_3", 5, level=14)
    assert eng.snapshot().warn == "⚠ Ур. ниже зоны −4"
    f.zone("G1_town", 9, level=15)
    assert eng.snapshot().warn is None
    f.zone("Hideout_A", 20, level=30)
    assert eng.snapshot().warn is None
    f.zone("G1_5", 30, level=14)
    assert eng.snapshot().warn is not None
    assert len(eng.snapshot().warn) <= 40
