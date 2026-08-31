#!/usr/bin/env python3
"""Render CursorBudget hicolor icons."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cairo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cursorbudget.icon import paint_app_icon  # noqa: E402

SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)


def render_png(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)
    paint_app_icon(cr, float(size))
    surface.write_to_png(str(path))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "icons" / "hicolor")
    parser.add_argument("--pixmap", type=Path, default=ROOT / "data" / "icons" / "cursorbudget.png")
    args = parser.parse_args()
    out: Path = args.out
    for size in SIZES:
        render_png(out / f"{size}x{size}" / "apps" / "cursorbudget.png", size)
    if args.pixmap:
        render_png(args.pixmap, 256)
    print(f"Wrote icons under {out}")


if __name__ == "__main__":
    main()
