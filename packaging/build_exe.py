"""Build dist/PoE2Pilot/PoE2Pilot.exe (one folder: faster start than one-file for Qt).

usage: python packaging/build_exe.py [--windowed]
--windowed hides the console; without it errors are visible in the console window (test builds).
"""
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]

args = [
    str(ROOT / "packaging" / "launcher.py"),
    "--name", "PoE2Pilot",
    "--noconfirm", "--clean",
    "--paths", str(ROOT / "src"),
    "--distpath", str(ROOT / "dist"),
    "--workpath", str(ROOT / "build"),
    "--specpath", str(ROOT / "build"),
    "--add-data", f"{ROOT / 'data'};data",
    "--add-data", f"{ROOT / 'builds'};builds",
    # Qt parts the app never uses
    *[a for m in ("PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
                  "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts",
                  "PySide6.QtDataVisualization", "PySide6.QtPdf", "tkinter") for a in ("--exclude-module", m)],
]
if "--windowed" in sys.argv:
    args.append("--windowed")

PyInstaller.__main__.run(args)

# one-click launchers next to the exe (PyInstaller recreates dist/PoE2Pilot, so write them each build)
LAUNCHERS = {
    "PoE2Pilot - Monk.bat": "twister_monk_guythatdies_0_5_5.build",
    "PoE2Pilot - Mercenary (Travic).bat": "twister_speed_campaign_travic_0_5_5.pob",
    "PoE2Pilot - Blood Mage.bat": "bloodmage_iceshot_syncoh_0_5_5.build",
    "PoE2Pilot - Blood Mage (Spark).bat": "bloodmage_spark_poevault_0_5.build",
    "PoE2Pilot - Witch (Ice Nova).bat": "witch_ice_nova_contagion_0_5_5.build",
    "PoE2Pilot - Warbringer (Bone).bat": "warbringer_bone_spells_0_5_5.build",
}
for name, build in LAUNCHERS.items():
    (ROOT / "dist" / "PoE2Pilot" / name).write_text(
        f'@echo off\r\nstart "" "%~dp0PoE2Pilot.exe" --build {build}\r\n', encoding="ascii")
