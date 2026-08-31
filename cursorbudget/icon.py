"""CursorBudget mark: an open day-ledger, not a monitor glyph."""

from __future__ import annotations

import math

import cairo

INKSTONE = (0.18, 0.14, 0.11)
LEAF = (0.965, 0.945, 0.910)
OCHRE = (0.78, 0.55, 0.22)
CINNABAR = (0.78, 0.28, 0.22)
AMBER = (0.86, 0.58, 0.18)
SOOT = (0.16, 0.13, 0.11)
RULE = (0.62, 0.42, 0.16, 0.45)


def rounded_rect(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
    r = min(r, w / 2.0, h / 2.0)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _tone_color(tone: str) -> tuple[float, float, float]:
    if tone == "critical":
        return CINNABAR
    if tone == "warn":
        return AMBER
    return OCHRE


def paint_app_icon(cr: cairo.Context, size: float, tone: str = "ok") -> None:
    cr.save()
    rounded_rect(cr, 0, 0, size, size, size * 0.20)
    cr.set_source_rgb(*INKSTONE)
    cr.fill()
    paint_mark(cr, size / 2.0, size / 2.0, size * 0.38, tone=tone)
    cr.restore()


def paint_mark(
    cr: cairo.Context,
    cx: float,
    cy: float,
    radius: float,
    tone: str = "ok",
) -> None:
    """Open ledger: two leaves, ochre spine, a day-arc on the right page."""
    cr.save()
    w = radius * 1.72
    h = radius * 1.28
    x = cx - w / 2.0
    y = cy - h / 2.0
    spine = max(1.6, radius * 0.14)
    gutter = spine * 0.55

    # left leaf
    cr.set_source_rgb(*LEAF)
    cr.rectangle(x, y, w / 2.0 - gutter / 2.0, h)
    cr.fill()
    # right leaf
    cr.rectangle(x + w / 2.0 + gutter / 2.0, y, w / 2.0 - gutter / 2.0, h)
    cr.fill()
    # spine
    cr.set_source_rgb(*OCHRE)
    cr.rectangle(cx - spine / 2.0, y - radius * 0.04, spine, h + radius * 0.08)
    cr.fill()

    # ruled lines on the left page
    cr.set_source_rgba(*RULE)
    cr.set_line_width(max(0.7, radius * 0.035))
    left = x + radius * 0.16
    right = cx - spine / 2.0 - radius * 0.10
    for i in range(3):
        ly = y + h * (0.32 + i * 0.22)
        cr.move_to(left, ly)
        cr.line_to(right, ly)
        cr.stroke()

    # day-arc on the right page — remaining light of the workday
    accent = _tone_color(tone)
    rx = cx + w * 0.22
    ry = cy + h * 0.02
    cr.set_source_rgb(*accent)
    cr.set_line_width(max(1.4, radius * 0.10))
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.arc(rx, ry, radius * 0.28, math.radians(200), math.radians(20))
    cr.stroke()
    cr.arc(rx, ry, max(1.1, radius * 0.07), 0, math.tau)
    cr.fill()

    # soot edge
    cr.set_source_rgba(SOOT[0], SOOT[1], SOOT[2], 0.55)
    cr.set_line_width(max(0.8, radius * 0.04))
    cr.rectangle(x, y, w, h)
    cr.stroke()
    cr.restore()
