"""Write packaging/pilot.ico from pilot.brand (PNG-in-ICO, 16..256 px).

usage: python tools/make_icon.py
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pilot.brand import logo_pixmap  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def png(size: int) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    logo_pixmap(size).save(buf, "PNG")
    return bytes(data)


def main() -> int:
    QApplication.instance() or QApplication([])
    images = [png(s) for s in SIZES]
    out = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for s, img in zip(SIZES, images):
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(img), offset)
        offset += len(img)
    for img in images:
        out += img
    (ROOT / "packaging" / "pilot.ico").write_bytes(out)
    print(f"packaging/pilot.ico: {len(SIZES)} sizes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
