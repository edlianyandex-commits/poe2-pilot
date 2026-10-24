"""Decode and parse Path of Building (PoE2) builds.

A PoB export code is ``urlsafe_base64(zlib(xml))``. We accept:
  * the export code itself (whitespace is ignored),
  * a path to a file containing the code,
  * a path to a raw PoB ``.xml`` build file,
  * raw XML text.

Input is untrusted: decompressed size is capped and DTD/entity declarations are rejected
before the XML reaches ``xml.etree``.
"""
from __future__ import annotations

import base64
import binascii
import re
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass, field
from pathlib import Path

MAX_XML_BYTES = 16 * 1024 * 1024


class PobDecodeError(ValueError):
    pass


@dataclass(frozen=True)
class GemEntry:
    name: str
    gem_id: str = ""
    variant_id: str = ""
    skill_id: str = ""
    level: int = 1
    enabled: bool = True


@dataclass
class SkillGroup:
    index: int                      # 1-based position in the skill set (PoB mainSocketGroup numbering)
    gems: list[GemEntry] = field(default_factory=list)
    enabled: bool = True
    label: str = ""
    source: str | None = None       # "Item:..." / "Tree:..." -> granted, not socketed by the player
    slot: str | None = None


@dataclass
class TreeSpec:
    title: str = ""
    tree_version: str = ""
    class_id: int | None = None
    ascend_class_id: int | None = None
    class_internal_id: int | None = None
    ascendancy_internal_id: str = ""
    nodes: list[int] = field(default_factory=list)
    weapon_sets: dict[int, list[int]] = field(default_factory=dict)
    attribute_choice: dict[int, str] = field(default_factory=dict)  # node -> "str" | "dex" | "int"


@dataclass
class PobBuild:
    class_name: str
    ascendancy_name: str | None
    level: int
    main_socket_group: int
    specs: list[TreeSpec]
    active_spec: int                # 0-based
    skill_groups: list[SkillGroup]
    target_version: str = ""

    def target_spec_index(self) -> int:
        """The spec we plan towards: the one with the most nodes (ties -> the active one).

        Leveling PoBs often carry several trees ("Act 1", "Act 3", "Endgame"); the active one is
        whatever the author last looked at, the biggest one is the final goal.
        """
        if not self.specs:
            raise PobDecodeError("build has no passive tree <Spec>")
        best = self.active_spec if 0 <= self.active_spec < len(self.specs) else 0
        for i, s in enumerate(self.specs):
            if len(s.nodes) > len(self.specs[best].nodes):
                best = i
        return best

    @property
    def spec(self) -> TreeSpec:
        return self.specs[self.target_spec_index()]

    @property
    def main_group(self) -> SkillGroup | None:
        for g in self.skill_groups:
            if g.index == self.main_socket_group:
                return g
        return None


# ----------------------------------------------------------------------------- decoding

def decode_pob_code(code: str) -> str:
    """PoB export code -> XML text."""
    s = re.sub(r"\s+", "", code)
    if not s:
        raise PobDecodeError("empty PoB code")
    s += "=" * (-len(s) % 4)
    try:
        raw = base64.urlsafe_b64decode(s.replace("+", "-").replace("/", "_"))
    except (binascii.Error, ValueError) as e:
        raise PobDecodeError(f"not base64: {e}") from None
    try:
        d = zlib.decompressobj()
        xml = d.decompress(raw, MAX_XML_BYTES)
        if d.unconsumed_tail:
            raise PobDecodeError("decompressed build is too large")
    except zlib.error as e:
        raise PobDecodeError(f"not zlib data: {e}") from None
    return xml.decode("utf-8", errors="replace")


def _read_source(source: str | Path) -> str:
    """Return XML text for code / code file / xml file / xml text."""
    if isinstance(source, Path) or (isinstance(source, str) and len(source) < 1024
                                     and not source.lstrip().startswith("<")):
        p = Path(source)
        try:
            is_file = p.is_file()
        except OSError:
            is_file = False
        if is_file:
            if p.stat().st_size > MAX_XML_BYTES:
                raise PobDecodeError("file too large")
            text = p.read_text(encoding="utf-8-sig", errors="replace")
            return text if text.lstrip().startswith("<") else decode_pob_code(text)
        if isinstance(source, Path):
            raise PobDecodeError(f"no such file: {source}")
    text = str(source)
    if text.lstrip().startswith("<"):
        return text
    return decode_pob_code(text)


