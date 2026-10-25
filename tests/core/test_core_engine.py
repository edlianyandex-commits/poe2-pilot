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
    assert eng.snapshot().running                 # tentative: may be a new character
    f.feed(LevelUp, 50, "X", "Mage", 8)
    assert not eng.snapshot().running             # it wasn't
    eng2, f2, _ = make()
    f2.zone("G1_1", 5, level=1, name="Берег")
    s = eng2.snapshot()
    assert s.running and s.area_name == "Берег" and s.act == 1
    assert eng2.split_times() == {"a": 0.0}


def test_steps_progress_skip_and_hideout_and_time():
    """The HUD shows the step of the zone the player is in, in any order."""
    eng, f, clk = make()
    f.zone("G1_1", 0, 1)
    f.zone("G1_2", 100, 2)                      # b's zone
    assert eng.snapshot().step_index == 1 and eng.snapshot().step_short == "→ b"
    f.zone("Hideout_X", 150)                    # ignored
    assert eng.snapshot().step_short == "→ b"
    f.zone("G1_town", 200)                      # no step here: next open objective
    assert eng.snapshot().step_short == "→ c"
    f.zone("G1_3", 300, 3)
    assert eng.snapshot().step_short == "→ c"
    f.zone("G1_2", 310)                         # back in b's zone: b again
    assert eng.snapshot().step_short == "→ b"
    f.zone("G1_town", 400)
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
    assert eng.snapshot().run_time_s == 7.0 + 9.0        # 30 s without focus = paused
    f.feed(FocusChanged, 100030 + 3600, True)    # silent hour = idle, not counted
    assert eng.snapshot().run_time_s == 7.0 + 9.0


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
    toasts = [t.text for t in eng.snapshot().toasts]
    assert toasts[-2:] == ["Ур. 3: +Быстрота", "Ледяная стрела"]
    f.feed(LevelUp, 1, "X", "Mage", 4)
    assert eng.snapshot().toasts[-1].text == "Ур. 4"
    assert eng.snapshot().char_level == 4
    f.feed(PassiveAllocated, 2, "n1", "ok", True)
    f.feed(PassiveAllocated, 3, "zzz", "bad", True)
    texts = [t.text for t in eng.snapshot().toasts]
    assert texts.count("Пассивки не по плану: 1") == 1
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


def test_progress_kinds_and_marks():
    eng, f, _ = make()
    s = eng.snapshot()
    assert s.progress == 0.0 and s.step_kind == "move" and s.next_kind == "move"
    assert s.split_marks == (0.0, 0.6, 0.8)         # steps a, d, e of 5
    f.zone("G1_1", 0, 1)
    f.zone("G1_2", 10)
    s = eng.snapshot()
    assert s.progress == 0.4 and s.step_index == 1      # a and b done of 5
    f.zone("G_Endgame_Town", 100, 65)
    s = eng.snapshot()
    assert s.progress == 1.0 and s.step_kind is None and s.next_kind is None


def test_gear_toast_and_max_three_toasts():
    plan = LevelPlan("p", "W", {5: LevelHint(5, passives=("A",), gems=("G",), note="N",
                                             gear=("Надеть Skysliver", "Новое копьё"))})
    eng, f, _ = make(plan=plan)
    f.feed(LevelUp, 0, "X", "W", 5)
    toasts = eng.snapshot().toasts
    assert len(toasts) == 3
    assert (toasts[-1].kind, toasts[-1].ttl_s, toasts[-1].text) == ("gear", 5.0, "Надеть Skysliver · Новое копьё")
    assert [t.kind for t in toasts[:2]] == ["level", "level"]


def test_details_with_setups():
    plan = LevelPlan("p", "W", setups={1: ("Twister: A",), 10: tuple(f"L{k}" for k in range(6))})
    steps = (Step("s0", 1, "G1_1", "→ s0", "move", detail="d0", reward="R"),
             *(Step(f"s{k}", 1, f"G1_{k + 1}", f"→ s{k}", "move") for k in range(1, 6)))
    eng = RunEngine(Route("w", "w", steps), plan)
    eng.feed(LevelUp(T0, "X", "W", 3))
    assert eng.details() == ["d0", "Награда: R", "Twister: A", "→ s1", "→ s2", "→ s3"]
    eng.feed(LevelUp(T0, "X", "W", 12))
    d = eng.details()
    assert d == ["d0", "Награда: R", "L0", "L1", "L2", "→ s1", "→ s2", "→ s3"] and len(d) <= 10


