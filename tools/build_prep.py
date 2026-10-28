"""Gem pacing for downloaded build files (shared by tools/prep_*.py)."""


def stagger(st: dict, start: int, prev: dict | None, per_level: int = 3, skill_gap: int = 0,
            not_before: dict[str, int] | None = None) -> None:
    """Delay a stage's new skills and supports: at most `per_level` new gems a level and a new
    skill at most every `skill_gap` levels, in the file's order (each skill before its supports).
    `not_before` holds a first level for some skills (e.g. one granted by the ascendancy)."""
    # gems the previous stage already had in use before this stage starts
    old = {sk["id"]: {x["id"] for x in sk.get("support_skills") or () if x["level_interval"][0] < start}
           for sk in (prev or {}).get("skills") or () if sk["level_interval"][0] < start}
    used: dict[int, int] = {}
    last_skill = start - skill_gap

    def place(item: dict, earliest: int) -> int:
        lv = max(earliest, item["level_interval"][0])
        while used.get(lv, 0) >= per_level:
            lv += 1
        used[lv] = used.get(lv, 0) + 1
        item["level_interval"] = [lv, item["level_interval"][1]]
        return lv

    # a skill the file starts later than the stage (e.g. from 14) goes after the ones open at
    # the stage start, so it does not push them back; otherwise the file's order
    for sk in sorted(st["skills"], key=lambda s: max(s["level_interval"][0], start)):
        if sk["id"] in old:
            lv = start
        else:
            late = (not_before or {}).get(sk["id"], 0)
            lv = place(sk, max(start, last_skill + skill_gap, late))
            if not late:              # a gated skill does not hold back the others
                last_skill = lv
        for sup in sk.get("support_skills") or ():
            if sup["id"] not in old.get(sk["id"], ()):
                place(sup, lv)
