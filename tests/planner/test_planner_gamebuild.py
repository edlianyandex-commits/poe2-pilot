"""In-game .build files (zip of stages) -> plan with the guide's own gems per stage."""
from pathlib import Path

from pilot.planner import build_plan, load_pob

BUILD = Path(__file__).resolve().parents[2] / "builds" / "twister_monk_guythatdies_0_5_5.build"


def test_stages_class_and_islands_dropped():
    b = load_pob(BUILD)
    assert b.class_name == "Monk"
    assert [len(s.nodes) for s in b.specs] == sorted(len(s.nodes) for s in b.specs)   # early stage first
    p = build_plan(BUILD)
    assert not any("filler" in w for w in p.warnings)


def test_guide_gems_by_stage_and_ingame_names():
    p = build_plan(BUILD)
    lv1 = {r.skill.name: [s.name for s in r.supports] for r in p.gem_rows_for(1)}
    assert lv1["Whirling Slash"] == ["Rage I", "Rapid Attacks I"]       # SupportGemMartialTempo
    assert lv1["Twister"] == ["Retreat I"]
    assert "Barrage" not in lv1 and "Barrage" in {r.skill.name for r in p.gem_rows_for(14)}
    assert all(r.skill.icon_url for r in p.gem_rows_for(1))


def test_zone_hints_from_sidecar():
    p = build_plan(BUILD)
    assert p.zone_hints["G1_town"] == ("Renly: Twister",)
    assert all(len(s) <= 40 for v in p.zone_hints.values() for s in v)


def test_shared_start_class_from_name():
    """Ranger/Huntress share a start: without ascendancy nodes the build name decides."""
    from pilot.planner.gamebuild import _class_of
    from pilot.planner.tree import PassiveTree
    t = PassiveTree.load()
    start = t.class_start("Huntress")
    near = [t.nodes[o].sid for o in t.nodes[start].adj if t.nodes[o].sid and not t.nodes[o].asc][:1]
    asc = [t.nodes[o].sid for o in t.nodes[start].adj if t.nodes[o].asc == "Amazon"]
    assert _class_of(t, near + asc, "Lightning Arrow Ranger") == "Huntress"   # ascendancy wins
    assert _class_of(t, near, "Spear Huntress levelling") == "Huntress"
    assert _class_of(t, near, "Lightning Arrow Ranger") == "Ranger"


def test_sidecar_route_profile_and_ascendancy_override():
    from pilot.planner import build_plan_detail
    d = build_plan_detail(BUILD.with_name("bloodmage_iceshot_syncoh_0_5_5.build"))
    p = d.plan
    assert p.char_class == "Witch"
    assert p.route_require == ("a2-007", "a3-005")
    assert p.ascendancy["G2_13"].passives == ("Blood Barbs",)    # guide's order, not the PoB's
    assert p.zone_hints["G1_12"] == ("King in the Mists: +30 Spirit",)
    assert not any(g.startswith("Надеть") for h in p.hints.values() for g in h.gear)


def test_lvl_stage_names_and_ice_shot_switch():
    from pilot.planner.gamebuild import stage_starts
    assert stage_starts([{"name": "Lvl 1-22 - X"}, {"name": "Lvl 31 (Ice Shot Switch)"},
                         {"name": "END GAME CRIT SWAP (Level 92+)"}]) == [1, 31, 92]
    p = build_plan(BUILD.with_name("bloodmage_iceshot_syncoh_0_5_5.build"))
    early = {r.skill.name for r in p.gem_rows_for(22)}
    assert {"Lightning Arrow", "Lightning Rod"} <= early and "Ice Shot" not in early
    assert "Ice Shot" in {r.skill.name for r in p.gem_rows_for(31)}


def test_text_guide_build_without_tree_class_from_name():
    """A .build written from a text guide: class from the name, gems per act, guide ascendancy."""
    from pilot.planner import build_plan_detail
    d = build_plan_detail(BUILD.with_name("bloodmage_spark_poevault_0_5.build"))
    p = d.plan
    assert p.char_class == "Witch" and not p.warnings
    assert {r.skill.name for r in p.gem_rows_for(1)} == {"Spark", "Frost Bomb", "Flame Wall"}
    assert "Orb of Storms" in {r.skill.name for r in p.gem_rows_for(6)}
    assert "Flame Wall" not in {r.skill.name for r in p.gem_rows_for(45)}
    assert p.ascendancy["G2_13"].passives == ("Sanguimancy", "Sunder the Flesh")
    assert p.route_require == ("a2-007",)
    at = {x: lv for lv, h in sorted(p.hints.items()) for x in h.passives}
    assert at["Secrets of the Orb"] <= 25                     # the guide's ~23
    assert 38 <= at["Elemental Equilibrium"] <= 48            # the guide's ~41
    assert not any("Power of the Dead" in x for x in at)      # no minion notables on the way


def test_ice_nova_contagion_build():
    """Our own write-up (no guide has both skills): Ice Nova from level 1, no Spark, boss skill in Act 1."""
    from pilot.planner import build_plan_detail
    d = build_plan_detail(BUILD.with_name("witch_ice_nova_contagion_0_5_5.build"))
    p = d.plan
    assert p.char_class == "Witch" and not p.warnings
    assert {r.skill.name for r in p.gem_rows_for(1)} == {"Ice Nova", "Frost Bomb"}
    lv7 = {r.skill.name: [s.name for s in r.supports] for r in p.gem_rows_for(7)}
    assert lv7["Ice Nova"] == ["Magnified Area I", "Rapid Casting I", "Unleash"]
    assert {"Contagion", "Frost Darts"} <= set(lv7)
    assert not any(r.skill.name == "Spark" for lv in range(1, 66) for r in p.gem_rows_for(lv))
    assert "Blasphemy" in {r.skill.name for r in p.gem_rows_for(29)}
    assert p.route_require == ("a2-007",)
    at = {x: lv for lv, h in sorted(p.hints.items()) for x in h.passives}
    assert at["Breath of Ice"] <= 15 and at["Endless Blizzard"] <= 44
    assert not any("Power of the Dead" in x for x in at)