def test_level1_hint_at_run_start_and_gear_in_details():
    gear = ("Tabula Rasa", "Редкое копьё", "Whirling Slash ур. 1")
    plan = LevelPlan("p", "W", hints={1: LevelHint(1, gems=("+ Twister",), gear=gear),
                                      16: LevelHint(16, gear=("Надеть Skysliver",))},
                     setups={1: ("Twister",)})
    eng, f, _ = make(plan=plan)
    f.zone("G1_1", 0, 1)                      # run starts at level 1: no LevelUp line exists
    texts = [t.text for t in eng.snapshot().toasts]
    assert "+ Twister" in texts
    assert "Tabula Rasa · +2 (Alt+Q)" in texts            # >2 items: first + count
    assert eng.details()[:3] == ["Tabula Rasa", "Редкое копьё", "Twister"]
    f.feed(LevelUp, 10, "X", "W", 16)
    assert "Надеть Skysliver" in [t.text for t in eng.snapshot().toasts]
    assert eng.details()[0] == "Надеть Skysliver"


def test_segments_accounting():
    eng, f, _ = make()
    f.zone("G1_1", 0, 1)
    f.zone("G1_town", 100)
    f.feed(LoadingScreen, 130, "T", 5.0)
    f.feed(Death, 150, "X")
    f.zone("G1_1", 200, 1)
    rec = eng.current_record()
    segs = {s["area_id"]: s for s in rec.segments}
    assert segs["G1_1"]["visits"] == 2 and segs["G1_town"]["is_town"]
    assert segs["G1_town"]["loading_s"] == 5.0 and segs["G1_town"]["deaths"] == 1
    assert abs(segs["G1_town"]["seconds"] - 95.0) < 1e-9
    assert abs(sum(s["seconds"] for s in rec.segments) - rec.total_s) < 1e-9


def test_allocated_nodes():
    eng, f, _ = make()
    assert eng.allocated_nodes() is None
    f.feed(PassiveAllocated, 0, "n0", "x", True)          # before any run start: ignored
    assert eng.allocated_nodes() is None
    f.zone("G1_1", 5, 1)
    assert eng.allocated_nodes() == set()
    f.feed(PassiveAllocated, 10, "a", "A", True)
    f.feed(PassiveAllocated, 11, "b", "B", True)
    f.feed(PassiveAllocated, 12, "a", "A", False)
    got = eng.allocated_nodes()
    assert got == {"b"}
    got.add("zzz")                                         # returned copy is detached
    assert eng.allocated_nodes() == {"b"}
    eng.reset_run()
    f.zone("G1_1", 100, 1)                                 # new run start resets
    assert eng.allocated_nodes() == set()


def test_zone_hints_on_first_visit_only():
    plan = LevelPlan("p", "W", zone_hints={"G1_2": ("Renly: Twister", "a", "b")})
    eng, f, _ = make(plan=plan)
    f.zone("G1_1", 0, 1)
    f.zone("G1_2", 10)
    texts = [t.text for t in eng.snapshot().toasts]
    assert "Renly: Twister" in texts and "+1 здесь (Alt+Q)" in texts
    assert eng.details()[:3] == ["Renly: Twister", "a", "b"]
    eng.clear_toasts()
    f.zone("G1_1", 20)
    f.zone("G1_2", 30)
    assert "Renly: Twister" not in [t.text for t in eng.snapshot().toasts]


def test_new_character_while_running_starts_run():
    """App open while switching characters: old char was level 7, the new one enters Riverbank."""
    eng, f, _ = make()
    f.feed(LevelUp, 0, "Old", "Monk", 7)
    f.zone("G1_1", 10, 1)                       # new character, no LevelUp yet
    assert eng.snapshot().running and eng.snapshot().char_level == 1
    f.feed(LevelUp, 100, "New", "Monk", 2)      # confirms the run
    f.zone("G1_town", 200)
    s = eng.snapshot()
    assert s.running and s.char_level == 2 and s.run_time_s > 0


def test_old_character_revisiting_riverbank_cancels_tentative_run():
    eng, f, _ = make()
    f.feed(LevelUp, 0, "Old", "Monk", 7)
    f.zone("G1_1", 10, 1)
    f.feed(LevelUp, 100, "Old", "Monk", 8)
    s = eng.snapshot()
    assert not s.running and s.char_level == 8


