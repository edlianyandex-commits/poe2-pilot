"""Write data/ui/classes/<class>.svg: our own chibi bust per class for the start window.

usage: python tools/make_class_art.py
One template (face, big anime eyes, bangs, shoulders) and per class: hair, eye and outfit colours,
headwear and the class weapon behind the shoulder. viewBox 0 0 200 200, transparent background:
the card paints the class colour behind. Then run tools/make_content_manifest.py.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "ui" / "classes"

SKIN, SKIN_SHADE = "#FFE6D6", "#F6C9B4"
LINE = "#3A2A3F"


def grad(id_: str, top: str, bottom: str) -> str:
    return (f'<linearGradient id="{id_}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient>')


def eye(cx: float, iris: tuple[str, str], flip: bool) -> str:
    s = -1 if flip else 1
    lash = (f'M{cx - 11 * s},{96} Q{cx - 1 * s},{86} {cx + 11 * s},{93}'
            f' L{cx + 13 * s},{90} L{cx + 9 * s},{96} Q{cx},{90} {cx - 10 * s},{98} Z')
    return (f'<ellipse cx="{cx}" cy="101" rx="9.5" ry="11.5" fill="#FFFFFF"/>'
            f'<ellipse cx="{cx}" cy="102" rx="8" ry="10.5" fill="url(#iris)"/>'
            f'<ellipse cx="{cx}" cy="103" rx="3.8" ry="5.5" fill="{LINE}"/>'
            f'<circle cx="{cx - 3 * s}" cy="97" r="3" fill="#FFFFFF"/>'
            f'<circle cx="{cx + 3 * s}" cy="107" r="1.4" fill="#FFFFFF" opacity="0.9"/>'
            f'<path d="{lash}" fill="{LINE}"/>')


def face(c: dict) -> str:
    iris = c["eyes"]
    parts = [
        f'<path d="M90,122 L110,122 L111,150 L89,150 Z" fill="{SKIN_SHADE}"/>',     # neck
        f'<path d="M58,92 C58,124 84,140 100,140 C116,140 142,124 142,92 C142,62 122,48 100,48'
        f' C78,48 58,62 58,92 Z" fill="{SKIN}"/>',
        f'<ellipse cx="78" cy="115" rx="7.5" ry="3.6" fill="#FF8FA8" opacity="0.45"/>',
        f'<ellipse cx="122" cy="115" rx="7.5" ry="3.6" fill="#FF8FA8" opacity="0.45"/>',
        eye(84, iris, False), eye(116, iris, True),
        f'<path d="M73,83 Q81,79 90,82" stroke="{c["hair_dark"]}" stroke-width="2.6" fill="none" stroke-linecap="round"/>',
        f'<path d="M110,82 Q119,79 127,83" stroke="{c["hair_dark"]}" stroke-width="2.6" fill="none" stroke-linecap="round"/>',
        c.get("mouth", f'<path d="M95,121 Q97.5,124.5 100,121.5 Q102.5,124.5 105,121" stroke="#C2566E"'
                       f' stroke-width="2" fill="none" stroke-linecap="round"/>'),
    ]
    return "".join(parts)


BANGS = ('M54,100 C50,60 74,38 100,38 C126,38 150,60 146,100 L138,80 L131,96 L121,72 L111,92'
         ' L100,68 L90,92 L80,72 L70,96 L62,80 Z')
SHINE = '<path d="M70,56 Q100,40 130,56" stroke="#FFFFFF" stroke-width="4" opacity="0.35" fill="none" stroke-linecap="round"/>'


def body(c: dict) -> str:
    return (f'<path d="M36,200 C40,164 66,148 100,148 C134,148 160,164 164,200 Z" fill="url(#outfit)"/>'
            f'<path d="M84,148 L100,170 L116,148" fill="none" stroke="{c["trim"]}" stroke-width="5" stroke-linejoin="round"/>'
            + c.get("body_extra", ""))


def svg(c: dict) -> str:
    defs = (grad("hair", c["hair"], c["hair_dark"]) + grad("outfit", c["outfit"], c["outfit_dark"])
            + grad("iris", c["eyes"][1], c["eyes"][0]))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200">'
            f'<defs>{defs}</defs>'
            + c.get("prop", "")
            + c.get("back", f'<path d="M48,96 C44,52 72,30 100,30 C128,30 156,52 152,96 L150,140 L50,140 Z" fill="url(#hair)"/>')
            + body(c) + face(c)
            + f'<path d="{c.get("bangs", BANGS)}" fill="url(#hair)"/>' + SHINE
            + c.get("front", "") + "</svg>")


CLASSES: dict[str, dict] = {
    "warrior": dict(
        hair="#FF7F50", hair_dark="#C2412B", eyes=("#B4561C", "#FFC870"),
        outfit="#C9D2E3", outfit_dark="#7E8AA3", trim="#E2553B",
        back='<path d="M50,96 C46,54 72,32 100,32 C128,32 154,54 150,96 L146,120 L54,120 Z" fill="url(#hair)"/>',
        prop=('<line x1="150" y1="190" x2="176" y2="70" stroke="#6B4A2E" stroke-width="9" stroke-linecap="round"/>'
              '<circle cx="178" cy="60" r="20" fill="#8C96AB"/>'
              + "".join(f'<circle cx="{178 + 22 * dx}" cy="{60 + 22 * dy}" r="5" fill="#8C96AB"/>'
                        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (.7, .7), (-.7, -.7), (.7, -.7), (-.7, .7)))
              + '<circle cx="172" cy="54" r="6" fill="#FFFFFF" opacity="0.4"/>'),
        body_extra=('<ellipse cx="52" cy="172" rx="22" ry="16" fill="#AEB8CC"/>'
                    '<ellipse cx="148" cy="172" rx="22" ry="16" fill="#AEB8CC"/>'
                    '<path d="M36,176 Q52,160 68,176" stroke="#E2553B" stroke-width="4" fill="none"/>'
                    '<path d="M132,176 Q148,160 164,176" stroke="#E2553B" stroke-width="4" fill="none"/>'),
        front=('<path d="M55,70 Q100,52 145,70 L145,80 Q100,63 55,80 Z" fill="#2E3A59"/>'
               '<path d="M88,58 L112,58 L110,70 L90,70 Z" fill="#C9D2E3" stroke="#7E8AA3" stroke-width="1.5"/>'
               '<path d="M145,72 L164,62 L160,82 Z" fill="#2E3A59"/>'),
        mouth='<path d="M94,120 Q100,126 106,120" stroke="#C2566E" stroke-width="2.2" fill="none" stroke-linecap="round"/>',
    ),
    "ranger": dict(
        hair="#FFE08A", hair_dark="#D9A441", eyes=("#2E7D4F", "#9BE38C"),
        outfit="#5DAF6E", outfit_dark="#2F6B42", trim="#F2D27A",
        prop=('<path d="M24,40 Q-6,110 24,180" stroke="#8B5A2B" stroke-width="7" fill="none" stroke-linecap="round"/>'
              '<line x1="24" y1="40" x2="24" y2="180" stroke="#F5EBD0" stroke-width="2"/>'),
        back=('<path d="M40,104 C34,46 68,20 100,20 C132,20 166,46 160,104 L166,160 L34,160 Z" fill="url(#outfit)"/>'
              '<path d="M54,100 C50,62 74,44 100,44 C126,44 150,62 146,100 L146,128 L54,128 Z" fill="url(#hair)"/>'),
        front=('<path d="M40,104 C34,46 68,20 100,20 C132,20 166,46 160,104 C150,64 128,44 100,44'
               ' C72,44 50,64 40,104 Z" fill="url(#outfit)"/>'
               '<path d="M150,46 Q178,30 184,6 Q170,34 150,52 Z" fill="#E85D5D"/>'
               '<path d="M152,48 Q172,32 182,10" stroke="#FFFFFF" stroke-width="1.5" fill="none"/>'),
    ),
    "huntress": dict(
        hair="#2EC4B6", hair_dark="#14707A", eyes=("#0F5E66", "#7FF0E0"),
        outfit="#B07A52", outfit_dark="#6E4529", trim="#2EC4B6",
        prop=('<line x1="18" y1="196" x2="172" y2="24" stroke="#7A5232" stroke-width="7" stroke-linecap="round"/>'
              '<path d="M172,24 L196,2 L184,32 Z" fill="#D9E4EE"/>'
              '<path d="M166,30 L178,42" stroke="#2EC4B6" stroke-width="5" stroke-linecap="round"/>'),
        back=('<path d="M48,96 C44,52 72,30 100,30 C128,30 156,52 152,96 L150,128 L50,128 Z" fill="url(#hair)"/>'
              '<path d="M140,50 Q190,60 178,150 Q170,110 146,90 Z" fill="url(#hair)"/>'),
        front='<circle cx="146" cy="56" r="7" fill="#F2C14E"/>',
    ),
    "mercenary": dict(
        hair="#9A6A47", hair_dark="#5E3B22", eyes=("#8A4B12", "#FFB347"),
        outfit="#4A5068", outfit_dark="#272B3A", trim="#F4A340",
        prop=('<path d="M120,40 L196,40" stroke="#5B3B22" stroke-width="10" stroke-linecap="round"/>'
              '<path d="M150,10 Q170,40 150,70" stroke="#8C96AB" stroke-width="6" fill="none" stroke-linecap="round"/>'
              '<path d="M150,10 L132,40 L150,70" stroke="#F5EBD0" stroke-width="1.5" fill="none"/>'
              '<path d="M196,40 L186,33 L186,47 Z" fill="#D9E4EE"/>'),
        bangs=('M54,100 C50,58 74,36 100,36 C126,36 150,58 146,100 L140,76 L134,94 L124,66 L114,90'
               ' L104,62 L94,90 L84,64 L74,94 L66,72 L60,92 Z'),
        body_extra=''.join(f'<circle cx="100" cy="{y}" r="3.2" fill="#F4A340"/>' for y in (176, 188))
                   + '<path d="M60,160 L84,148 L90,200 L60,200 Z" fill="#5E6680" opacity="0.6"/>',
        front=('<rect x="66" y="52" width="68" height="9" rx="4" fill="#3A2A2A"/>'
               '<circle cx="82" cy="56" r="11" fill="#F4A340" stroke="#3A2A2A" stroke-width="4"/>'
               '<circle cx="118" cy="56" r="11" fill="#F4A340" stroke="#3A2A2A" stroke-width="4"/>'
               '<circle cx="79" cy="53" r="3" fill="#FFFFFF" opacity="0.8"/>'
               '<circle cx="115" cy="53" r="3" fill="#FFFFFF" opacity="0.8"/>'),
        mouth='<path d="M94,121 Q101,125 107,119" stroke="#C2566E" stroke-width="2.2" fill="none" stroke-linecap="round"/>',
    ),
    "monk": dict(
        hair="#3B3B55", hair_dark="#1C1C2C", eyes=("#1F6FB5", "#8FD3FF"),
        outfit="#F4F7FF", outfit_dark="#BFD3F2", trim="#5BB8FF",
        prop=('<line x1="168" y1="198" x2="168" y2="14" stroke="#8B5A2B" stroke-width="7" stroke-linecap="round"/>'
              '<rect x="162" y="30" width="12" height="8" rx="2" fill="#5BB8FF"/>'
              '<rect x="162" y="160" width="12" height="8" rx="2" fill="#5BB8FF"/>'
              '<path d="M14,120 Q34,96 58,110" stroke="#5BB8FF" stroke-width="4" fill="none" stroke-linecap="round" opacity="0.7"/>'
              '<path d="M8,140 Q30,118 52,132" stroke="#5BB8FF" stroke-width="3" fill="none" stroke-linecap="round" opacity="0.5"/>'),
        back=('<circle cx="100" cy="28" r="17" fill="url(#hair)"/>'
              '<path d="M50,96 C46,54 72,34 100,34 C128,34 154,54 150,96 L148,118 L52,118 Z" fill="url(#hair)"/>'),
        body_extra=(''.join(f'<circle cx="{100 + 30 * dx}" cy="{150 + 14 * dy}" r="4.5" fill="#8B5A2B"/>'
                            for dx, dy in ((-1, 0), (-.7, .55), (-.35, .9), (0, 1), (.35, .9), (.7, .55), (1, 0)))),
        front='<rect x="94" y="12" width="12" height="5" rx="2" fill="#5BB8FF"/>',
    ),
    "witch": dict(
        hair="#E6DDFF", hair_dark="#9C88D9", eyes=("#6A2BC2", "#D4A8FF"),
        outfit="#6E46C7", outfit_dark="#36226E", trim="#C9A7FF",
        back='<path d="M46,96 C42,52 72,30 100,30 C128,30 158,52 154,96 L162,176 L38,176 Z" fill="url(#hair)"/>',
        prop=('<g opacity="0.85"><circle cx="30" cy="150" r="13" fill="#F4F0FF"/>'
              '<circle cx="25" cy="149" r="3.5" fill="#6E46C7"/><circle cx="35" cy="149" r="3.5" fill="#6E46C7"/>'
              '<rect x="24" y="158" width="12" height="7" rx="2" fill="#F4F0FF"/>'
              '<path d="M18,168 Q12,182 22,192" stroke="#C9A7FF" stroke-width="3" fill="none" opacity="0.6"/></g>'),
        front=('<ellipse cx="100" cy="60" rx="72" ry="15" fill="#4A2D8F"/>'
               '<path d="M58,60 Q74,24 98,12 Q118,0 146,-4 Q124,14 128,30 Q136,46 142,60 Z" fill="#5A37AE"/>'
               '<path d="M62,52 Q100,40 140,52 L141,61 Q100,49 61,61 Z" fill="#F2C14E"/>'
               '<circle cx="100" cy="51" r="7" fill="#F4F0FF"/>'
               '<circle cx="97.5" cy="50" r="1.8" fill="#4A2D8F"/><circle cx="102.5" cy="50" r="1.8" fill="#4A2D8F"/>'),
        mouth='<path d="M96,121 Q100,125 104,121" stroke="#C2566E" stroke-width="2" fill="none" stroke-linecap="round"/>'
              '<path d="M101.5,122 L102.5,125" stroke="#FFFFFF" stroke-width="1.6"/>',
    ),
    "sorceress": dict(
        hair="#7FA8FF", hair_dark="#3155C9", eyes=("#1D3FA8", "#9EE7FF"),
        outfit="#FFFFFF", outfit_dark="#B9C8F5", trim="#4D7CFF",
        prop=('<line x1="26" y1="198" x2="26" y2="52" stroke="#C9A24A" stroke-width="6" stroke-linecap="round"/>'
              '<circle cx="26" cy="36" r="17" fill="#9EE7FF" opacity="0.35"/>'
              '<circle cx="26" cy="36" r="11" fill="#6FD0FF"/>'
              '<circle cx="22" cy="32" r="3.5" fill="#FFFFFF"/>'
              '<path d="M178,30 L166,62 L176,62 L164,96 L190,54 L180,54 L190,30 Z" fill="#FFE066"/>'),
        back='<path d="M46,96 C42,52 72,30 100,30 C128,30 158,52 154,96 L160,180 L40,180 Z" fill="url(#hair)"/>',
        body_extra='<path d="M70,152 Q100,184 130,152" stroke="#C9A24A" stroke-width="3" fill="none"/>',
        front=('<path d="M68,50 Q100,36 132,50 L128,56 Q100,44 72,56 Z" fill="#E8C35A"/>'
               '<path d="M100,32 L108,46 L100,52 L92,46 Z" fill="#4D7CFF" stroke="#E8C35A" stroke-width="2"/>'),
    ),
    "druid": dict(
        hair="#B9744A", hair_dark="#6E3B20", eyes=("#4E7A1E", "#D8F27A"),
        outfit="#5FAF6E", outfit_dark="#2C6A3A", trim="#F2E6C9",
        back=('<path d="M46,96 C42,52 72,30 100,30 C128,30 158,52 154,96 Q162,140 150,170 L50,170 Q38,140 46,96 Z" fill="url(#hair)"/>'
              '<path d="M60,40 Q48,14 58,0 M58,22 Q44,20 40,10 M140,40 Q152,14 142,0 M142,22 Q156,20 160,10"'
              ' stroke="#E8D7B5" stroke-width="5" fill="none" stroke-linecap="round"/>'),
        body_extra='<path d="M40,190 Q44,156 70,150 Q100,166 130,150 Q156,156 160,190 Q130,170 100,178 Q70,170 40,190 Z" fill="#F2E6C9"/>',
        prop=''.join(f'<path d="M{150 + d},{120} Q{176 + d},{150} {160 + d},{196}" stroke="#E8D7B5" stroke-width="4"'
                     f' fill="none" stroke-linecap="round" opacity="0.8"/>' for d in (0, 12, 24)),
        front=''.join(f'<ellipse cx="{x}" cy="{y}" rx="9" ry="5" fill="{col}" transform="rotate({a} {x} {y})"/>'
                      for x, y, a, col in ((70, 50, -30, "#7BC96F"), (84, 42, -15, "#5FAF6E"), (100, 39, 0, "#7BC96F"),
                                           (116, 42, 15, "#5FAF6E"), (130, 50, 30, "#7BC96F")))
              + '<circle cx="100" cy="40" r="4" fill="#FF8FA8"/>',
    ),
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, c in CLASSES.items():
        (OUT / f"{name}.svg").write_text(svg(c) + "\n", encoding="utf-8")
    print(f"{len(CLASSES)} arts -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
