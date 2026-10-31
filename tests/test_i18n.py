"""English UI: every text passed to tr() has its English, and the switch works."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from pilot import i18n
from pilot.i18n_en import EN

SRC = Path(__file__).resolve().parents[1] / "src" / "pilot"
CYR = re.compile(r"[А-Яа-яЁё]")


def tr_literals() -> set[str]:
    found = set()
    for f in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.add(node.args[0].value)
    return found


def tables() -> set[str]:
    """Texts that reach tr() through a table instead of a literal."""
    from pilot.launcher import help, style
    from pilot.overlay import gems_window, tree_window
    from pilot.planner import plan
    out = set(help.ACTIONS.values()) | set(help.TIPS)
    out |= {v[2] for v in style.RARITY.values()} | {style.OUTDATED[2]}
    out |= set(gems_window.KIND_LABEL.values()) | set(tree_window.KIND_LABEL.values())
    out |= set(plan.ATTR_RU.values()) | {"+5 Атрибут"}
    return out


def test_every_text_has_english():
    missing = sorted((tr_literals() | tables()) - EN.keys())
    assert not missing, missing


def test_english_has_no_russian_and_keeps_placeholders():
    for ru, en in EN.items():
        assert not CYR.search(en), en
        assert re.findall(r"{\w+}", ru) == re.findall(r"{\w+}", en), ru


def test_switch_and_pick():
    i18n.set_lang("en")
    assert i18n.tr("Ур. {level}", level=5) == "Lv 5"
    assert i18n.tr("не в словаре") == "не в словаре"
    assert i18n.pick({"note": "ру", "note_en": "en"}, "note") == "en"
    assert i18n.pick({"note": "ру", "note_en": ""}, "note") == "ру"
    i18n.set_lang("ru")
    assert i18n.tr("Ур. {level}", level=5) == "Ур. 5"
    assert i18n.pick({"note": "ру", "note_en": "en"}, "note") == "ру"
    assert i18n.set_lang("auto") in i18n.LANGS


def test_builds_have_english_hints():
    import json
    root = SRC.parents[1] / "builds"
    for f in root.glob("*.gear.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        for sec in ("gear", "zones"):
            ru = {k: v for k, v in d.get(sec, {}).items() if not k.startswith("_")}
            en = d.get(f"{sec}_en", {})
            assert en.keys() == ru.keys(), (f.name, sec)
            assert not CYR.search(json.dumps(en, ensure_ascii=False)), (f.name, sec)
    cat = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    for b in cat["builds"]:
        assert b.get("note_en") and not CYR.search(b["note_en"]), b["code"]


def test_english_plan_and_route():
    from pilot.catalog import load_catalog
    from pilot.core.route import load_route
    from pilot.planner import build_plan
    root = SRC.parents[1]
    i18n.set_lang("en")
    route = load_route(root / "data" / "routes" / "campaign-0.5.json")
    assert not CYR.search(route.title)
    assert not [s.short for s in route.steps if CYR.search(s.short + s.detail)]
    plan = build_plan(root / "builds" / "grenades_gemling_0_5_5.build")
    lines = [g for h in plan.hints.values() for g in h.gear]
    assert "Crossbow is top priority" in lines and not [g for g in lines if CYR.search(g)]
    e = load_catalog(root / "builds").find("grenades_gemling_0_5_5.build")
    assert e.musts == ("Trial of the Sekhemas", "The Azak Bog") and e.note.startswith("Grenades")
