"""Russian or English. Code keeps its Russian text; tr() swaps in the English from pilot/i18n_en.py.

Content files carry both: a field `x` (Russian) may have `x_en` next to it, read through pick().
Language: config "language" = "ru" | "en" | "auto" (Windows UI language: ru/uk/be/kk -> ru, else en).
"""
from __future__ import annotations

import locale
import sys

LANGS = ("ru", "en")
_lang: str | None = None


def system_lang() -> str:
    if sys.platform == "win32":
        try:
            import ctypes
            primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
            return "ru" if primary in (0x19, 0x22, 0x23, 0x3F) else "en"
        except (AttributeError, OSError):
            pass
    code = (locale.getlocale()[0] or "").lower()
    return "ru" if code.startswith(("ru", "uk", "be", "kk", "russian", "ukrainian")) else "en"


def set_lang(value: str | None) -> str:
    global _lang
    _lang = value if value in LANGS else system_lang()
    return _lang


def lang() -> str:
    if _lang is None:
        from pilot.config import load_config
        set_lang(load_config().get("language"))
    return _lang


def tr(ru: str, **kw) -> str:
    """The English for this Russian text when the UI is English; `kw` fill {placeholders}."""
    text = ru
    if lang() == "en":
        from pilot.i18n_en import EN
        text = EN.get(ru, ru)
    return text.format(**kw) if kw else text


def pick(d: dict, key: str, default=None):
    """d[key + '_en'] for English when present, else d[key]."""
    if lang() == "en" and d.get(f"{key}_en") not in (None, "", {}, []):
        return d[f"{key}_en"]
    return d.get(key, default)
