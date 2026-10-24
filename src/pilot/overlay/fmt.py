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
