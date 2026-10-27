import json

import pytest

from pilot.core.route import RouteError, load_route


def _step(**kw):
    base = {"id": "s1", "act": 1, "area": "G1_1", "short": "→ Ривер", "kind": "move"}
    base.update(kw)
    return base


def _write(tmp_path, steps, **top):
    data = {"id": "r", "steps": steps}
    data.update(top)
    p = tmp_path / "r.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_valid_route(tmp_path):
    p = _write(tmp_path, [
        _step(detail="d", split=True, reward="Gem", done_on={"enter": "G1_town"}, _note="ignored"),
        _step(id="s2", act=101, area="P1_1", kind="boss"),
    ], title="T", patch="0.5", _comment="x")
    r = load_route(p)
    assert r.id == "r" and r.title == "T" and len(r.steps) == 2
    assert r.steps[0].split and r.steps[0].done_on_enter == "G1_town"
    assert r.steps[1].act == 101 and r.steps[1].done_on_enter is None


def test_lists_all_violations(tmp_path):
    p = _write(tmp_path, [
        _step(short="x" * 41),
        _step(detail="d" * 121, reward="r" * 33),          # duplicate id too
        _step(id="s3", kind="nope"),
        _step(id="s4", act=7),
        _step(id="s5", bogus=1),
    ])
    with pytest.raises(RouteError) as ei:
        load_route(p)
    msg = str(ei.value)
    for needle in ("short is 41", "detail is 121", "reward is 33", "duplicate id", "kind 'nope'", "act must", "unknown key 'bogus'"):
        assert needle in msg
    assert len(ei.value.violations) >= 7


def test_bad_file(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(RouteError):
        load_route(p)
    with pytest.raises(RouteError):
        load_route(tmp_path / "missing.json")


def test_empty_steps(tmp_path):
    with pytest.raises(RouteError):
        load_route(_write(tmp_path, []))


def test_optional_boss_does_not_lead_its_zone():
    from pilot.core.route import parse_route
    r = parse_route({"id": "x", "title": "t", "steps": [
        {"id": "a", "act": 1, "area": "G1_3", "short": "◆ WP", "kind": "wp"},
        {"id": "b", "act": 1, "area": "G1_3", "short": "⚔ The Devourer", "kind": "boss", "optional": True},
        {"id": "c", "act": 1, "area": "G1_4", "short": "⚔ Brambleghast", "kind": "boss"},
        {"id": "d", "act": 1, "area": "G1_5", "short": "⚔ Optional only", "kind": "boss", "optional": True},
    ]})
    kinds = [s.display_kind for s in r.steps]
    assert kinds == ["wp", "boss", "boss_opt"]       # wp leads G1_3; must-kill keeps "boss"


def test_require_steps_makes_optional_and_skipped_steps_due():
    from pilot.core.route import Route, Step, require_steps
    r = Route("r", "T", (
        Step("t", 2, "G2_13", "✦ Trial", "trial", optional=True, merged_ids=("t",)),
        Step("s", 3, "G3_7", "✕ Bog", "skip", merged_ids=("s",)),
        Step("x", 3, "G3_8", "✕ Other", "skip", merged_ids=("x",)),
    ))
    out = require_steps(r, ("t", "s"))
    t, s, x = out.steps
    assert not t.optional and not t.skippable and t.kind == "trial"
    assert s.kind == "quest" and s.short == "! Bog" and not s.skippable
    assert x == r.steps[2]
    assert require_steps(r, ()) is r
