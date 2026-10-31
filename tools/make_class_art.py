"""Write data/ui/classes/<class>.svg: our own anime bust per class, in its own scene, for the start window.

usage: python tools/make_class_art.py
Anime screencap look, drawn with line art and cel shading: layered eyes (gradient iris, lid shadow,
glow crescent, three highlights and a twinkle, winged lashes, crease, lower lashes), blush with
hatching, hair locks with strands, an angel-ring shine, two-tone shadows on hair and face, and
diagonal light flares over everything. Each class brings its palette, hairstyle, outfit, headwear,
weapon and a background scene in its colour (Warrior crimson sunset, Witch violet night, ...).
viewBox 0 0 200 200, full bleed. SVG Tiny only (QtSvg): gradients, paths, transforms, opacity.
Then run tools/make_content_manifest.py.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "ui" / "classes"

SKIN, SKIN_SHADE, SKIN_LINE = "#FFE9DC", "#F7C6B2", "#C9877A"
LASH = "#2A1B2E"
MIRROR = 'transform="matrix(-1 0 0 1 200 0)"'


def shape(d: str, fill: str, line: str | None = None, w: float = 1.6, extra: str = "") -> str:
    stroke = f' stroke="{line}" stroke-width="{w}" stroke-linejoin="round" stroke-linecap="round"' if line else ""
    return f'<path d="{d}" fill="{fill}"{stroke}{extra}/>'


def stroke(d: str, color: str, w: float = 1.2, opacity: float = 1.0) -> str:
    op = f' opacity="{opacity}"' if opacity < 1 else ""
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" stroke-linecap="round"'
            f' stroke-linejoin="round"{op}/>')


def lin(id_: str, *stops: tuple[float, str], x2: float = 0, y2: float = 1, opacity: tuple = ()) -> str:
    s = "".join(f'<stop offset="{o}" stop-color="{c}"'
                + (f' stop-opacity="{opacity[k]}"' if opacity else "") + "/>" for k, (o, c) in enumerate(stops))
    return f'<linearGradient id="{id_}" x1="0" y1="0" x2="{x2}" y2="{y2}">{s}</linearGradient>'


def rad(id_: str, cx: float, cy: float, r: float, *stops: tuple[float, str, float]) -> str:
    s = "".join(f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a}"/>' for o, c, a in stops)
    return (f'<radialGradient id="{id_}" gradientUnits="userSpaceOnUse" cx="{cx}" cy="{cy}" r="{r}"'
            f' fx="{cx}" fy="{cy}">{s}</radialGradient>')


def twinkle(x: float, y: float, s: float, color: str = "#FFFFFF", opacity: float = 1.0) -> str:
    d = (f"M{x},{y - s} Q{x},{y} {x + s},{y} Q{x},{y} {x},{y + s} Q{x},{y} {x - s},{y} Q{x},{y} {x},{y - s} Z")
    return f'<path d="{d}" fill="{color}" opacity="{opacity}"/>'


# ---------------------------------------------------------------- face
# TV-anime look: flat colours with one hard shadow tone, almond eyes with a small iris and two
# highlights, thin coloured lines. The head is drawn at 1:1 here and scaled down as a group (HEAD).
HEAD = 'transform="matrix(0.84 0 0 0.84 16 12.2)"'


def eye(c: dict) -> str:
    """Left eye (viewer's left), centred near (85, 101); the right one is its mirror."""
    return "".join([
        shape("M71,101 C75,94 90,92.5 96.5,98.5 C93.5,108 77,110 71,101 Z", "#FFFFFF"),
        shape("M71.5,100 C76,94.5 90,93.5 96,98.5 L95.5,100.5 C89,96.5 77,97 72,101.5 Z", "#DCD8EA"),
        '<ellipse cx="85" cy="101.5" rx="6.6" ry="8" fill="{mid}"/>'.format(mid=c["eye_mid"]),
        '<ellipse cx="85" cy="98.6" rx="6.1" ry="4.8" fill="{d}" opacity="0.85"/>'.format(d=c["eye_dark"]),
        '<ellipse cx="85" cy="102" rx="2.8" ry="4" fill="#140C1C"/>',
        '<ellipse cx="85.5" cy="106" rx="3.8" ry="1.8" fill="{l}" opacity="0.8"/>'.format(l=c["eye_light"]),
        '<ellipse cx="82.5" cy="98.4" rx="2.3" ry="2.9" fill="#FFFFFF"/>',
        '<circle cx="88.2" cy="104.6" r="1.1" fill="#FFFFFF"/>',
        shape("M69,100.5 C73,92.5 90,90.5 97.5,97 L98.5,99.5 C91,94.5 76.5,94.5 70.5,102.5 Z", LASH),
        shape("M69.5,100.5 L65.5,98.8 L70.6,102.4 Z", LASH),
        stroke("M76,107.8 Q84,110.3 91.5,107.2", LASH, 0.9, 0.5),
        stroke("M74,91.5 Q84,87.5 94,90.5", LASH, 0.8, 0.35),
    ])


def eye_defs(c: dict) -> str:
    return ""


def face(c: dict) -> str:
    mouths = {
        "smile": stroke("M95,126.5 Q100,130 105,126.5", "#A8485C", 1.4),
        "cat": stroke("M95,126.5 Q100,129 105,126.5", "#A8485C", 1.3),
        "smirk": stroke("M95.5,127.5 Q101,129 105.5,125.5", "#A8485C", 1.4),
        "fang": stroke("M95,126.5 Q100,129.5 105,126.5", "#A8485C", 1.4)
                + shape("M101.6,127.6 L103.4,127.4 L102.6,130 Z", "#FFFFFF", "#A8485C", 0.5),
    }
    freckles = "".join(f'<circle cx="{x}" cy="{y}" r="0.7" fill="#D99A80"/>'
                       for x, y in ((78, 113), (81, 115), (84, 113), (116, 113), (119, 115), (122, 113))
                       ) if c.get("freckles") else ""
    return "".join([
        '<ellipse cx="64" cy="104" rx="5" ry="7.5" fill="{s}" stroke="{l}" stroke-width="1.1"/>'.format(s=SKIN, l=SKIN_LINE),
        '<ellipse cx="136" cy="104" rx="5" ry="7.5" fill="{s}" stroke="{l}" stroke-width="1.1"/>'.format(s=SKIN, l=SKIN_LINE),
        shape("M64,88 C64,58 81,46 100,46 C119,46 136,58 136,88 C136,112 122,131 100,145"
              " C78,131 64,112 64,88 Z", SKIN, SKIN_LINE, 1.2),
        shape("M64.5,88 C64.5,111 77,131 100,144.5 C87,131 74,114 71,94 Z", SKIN_SHADE),       # cel shadow
        '<ellipse cx="78" cy="116" rx="8" ry="3.6" fill="#FF8FA8" opacity="0.22"/>',
        '<ellipse cx="122" cy="116" rx="8" ry="3.6" fill="#FF8FA8" opacity="0.22"/>',
        freckles,
        eye(c), f'<g {MIRROR}>{eye(c)}</g>',
        shape("M101.5,113 L99.2,120.2 L102.6,120.2 Z", SKIN_SHADE),                           # nose shadow
        stroke("M99.5,120.4 L102.4,120.4", SKIN_LINE, 0.9),
        mouths[c.get("mouth", "smile")],
    ])


def neck() -> str:
    return (shape("M92,126 L108,126 L109.5,162 L90.5,162 Z", SKIN, SKIN_LINE, 1.1)
            + shape("M92,126 L108,126 L108.6,140 Q100,146 91.4,140 Z", SKIN_SHADE))


# ---------------------------------------------------------------- hair
BANGS = ("M55,102 C50,66 70,36 100,34 C130,36 150,66 145,102 C142,90 138,82 133,77 C133,86 130,92 125,96"
         " C123,86 119,78 113,72 C113,80 109,86 103,89 C101,80 97,73 91,69 C89,79 85,86 79,90"
         " C79,82 75,76 69,73 C67,84 62,94 55,102 Z")
BANGS_SHADOW = ("M63,84 C66,80 69,78 71,80 C74,86 78,92 81,93 C86,90 89,82 91,74 C95,80 100,88 103,92"
                " C107,88 111,82 113,77 C117,84 121,92 125,98 C129,94 132,88 135,84 L137,78 L63,78 Z")
SIDE_SHORT = "M60,82 C51,100 52,122 57,138 C61,128 65,112 68,96 Z"
SIDE_LONG = "M61,80 C49,104 48,140 55,176 C62,160 66,128 69,98 Z"
STRANDS = ("M85,50 Q81,62 80,74", "M115,50 Q119,62 120,74")
SHINES = ("M74,58 C82,50 92,47 100,47 C92,50 84,54 78,62 Z", "M110,48 C118,49 126,54 130,60 C124,56 117,53 110,50 Z")


def hair_front(c: dict) -> str:
    side = SIDE_LONG if c.get("long") else SIDE_SHORT
    return "".join([
        shape(BANGS_SHADOW, SKIN_SHADE),                                           # bangs' shadow on the brow
        shape(side, c["hair"], c["hair_line"], 1.2), f'<g {MIRROR}>' + shape(side, c["hair"], c["hair_line"], 1.2) + "</g>",
        shape(side, "url(#cel)"), f'<g {MIRROR}>' + shape(side, "url(#cel)") + "</g>",
        shape(c.get("bangs", BANGS), c["hair"], c["hair_line"], 1.3),
        shape(c.get("bangs", BANGS), "url(#cel)"),
        "".join(shape(d, c["hair_light"], extra=' opacity="0.85"') for d in SHINES),
        "".join(stroke(d, c["hair_line"], 0.9, 0.4) for d in STRANDS),
        brows(c),
    ])


def brows(c: dict) -> str:
    """Drawn over the bangs, as anime does."""
    d = c.get("brow", "M74,86.5 Q82,83 91.5,85.2")
    return stroke(d, c["hair_line"], 1.5, 0.9) + f'<g {MIRROR}>' + stroke(d, c["hair_line"], 1.5, 0.9) + "</g>"


def hair_back(c: dict) -> str:
    if "back" in c:
        return c["back"]
    if c.get("long"):
        d = "M48,98 C42,52 72,28 100,28 C128,28 158,52 152,98 C156,130 160,160 164,186 L36,186 C40,160 44,130 48,98 Z"
    else:
        d = "M50,98 C45,54 72,30 100,30 C128,30 155,54 150,98 C152,112 150,124 146,132 L54,132 C50,124 48,112 50,98 Z"
    return shape(d, "url(#hairback)", c["hair_line"], 1.3)


# ---------------------------------------------------------------- body
def body(c: dict) -> str:
    return "".join([
        shape("M26,200 C28,170 58,154 100,154 C142,154 172,170 174,200 Z", "url(#outfit)", c["outfit_line"], 1.3),
        stroke("M56,178 Q62,190 60,200", c["outfit_line"], 1.0, 0.5),
        stroke("M144,178 Q138,190 140,200", c["outfit_line"], 1.0, 0.5),
        shape("M86,154 L100,176 L114,154 L108,154 L100,166 L92,154 Z", c["trim"], c["outfit_line"], 1.1),
        c.get("body_extra", ""),
    ])


def svg(c: dict) -> str:
    defs = "".join([
        lin("hair", (0, c["hair"]), (1, c["hair"])),
        lin("hairback", (0, c["hair_dark"]), (1, c["hair_dark"])),
        lin("outfit", (0, c["outfit_dark"]), (0.3, c["outfit_dark"]), (0.31, c["outfit"]), (1, c["outfit"]),
            x2=1, y2=0),                                    # cel shadow on the left, like the face
        lin("cel", (0, c["hair_dark"]), (0.6, c["hair_dark"]), (0.61, c["hair_dark"]), (1, c["hair_dark"]),
            opacity=(0, 0, 0.5, 0.5)),
        c.get("defs", ""),
    ])
    scene_defs, scene = SCENES[c["name"]]()
    head = hair_back(c)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200">'
            f"<defs>{defs}{scene_defs}{FLARE_DEFS}</defs>"
            + scene + c.get("prop", "")
            + f"<g {HEAD}>{head}</g>" + neck() + body(c)
            + f"<g {HEAD}>{face(c)}{hair_front(c)}{c.get('front', '')}</g>"
            + flare(c.get("flare", (0.0, 0.0))) + "</svg>")


