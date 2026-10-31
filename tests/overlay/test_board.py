"""Start window: flap rows, picking, take-off, update news."""
from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from pilot.catalog import load_catalog
from pilot.launcher.board import BOARDING, BoardWindow
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


def _window(qapp, **kw):
    w = BoardWindow(load_catalog(ROOT / "builds"), **kw)
    w.show()
    return w


def test_last_build_is_preselected_and_boarding(qapp):
    w = _window(qapp, last="grenades_gemling_0_5_5.build")
    sel = w.board.sel
    assert w.board.entries[sel].file == "grenades_gemling_0_5_5.build"
    assert w.board.rows[sel][2].text == BOARDING[0]
    assert w.ticket.entry.file == "grenades_gemling_0_5_5.build"
    w.close()


def test_keys_pick_and_enter_takes_off(qapp):
    w = _window(qapp)
    QTest.keyClick(w, Qt.Key_Down)
    QTest.keyClick(w, Qt.Key_Down)
    assert w.board.sel == 2 and w.ticket.entry is w.board.entries[2]
    assert w.board.rows[0][2].text != BOARDING[0]
    QTest.keyClick(w, Qt.Key_End)
    assert w.board.sel == len(w.board.entries) - 1
    QTest.keyClick(w, Qt.Key_Return)
    assert w.result == w.board.entries[-1].file and not w.isVisible()


def test_escape_quits_without_a_build(qapp):
    w = _window(qapp)
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
