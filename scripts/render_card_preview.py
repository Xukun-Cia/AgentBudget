#!/usr/bin/env python3
"""Render deterministic card previews without contacting Cursor or OpenAI."""

from pathlib import Path
import sys

import cairo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentbudget.app import LedgerWindow  # noqa: E402
from agentbudget.fetch import Snapshot  # noqa: E402
from agentbudget.settings import BASE_H, BASE_W, DETAIL_H, Settings  # noqa: E402

PREVIEW_STEM = "agentbudget-v2.1"


class PreviewApp:
    def __init__(self, theme: str) -> None:
        self.settings = Settings(theme=theme)
        self.fetching = False
        self.last_updated = "14:32"
        self.snap = Snapshot(
            ok=True,
            api_percent=37.84,
            api_used_cents=9460,
            api_limit_cents=25000,
            auto_percent=12.67,
            auto_used_cents=38010,
            auto_limit_cents=300000,
            today_api_percent=0.64,
            today_api_cents=160,
            today_api_events=2,
            today_auto_percent=0.35,
            today_auto_cents=1042,
            today_auto_events=11,
            cycle_start="2026-10-03T08:00:00+08:00",
            cycle_end="2026-11-03T08:00:00+08:00",
            gpt_ok=True,
            gpt_plan="Pro",
            gpt_percent=4,
            gpt_reset_at="2026-10-10T09:40:38+08:00",
            gpt_cycle_estimated=True,
            gpt_cycle_start="2026-10-07T09:31:51+08:00",
            gpt_cycle_end="2026-11-07T09:31:51+08:00",
            gpt_today_percent=2,
        )
        self._mode_items = []
        self._item_top = None

    def tone(self) -> str:
        return "ok"


def render(path: Path, *, expanded: bool, theme: str) -> None:
    app = PreviewApp(theme)
    window = LedgerWindow.__new__(LedgerWindow)
    window.app = app
    window.details_expanded = expanded
    height = DETAIL_H if expanded else BASE_H
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, BASE_W, height)
    cr = cairo.Context(surface)
    window._paint_logical(cr)
    surface.write_to_png(str(path))


if __name__ == "__main__":
    design = ROOT / "design"
    design.mkdir(exist_ok=True)
    for expanded, suffix in ((False, "preview"), (True, "details")):
        out = design / f"{PREVIEW_STEM}-{suffix}.png"
        render(out, expanded=expanded, theme="dark")
        print(out)
