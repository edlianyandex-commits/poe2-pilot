"""Start-up chores of the app: one copy at a time, the previous log kept, Client.txt found or asked for."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

STEAM_LOGS = r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile 2\logs"


def instance_lock(path: Path, wait_ms: int = 0):
    """-> a held QLockFile, or None while another copy runs. A crashed copy's lock counts as free."""
    from PySide6.QtCore import QLockFile
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path))
    lock.setStaleLockTime(0)                 # never stale by age; a dead owner's PID still frees it
    return lock if lock.tryLock(wait_ms) else None


def rotate_log(log: Path) -> None:
    """Keep the last run's log as pilot.prev.log: a crash report survives the restart."""
    if log.is_file():
        log.replace(log.with_name(f"{log.stem}.prev{log.suffix}"))


def resolve_log(explicit: str | None, cfg: dict, find: Callable[[], object],
                ask: Callable[[], str | None]) -> Path | None:
    """--log, then the config, then auto-detect, then ask the user; a picked file goes into cfg."""
    for cand in (explicit, cfg.get("log_path"), find()):
        if cand and Path(cand).is_file():
            return Path(cand)
    picked = ask()
    if picked and Path(picked).is_file():
        cfg["log_path"] = str(picked)
        return Path(picked)
    return None


def ask_client_log() -> str | None:
    """Explain what is missing and let the user point at Client.txt."""
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    QApplication.instance() or QApplication([])
    box = QMessageBox(QMessageBox.Warning, "PoE2 Pilot",
                      "Не найден лог игры Client.txt.\n\nОн лежит в папке игры: …\\Path of Exile 2\\logs\\Client.txt. "
                      "Если игра ещё не запускалась, запусти её один раз.")
    pick = box.addButton("Указать файл…", QMessageBox.AcceptRole)
    box.addButton("Выход", QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is not pick:
        return None
    start = STEAM_LOGS if Path(STEAM_LOGS).is_dir() else ""
    path, _ = QFileDialog.getOpenFileName(None, "Где Client.txt?", start,
                                          "Client.txt (Client.txt);;Текстовые файлы (*.txt)")
    return path or None


def already_running() -> None:
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])
    QMessageBox.information(None, "PoE2 Pilot",
                            "PoE2 Pilot уже запущен: его значок в трее, справа на панели задач.")
