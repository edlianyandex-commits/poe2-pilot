"""Build dist/PoE2Pilot/PoE2Pilot.exe (one folder: faster start than one-file for Qt).

usage: python packaging/build_exe.py [--windowed]
--windowed hides the console; without it errors are visible in the console window (test builds).
One exe for every build: the start window picks the build (no per-build shortcuts).
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
    "--add-data", f"{ROOT / 'content.json'};.",       # the bundled content version (pilot.paths)
    "--icon", str(ROOT / "packaging" / "pilot.ico"),
    # Qt parts the app never uses
    *[a for m in ("PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
                  "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts",
                  "PySide6.QtDataVisualization", "PySide6.QtPdf", "tkinter") for a in ("--exclude-module", m)],
]
if "--windowed" in sys.argv:
    args.append("--windowed")

PyInstaller.__main__.run(args)

