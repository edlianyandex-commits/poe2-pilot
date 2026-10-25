import time

from pilot.assets import IconCache

URL = "https://cdn.poe2db.tw/image/Art/2DArt/SkillIcons/TwisterSkillIcon.webp"


def _wait(pred, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not pred():
        time.sleep(0.01)
    return pred()


def test_fetch_once_then_cached(tmp_path):
    calls = []
    cache = IconCache(tmp_path, fetch=lambda u: calls.append(u) or b"RIFF....WEBP")
    ready = []
    assert cache.get(URL, on_ready=lambda: ready.append(1)) is None   # first call: async fetch
    assert _wait(lambda: ready)
    path = cache.get(URL)
    assert path and path.endswith(".webp")
    assert calls == [URL]


def test_rejects_other_hosts_and_failures(tmp_path):
    cache = IconCache(tmp_path, fetch=lambda u: (_ for _ in ()).throw(OSError("down")))
    assert cache.get("https://evil.example/x.webp") is None
    assert cache.get(None) is None
    cache.get(URL)
    assert _wait(lambda: URL in cache._failed)
    assert cache.get(URL) is None                 # failed URLs are not retried in this session


def test_downloads_run_on_a_small_pool(tmp_path):
    import threading
    import pilot.assets as assets
    gate, live, peak = threading.Event(), [0], [0]
    lock = threading.Lock()

    def slow(url):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        gate.wait(2)
        with lock:
            live[0] -= 1
        return b"x"
    cache = IconCache(tmp_path, fetch=slow)
    for i in range(20):
        cache.get(f"https://cdn.poe2db.tw/image/i{i}.webp")
    time.sleep(0.2)
    gate.set()
    assert _wait(lambda: not cache._pending)
    assert peak[0] <= assets.WORKERS
