"""Start window: class gates, flap rows, picking, take-off, update news."""
from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtTest import QTest

from pilot.catalog import load_catalog
from pilot.launcher.board import BOARDING, BoardWindow
from pilot.launcher.classes import CLASSES, draw_glyph, flights
from pilot.launcher.flaps import FlapLine
from pilot.updates import Check

ROOT = Path(__file__).resolve().parents[2]


def settle(*lines):
    while any([line.step() for line in lines]):
        pass


def test_flaps_flip_forward_to_the_target_and_leave_still_tiles_alone():
    line = FlapLine(6, random.Random(1))
    line.set("mr 202")
    assert line.busy and line.shown == list("      ")
    settle(line)
    assert "".join(line.shown) == "MR 202" and line.text == "MR 202"
    line.set("MR 203")
    assert line.left[:5] == [0] * 5 and line.left[5] > 0
    settle(line)
    assert "".join(line.shown) == "MR 203"


def test_flights_in_russian():
    assert [flights(n) for n in (0, 1, 2, 4, 5, 11, 21, 22)] == [
        "рейсов нет", "1 рейс", "2 рейса", "4 рейса", "5 рейсов", "11 рейсов", "21 рейс", "22 рейса"]


def test_every_class_has_a_pictogram(qapp):
    pm = QPixmap(64, 64)
    for c in CLASSES:
        pm.fill(QColor(255, 178, 62))
        p = QPainter(pm)
        draw_glyph(p, c, QRectF(8, 8, 48, 48), QColor(0, 0, 0), QColor(255, 178, 62))
        p.end()
        img = pm.toImage()
        dark = sum(img.pixelColor(x, y).red() < 100 for x in range(0, 64, 2) for y in range(0, 64, 2))
        assert dark > 20, c


def _window(qapp, **kw):
    w = BoardWindow(load_catalog(ROOT / "builds"), **kw)
    w.show()
    return w


def test_opens_on_the_gates_with_the_last_class_in_focus(qapp):
    w = _window(qapp, last="grenades_gemling_0_5_5.build")
    assert not w.on_board and CLASSES[w.gates.focus] == "Mercenary"
    QTest.keyClick(w, Qt.Key_Return)
    assert w.on_board and {e.cls for e in w.board.entries} == {"Mercenary"}
    sel = w.board.sel
    assert w.board.entries[sel].file == "grenades_gemling_0_5_5.build"
    assert w.board.rows[sel][2].text == BOARDING[0]
    assert w.ticket.entry.file == "grenades_gemling_0_5_5.build"
    w.close()


def test_a_gate_without_builds_stays_shut(qapp):
    w = _window(qapp)
    w.gates.focus = CLASSES.index("Druid")
    QTest.keyClick(w, Qt.Key_Return)
    assert not w.on_board
    w.close()


def test_keys_pick_and_enter_takes_off(qapp):
    w = _window(qapp)
    w.open_class("Witch")
    QTest.keyClick(w, Qt.Key_Down)
    QTest.keyClick(w, Qt.Key_Down)
    assert w.board.sel == 2 and w.ticket.entry is w.board.entries[2]
    assert w.board.rows[0][2].text != BOARDING[0]
    QTest.keyClick(w, Qt.Key_End)
    assert w.board.sel == len(w.board.entries) - 1
    QTest.keyClick(w, Qt.Key_Return)
    assert w.result == w.board.entries[-1].file and w.result.startswith("witch_minions")
    assert not w.isVisible()


def test_escape_goes_back_then_quits(qapp):
    w = _window(qapp)
    w.open_class("Monk")
    QTest.keyClick(w, Qt.Key_Escape)
    assert not w.on_board and w.isVisible()
    QTest.keyClick(w, Qt.Key_Return)                 # Enter on the gates only opens a class
    assert w.on_board and w.result is None
    QTest.keyClick(w, Qt.Key_Backspace)
    QTest.keyClick(w, Qt.Key_Escape)
    assert w.result is None and not w.isVisible()


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
