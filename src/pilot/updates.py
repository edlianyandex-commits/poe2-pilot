"""In-app updates from GitHub: new builds and game data (content), and news of a new app release.

Content = every file under data/ and builds/, listed with its sha256 in content.json at the repo
root (written by tools/make_content_manifest.py). An update downloads only the files whose hash
changed, verifies each one, and swaps %APPDATA%/poe2-pilot/content in whole; pilot.paths picks it
up on the next start. Code never comes this way: a new exe is a GitHub release the user downloads.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from pilot import __version__
from pilot.paths import CONTENT, MANIFEST, read_manifest, user_content, version_key

REPO = "edlianyandex-commits/poe2-pilot"
BRANCH = "main"
TIMEOUT_S = 6

Fetch = Callable[[str], bytes]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"poe2-pilot/{__version__}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return r.read()


def raw_url(repo: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{BRANCH}/{path}"


@dataclass(frozen=True)
class Check:
    content: dict | None = None     # remote manifest, when it is newer and this app can use it
    needs_app: str | None = None    # remote content wants at least this app version
    app_version: str | None = None  # newer release tag, e.g. "1.0.1"
    app_url: str | None = None


def check(repo: str = REPO, get: Fetch = fetch) -> Check:
    """Raises OSError / ValueError when GitHub can't be reached or answers nonsense."""
    remote = json.loads(get(raw_url(repo, MANIFEST)))
    local = read_manifest(CONTENT) or {}
    content = needs = None
    if version_key(remote.get("version")) > version_key(local.get("version")):
        if version_key(remote.get("min_app")) > version_key(__version__):
            needs = remote["min_app"]
        else:
            content = remote
    app = url = None
    try:
        rel = json.loads(get(f"https://api.github.com/repos/{repo}/releases/latest"))
        tag = str(rel.get("tag_name", "")).lstrip("v")
        if version_key(tag) > version_key(__version__):
            app, url = tag, rel.get("html_url")
    except (OSError, ValueError):
        pass                        # no release yet is fine; content still counts
    return Check(content, needs, app, url)


def _safe(rel: str) -> PurePosixPath:
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts or p.parts[:1] not in (("data",), ("builds",)):
        raise ValueError(f"unexpected path in manifest: {rel}")
    return p


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply(remote: dict, repo: str = REPO, get: Fetch = fetch, dest: Path | None = None,
          current: Path = CONTENT) -> int:
    """Build the new content next to `dest`, then swap it in. -> number of files downloaded."""
    dest = dest or user_content()
    stage = dest.with_name(dest.name + ".new")
    shutil.rmtree(stage, ignore_errors=True)
    fetched = 0
    for rel, sha in remote["files"].items():
        p = _safe(rel)
        have = current / p
        data = have.read_bytes() if have.is_file() else b""
        if _sha(data) != sha:
            data = get(raw_url(repo, rel))
            fetched += 1
            if _sha(data) != sha:
                shutil.rmtree(stage, ignore_errors=True)
                raise ValueError(f"hash mismatch: {rel}")
        out = stage / p
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    (stage / MANIFEST).write_text(json.dumps(remote, ensure_ascii=False, indent=1), encoding="utf-8")
    old = dest.with_name(dest.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if dest.exists():
        dest.rename(old)
    stage.rename(dest)
    shutil.rmtree(old, ignore_errors=True)
    return fetched


class Updater:
    """What the start window calls (on a worker thread)."""

    def __init__(self, repo: str = REPO):
        self.repo = repo

    def check(self) -> Check:
        return check(self.repo)

    def apply(self, remote: dict) -> int:
        return apply(remote, self.repo)

    def releases_url(self) -> str:
        return f"https://github.com/{self.repo}/releases/latest"