# ----------------------------------------------------------------------------- parsing

def _int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _ids(csv: str | None) -> list[int]:
    out = []
    for part in (csv or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def _parse_spec(el: ET.Element) -> TreeSpec:
    spec = TreeSpec(
        title=el.get("title", "") or "",
        tree_version=el.get("treeVersion", "") or "",
        class_id=_int(el.get("classId")),
        ascend_class_id=_int(el.get("ascendClassId")),
        class_internal_id=_int(el.get("classInternalId")),
        ascendancy_internal_id=el.get("ascendancyInternalId", "") or "",
        nodes=_ids(el.get("nodes")),
    )
    for child in el:
        m = re.fullmatch(r"WeaponSet(\d+)", child.tag)
        if m:
            spec.weapon_sets[int(m.group(1))] = _ids(child.get("nodes"))
    for ov in el.iter("AttributeOverride"):
        for key, attr in (("strNodes", "str"), ("dexNodes", "dex"), ("intNodes", "int")):
            for nid in _ids(ov.get(key)):
                spec.attribute_choice[nid] = attr
    return spec


def _parse_skills(root: ET.Element) -> list[SkillGroup]:
    skills = root.find("Skills")
    if skills is None:
        return []
    sets = skills.findall("SkillSet")
    container = skills
    if sets:
        active = skills.get("activeSkillSet", "1")
        container = next((s for s in sets if s.get("id") == active), sets[0])
    groups = []
    for i, sk in enumerate(container.findall("Skill"), 1):
        g = SkillGroup(index=i, enabled=sk.get("enabled", "true") != "false",
                       label=sk.get("label", "") or "", source=sk.get("source"), slot=sk.get("slot"))
        for gem in sk.findall("Gem"):
            name = gem.get("nameSpec") or gem.get("skillId") or ""
            if not name:
                continue
            g.gems.append(GemEntry(
                name=name,
                gem_id=gem.get("gemId", "") or "",
                variant_id=gem.get("variantId", "") or "",
                skill_id=gem.get("skillId", "") or "",
                level=_int(gem.get("level"), 1) or 1,
                enabled=gem.get("enabled", "true") != "false",
            ))
        groups.append(g)
    return groups


def parse_pob_xml(xml_text: str) -> PobBuild:
    if len(xml_text) > MAX_XML_BYTES:
        raise PobDecodeError("build XML too large")
    if re.search(r"<!(DOCTYPE|ENTITY)", xml_text, re.I):
        raise PobDecodeError("DTD/entities are not allowed in PoB XML")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise PobDecodeError(f"bad XML: {e}") from None
    if root.tag != "PathOfBuilding2" and root.find("Build") is None:
        raise PobDecodeError(f"not a PoB build (root <{root.tag}>)")
    b = root.find("Build")
    if b is None:
        raise PobDecodeError("missing <Build>")
    asc = b.get("ascendClassName")
    tree = root.find("Tree")
    specs = [_parse_spec(s) for s in tree.findall("Spec")] if tree is not None else []
    active = (_int(tree.get("activeSpec"), 1) or 1) - 1 if tree is not None else 0
    return PobBuild(
        class_name=b.get("className", "") or "",
        ascendancy_name=None if asc in (None, "", "None", "nil") else asc,
        level=_int(b.get("level"), 1) or 1,
        main_socket_group=_int(b.get("mainSocketGroup"), 1) or 1,
        specs=specs,
        active_spec=active,
        skill_groups=_parse_skills(root),
        target_version=b.get("targetVersion", "") or "",
    )


def load_pob(source: str | Path) -> PobBuild:
    """Parse a PoB export code, a file containing one, or a raw XML file/text."""
    return parse_pob_xml(_read_source(source))
