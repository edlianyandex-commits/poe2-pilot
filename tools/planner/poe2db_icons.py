"""Build data/planner/gem_icons.json (gem name -> icon URL) from saved poe2db listing pages.

The pages are fetched separately (e.g. with curl) into a scratch folder and only *parsed* here:

    curl -sL -A "Mozilla/5.0" -o <dir>/Support_Gems.html https://poe2db.tw/us/Support_Gems
    curl -sL -A "Mozilla/5.0" -o <dir>/Skill_Gems.html   https://poe2db.tw/us/Skill_Gems
    curl -sL -A "Mozilla/5.0" -o <dir>/Spirit_Gems.html  https://poe2db.tw/us/Spirit_Gems
    python -I tools/planner/poe2db_icons.py <dir> --out data/planner/gem_icons.json

Only the mapping is stored; images are not downloaded.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

CDN = "https://cdn.poe2db.tw/image/"
# <a ... href="/us/Salvo"><img ... src="https://cdn.poe2db.tw/image/Art/.../SalvoSupport.webp" ...></a>
#   ... followed shortly by <a ...>Salvo</a> (display name)
_LINK_IMG = re.compile(
    r'<a[^>]*href="/us/([^"#?]+)"[^>]*>\s*<img[^>]*src="(https://cdn\.poe2db\.tw/image/[^"]+\.webp)"',
    re.I)
_NAMED_LINK = re.compile(r'<a[^>]*href="/us/([^"#?]+)"[^>]*>([^<]{2,60})</a>', re.I)

PAGES = ("Support_Gems", "Skill_Gems", "Spirit_Gems")


def parse_page(text: str) -> dict[str, str]:
    """display name -> icon URL, joined through the poe2db page slug."""
    slug_icon: dict[str, str] = {}
    for slug, url in _LINK_IMG.findall(text):
        if "/SkillIcons/" in url or "/Gems/" in url:
            slug_icon.setdefault(slug, url)
    out: dict[str, str] = {}
    for slug, name in _NAMED_LINK.findall(text):
        name = html.unescape(name).strip()
        if slug in slug_icon and name and not name.startswith("http"):
            out.setdefault(name, slug_icon[slug])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pages_dir", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/planner/gem_icons.json"))
    a = ap.parse_args(argv)
    icons: dict[str, str] = {}
    used = []
    for page in PAGES:
        p = a.pages_dir / f"{page}.html"
        if not p.is_file():
            continue
        used.append(f"https://poe2db.tw/us/{page}")
        for name, url in parse_page(p.read_text(encoding="utf-8", errors="replace")).items():
            icons.setdefault(name, url)
    doc = {
        "_source": used,
        "_note": ("Gem name -> icon URL on cdn.poe2db.tw, parsed from poe2db listing pages "
                  f"on {date.today().isoformat()}. Used for supports (PoB has no support icons) and "
                  "skills whose PoB icon is missing. Images are fetched by the app, not stored here."),
        "icons": dict(sorted(icons.items())),
    }
    a.out.write_text(json.dumps(doc, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(icons)} icons -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
