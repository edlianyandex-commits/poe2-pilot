"""Write content.json: sha256 of every file under data/ and builds/, for the in-app update.

usage: python tools/make_content_manifest.py [--min-app 1.0.0]
Run after changing any build or data file, then commit content.json with it (a test checks it).
The version is today's date; a second change on the same day adds .2, .3, ...
--min-app: content that only a newer app can read (e.g. a new build format); older apps skip it
and point to the release page instead. Kept from the previous manifest when not given.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRS = ("data", "builds")


def scan(root: Path = ROOT) -> dict[str, str]:
    files = {}
    for d in DIRS:
        for p in sorted((root / d).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                files[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return files


def next_version(prev: str | None, today: datetime.date) -> str:
    day = f"{today.year}.{today.month}.{today.day}"
    if not prev or not prev.startswith(day):
        return day
    n = prev[len(day) + 1:] or "1"
    return f"{day}.{int(n) + 1}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-app")
    args = ap.parse_args()
    path = ROOT / "content.json"
    prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    files = scan()
    if files == prev.get("files") and not args.min_app:
        print(f"unchanged: {prev['version']}")
        return 0
    out = {"version": next_version(prev.get("version"), datetime.date.today()),
           "min_app": args.min_app or prev.get("min_app", "0.9.0"),
           "files": files}
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"content {out['version']}: {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
