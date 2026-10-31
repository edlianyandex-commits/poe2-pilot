"""Catalog, content manifest, content root and the GitHub update (with a fake fetch, no network)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pilot import __version__, paths, updates  # noqa: E402
from pilot.catalog import STATUSES, load_catalog  # noqa: E402


def test_catalog_lists_every_build_once():
    cat = load_catalog(ROOT / "builds")
    assert len(cat.entries) == 10
    assert len({e.code for e in cat.entries}) == len(cat.entries)
    assert len({e.file for e in cat.entries}) == len(cat.entries)
    assert all(e.status in STATUSES and e.skills and e.patch for e in cat.entries)
    assert cat.route == "campaign-0.5" and cat.start and cat.finish


def test_catalog_reads_required_steps_from_the_sidecar():
    e = load_catalog(ROOT / "builds").find("grenades_gemling_0_5_5.build")
    assert e.musts == ("Испытание Сехем", "Болото Азак")
    assert e.role == "Gemling Legionnaire"


def test_builds_for_an_older_patch_wait_for_an_update(tmp_path):
    raw = json.loads((ROOT / "builds" / "catalog.json").read_text(encoding="utf-8"))
    raw["game"] = "1.0"
    raw["builds"] = raw["builds"][:1]
    (tmp_path / "catalog.json").write_text(json.dumps(raw), encoding="utf-8")
    (tmp_path / raw["builds"][0]["file"]).write_bytes(b"x")
    assert load_catalog(tmp_path).entries[0].outdated
    raw["builds"][0]["patch"] = "1.0.2"
    (tmp_path / "catalog.json").write_text(json.dumps(raw), encoding="utf-8")
    assert not load_catalog(tmp_path).entries[0].outdated


def test_content_manifest_is_up_to_date():
    from make_content_manifest import scan
    manifest = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
    assert manifest["files"] == scan(ROOT), "run: python tools/make_content_manifest.py"


def test_manifest_version_counts_up_within_a_day():
    import datetime
    from make_content_manifest import next_version
    d = datetime.date(2026, 11, 2)
    assert next_version(None, d) == "2026.11.2"
    assert next_version("2026.11.1", d) == "2026.11.2"
    assert next_version("2026.11.2", d) == "2026.11.2.2"
    assert next_version("2026.11.2.2", d) == "2026.11.2.3"


def test_newer_downloaded_content_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    user = paths.user_content()
    user.mkdir(parents=True)
    (user / "content.json").write_text('{"version": "2000.1.1"}', encoding="utf-8")
    assert paths.content_root() == paths.root()
    (user / "content.json").write_text('{"version": "9999.1.1"}', encoding="utf-8")
    assert paths.content_root() == user


# ---------------------------------------------------------------- updates
def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _fake(files: dict[str, bytes], manifest: dict, release: str | None = None):
    def get(url: str) -> bytes:
        if url.endswith("/releases/latest"):
            if release is None:
                raise OSError("404")
            return json.dumps({"tag_name": release, "html_url": "https://example/rel"}).encode()
        if url.endswith("/content.json"):
            return json.dumps(manifest).encode()
        return files[url.split("/main/", 1)[1]]
    return get


def test_check_reports_newer_content_and_release():
    m = {"version": "9999.1.1", "min_app": "0.1.0", "files": {}}
    res = updates.check("o/r", _fake({}, m, release="v99.0.0"))
    assert res.content == m and res.needs_app is None
    assert res.app_version == "99.0.0" and res.app_url == "https://example/rel"


def test_check_holds_content_that_needs_a_newer_app():
    m = {"version": "9999.1.1", "min_app": "99.0", "files": {}}
    res = updates.check("o/r", _fake({}, m))
    assert res.content is None and res.needs_app == "99.0" and res.app_version is None


def test_check_ignores_older_content():
    res = updates.check("o/r", _fake({}, {"version": "2000.1.1", "files": {}}, release=f"v{__version__}"))
    assert res.content is None and res.app_version is None


def test_apply_downloads_only_changed_files_and_swaps(tmp_path):
    current = tmp_path / "bundled"
    (current / "builds").mkdir(parents=True)
    (current / "builds" / "a.build").write_bytes(b"old-a")
    (current / "builds" / "same.build").write_bytes(b"same")
    new = {"builds/a.build": b"new-a", "builds/same.build": b"same", "data/routes/r.json": b"{}"}
    m = {"version": "9999.1.1", "files": {k: _sha(v) for k, v in new.items()}}
    asked = []

    def get(url):
        asked.append(url)
        return _fake(new, m)(url)
    dest = tmp_path / "content"
    dest.mkdir()
    (dest / "stale.txt").write_text("x")
    assert updates.apply(m, "o/r", get, dest=dest, current=current) == 2
    assert len(asked) == 2 and not any("same.build" in u for u in asked)
    assert (dest / "builds" / "a.build").read_bytes() == b"new-a"
    assert (dest / "builds" / "same.build").read_bytes() == b"same"
    assert json.loads((dest / "content.json").read_text(encoding="utf-8"))["version"] == "9999.1.1"
    assert not (dest / "stale.txt").exists()


def test_apply_rejects_bad_hashes_and_paths(tmp_path):
    m = {"version": "9999.1.1", "files": {"builds/a.build": _sha(b"good")}}
    with pytest.raises(ValueError, match="hash"):
        updates.apply(m, "o/r", _fake({"builds/a.build": b"evil"}, m), dest=tmp_path / "c",
                      current=tmp_path)
    assert not (tmp_path / "c").exists()
    for bad in ("../x", "src/pilot/app.py", "/etc/x"):
        with pytest.raises(ValueError, match="path"):
            updates.apply({"version": "1", "files": {bad: "0"}}, "o/r", _fake({}, {}),
                          dest=tmp_path / "c", current=tmp_path)