# ---------------------------------------------------------------- scenes (behind the hero)
def sky(id_: str, *stops) -> tuple[str, str]:
    return lin(id_, *stops), f'<rect x="0" y="0" width="200" height="200" fill="url(#{id_})"/>'


def glow(id_: str, x: float, y: float, r: float, color: str, a: float) -> tuple[str, str]:
    return (rad(id_, x, y, r, (0, color, a), (1, color, 0)),
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="url(#{id_})"/>')


def dots(seed: int, n: int, box: tuple, color: str, size: tuple, alpha: tuple) -> str:
    rng = random.Random(seed)
    x0, y0, x1, y1 = box
    return "".join(f'<circle cx="{rng.uniform(x0, x1):.1f}" cy="{rng.uniform(y0, y1):.1f}"'
                   f' r="{rng.uniform(*size):.2f}" fill="{color}" opacity="{rng.uniform(*alpha):.2f}"/>'
                   for _ in range(n))


def ridge(seed: int, base: float, amp: float, step: float, color: str, rough: float = 0.5) -> str:
    """A silhouette from x=0 to 200 along y=base, closed to the bottom."""
    rng = random.Random(seed)
    pts, x = [], -10.0
    while x <= 210:
        pts.append(f"L{x:.1f},{base - amp * (0.5 + rough * (rng.random() - 0.5)) * (1 + math.sin(x / 31 + seed)) / 2:.1f}")
        x += step
    return f'<path d="M-10,210 {" ".join(pts)} L210,210 Z" fill="{color}"/>'


def trees(seed: int, n: int, y: float, r: tuple, color: str, shade: str) -> str:
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        x, rr = rng.uniform(-10, 210), rng.uniform(*r)
        out.append(f'<rect x="{x - rr * 0.12:.1f}" y="{y - rr * 0.2:.1f}" width="{rr * 0.24:.1f}" height="{rr * 1.4:.1f}"'
                   f' fill="{shade}"/>')
        for dx, dy, k in ((0, -rr * 0.9, 1), (-rr * 0.6, -rr * 0.4, 0.8), (rr * 0.6, -rr * 0.4, 0.8)):
            out.append(f'<circle cx="{x + dx:.1f}" cy="{y + dy:.1f}" r="{rr * k:.1f}" fill="{color}"/>')
        out.append(f'<circle cx="{x + rr * 0.3:.1f}" cy="{y - rr * 1.1:.1f}" r="{rr * 0.45:.1f}" fill="#FFFFFF" opacity="0.12"/>')
    return "".join(out)


def leaf(x: float, y: float, s: float, a: float, color: str, vein: str) -> str:
    return (f'<g transform="translate({x} {y}) rotate({a}) scale({s})">'
            f'<path d="M0,0 C10,-14 34,-14 44,0 C34,14 10,14 0,0 Z" fill="{color}" stroke="{vein}" stroke-width="1"/>'
            f'<path d="M2,0 L40,0" stroke="{vein}" stroke-width="0.9" opacity="0.7"/></g>')


def scene_warrior() -> tuple[str, str]:
    d1, b1 = sky("bg", (0, "#3A0A16"), (0.45, "#B3263A"), (0.8, "#FF7B52"), (1, "#FFC07A"))
    d2, sun = glow("sun", 150, 150, 70, "#FFE2A0", 0.95)
    keep = ('<path d="M-10,210 L-10,150 L12,150 L12,128 L18,128 L18,122 L24,122 L24,128 L30,128 L30,150 L46,150'
            ' L46,138 L52,138 L52,150 L70,146 L84,150 L118,152 L132,144 L132,118 L136,112 L140,118 L140,144'
            ' L160,148 L176,140 L176,124 L182,124 L182,118 L188,118 L188,124 L194,124 L194,140 L210,146 L210,210 Z"'
            ' fill="#4A0F1C"/>'
            '<path d="M136,112 L136,96 L150,102 L136,106" fill="#FFB347"/>'
            '<path d="M21,122 L21,108 L33,112 L21,116" fill="#FFB347"/>')
    ground = ridge(3, 182, 26, 12, "#2A0610", 0.8)
    embers = dots(11, 26, (0, 20, 200, 180), "#FFB347", (0.6, 1.8), (0.4, 0.95))
    return d1 + d2, b1 + '<circle cx="150" cy="150" r="22" fill="#FFE9B8"/>' + sun + keep + ground + embers


def scene_ranger() -> tuple[str, str]:
    d1, b1 = sky("bg", (0, "#BFEFD0"), (0.55, "#F2F7C8"), (1, "#FFF2C2"))
    d2, sun = glow("sun", 40, 30, 80, "#FFFFFF", 0.9)
    far = ridge(5, 120, 40, 9, "#8CCB9A", 0.9) + trees(6, 9, 128, (12, 18), "#76B887", "#5A8F69")
    mid = trees(7, 7, 160, (16, 26), "#3E8A55", "#2C5E3B")
    shafts = "".join(f'<path d="M{x},0 L{x + 26},0 L{x - 30},200 L{x - 56},200 Z" fill="#FFFFFF" opacity="0.13"/>'
                     for x in (60, 120, 175))
    fg = leaf(-6, 196, 1.3, -40, "#2F7A44", "#1E5530") + leaf(170, 200, 1.4, -140, "#2F7A44", "#1E5530")
    return d1 + d2, b1 + sun + far + shafts + mid + fg


def scene_huntress() -> tuple[str, str]:
    d1, b1 = sky("bg", (0, "#7FE3DA"), (0.6, "#D8FFF6"), (1, "#E9FFF2"))
    d2, water = lin("water", (0, "#2EC4B6"), (1, "#0F6A72")), ""
    ruins = ('<path d="M-10,150 L-10,70 L6,62 L22,70 L22,150 Z" fill="#5E9E98"/>'
             '<path d="M-6,80 L18,80 M-6,100 L18,100 M-6,120 L18,120" stroke="#4A807A" stroke-width="2"/>'
             '<path d="M168,150 L168,84 L178,78 L188,84 L188,150 Z" fill="#5E9E98"/>'
             '<path d="M196,150 L196,96 L210,96 L210,150 Z" fill="#6FB0A9"/>'
             '<path d="M160,84 L196,84 L196,90 L160,90 Z" fill="#4A807A"/>')
    hills = ridge(9, 140, 30, 10, "#9ED9C4", 0.8)
    lagoon = ('<rect x="-10" y="148" width="220" height="62" fill="url(#water)"/>'
              + "".join(f'<path d="M{x},{y} L{x + w},{y}" stroke="#FFFFFF" stroke-width="1.4" opacity="0.6"/>'
                        for x, y, w in ((20, 158, 24), (120, 166, 30), (60, 176, 18), (150, 186, 26))))
    ferns = leaf(-8, 200, 1.4, -55, "#1F8A6A", "#0E5A45") + leaf(178, 204, 1.3, -125, "#1F8A6A", "#0E5A45")
    return d1 + d2, b1 + hills + ruins + lagoon + ferns + water


def scene_mercenary() -> tuple[str, str]:
    d1, b1 = sky("bg", (0, "#FF9F43"), (0.5, "#FFC56E"), (1, "#FFE6A8"))
    d2, sun = glow("sun", 34, 120, 70, "#FFF4D0", 0.9)
    dunes = ridge(12, 150, 24, 14, "#E89A4A", 0.6) + ridge(13, 172, 22, 16, "#C9752E", 0.6)
    town = ('<path d="M120,150 L120,128 L134,128 L134,150 Z M138,150 L138,118 L150,118 L150,150 Z'
            ' M154,150 L154,132 L170,132 L170,150 Z M174,150 L174,110 L180,104 L186,110 L186,150 Z" fill="#9C5524"/>'
            '<path d="M180,104 L180,88" stroke="#9C5524" stroke-width="2"/><path d="M180,88 L192,92 L180,96 Z" fill="#E2553B"/>'
            '<path d="M124,134 L130,134 M142,124 L146,124 M158,138 L166,138" stroke="#FFD27A" stroke-width="2"/>')
    dust = dots(21, 30, (0, 60, 200, 200), "#FFF0C8", (0.5, 1.4), (0.3, 0.8))
    return d1 + d2, b1 + '<circle cx="34" cy="120" r="20" fill="#FFF8E0"/>' + sun + town + dunes + dust


def scene_monk() -> tuple[str, str]:
    d1, b1 = sky("bg", (0, "#5BB8FF"), (0.55, "#BFE6FF"), (1, "#EAF7FF"))
    peaks = (ridge(31, 120, 70, 18, "#A8D4F2", 1.0) + '<rect x="-10" y="112" width="220" height="16" fill="#FFFFFF" opacity="0.5"/>'
             + ridge(32, 150, 50, 20, "#7FB6DE", 1.0))
    pagoda = ('<path d="M10,150 L10,124 L40,124 L40,150 Z" fill="#3F6E99"/>'
              '<path d="M0,126 Q25,114 50,126 L46,120 Q25,108 4,120 Z" fill="#2E5478"/>'
              '<path d="M14,112 L36,112 L36,124 L14,124 Z" fill="#3F6E99"/>'
              '<path d="M6,114 Q25,100 44,114 L40,108 Q25,96 10,108 Z" fill="#2E5478"/>'
              '<path d="M25,96 L25,88" stroke="#2E5478" stroke-width="2"/>')
    clouds = "".join(f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="#FFFFFF" opacity="0.8"/>'
                     for x, y, rx, ry in ((40, 40, 30, 9), (62, 36, 20, 8), (170, 60, 26, 8), (150, 64, 18, 6)))
    petals = "".join(f'<ellipse cx="{x}" cy="{y}" rx="2.6" ry="1.4" fill="#FFB7D5" transform="rotate({a} {x} {y})"/>'
                     for x, y, a in ((20, 70, 30), (178, 30, -20), (160, 120, 60), (34, 160, 10), (188, 160, -40),
                                     (8, 110, 80), (140, 20, 45)))
    return d1, b1 + clouds + peaks + pagoda + ridge(33, 182, 20, 16, "#5E95C2", 0.8) + petals


def scene_witch() -> tuple[str, str]:
    d1, b1 = sky("bg", (0, "#12062E"), (0.6, "#3A1A72"), (1, "#7A4AC0"))
    d2, moon = glow("moon", 46, 46, 60, "#E7D6FF", 0.7)
    stars = dots(41, 40, (0, 0, 200, 120), "#FFFFFF", (0.4, 1.2), (0.4, 1.0))
    graves = ('<path d="M150,160 L150,138 C150,128 166,128 166,138 L166,160 Z M172,162 L172,146 C172,140 182,140 182,146'
              ' L182,162 Z" fill="#2A1556"/>'
              '<path d="M12,162 L12,128 M2,138 L22,138" stroke="#2A1556" stroke-width="4"/>'
              '<path d="M178,128 L178,108 C178,96 196,96 196,108 L196,130" fill="#2A1556"/>')
    spire = ('<path d="M120,150 L124,96 L118,96 L128,70 L138,96 L132,96 L136,150 Z" fill="#241048"/>'
             '<path d="M126,108 L130,108 L130,116 L126,116 Z" fill="#FFD27A"/>')
    mist = "".join(f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="7" fill="#C9A7FF" opacity="0.22"/>'
                   for x, y, rx in ((40, 168, 60), (150, 176, 70), (100, 186, 90)))
    wisps = "".join(twinkle(x, y, s, "#E7C4FF", 0.9) for x, y, s in ((24, 100, 3), (186, 80, 2.5), (160, 26, 2)))
    return d1 + d2, (b1 + stars + moon + '<circle cx="46" cy="46" r="18" fill="#F4ECFF"/>'
                     '<circle cx="54" cy="42" r="16" fill="#3A1A72" opacity="0.35"/>'
                     + ridge(42, 168, 28, 12, "#1C0C3E", 0.8) + spire + graves + mist + wisps)


def scene_sorceress() -> tuple[str, str]:
    d1, b1 = sky("bg", (0, "#0A1A4A"), (0.55, "#1F4AB8"), (1, "#5C8CFF"))
    clouds = "".join(f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="#0E2466" opacity="0.8"/>'
                     for x, y, rx, ry in ((30, 30, 50, 16), (160, 20, 60, 18), (100, 10, 40, 12)))
    bolts = ('<path d="M150,24 L140,52 L148,52 L136,84 L158,46 L150,46 L158,24 Z" fill="#CFF4FF" opacity="0.85"/>'
             '<path d="M40,30 L34,48 L40,48 L32,70" stroke="#CFF4FF" stroke-width="1.6" fill="none" opacity="0.6"/>')
    d2, ring = glow("arcane", 100, 186, 90, "#7FD8FF", 0.55)
    circle = ('<ellipse cx="100" cy="190" rx="90" ry="16" fill="none" stroke="#9EE7FF" stroke-width="1.6" opacity="0.7"/>'
              '<ellipse cx="100" cy="190" rx="70" ry="11" fill="none" stroke="#9EE7FF" stroke-width="1" opacity="0.6"/>')
    crystals = "".join(f'<path d="M{x},{y - h} L{x + w},{y} L{x},{y + h * 0.6} L{x - w},{y} Z" fill="#8FE0FF"'
                       f' stroke="#E6FBFF" stroke-width="0.8" opacity="0.85"/>'
                       for x, y, w, h in ((176, 120, 6, 14), (12, 120, 5, 12), (190, 160, 4, 9), (40, 96, 3, 7)))
    return d1 + d2, b1 + clouds + bolts + ridge(51, 170, 30, 14, "#122E7A", 0.7) + ring + circle + crystals


def scene_druid() -> tuple[str, str]:
    d1, b1 = sky("bg", (0, "#0F3A22"), (0.55, "#2E7A45"), (1, "#7CC46E"))
    d2, sun = glow("sun", 100, 20, 90, "#E9FFB8", 0.55)
    trunks = ('<path d="M-10,210 L-10,0 L22,0 C18,60 26,120 34,210 Z" fill="#3B2412"/>'
              '<path d="M210,210 L210,0 L176,0 C182,70 172,130 166,210 Z" fill="#3B2412"/>'
              '<path d="M4,0 C2,60 8,120 14,210" stroke="#5A3A20" stroke-width="2" fill="none"/>'
              '<path d="M196,0 C198,70 190,130 186,210" stroke="#5A3A20" stroke-width="2" fill="none"/>')
    canopy = trees(61, 8, 30, (20, 30), "#1E5A32", "#1E5A32")
    shrooms = ('<path d="M30,196 L30,184 M28,184 Q32,174 40,184 Z" stroke="#F2E6C9" stroke-width="2" fill="#E2553B"/>'
               '<path d="M168,198 L168,188 M162,188 Q168,178 176,188 Z" stroke="#F2E6C9" stroke-width="2" fill="#E2553B"/>')
    flies = dots(71, 22, (0, 20, 200, 190), "#F6FF9A", (0.8, 2.0), (0.5, 1.0))
    ferns = leaf(-6, 204, 1.3, -50, "#3E9A4E", "#1F5A2A") + leaf(176, 206, 1.3, -130, "#3E9A4E", "#1F5A2A")
    return d1 + d2, b1 + sun + canopy + trunks + ridge(62, 176, 20, 12, "#1F5A2A", 0.8) + shrooms + ferns + flies


SCENES = {"warrior": scene_warrior, "ranger": scene_ranger, "huntress": scene_huntress,
          "mercenary": scene_mercenary, "monk": scene_monk, "witch": scene_witch,
          "sorceress": scene_sorceress, "druid": scene_druid}


# ---------------------------------------------------------------- light flares (in front of everything)
FLARE_DEFS = ('<linearGradient id="beam" x1="0" y1="0" x2="1" y2="1">'
              '<stop offset="0" stop-color="#FFFFFF" stop-opacity="0"/>'
              '<stop offset="0.4" stop-color="#FFFFFF" stop-opacity="0.32"/>'
              '<stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>'
              '<linearGradient id="prism" x1="0" y1="0" x2="1" y2="1">'
              '<stop offset="0" stop-color="#FF9AD5" stop-opacity="0"/>'
              '<stop offset="0.4" stop-color="#9AE7FF" stop-opacity="0.3"/>'
              '<stop offset="1" stop-color="#FFF59A" stop-opacity="0"/></linearGradient>')


def flare(shift: tuple[float, float]) -> str:
    """Two diagonal beams from the upper right, a prism fringe, bokeh and a twinkle (as in anime key art)."""
    dx, dy = shift
    beams = (f'<path d="M{206 + dx},{-8 + dy} L{218 + dx},{4 + dy} L{70 + dx},{214 + dy} L{58 + dx},{202 + dy} Z"'
             f' fill="url(#beam)"/>'
             f'<path d="M{221 + dx},{6 + dy} L{223 + dx},{8 + dy} L{76 + dx},{216 + dy} L{74 + dx},{214 + dy} Z"'
             f' fill="url(#prism)"/>')
    bokeh = "".join(f'<circle cx="{x + dx}" cy="{y + dy}" r="{r}" fill="#FFFFFF" opacity="{a}"/>'
                    for x, y, r, a in ((176, 40, 7, 0.16), (160, 62, 3.5, 0.22), (140, 92, 9, 0.08), (186, 74, 2.5, 0.3)))
    return beams + bokeh + twinkle(176 + dx, 36 + dy, 6, "#FFFFFF", 0.95)


# ---------------------------------------------------------------- classes
def mace() -> str:
    spikes = "".join(
        shape(f"M{178 + 13 * dx},{58 + 13 * dy} L{178 + 27 * dx - 4 * dy},{58 + 27 * dy + 4 * dx}"
              f" L{178 + 27 * dx + 4 * dy},{58 + 27 * dy - 4 * dx} Z", "#8C96AB", "#4A5266", 1.1)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (.71, .71), (-.71, -.71), (.71, -.71), (-.71, .71)))
    return (shape("M146,196 L172,74 L180,76 L155,198 Z", "url(#wood)", "#4A3220", 1.4)
            + spikes + '<circle cx="178" cy="58" r="18" fill="url(#steel)" stroke="#4A5266" stroke-width="1.6"/>'
            + '<ellipse cx="172" cy="51" rx="6" ry="4" fill="#FFFFFF" opacity="0.6"/>'
            + shape("M162,128 L172,130 L170,140 L160,138 Z", "#E2553B", "#7A2A1E", 1.1))


