"""Start window: hero cards, build list, start, update news, art and font."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtTest import QTest

from pilot.catalog import load_catalog
from pilot.launcher import style as S
from pilot.launcher.board import BoardWindow
from pilot.launcher.heroes import CLASSES, class_art, draw_glyph
from pilot.updates import Check

ROOT = Path(__file__).resolve().parents[2]


def test_builds_word_in_russian():
    assert [S.builds_word(n) for n in (0, 1, 2, 4, 5, 11, 21, 22)] == [
        "скоро", "1 билд", "2 билда", "4 билда", "5 билдов", "11 билдов", "21 билд", "22 билда"]


def test_status_is_shown_as_rarity():
    cat = load_catalog(ROOT / "builds")
    tags = {e.status: S.rarity(e)[:2] for e in cat.entries}
    assert tags == {"verified": ("SSR", 5), "guide": ("SR", 4), "custom": ("R", 3)}


def test_bundled_font_loads(qapp):
    assert S.load_fonts() == S.FAMILY


def test_every_class_has_art_and_a_pictogram(qapp):
    for c in CLASSES:
        art = class_art(c, 96)
        assert art is not None and not art.isNull(), c
        img = art.toImage()
        assert img.pixelColor(48, 48).alpha() > 0, c          # the face is in the middle
        pm = QPixmap(64, 64)
        pm.fill(QColor(255, 255, 255))
        p = QPainter(pm)
        draw_glyph(p, c, QRectF(8, 8, 48, 48), QColor(0, 0, 0), QColor(255, 255, 255))
        p.end()
        img = pm.toImage()
        dark = sum(img.pixelColor(x, y).red() < 100 for x in range(0, 64, 2) for y in range(0, 64, 2))
        assert dark > 20, c


def _window(qapp, **kw):
    w = BoardWindow(load_catalog(ROOT / "builds"), **kw)
    w.show()
    return w


def test_opens_on_the_heroes_with_the_last_class_in_focus(qapp):
    w = _window(qapp, last="grenades_gemling_0_5_5.build")
    assert not w.on_board and CLASSES[w.heroes.focus] == "Mercenary"
    QTest.keyClick(w, Qt.Key_Return)
    assert w.on_board and {e.cls for e in w.builds.entries} == {"Mercenary"}
    assert w.builds.entries[w.builds.sel].file == "grenades_gemling_0_5_5.build"
    assert w.card.entry.file == "grenades_gemling_0_5_5.build"
    w.close()


def test_a_hero_without_builds_stays_shut(qapp):
    w = _window(qapp)
    w.heroes.focus = CLASSES.index("Druid")
    QTest.keyClick(w, Qt.Key_Return)
    assert not w.on_board
    w.close()


def test_keys_pick_and_enter_starts(qapp):
    w = _window(qapp)
    w.open_class("Witch")
    QTest.keyClick(w, Qt.Key_Down)
    QTest.keyClick(w, Qt.Key_Down)
    assert w.builds.sel == 2 and w.card.entry is w.builds.entries[2]
    QTest.keyClick(w, Qt.Key_End)
    assert w.builds.sel == len(w.builds.entries) - 1
    QTest.keyClick(w, Qt.Key_Return)
    assert w.result == w.builds.entries[-1].file and w.result.startswith("witch_minions")
    assert not w.isVisible()


def test_escape_goes_back_then_quits(qapp):
    w = _window(qapp)
    w.open_class("Monk")
    QTest.keyClick(w, Qt.Key_Escape)
    assert not w.on_board and w.isVisible()
    QTest.keyClick(w, Qt.Key_Return)                 # Enter on the heroes only opens a class
    assert w.on_board and w.result is None
    QTest.keyClick(w, Qt.Key_Backspace)
    QTest.keyClick(w, Qt.Key_Escape)
    assert w.result is None and not w.isVisible()


def test_twinkle_tick_reaches_the_animated_parts(qapp):
    w = _window(qapp)
    w._twinkle()
    assert w.heroes.phase == w.card.phase == w.go.phase > 0
    w.close()


class FakeUpdater:
    def releases_url(self):
        return "https://example/releases"


def test_update_news_in_the_footer(qapp):
    w = _window(qapp)
    w.updater = FakeUpdater()
    w._checked(Check(content={"version": "2026.11.2"}), None)
    assert "2026.11.2" in w.news.text() and w.action.text() == "Обновить" and w._remote
    w2 = _window(qapp)
    w2.updater = FakeUpdater()
    w2._checked(Check(needs_app="1.0.0"), None)
    assert w2.action.text() == "Скачать" and w2._open_url == "https://example/releases"
    w2._checked(None, OSError("offline"))
    assert "GitHub" in w2.news.text()
    w.close()
    w2.close()


def test_hotkeys_cheat_sheet(qapp):
    from pilot.launcher.help import ACTIONS, HotkeysDialog, pretty, rows
    assert pretty("alt+]") == "Alt + ]" and pretty("ctrl+shift+g") == "Ctrl + Shift + G"
    r = rows({"gems": "ctrl+g"})
    assert len(r) == len(ACTIONS) and ("Ctrl + G", ACTIONS["gems"]) in r
    d = HotkeysDialog(None)
    d.show()
    assert d.grab().width() == d.W
    d.close()


def test_language_switch_saves_and_restarts(qapp):
    picked = []
    w = BoardWindow(load_catalog(ROOT / "builds"), on_language=picked.append)
    w.show()
    w._language("en")
    assert picked == ["en"] and w.restart and not w.isVisible()


def test_english_start_window(qapp):
    from pilot import i18n
    i18n.set_lang("en")
    w = _window(qapp)
    assert w.bar.title == "Choose your hero" and w.back.text() == "← Heroes"
    w.open_class("Witch")
    assert w.bar.title == "Choose a build" and S.builds_word(4) == "4 builds"
    w.close()
