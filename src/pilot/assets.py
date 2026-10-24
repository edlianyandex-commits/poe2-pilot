"""Local cache for remote gem icons (lead-owned).

Icons are game art: they are never shipped with the project, only fetched on first use
into %APPDATA%/poe2-pilot/icons. Callers get a local path or None and draw a fallback.
"""
from __future__ import annotations

import hashlib
import threading
import urllib.request
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from pilot.config import config_dir

ALLOWED_HOSTS = {"cdn.poe2db.tw"}
MAX_BYTES = 512 * 1024
TIMEOUT_S = 8


class IconCache:
    def __init__(self, root: Path | None = None,
                 fetch: Callable[[str], bytes] | None = None):
        self.root = root or (config_dir() / "icons")
        self._fetch = fetch or _http_get
        self._lock = threading.Lock()
        self._pending: set[str] = set()
        self._failed: set[str] = set()

    def path_for(self, url: str) -> Path:
        suffix = Path(urlparse(url).path).suffix.lower() or ".img"
        return self.root / (hashlib.sha1(url.encode()).hexdigest()[:16] + suffix)

    def get(self, url: str | None, on_ready: Callable[[], None] | None = None) -> str | None:
        """Local path if cached; otherwise start a background fetch and return None."""
        if not url or urlparse(url).hostname not in ALLOWED_HOSTS:
            return None
        p = self.path_for(url)
        if p.is_file():
            return str(p)
        with self._lock:
            if url in self._pending or url in self._failed:
                return None
            self._pending.add(url)
        threading.Thread(target=self._download, args=(url, p, on_ready), daemon=True).start()
        return None

    def _download(self, url: str, p: Path, on_ready) -> None:
        try:
            data = self._fetch(url)
            if not data or len(data) > MAX_BYTES:
                raise ValueError("bad icon size")
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".part")
            tmp.write_bytes(data)
            tmp.replace(p)
        except Exception:
            with self._lock:
                self._failed.add(url)
        else:
            if on_ready:
                on_ready()
        finally:
            with self._lock:
                self._pending.discard(url)


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "poe2-pilot/0.1"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return r.read(MAX_BYTES + 1)
