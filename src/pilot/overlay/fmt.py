"""Pure text formatting for the HUD (no Qt required except `elide`)."""
from __future__ import annotations

MINUS = "−"  # real minus sign, matches the UX mock-up


def format_time(seconds: float | None) -> str:
    """Run timer: h:mm:ss (e.g. 1:12:40, 0:05:03)."""
    s = max(0, int(seconds or 0))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}"


def format_delta(delta_s: float | None) -> str | None:
    """Split delta vs PB: '-0:42', '+1:05', '-1:02:03'. None stays None (hidden)."""
    if delta_s is None:
        return None
    r = int(round(delta_s))
    if r == 0:
        return "0:00"
    sign = MINUS if r < 0 else "+"
    r = abs(r)
    h, rem = divmod(r, 3600)
    m, s = divmod(rem, 60)
    body = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
    return sign + body


def delta_kind(delta_s: float | None) -> str | None:
    """'ahead' (green) / 'behind' (red) / None (neutral or hidden)."""
    if delta_s is None:
        return None
    r = int(round(delta_s))
    if r < 0:
        return "ahead"
    if r > 0:
        return "behind"
    return None


def act_label(act: int | None, area_level: int | None) -> str:
    """'A2 · 19'. Interludes (act >= 101) render as 'И1'..'И3'."""
    parts: list[str] = []
    if act is not None:
        parts.append(f"И{act - 100}" if act >= 101 else f"A{act}")
    if area_level is not None:
        parts.append(str(area_level))
    return " · ".join(parts)


def warn_text(warn: str) -> str:
    return warn if warn.startswith("⚠") else "⚠ " + warn


def elide(text: str, metrics, width: float) -> str:
    """Elide on the right so the text never wraps and never exceeds `width`."""
    from PySide6.QtCore import Qt

    if width <= 0:
        return ""
    return metrics.elidedText(text, Qt.ElideRight, int(width))


def details_lines(state, extra: list[str] | None = None, limit: int = 10) -> list[str]:
    """Content of the hold-to-show panel: what HudState offers + provider lines."""
    lines: list[str] = []
    head: list[str] = []
    if state.step_total:
        head.append(f"{state.step_index + 1}/{state.step_total}")
    if state.char_level is not None:
        head.append(f"ур. {state.char_level}")
    if state.area_name:
        head.append(state.area_name)
    if head:
        lines.append(" · ".join(head))
    if extra:
        # the bar already shows the current and next step; don't repeat them
        shown = {state.step_short, state.next_short}
        lines.extend(str(ln) for ln in extra if ln not in shown)
        return lines[:limit]
    if state.step_short:
        lines.append(state.step_short)
    if state.next_short:
        lines.append("затем: " + state.next_short)
    return lines[:limit]


# ---------------------------------------------------------------- redesign helpers
import re
from typing import NamedTuple

from . import theme

GLYPH_KIND = {"→": "move", "◆": "wp", "⚔": "boss", "⌂": "town", "!": "quest", "✦": "trial",
              "✕": "skip", "·": None}
_GLYPH_RE = re.compile(r"^([" + "".join(GLYPH_KIND) + r"])️?\s+")


def strip_glyph(text: str) -> tuple[str | None, str]:
    """('⚔', 'Rudja') from '⚔ Rudja'; (None, text) if no leading kind glyph + space."""
    m = _GLYPH_RE.match(text or "")
    if not m:
        return None, text or ""
    return m.group(1), text[m.end():].strip()


def short_boss(name: str) -> str:
    """Cut the epithet: 'Rudja, the Dread Engineer' -> 'Rudja'. ' & ' / ' и ' pairs stay."""
    head = name.split(", ", 1)[0].strip()
    return head or name


def step_parts(text: str | None, kind: str | None) -> tuple[str | None, str]:
    """-> (kind, display name). Kind falls back to the glyph's kind; boss names lose epithets."""
    if not text:
        return kind, ""
    glyph, name = strip_glyph(text)
    if kind is None and glyph is not None:
        kind = GLYPH_KIND.get(glyph)
    if kind in ("boss", "boss_opt"):
        name = short_boss(name)
    return kind, name


class PillStyle(NamedTuple):
    kind: str          # "ahead" | "behind" | "even"
    text: str
    fg: tuple
    bg: tuple


def pill_style(delta_s: float | None, palette: str | None = "default") -> PillStyle | None:
    """Delta pill: None when no delta; green/red (or blue/orange) when ahead/behind."""
    txt = format_delta(delta_s)
    if txt is None:
        return None
    pal = theme.palette(palette)
    k = delta_kind(delta_s)
    if k == "ahead":
        fg, bg = pal["pill_ahead"]
    elif k == "behind":
        fg, bg = pal["pill_behind"]
    else:
        fg, bg = theme.PILL_EVEN
        k = "even"
    return PillStyle(k, txt, fg, bg)


class ZonePill(NamedTuple):
    text: str
    amber: bool
    red: bool = False


# zone level above the character level: amber from 2, red from 3 (12 of 15 deaths in a
# reviewed run came at a 1-2 gap, the worst zones at 4)
AMBER_GAP = 2
RED_GAP = 3


def level_text(char_level: int | None) -> str | None:
    return None if char_level is None else f"ур {char_level}"


def zone_pill(area_level: int | None, char_level: int | None) -> ZonePill | None:
    """'зона 19': amber when the zone is 2 levels above the character, red from 3."""
    if area_level is None:
        return None
    gap = area_level - char_level if char_level is not None else 0
    return ZonePill(f"зона {area_level}", gap >= AMBER_GAP, gap >= RED_GAP)


class Segment(NamedTuple):
    a: float
    b: float
    state: str      # "done" | "current" | "todo"
    frac: float     # filled fraction of the segment (1 done, 0 todo, 0..1 current)


def progress_segments(progress: float, marks) -> list[Segment]:
    """Segments between split marks. Done = fully passed, current = contains `progress`."""
    p = min(1.0, max(0.0, float(progress or 0.0)))
    pts = sorted({round(float(m), 6) for m in (marks or ()) if 0.0 < float(m) < 1.0})
    edges = [0.0] + pts + [1.0]
    out: list[Segment] = []
    for a, b in zip(edges, edges[1:]):
        if p >= b:
            out.append(Segment(a, b, "done", 1.0))
        elif p > a:
            out.append(Segment(a, b, "current", (p - a) / (b - a)))
        else:
            out.append(Segment(a, b, "todo", 0.0))
    if p < 1.0 and not any(s.state == "current" for s in out):
        i = next(i for i, s in enumerate(out) if s.state == "todo")   # progress sits on a boundary
        out[i] = Segment(out[i].a, out[i].b, "current", 0.0)
    return out


def strip_warn_glyph(warn: str) -> str:
    return warn[1:].lstrip("️ ").strip() if warn.startswith("⚠") else warn
