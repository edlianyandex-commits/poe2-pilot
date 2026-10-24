import time

from pilot.core.logwatch import LogWatcher, replay

L1 = "2025/12/12 22:00:00 1 a [INFO Client 1] one"
L2 = "2025/12/12 22:00:10 1 a [INFO Client 1] two"
L3 = "2025/12/12 22:01:10 1 a [INFO Client 1] три"


def _watcher(path, **kw):
    got = []
    return LogWatcher(path, got.append, **kw), got


def test_poll_partial_lines_and_utf8(tmp_path):
    p = tmp_path / "c.txt"
    p.write_bytes(b"")
    w, got = _watcher(p, from_end=False)
    data = (L3 + "\r\n").encode("utf-8")
    cut = len(data) - 9                       # split inside a multi-byte char and before newline
    p.write_bytes(data[:cut])
    w.poll_once()
    assert got == []
    with open(p, "ab") as f:
        f.write(data[cut:] + b"bad \xff byte\n")
    w.poll_once()
    assert got[0] == L3
    assert "�" in got[1]


def test_truncation_and_rotation(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text(L1 + "\n" + L2 + "\n", encoding="utf-8")
    w, got = _watcher(p, from_end=False)
    w.poll_once()
    assert got == [L1, L2]
    p.write_text("x\n", encoding="utf-8")           # truncated (smaller than pos)
    w.poll_once()
    assert got[-1] == "x"
    p.unlink()
    assert w.poll_once() == 0                         # missing file tolerated
    p.write_text("new1\nnew2\n", encoding="utf-8")    # recreated
    w.poll_once()
    assert got[-2:] == ["new1", "new2"]


def test_thread_from_end(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text(L1 + "\n", encoding="utf-8")
    w, got = _watcher(p, from_end=True, poll_interval=0.02)
    w.start()
    try:
        with open(p, "a", encoding="utf-8") as f:
            f.write(L2 + "\n")
        deadline = time.time() + 3
        while not got and time.time() < deadline:
            time.sleep(0.02)
    finally:
        w.stop()
    assert got == [L2]
    assert not w._thread


def test_thread_file_appears_later(tmp_path):
    p = tmp_path / "later.txt"
    w, got = _watcher(p, poll_interval=0.02)
    w.start()
    try:
        p.write_text(L1 + "\n", encoding="utf-8")
        deadline = time.time() + 3
        while not got and time.time() < deadline:
            time.sleep(0.02)
    finally:
        w.stop()
    assert got == [L1]


def test_replay_speed(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("\n".join([L1, L2, L3]) + "\n", encoding="utf-8")
    sleeps, got = [], []
    n = replay(p, got.append, speed=10.0, max_sleep_s=100, sleep=sleeps.append)
    assert n == 3 and got == [L1, L2, L3]
    assert sleeps == [1.0, 6.0]
    sleeps.clear()
    replay(p, lambda _l: None, speed=0, sleep=sleeps.append)
    assert sleeps == []
    replay(p, lambda _l: None, speed=1.0, max_sleep_s=2.0, sleep=sleeps.append)
    assert sleeps == [2.0, 2.0]
