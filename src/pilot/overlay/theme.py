"""Colors (plain RGB(A) tuples, no Qt) shared by the HUD, pills, icons and tests."""
from __future__ import annotations

RGB = tuple[int, int, int]
RGBA = tuple[int, int, int, int]

WHITE: RGB = (255, 255, 255)
YELLOW: RGB = (255, 216, 74)

# one color per route kind; toasts reuse the same hues (see TOAST_COLORS)
KIND_COLORS: dict[str, RGB] = {
    "move": (225, 225, 225),
    "wp": (96, 205, 255),
    "boss": (255, 140, 90),        # must kill to progress
    "boss_opt": (140, 140, 140),   # optional boss: same swords, greyed out
    "quest": (255, 216, 74),
    "town": (232, 200, 150),
    "trial": (236, 140, 226),
    "skip": (150, 150, 150),
}
TOAST_COLORS: dict[str, RGB] = {
    "level": (255, 214, 102),
    "split": (255, 255, 255),
    "warn": YELLOW,
    "gear": (190, 170, 255),
    "zone": KIND_COLORS["wp"],
}
TOAST_ICONS: dict[str, str] = {
    "level": "level", "split": "flag", "warn": "alert", "gear": "shield", "zone": "pin",
}

PALETTES: dict[str, dict[str, object]] = {
    "default": {
        "ahead": (92, 240, 120),          # progress / accents
        "behind": (255, 92, 92),
        "pill_ahead": ((225, 255, 232), (24, 118, 58, 238)),    # (text, background)
        "pill_behind": ((255, 226, 226), (160, 38, 38, 238)),
    },
    "colorblind": {                       # blue / orange instead of green / red
        "ahead": (90, 170, 255),
        "behind": (255, 160, 50),
        "pill_ahead": ((226, 241, 255), (26, 84, 170, 238)),
        "pill_behind": ((255, 240, 214), (176, 98, 10, 238)),
    },
}
PILL_EVEN = ((235, 235, 235), (80, 80, 80, 235))
ZONE_NEUTRAL = ((228, 228, 228), (255, 255, 255, 46))
ZONE_AMBER = ((255, 240, 200), (176, 122, 8, 240))
ZONE_RED = ((255, 228, 228), (186, 38, 38, 240))


def palette(name: str | None) -> dict[str, object]:
    return PALETTES.get(name or "default", PALETTES["default"])
