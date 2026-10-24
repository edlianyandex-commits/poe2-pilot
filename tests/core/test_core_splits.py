from pilot.core.splits import RunRecord, SplitStore


def _rec(status, total, **splits):
    return RunRecord("r", status, "2025-12-12T22:10:21", total, dict(splits))


def test_pb_and_delta(tmp_path):
    s = SplitStore(tmp_path)
    assert s.pb_split("r", "a") is None and s.delta("r", "a", 10) is None
    s.save_run(_rec("finished", 200, a=50, b=200))
    s.save_run(_rec("finished", 220, a=40, b=220))
    assert s.pb_split("r", "a") == 40 and s.pb_split("r", "b") == 200
    assert s.pb_total("r") == 200
    assert s.delta("r", "a", 45) == 5
    assert s.delta("r", "a", 30) == -10


def test_abandoned_does_not_set_pb_but_is_saved(tmp_path):
    s = SplitStore(tmp_path)
    s.save_run(_rec("abandoned", 10, a=5))
    assert s.pb_split("r", "a") is None
    assert [r.status for r in s.list_runs("r")] == ["abandoned"]


def test_persistence_and_same_second_collision(tmp_path):
    s = SplitStore(tmp_path)
    s.save_run(_rec("finished", 100, a=10))
    s.save_run(_rec("finished", 90, a=9))
    s2 = SplitStore(tmp_path)
    assert s2.pb_split("r", "a") == 9 and len(s2.list_runs()) == 2


def test_corrupt_pb_file(tmp_path):
    (tmp_path / "pb.json").write_text("garbage", encoding="utf-8")
    assert SplitStore(tmp_path).pb_total("r") is None
