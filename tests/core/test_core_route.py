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
