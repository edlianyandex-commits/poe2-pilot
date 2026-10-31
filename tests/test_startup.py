"""Start-up chores: one copy at a time, the previous log kept, Client.txt found or asked for."""
from __future__ import annotations

from pilot.startup import instance_lock, resolve_log, rotate_log


def test_a_second_copy_does_not_get_the_lock(tmp_path):
    first = instance_lock(tmp_path / "pilot.lock")
    assert first is not None
    assert instance_lock(tmp_path / "pilot.lock") is None
    first.unlock()
    again = instance_lock(tmp_path / "pilot.lock")
    assert again is not None
    again.unlock()


def test_the_previous_log_is_kept(tmp_path):
    log = tmp_path / "pilot.log"
    rotate_log(log)                                    # nothing yet: nothing to keep
    assert not (tmp_path / "pilot.prev.log").exists()
    log.write_text("crash here")
    rotate_log(log)
    assert (tmp_path / "pilot.prev.log").read_text() == "crash here" and not log.exists()


def test_client_log_order_and_asking(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("")
    b.write_text("")
    never = lambda: (_ for _ in ()).throw(AssertionError("asked"))   # noqa: E731
    assert resolve_log(str(a), {"log_path": str(b)}, lambda: None, never) == a
    assert resolve_log(None, {"log_path": str(b)}, lambda: str(a), never) == b
    assert resolve_log(None, {"log_path": str(tmp_path / "gone.txt")}, lambda: str(a), never) == a
    cfg = {}
    assert resolve_log(None, cfg, lambda: None, lambda: str(b)) == b and cfg["log_path"] == str(b)
    cfg = {}
    assert resolve_log(None, cfg, lambda: None, lambda: None) is None and "log_path" not in cfg