WOOD = lin("wood", (0, "#A8774A"), (1, "#6B4A2E"), x2=1, y2=0)
STEEL = rad("steel", 172, 52, 22, (0, "#F4F7FB", 1), (0.5, "#AEB8CC", 1), (1, "#6F7A92", 1))

CLASSES: dict[str, dict] = {
    "warrior": dict(
        hair="#FF7F50", hair_light="#FFB08A", hair_dark="#B83A24", hair_line="#7A2416",
        eye_dark="#7A3510", eye_mid="#D9782C", eye_light="#FFD27A", eye_glow="#FFE3A3",
        outfit="#D5DCEA", outfit_dark="#8792AB", outfit_line="#4A5266", trim="#E2553B", mouth="fang",
        brow="M73,87.5 Q81,81.5 91.5,83.5",
        bangs=("M54,100 C50,66 70,34 100,32 C130,34 150,66 146,100 L139,82 L133,94 L126,74 L119,90 L111,68"
               " L104,88 L97,66 L90,88 L82,70 L76,91 L69,76 L63,94 Z"),
        defs=WOOD + STEEL, prop=mace(),
        body_extra=(shape("M28,184 C26,164 40,154 58,156 C72,158 78,170 76,184 Z", "url(#steel)", "#4A5266", 1.6)
                    + shape("M172,184 C174,164 160,154 142,156 C128,158 122,170 124,184 Z", "url(#steel)", "#4A5266", 1.6)
                    + stroke("M34,176 Q50,164 70,174", "#E2553B", 3)
                    + stroke("M166,176 Q150,164 130,174", "#E2553B", 3)
                    + '<circle cx="100" cy="186" r="6" fill="#F2C14E" stroke="#8A6A1E" stroke-width="1.2"/>'),
        front=(shape("M56,72 Q100,54 144,72 L144,82 Q100,64 56,82 Z", "#2E3A59", "#151C2E", 1.3)
               + shape("M88,60 L112,60 L110,72 L90,72 Z", "url(#steel)", "#4A5266", 1.2)
               + shape("M144,74 L166,62 L161,84 Z", "#2E3A59", "#151C2E", 1.2)
               + shape("M144,78 L162,90 L150,92 Z", "#2E3A59", "#151C2E", 1.2)),
    ),
    "ranger": dict(
        hair="#FFD978", hair_light="#FFF1BF", hair_dark="#D49A3A", hair_line="#8A5A1C",
        eye_dark="#1E5A36", eye_mid="#3FA866", eye_light="#B8F59A", eye_glow="#D8FFC2",
        outfit="#6BBF7B", outfit_dark="#2F6B42", outfit_line="#1F4A2D", trim="#F2D27A", mouth="cat",
        defs=WOOD,
        prop=(stroke("M26,34 Q-8,110 26,186", "#4A3220", 9) + stroke("M26,34 Q-8,110 26,186", "url(#wood)", 6)
              + stroke("M26,34 L26,186", "#F5EBD0", 1.6)
              + shape("M20,30 L32,30 L30,40 L22,40 Z", "#F2C14E", "#8A6A1E", 1)),
        back=(shape("M38,108 C30,44 66,16 100,16 C134,16 170,44 162,108 L170,170 L30,170 Z", "url(#outfit)",
                    "#1F4A2D", 1.8)
              + shape("M52,100 C48,60 72,40 100,40 C128,40 152,60 148,100 L148,132 L52,132 Z", "url(#hairback)",
                      "#8A5A1C", 1.4)),
        front=(shape("M38,108 C30,44 66,16 100,16 C134,16 170,44 162,108 C152,62 128,40 100,40 C72,40 48,62 38,108 Z",
                     "url(#outfit)", "#1F4A2D", 1.8)
               + stroke("M52,46 Q100,22 148,46", "#9BE3A8", 2, 0.6)
               + shape("M150,40 Q182,22 190,0 Q176,30 156,48 Z", "#E85D5D", "#8A2A2A", 1.2)
               + stroke("M153,42 Q176,26 188,4", "#FFFFFF", 1.1, 0.8)),
        body_extra=(shape("M60,166 L100,200 L140,166 L132,162 L100,190 L68,162 Z", "#4A8F59", "#1F4A2D", 1.2)
                    + '<circle cx="100" cy="176" r="5" fill="#F2D27A" stroke="#8A6A1E" stroke-width="1.2"/>'),
    ),
    "huntress": dict(
        hair="#2EC4B6", hair_light="#9FF5EA", hair_dark="#0F6A72", hair_line="#06474D",
        eye_dark="#08484F", eye_mid="#1FA7A0", eye_light="#9DFCEE", eye_glow="#CFFFF6",
        outfit="#C08A5E", outfit_dark="#6E4529", outfit_line="#3E2514", trim="#2EC4B6", mouth="smirk",
        brow="M73,86.5 Q81,82 91.5,84",
        defs=WOOD + STEEL,
        prop=(shape("M16,194 L166,28 L172,34 L22,200 Z", "url(#wood)", "#3E2514", 1.4)
              + shape("M166,28 L196,0 L180,40 L170,36 Z", "url(#steel)", "#4A5266", 1.4)
              + stroke("M160,34 L174,48", "#2EC4B6", 6) + stroke("M160,34 L174,48", "#06474D", 1, 0.5)
              + shape("M162,44 Q150,60 156,74 Q164,58 170,50 Z", "#FFFFFF", "#9FB8C8", 1)),
        back=(shape("M48,98 C42,52 72,28 100,28 C128,28 158,52 152,98 L150,132 L50,132 Z", "url(#hairback)",
                    "#06474D", 1.6)
              + shape("M136,44 C170,30 196,66 186,112 C182,140 174,158 166,170 C168,140 164,110 150,90 Z",
                      "url(#hair)", "#06474D", 1.6)
              + stroke("M150,52 Q180,70 176,120", "#06474D", 1, 0.5)),
        front=('<circle cx="142" cy="48" r="6.5" fill="#F2C14E" stroke="#8A6A1E" stroke-width="1.2"/>'
               + stroke("M58,74 Q64,70 70,74", "#F2C14E", 2.4)),
        body_extra=(shape("M30,200 C34,176 50,162 74,158 L82,200 Z", "#8A5A36", "#3E2514", 1.2)
                    + stroke("M44,188 L76,166", "#2EC4B6", 3)),
    ),
    "mercenary": dict(
        hair="#9A6A47", hair_light="#D3A27A", hair_dark="#5A361E", hair_line="#3A2212",
        eye_dark="#6A3510", eye_mid="#D07A22", eye_light="#FFD08A", eye_glow="#FFE6B8",
        outfit="#4E5672", outfit_dark="#22263A", outfit_line="#141826", trim="#F4A340", mouth="smirk",
        brow="M73,87 Q80,81.5 91,83",
        bangs=("M54,100 C50,62 72,32 100,32 C128,32 150,62 146,100 C142,88 138,80 134,75 C134,84 130,91 126,95"
               " C124,84 120,74 114,67 C114,78 110,86 104,91 C102,80 98,71 92,64 C90,76 86,85 80,90"
               " C80,80 76,73 70,70 C68,82 62,92 54,100 Z"),
        defs=WOOD + STEEL,
        prop=(shape("M112,44 L192,38 L193,46 L113,52 Z", "url(#wood)", "#3A2212", 1.4)
              + stroke("M152,8 Q174,42 150,76", "#3A2212", 8) + stroke("M152,8 Q174,42 150,76", "#8C96AB", 5)
              + stroke("M152,8 L134,42 L150,76", "#F5EBD0", 1.3)
              + shape("M193,42 L182,34 L182,50 Z", "url(#steel)", "#4A5266", 1.1)),
        body_extra=(shape("M30,200 C32,174 50,160 76,156 L92,200 Z", "#3A4058", "#141826", 1.3)
                    + shape("M170,200 C168,174 150,160 124,156 L108,200 Z", "#3A4058", "#141826", 1.3)
                    + "".join(f'<circle cx="100" cy="{y}" r="3.4" fill="#F4A340" stroke="#8A5A10" stroke-width="1"/>'
                              for y in (178, 190))
                    + stroke("M40,190 L74,170", "#F4A340", 2.4)),
        front=(shape("M64,52 Q100,42 136,52 L136,62 Q100,52 64,62 Z", "#3A2A2A", "#1A1010", 1.2)
               + '<circle cx="82" cy="56" r="12" fill="#3A2A2A"/><circle cx="118" cy="56" r="12" fill="#3A2A2A"/>'
               + '<circle cx="82" cy="56" r="8.5" fill="url(#lens)"/><circle cx="118" cy="56" r="8.5" fill="url(#lens)"/>'
               + '<ellipse cx="79" cy="53" rx="3" ry="2.2" fill="#FFFFFF" opacity="0.9"/>'
               + '<ellipse cx="115" cy="53" rx="3" ry="2.2" fill="#FFFFFF" opacity="0.9"/>'),
    ),
    "monk": dict(
        hair="#3B3B5C", hair_light="#8C8CC0", hair_dark="#16162A", hair_line="#0C0C18",
        eye_dark="#0F4A8A", eye_mid="#3D9BE8", eye_light="#B8E8FF", eye_glow="#D8F4FF",
        outfit="#F7F9FF", outfit_dark="#C4D6F2", outfit_line="#5A6E92", trim="#5BB8FF", mouth="smile",
        defs=WOOD,
        prop=(shape("M164,198 L164,12 L172,12 L172,198 Z", "url(#wood)", "#4A3220", 1.4)
              + shape("M162,28 L174,28 L174,38 L162,38 Z", "#5BB8FF", "#1F5A8A", 1.1)
              + shape("M162,158 L174,158 L174,168 L162,168 Z", "#5BB8FF", "#1F5A8A", 1.1)
              + stroke("M10,118 Q32,92 60,106", "#5BB8FF", 4, 0.7)
              + stroke("M4,140 Q28,114 54,128", "#5BB8FF", 3, 0.5)
              + stroke("M14,98 Q30,82 48,88", "#9FD8FF", 2, 0.5)),
        back=('<circle cx="100" cy="26" r="17" fill="url(#hair)" stroke="#0C0C18" stroke-width="1.6"/>'
              + stroke("M88,20 Q100,12 112,20", "#8C8CC0", 2, 0.7)
              + shape("M50,98 C45,54 72,32 100,32 C128,32 155,54 150,98 C152,112 150,124 146,132 L54,132"
                      " C50,124 48,112 50,98 Z", "url(#hairback)", "#0C0C18", 1.6)),
        body_extra=(shape("M60,152 Q100,140 140,152 L132,200 L68,200 Z", "#EAF2FF", "#5A6E92", 1.2)
                    + stroke("M76,154 L100,190 L124,154", "#5BB8FF", 3)
                    + "".join(f'<circle cx="{100 + 32 * dx}" cy="{152 + 16 * dy}" r="4.6" fill="url(#wood)"'
                              f' stroke="#4A3220" stroke-width="1"/>'
                              for dx, dy in ((-1, 0), (-.72, .58), (-.38, .9), (0, 1), (.38, .9), (.72, .58), (1, 0)))),
        front=shape("M92,10 L108,10 L108,16 L92,16 Z", "#5BB8FF", "#1F5A8A", 1.1),
    ),
    "witch": dict(
        hair="#ECE4FF", hair_light="#FFFFFF", hair_dark="#9D86DA", hair_line="#5A3E9E", long=True,
        eye_dark="#4A1690", eye_mid="#9B4BF0", eye_light="#E7C4FF", eye_glow="#F2DEFF",
        outfit="#7550D0", outfit_dark="#33206A", outfit_line="#1E1240", trim="#C9A7FF", mouth="fang",
        prop=('<g opacity="0.9">'
              + shape("M18,150 C18,136 42,136 42,150 C42,158 38,162 36,166 L24,166 C22,162 18,158 18,150 Z",
                      "#F6F2FF", "#7A6AAE", 1.2)
              + '<circle cx="25.5" cy="150" r="3.6" fill="#5A3E9E"/><circle cx="34.5" cy="150" r="3.6" fill="#5A3E9E"/>'
              + stroke("M24,166 L24,170 M28,166 L28,170 M32,166 L32,170 M36,166 L36,170", "#7A6AAE", 1)
              + stroke("M16,174 Q8,186 18,196", "#C9A7FF", 3, 0.6) + "</g>"
              + twinkle(30, 128, 4, "#E7C4FF") + twinkle(14, 136, 2.5, "#FFFFFF")),
        front=(shape("M24,62 C40,50 160,50 176,62 C160,74 40,74 24,62 Z", "url(#hat)", "#1E1240", 1.6)
               + shape("M58,60 C66,34 84,16 104,8 C124,2 142,-2 156,-6 C140,8 132,20 134,34 C138,46 142,54 144,60"
                       " C116,66 84,66 58,60 Z", "url(#hat)", "#1E1240", 1.6)
               + shape("M60,52 C86,44 116,44 142,52 L143,61 C116,54 86,54 59,61 Z", "#F2C14E", "#8A6A1E", 1.2)
               + shape("M93,50 C93,43 107,43 107,50 C107,54 104,56 103,58 L97,58 C96,56 93,54 93,50 Z",
                       "#F6F2FF", "#1E1240", 1)
               + '<circle cx="97.5" cy="50" r="1.8" fill="#33206A"/><circle cx="102.5" cy="50" r="1.8" fill="#33206A"/>'
               + stroke("M78,34 Q96,18 118,12", "#B79CFF", 2, 0.5)),
        defs=lin("hat", (0, "#7A55D8"), (1, "#3A2478")),
        body_extra=(shape("M58,152 Q100,168 142,152 L136,170 Q100,184 64,170 Z", "#33206A", "#1E1240", 1.2)
                    + '<circle cx="100" cy="174" r="5.5" fill="#C9A7FF" stroke="#1E1240" stroke-width="1"/>'),
    ),
    "sorceress": dict(
        hair="#7FA8FF", hair_light="#D4E2FF", hair_dark="#2E4FC0", hair_line="#172B7A", long=True,
        eye_dark="#122D8C", eye_mid="#3E7BFF", eye_light="#A8F0FF", eye_glow="#D2FAFF",
        outfit="#FFFFFF", outfit_dark="#BFCDF5", outfit_line="#4A5C9A", trim="#4D7CFF", mouth="cat",
        defs=lin("gold", (0, "#FFE7A0"), (1, "#C9962E")),
        prop=(shape("M22,198 L22,54 L30,54 L30,198 Z", "url(#gold)", "#8A6A1E", 1.3)
              + '<circle cx="26" cy="38" r="19" fill="#9EE7FF" opacity="0.3"/>'
              + '<circle cx="26" cy="38" r="12" fill="url(#orb)" stroke="#2E6FA8" stroke-width="1.3"/>'
              + '<ellipse cx="22" cy="33" rx="4" ry="3" fill="#FFFFFF"/>'
              + shape("M14,54 Q26,62 38,54 L34,50 Q26,56 18,50 Z", "url(#gold)", "#8A6A1E", 1)
              + shape("M180,26 L166,62 L177,62 L163,100 L192,52 L181,52 L192,26 Z", "#FFE066", "#C9962E", 1.3)
              + twinkle(154, 40, 4) + twinkle(190, 92, 3)),
        body_extra=(stroke("M66,154 Q100,190 134,154", "url(#gold)", 3)
                    + shape("M93,176 L100,166 L107,176 L100,186 Z", "#4D7CFF", "#172B7A", 1.1)),
        front=(shape("M66,50 Q100,34 134,50 L130,57 Q100,44 70,57 Z", "url(#gold)", "#8A6A1E", 1.2)
               + shape("M100,30 L109,45 L100,53 L91,45 Z", "#4D7CFF", "#172B7A", 1.2)
               + '<ellipse cx="98" cy="40" rx="2" ry="3" fill="#FFFFFF" opacity="0.9"/>'),
    ),
    "druid": dict(
        hair="#B9744A", hair_light="#EAB08A", hair_dark="#6A381C", hair_line="#3E1E0C", long=True,
        eye_dark="#3E5E10", eye_mid="#8CC23A", eye_light="#E8FF9A", eye_glow="#F2FFC8",
        outfit="#5FAF6E", outfit_dark="#2C6A3A", outfit_line="#163C20", trim="#F2E6C9", mouth="smile",
        back=(shape("M60,44 Q46,16 58,-2 M58,20 Q42,18 38,6 M56,30 Q44,32 36,26", "none", "#7A5A3A", 6.5)
              + shape("M60,44 Q46,16 58,-2 M58,20 Q42,18 38,6 M56,30 Q44,32 36,26", "none", "#EAD7B5", 4)
              + f'<g {MIRROR}>'
              + shape("M60,44 Q46,16 58,-2 M58,20 Q42,18 38,6 M56,30 Q44,32 36,26", "none", "#7A5A3A", 6.5)
              + shape("M60,44 Q46,16 58,-2 M58,20 Q42,18 38,6 M56,30 Q44,32 36,26", "none", "#EAD7B5", 4)
              + "</g>"
              + shape("M48,98 C42,52 72,28 100,28 C128,28 158,52 152,98 C160,124 150,144 160,164 C150,176 140,180 130,184"
                      " L70,184 C60,180 50,176 40,164 C50,144 40,124 48,98 Z", "url(#hairback)", "#3E1E0C", 1.6)),
        body_extra=(shape("M30,198 C34,166 56,154 72,152 Q100,170 128,152 C144,154 166,166 170,198"
                          " C150,182 128,178 100,186 C72,178 50,182 30,198 Z", "url(#fur)", "#8A7A5A", 1.3)
                    + stroke("M50,180 Q56,174 62,178 M138,178 Q144,174 150,180", "#B8A880", 1.1)),
        prop="".join(stroke(f"M{150 + d},{118} Q{178 + d},{150} {160 + d},{198}", "#F2E6C9", 4, 0.85)
                     for d in (0, 12, 24)),
        defs=lin("fur", (0, "#FFF6E0"), (1, "#D9C9A4")),
        front=("".join(shape(f"M{x - 9},{y} Q{x},{y - 7} {x + 9},{y} Q{x},{y + 7} {x - 9},{y} Z", col, "#235A2A", 1,
                             extra=f' transform="rotate({a} {x} {y})"')
                       + stroke(f"M{x - 7},{y} L{x + 7},{y}", "#235A2A", 0.8, 0.6).replace(
                           "/>", f' transform="rotate({a} {x} {y})"/>')
                       for x, y, a, col in ((68, 52, -32, "#86D27A"), (82, 43, -16, "#5FAF6E"), (100, 40, 0, "#86D27A"),
                                            (118, 43, 16, "#5FAF6E"), (132, 52, 32, "#86D27A")))
               + '<circle cx="100" cy="40" r="4.4" fill="#FF8FA8" stroke="#B4485F" stroke-width="1"/>'
               + '<circle cx="99" cy="39" r="1.3" fill="#FFFFFF"/>'),
    ),
}
CLASSES["mercenary"]["defs"] += rad("lens", 80, 52, 12, (0, "#FFF0C0", 1), (0.5, "#FFB347", 1), (1, "#B8620E", 1))
CLASSES["sorceress"]["defs"] += rad("orb", 22, 33, 14, (0, "#FFFFFF", 1), (0.4, "#9EE7FF", 1), (1, "#3D8FD8", 1))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, c in CLASSES.items():
        c["name"] = name
        (OUT / f"{name}.svg").write_text(svg(c) + "\n", encoding="utf-8")
    print(f"{len(CLASSES)} arts -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
