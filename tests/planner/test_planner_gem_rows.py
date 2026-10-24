"""Gem window data: GemCard/GemRow per level, card data, Barrage timing on the Travic build."""
from __future__ import annotations

import json

from pilot.contracts import GemCard, GemRow
from pilot.planner import build_plan, data, load_pob
from pilot.planner.plan import earliest_level, gem_info
from pilot.planner.pobcode import GemEntry

from planner_helpers import FIX, ROOT

SPEED = FIX / "twister_speed_campaign_0_5_5.pob"
BUILDS = sorted((ROOT / "builds").glob("*.pob"))


def _names(line: str) -> tuple[str, list[str]]:
    skill, _, rest = line.partition(": ")
    return skill, [x for x in rest.split(", ") if x] if rest else []


def test_gem_rows_match_setups():
    p = build_plan(SPEED)
    assert p.gem_rows and set(p.gem_rows) == set(p.setups)
    for lvl, rows in p.gem_rows.items():
        lines = p.setups[lvl]
        assert len(rows) == len(lines)
        for row, line in zip(rows, lines):
            assert isinstance(row, GemRow) and isinstance(row.skill, GemCard)
            skill, sups = _names(line)
            assert row.skill.name == skill
            shown = [s for s in sups if not s.startswith("+")]
            assert [c.name for c in row.supports[: len(shown)]] == shown   # setups may "+N"-clip
            extra = [s for s in sups if s.startswith("+")]
            if extra:
                assert len(row.supports) == len(shown) + int(extra[0][1:])
            else:
                assert len(row.supports) == len(shown)
    assert p.gem_rows_for(1) == p.gem_rows[1]
    assert p.gem_rows_for(29) == p.gem_rows_for(15)


def test_rows_main_first_and_cards_complete():
    p = build_plan(SPEED)
    assert p.gem_rows_for(1)[0].skill.name == "Twister"
    gems = {r["n"] for r in data.gems_data().values()}
    for rows in p.gem_rows.values():
        for row in rows:
            assert row.skill.kind in ("skill", "spirit")
            for card in (row.skill, *row.supports):
                assert card.kind in ("skill", "support", "spirit")
                assert card.color in ("str", "dex", "int", "none")
                assert card.name in gems                  # exact English game name
                assert len(card.description) <= 400
                assert card.icon_url is None or card.icon_url.startswith("https://cdn.poe2db.tw/")
            assert all(s.kind == "support" for s in row.supports)
    final = p.gem_rows_for(100)
    twister = next(r for r in final if r.skill.name == "Twister")
    assert {s.name for s in twister.supports} == {"Armour Break III", "Projectile Acceleration III",
                                                  "Prolonged Duration II", "Salvo"}
    assert twister.skill.description.startswith("Whip up a twister")
    assert twister.skill.color == "dex"


def test_icon_coverage_for_bundled_builds():
    names, with_icon = set(), set()
    for f in BUILDS:
        for g in load_pob(f).skill_groups:
            for e in g.gems:
                inf = gem_info(e)
                names.add(inf.name)
                if inf.icon:
                    assert inf.icon.startswith("https://cdn.poe2db.tw/image/")
                    with_icon.add(inf.name)
    assert names and len(with_icon) / len(names) >= 0.95


def test_gem_icon_map_file():
    doc = json.loads((data.data_dir() / "gem_icons.json").read_text(encoding="utf-8"))
    assert doc["_source"] and doc["_note"]
    icons = doc["icons"]
    assert len(icons) > 500
    assert all(u.startswith("https://cdn.poe2db.tw/image/") and u.endswith(".webp") for u in icons.values())
    assert icons["Salvo"].endswith("/Support/SalvoSupport.webp")


def test_extracted_card_fields():
    g = data.gems_data()
    assert all(r.get("c") in ("str", "dex", "int", "none") for r in g.values())
    assert sum(1 for r in g.values() if r.get("d")) > 0.9 * len(g)
    assert all(len(r.get("d", "")) <= 400 for r in g.values())


def test_barrage_and_early_skill_timing():
    """Barrage is Tier 5: engraved from a level-5 uncut gem (Executioner, Ogham Village, area 13),
    the gem is level 5 and needs character level 14."""
    req = data.gem_rules()["skill_level_requirement"]
    barrage = gem_info(GemEntry("Barrage"))
    assert barrage.tier == 5 and earliest_level(barrage) == req[4] == 14
    for name in ("Twister", "Whirling Slash"):
        assert earliest_level(gem_info(GemEntry(name))) == 1
    salvo = gem_info(GemEntry("Salvo"))
    assert salvo.kind == "support" and salvo.tier == 3
    p = build_plan(SPEED)
    assert not any(r.skill.name == "Barrage" for r in p.gem_rows_for(13))
    assert any(r.skill.name == "Barrage" for r in p.gem_rows_for(14))
    salvo_lvl = min(lvl for lvl, rows in p.gem_rows.items()
                    if any(s.name == "Salvo" for r in rows for s in r.supports))
    assert salvo_lvl == max(earliest_level(salvo), 1)
