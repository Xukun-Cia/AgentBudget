#!/usr/bin/env python3
"""Render deterministic card previews without contacting Cursor or OpenAI."""

from pathlib import Path
import sys

import cairo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cursorbudget.app import LedgerWindow  # noqa: E402
from cursorbudget.fetch import Snapshot  # noqa: E402
from cursorbudget.settings import BASE_H, BASE_W, DETAIL_H, Settings  # noqa: E402


class PreviewApp:
    def __init__(self, theme: str) -> None:
        self.settings = Settings(theme=theme)
        self.fetching = False
        self.last_updated = "14:32"
        self.snap = Snapshot(
            ok=True,
            remaining_days=11.42,
            api_percent=37.84,
            api_used_cents=9460,
            api_limit_cents=25000,
            auto_percent=12.67,
            auto_used_cents=38010,
            auto_limit_cents=300000,
            today_percent=0.64,
            today_cents=160,
            today_events=2,
            daily_budget=4.08,
            membership_type="ultra",
            included_used_cents=16520,
            included_limit_cents=40000,
            cycle_start="2026-10-03T08:00:00+08:00",
            cycle_end="2026-11-03T08:00:00+08:00",
            gpt_ok=True,
            gpt_plan="Pro",
            gpt_percent=4,
            gpt_reset_at="2026-10-10T09:40:38+08:00",
            gpt_window_seconds=604800,
            gpt_windows=(
                {
                    "label": "GPT 周额度", "percent": 4.0,
                    "reset_at": "2026-10-10T09:40:38+08:00", "is_main": True,
                },
                {
                    "label": "Codex Spark 5 小时额度", "percent": 12.0,
                    "reset_at": "2026-10-03T17:18:05+08:00", "is_main": False,
                },
                {
                    "label": "Codex Spark 周额度", "percent": 2.0,
                    "reset_at": "2026-10-10T13:38:05+08:00", "is_main": False,
                },
                {
                    "label": "Reserve 周额度", "percent": 0.0,
                    "reset_at": "2026-10-10T13:38:05+08:00", "is_main": False,
                },
            ),
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
    render(design / "cursorbudget-v1.2-preview.png", expanded=False, theme="dark")
    render(design / "cursorbudget-v1.2-details.png", expanded=True, theme="dark")
    print(design / "cursorbudget-v1.2-preview.png")
    print(design / "cursorbudget-v1.2-details.png")
