from __future__ import annotations

import base64
import zlib

import pytest

from pilot.planner.pobcode import PobDecodeError, decode_pob_code, load_pob, parse_pob_xml

from planner_helpers import AMAZON, GEMLING


def test_decode_real_code():
    xml = decode_pob_code(AMAZON.read_text())
    assert "<PathOfBuilding2>" in xml
    b = parse_pob_xml(xml)
    assert b.class_name == "Huntress"
    assert b.ascendancy_name == "Amazon"
    assert b.level == 52
    assert b.spec.tree_version == "0_5"
    assert len(b.spec.nodes) == 73
    assert b.spec.attribute_choice  # AttributeOverride parsed
    assert len(b.skill_groups) == 8
    assert b.main_group is not None and b.main_group.gems[0].name == "Shred"
    names = [g.name for grp in b.skill_groups for g in grp.gems]
    assert "Herald of Ice" in names and "Ice Bite II" in names


def test_load_accepts_code_file_xml_file_and_text(tmp_path):
    code = GEMLING.read_text()
    a = load_pob(code)
    b = load_pob(GEMLING)            # Path to file with code
    c = load_pob(str(GEMLING))       # str path
    xml = decode_pob_code(code)
    p = tmp_path / "build.xml"
    p.write_text(xml, encoding="utf-8")
    d = load_pob(p)
    e = load_pob(xml)
    for x in (b, c, d, e):
        assert x.class_name == a.class_name == "Mercenary"
        assert x.ascendancy_name == "Gemling Legionnaire"
        assert x.spec.nodes == a.spec.nodes
    # granted skills (from items / tree) are flagged with a source
    assert any(g.source for g in a.skill_groups)


def test_whitespace_and_std_base64_tolerated():
    code = AMAZON.read_text().strip()
    wrapped = "\n".join(code[i:i + 76] for i in range(0, len(code), 76))
    assert load_pob(wrapped).class_name == "Huntress"
    std = code.replace("-", "+").replace("_", "/")
    assert load_pob(std).class_name == "Huntress"


@pytest.mark.parametrize("bad", ["", "!!!!", base64.urlsafe_b64encode(b"not zlib").decode()])
def test_garbage_rejected(bad):
    with pytest.raises(PobDecodeError):
        load_pob(bad)


def test_dtd_rejected():
    xml = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><PathOfBuilding2><Build/></PathOfBuilding2>'
    with pytest.raises(PobDecodeError):
        parse_pob_xml(xml)


def test_not_a_build_rejected():
    code = base64.urlsafe_b64encode(zlib.compress(b"<Foo/>")).decode()
    with pytest.raises(PobDecodeError):
        load_pob(code)
