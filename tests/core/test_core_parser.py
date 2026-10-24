from datetime import datetime
from pathlib import Path

from pilot.contracts import (
    AreaGenerated, Death, FocusChanged, GameClosed, LevelUp, LoadingScreen,
    PassiveAllocated, SceneEntered,
)
from pilot.core.parser import parse_line, parse_ts

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "campaign_ru.log"
HDR = "2025/12/12 22:10:21 219309250 2caa22da [INFO Client 10768] "
TS = datetime(2025, 12, 12, 22, 10, 21)


def test_area_generated():
    line = '2025/12/12 22:10:21 219309250 2caa22da [DEBUG Client 10768] Generating level 1 area "G1_1" with seed 3976951634'
    assert parse_line(line) == AreaGenerated(TS, "G1_1", 1, 3976951634)


def test_scene_and_dropped_scenes():
    assert parse_line(HDR + "[SCENE] Set Source [Берег реки]") == SceneEntered(TS, "Берег реки")
    assert parse_line(HDR + "[SCENE] Set Source [(null)]") is None
    assert parse_line(HDR + "[SCENE] Set Source [(unknown)]") is None


def test_loading_screen():
    ev = parse_line(HDR + "[LOADING SCREEN] (Сборочный цех) Duration = 3.33666 seconds")
    assert ev == LoadingScreen(TS, "Сборочный цех", 3.33666)


def test_level_up_ru_en():
    assert parse_line(HDR + ": TestExile (Чародейка) достигает 2 уровня") == LevelUp(TS, "TestExile", "Чародейка", 2)
    assert parse_line(HDR + ": Bob (Sorceress) is now level 12") == LevelUp(TS, "Bob", "Sorceress", 12)


def test_death_ru_en():
    assert parse_line(HDR + ": TestExile был повержен.") == Death(TS, "TestExile")
    assert parse_line(HDR + ": Bob has been slain.") == Death(TS, "Bob")


def test_passives():
    ev = parse_line(HDR + "Successfully allocated passive skill id: spells18, name: Урон чарами")
    assert ev == PassiveAllocated(TS, "spells18", "Урон чарами", True)
    ev = parse_line(HDR + "Successfully unallocated passive skill id: spells18, name: Урон чарами\r\n")
    assert ev == PassiveAllocated(TS, "spells18", "Урон чарами", False)


def test_focus_and_close():
    assert parse_line(HDR + "[WINDOW] Lost focus") == FocusChanged(TS, False)
    assert parse_line(HDR + "[WINDOW] Gained focus") == FocusChanged(TS, True)
    assert parse_line(HDR + "Closing game gracefully") == GameClosed(TS)


def test_junk_returns_none():
    for line in ("", "garbage", HDR + "Connecting to instance server",
                 HDR + "@From Bob: hi", "2025/12/12 99:99:99 1 a [INFO Client 1] : A (B) is now level 3"):
        assert parse_line(line) is None


def test_parse_ts():
    assert parse_ts(HDR) == TS
    assert parse_ts("nope") is None


def test_whole_fixture_parses():
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if parse_line(line) is None:
            assert "[SCENE]" in line and ("(null)" in line or "(unknown)" in line), line