def test_new_character_mid_run_restarts_from_its_riverbank():
    """Old run deep in Act 1; a new character enters Riverbank; its first level-up switches runs."""
    eng, f, _ = make()
    f.zone("G1_1", 0, 1)
    f.feed(LevelUp, 60, "Old", "Monk", 4)
    for i, z in enumerate(("G1_town", "G1_2", "G1_3", "G1_4")):
        f.zone(z, 100 + i * 100)
    assert eng.snapshot().step_index > 1
    f.zone("G1_1", 1000, 1)                      # new character spawns on Riverbank
    assert eng._pending_new is not None           # undecided: Riverbank shown, run kept
    f.feed(LevelUp, 1150, "New", "Monk", 2)
    s = eng.snapshot()
    assert s.running and s.step_index == 0 and s.char_level == 2
    assert 140 <= s.run_time_s <= 160            # counted from the new Riverbank


def test_old_character_back_on_riverbank_keeps_run():
    eng, f, _ = make()
    f.zone("G1_1", 0, 1)
    f.feed(LevelUp, 60, "Old", "Monk", 4)
    for i, z in enumerate(("G1_town", "G1_2", "G1_3")):
        f.zone(z, 100 + i * 100)
    done = eng.snapshot().progress
    f.zone("G1_1", 500, 1)
    f.feed(LevelUp, 600, "Old", "Monk", 5)
    s = eng.snapshot()
    assert s.running and s.progress >= done and s.run_time_s > 550


def test_manual_pause_stops_timer():
    eng, f, clk = make()
    f.zone("G1_1", 0, 1)
    clk.t += 10
    before = eng.snapshot().run_time_s
    eng.toggle_pause()
    assert eng.snapshot().paused
    clk.t += 120                                  # paused for two minutes
    f.zone("G1_town", 130)                        # a log event while paused (e.g. a chat line)
    clk.t += 60
    assert abs(eng.snapshot().run_time_s - before) < 1.0
    eng.toggle_pause()
    clk.t += 30
    s = eng.snapshot()
    assert not s.paused and abs(s.run_time_s - (before + 30)) < 1.0


def test_focus_lost_pauses_timer():
    from pilot.contracts import FocusChanged
    eng, f, clk = make()
    f.zone("G1_1", 0, 1)
    f.feed(FocusChanged, 100, False)
    t_lost = eng.snapshot().run_time_s
    assert eng.snapshot().paused
    f.feed(FocusChanged, 400, True)               # 5 minutes alt-tabbed
    assert abs(eng.snapshot().run_time_s - t_lost) < 1.0
    f.zone("G1_2", 460)
    assert abs(eng.snapshot().run_time_s - (t_lost + 60)) <= 1.5


def test_new_character_restart_counts_its_riverbank():
    eng, f, _ = make()
    f.zone("G1_1", 0, 1)
    f.feed(LevelUp, 60, "Old", "Monk", 4)
    for i, z in enumerate(("G1_2", "G1_3", "G1_4")):
        f.zone(z, 100 + i * 100)
    f.zone("G1_1", 1000, 1)
    f.feed(LevelUp, 1150, "New", "Monk", 2)        # still in Riverbank
    s = eng.snapshot()
    assert s.step_index == 0 and eng.split_times() == {"a": 0.0}
    f.zone("G1_2", 1300)
    rec = eng.current_record()
    segs = {sg["area_id"]: sg for sg in rec.segments}
    assert 290 <= segs["G1_1"]["seconds"] <= 310     # Riverbank 1000..1300
    assert eng.snapshot().next_short != "→ a"        # Riverbank step is done, no stale reminder


def test_cancelled_tentative_run_forgets_passives():
    eng, f, _ = make()
    f.feed(LevelUp, 0, "Old", "Monk", 30)
    f.zone("G1_1", 10, 1)
    assert eng.allocated_nodes() == set()
    f.feed(LevelUp, 50, "Old", "Monk", 31)
    assert eng.allocated_nodes() is None


def test_heartbeat_keeps_long_zone_stay_counted():
    from pilot.contracts import Tick
    eng, f, _ = make()
    f.zone("G1_1", 0, 1)
    for k in range(1, 21):                          # 20 minutes, a log line every minute
        f.feed(Tick, 60 * k)
    f.zone("G1_2", 1260)
    assert eng.snapshot().run_time_s >= 1250


def test_loading_not_taken_back_when_it_was_not_counted():
    from pilot.contracts import FocusChanged
    eng, f, _ = make()
    f.zone("G1_1", 0, 1)
    f.feed(AreaGenerated, 100, "G1_2", 2, 1)         # load starts ...
    f.feed(FocusChanged, 101, False)                # ... player alt-tabs during it
    f.feed(FocusChanged, 124, True)
    t0 = eng.snapshot().run_time_s
    f.feed(LoadingScreen, 125, "G1_2", 25.0)         # load ends: only 1+1 s of it were counted
    assert eng.snapshot().run_time_s >= t0 - 2.0 - 1e-6
    assert eng.snapshot().run_time_s >= 99.0
