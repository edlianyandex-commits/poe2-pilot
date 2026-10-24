from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).resolve().parent / "fixtures"
AMAZON = FIX / "amazon_leveling_0_5.pob"
GEMLING = FIX / "gemling_endgame_0_5.pob"
CAMPAIGN_LOG = ROOT / "tests" / "fixtures" / "campaign_ru.log"

ALLOC_RE = re.compile(r"Successfully (un)?allocated passive skill id: ([^,]+), name: (.*)")


def log_allocations() -> list[tuple[bool, str]]:
    """(allocated?, string id) in log order from the real ru campaign log."""
    out = []
    for line in CAMPAIGN_LOG.read_text(encoding="utf-8").splitlines():
        m = ALLOC_RE.search(line)
        if m:
            out.append((m.group(1) is None, m.group(2)))
    return out


def make_xml(class_name: str, asc_name: str | None, nodes: list[int], groups: list[list[str]],
             extra_specs: list[list[int]] = (), main_group: int = 1) -> str:
    """Minimal PoB2 XML for synthetic builds (gems by display name)."""
    specs = "".join(f'<Spec treeVersion="0_5" classId="1" nodes="{",".join(map(str, s))}"/>'
                    for s in extra_specs)
    specs += f'<Spec treeVersion="0_5" classId="1" nodes="{",".join(map(str, nodes))}"/>'
    skills = "".join(
        "<Skill enabled=\"true\">" + "".join(f'<Gem nameSpec="{g}" level="1"/>' for g in grp) + "</Skill>"
        for grp in groups)
    return (f'<?xml version="1.0" encoding="UTF-8"?><PathOfBuilding2>'
            f'<Build className="{class_name}" ascendClassName="{asc_name or "None"}" level="60" '
            f'mainSocketGroup="{main_group}"/>'
            f'<Tree activeSpec="1">{specs}</Tree>'
            f'<Skills activeSkillSet="1"><SkillSet id="1">{skills}</SkillSet></Skills>'
            f'</PathOfBuilding2>')
