import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# the offscreen platform has no font database of its own; point it at the system fonts
_fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
if os.path.isdir(_fonts):
    os.environ.setdefault("QT_QPA_FONTDIR", _fonts)

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