def test_warbringer_bone_spells_build():
    """The user's own plan: slams first, bone spells from 6, Bonestorm from Act 2, Warrior tree;
    gems come a few at a time so each level-up toast stays readable."""
    from pilot.planner import build_plan_detail
    p = build_plan_detail(BUILD.with_name("warbringer_bone_spells_0_5_5.build")).plan
    assert p.char_class == "Warrior" and not p.warnings
    assert {r.skill.name for r in p.gem_rows_for(1)} == {"Rolling Slam", "Boneshatter"}
    lv5 = {r.skill.name: [s.name for s in r.supports] for r in p.gem_rows_for(5)}
    assert lv5 == {"Rolling Slam": ["Magnified Area I", "Fist of War I"],                # two maces, supports
                   "Boneshatter": ["Brutality I", "Impact Shockwave"]}                  # from the start
    assert {r.skill.name for r in p.gem_rows_for(15)} == {"Bone Cage", "Bonestorm"}
    dd = {r.skill.name: [s.name for s in r.supports] for r in p.gem_rows_for(45)}["Detonate Dead"]
    assert not any(s.startswith("Brutality") for s in dd)     # it also deals fire damage
    assert p.ascendancy["G2_13"].passives == ("Anvil's Weight",)
    assert all(len(h.gems) <= 3 for h in p.hints.values())
    at = {x: lv for lv, h in sorted(p.hints.items()) for x in h.passives}
    assert at["Defender's Resolve"] <= 15 and at["Cruel Methods"] <= 31
    assert "Powerful Casting" not in at and "Deadly Thorns" not in at   # Oracle-only nodes


def test_hollow_palm_monk_build():
    """DEADRABB1T's file, prepared: stage levels, one weapon set, Hollow Palm Technique first."""
    from pilot.planner import build_plan_detail
    from pilot.planner.gamebuild import read_build_files
    path = BUILD.with_name("monk_hollow_palm_storm_wave_0_5_5.build")
    assert not any(p.get("weapon_set") == 2 for st in read_build_files(path) for p in st["passives"])
    p = build_plan_detail(path).plan
    assert p.char_class == "Monk" and not p.warnings
    assert "Glacial Cascade" in {r.skill.name for r in p.gem_rows_for(10)}
    lv22 = {r.skill.name for r in p.gem_rows_for(22)}
    assert "Storm Wave" in lv22 and "Glacial Cascade" not in lv22
    assert "Hand of Chayula" in {r.skill.name for r in p.gem_rows_for(32)}
    at = {x: lv for lv, h in sorted(p.hints.items()) for x in h.passives}
    assert at["Hollow Palm Technique"] <= 14                    # the guide's ~13
    assert all(len(h.gems) <= 3 for h in p.hints.values())      # 22 and 31 swaps spread out
    assert p.route_require == ("a2-007", "a3-005")


def test_ice_strike_monk_build():
    """PoE Vault's planner gems, our tree: Hollow Palm first, Ice Strike from 14, no weapon sets."""
    from pilot.planner import build_plan_detail
    p = build_plan_detail(BUILD.with_name("monk_ice_strike_0_5.build")).plan
    assert p.char_class == "Monk" and not p.warnings
    assert {r.skill.name for r in p.gem_rows_for(1)} == {"Whirling Slash"}
    assert {r.skill.name for r in p.gem_rows_for(9)} == {"Whirling Slash", "Twister"}   # few gems early
    assert "Twister" in {r.skill.name for r in p.gem_rows_for(13)}               # no gap before Ice Strike
    lv14 = {r.skill.name for r in p.gem_rows_for(14)}
    assert "Ice Strike" in lv14 and "Twister" not in lv14                       # tier 5: usable from 14
    assert "Frost Bomb" not in {r.skill.name for r in p.gem_rows_for(50)}     # after Heavy Frost
    assert all(len(h.gems) <= 3 for h in p.hints.values())
    at = {x: lv for lv, h in sorted(p.hints.items()) for x in h.passives}
    assert at["Hollow Palm Technique"] <= 14 and at["Heavy Frost"] <= 48
    assert p.route_require == ("a2-007", "a3-005")


def test_minion_witch_build():
    """Mattjestic's file, prepared: three campaign variants, Infernalist only, few gems early."""
    from pilot.planner import build_plan_detail
    p = build_plan_detail(BUILD.with_name("witch_minions_mattjestic_0_5.build")).plan
    assert p.char_class == "Witch" and not p.warnings
    assert {r.skill.name for r in p.gem_rows_for(1)} == {"Unearth"}
    assert len(p.gem_rows_for(9)) == 4                                   # four skills by 9
    assert all(len(h.gems) <= 2 for h in p.hints.values())
    assert "Spectre" in {r.skill.name for r in p.gem_rows_for(45)}       # "Spectre: {0}" shown plainly
    assert "Summon Infernal Hound" not in {r.skill.name for r in p.gem_rows_for(24)}
    assert p.ascendancy["G2_13"].passives[-1] == "Loyal Hellhound"
    at = {x: lv for lv, h in sorted(p.hints.items()) for x in h.passives}
    assert at["Raw Destruction"] <= 8 and at["Power of the Dead"] <= 10  # Witch variants: minion damage
    assert at["Relentless Fallen"] <= 16 and at["Potent Incantation"] <= 30   # damage first
    assert not any(x.startswith("+5") for lv, h in p.hints.items() if lv < 10 for x in h.passives)
