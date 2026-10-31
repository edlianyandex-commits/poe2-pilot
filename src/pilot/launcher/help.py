"""Hotkeys cheat sheet: shown once on the first take-off and from the tray ("Хоткеи…")."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath
from PySide6.QtWidgets import QDialog, QPushButton, QWidget

from . import style as S

# hotkey name (overlay.hotkeys.DEFAULT_HOTKEYS) -> what it does
ACTIONS = {
    "details": "подробности: следующие шаги, гемы (держать)",
    "gems": "окно гемов",
    "tree": "дерево пассивок",
    "next": "шаг маршрута вперёд",
    "prev": "шаг маршрута назад",
    "pause": "пауза таймера",
    "reset": "сбросить забег",
    "edit": "двигать HUD и менять размер (ещё раз — сохранить)",
    "hide": "скрыть / показать HUD",
}
TIPS = (
    "Игра — в режиме «Оконный полноэкранный», иначе HUD не виден.",
    "Игра запущена от имени администратора? Запусти так же и PoE2 Pilot, иначе хоткеи не дойдут.",
    "Правый клик по значку в трее: сменить билд, гемы, дерево, папка логов.",
)


def pretty(combo: str) -> str:
    """'alt+]' -> 'Alt + ]'."""
    return " + ".join(k if len(k) == 1 and not k.isalpha() else k.capitalize() for k in combo.split("+"))


def rows(hotkeys: dict | None) -> list[tuple[str, str]]:
    from pilot.overlay.hotkeys import DEFAULT_HOTKEYS
    keys = {**DEFAULT_HOTKEYS, **(hotkeys or {})}
    return [(pretty(keys[name]), text) for name, text in ACTIONS.items() if keys.get(name)]


class HotkeysDialog(QDialog):
    W = 620
    ROW = 36

    def __init__(self, hotkeys: dict | None, parent: QWidget | None = None):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("PoE2 Pilot — хоткеи")
        self.rows = rows(hotkeys)
        tf = S.font(12.5, QFont.Bold)
        self.tip_h = [QFontMetricsF(tf).boundingRect(QRectF(0, 0, self.W - 90, 200), Qt.TextWordWrap, t).height() + 8
                      for t in TIPS]
        self.setFixedSize(self.W, int(118 + self.ROW * len(self.rows) + sum(self.tip_h) + 90))
        ok = QPushButton("Понятно", self)
        from .board import button_css
        ok.setStyleSheet(button_css(S.load_fonts()))
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(self.accept)
        ok.resize(130, 34)
        ok.move(self.W - 130 - 34, self.height() - 34 - 28)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        shape = QPainterPath()
        shape.addRoundedRect(r, 22, 22)
        g = S.gradient(r, QColor(255, 236, 246), QColor(232, 243, 255))
        S.soft_card(p, r, 22, g, S.WHITE, 2)
        p.setFont(S.font(22, QFont.ExtraBold, 0.5))
        p.setPen(S.INK)
        p.drawText(QPointF(r.left() + 30, r.top() + 46), "Хоткеи")
        S.sparkle(p, QPointF(r.left() + 30 + QFontMetricsF(p.font()).horizontalAdvance("Хоткеи") + 18,
                             r.top() + 38), 7, S.PINK)
        p.setFont(S.font(12, QFont.Bold))
        p.setPen(S.DIM)
        p.drawText(QPointF(r.left() + 30, r.top() + 70), "работают, пока игра на переднем плане")

        y = r.top() + 92
        kf = S.font(13, QFont.ExtraBold)
        for combo, text in self.rows:
            S.chip(p, r.left() + 28, y, combo, kf, S.WHITE, S.PINK, h=26)
            p.setFont(S.font(14, QFont.Bold))
            p.setPen(S.INK)
            p.drawText(QRectF(r.left() + 150, y, r.width() - 170, 26), Qt.AlignVCenter, text)
            y += self.ROW
        y += 10
        p.setFont(S.font(12.5, QFont.Bold))
        for tip, h in zip(TIPS, self.tip_h):
            S.sparkle(p, QPointF(r.left() + 36, y + 10), 5, S.GOLD)
            p.setPen(S.DIM)
            p.drawText(QRectF(r.left() + 50, y, r.width() - 70, h), Qt.TextWordWrap, tip)
            y += h

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            self.accept()
        else:
            super().keyPressEvent(e)
