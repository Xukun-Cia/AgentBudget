#!/usr/bin/env python3
"""Small compatibility checks for the GTK-facing data boundary."""

from pathlib import Path
from datetime import datetime, timezone
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentbudget.app import _codex_today, _cursor_today, _cycle_text  # noqa: E402
from agentbudget.fetch import preserve_last_good_gpt, snapshot_from_dict  # noqa: E402
from agentbudget.fmt import fmt_pct, fmt_pct_fine  # noqa: E402
from agentbudget.indicator import LABEL_GUIDE, panel_label  # noqa: E402
from agentbudget.settings import BASE_H, DETAIL_H, Settings  # noqa: E402


# Headline figures carry no decimals; halves round up.
assert fmt_pct(34.22) == "34%"
assert fmt_pct(13.5) == "14%"
assert fmt_pct(0) == "0%"
assert fmt_pct(None) == "—"
assert fmt_pct_fine(0.71) == "0.71%"

assert panel_label(34.22, 39) == " A 34%  ·  G 39%"
assert panel_label(None, None) == " A —  ·  G —"
assert panel_label(9.46, 3, True).endswith("G ~3%")
assert LABEL_GUIDE.startswith(" A ")

settings = Settings()
assert settings.window_size(BASE_H)[1] < settings.window_size(DETAIL_H)[1]

# Detail rows: today's spend per pool, and the two subscription cycles.
assert _cursor_today(0.71, 177, 5, False) == "0.71% · $1.77 · 5 笔"
assert _cursor_today(0.71, 177, 5, True).endswith("未拉全")
assert _cursor_today(None, None, None, False) == "—"
assert _cycle_text(None, None) == "—"

snap = snapshot_from_dict({
    "ok": True,
    "apiPercent": 34.22,
    "todayApiPercent": 0.71,
    "todayApiCents": 177,
    "todayApiEvents": 5,
    "todayAutoPercent": 0.35,
    "todayAutoCents": 1042,
    "todayAutoEvents": 11,
    "cycleStart": "2026-09-04T14:06:00+08:00",
    "cycleEnd": "2026-10-04T14:06:00+08:00",
    "gptOk": True,
    "gptPercent": 39,
    "gptCycleEstimated": True,
    "gptCycleStart": "2026-09-07T09:31:51+08:00",
    "gptCycleEnd": "2026-10-07T09:31:51+08:00",
    "gptTodayPercent": 2,
})
assert snap.gpt_cycle_estimated is True
assert snap.today_api_cents == 177.0
assert snap.today_auto_events == 11
assert _codex_today(snap) == "2%"
assert _cycle_text(snap.cycle_start, snap.cycle_end) == "9/4 14:06 → 10/4 14:06"

partial = snapshot_from_dict({
    "ok": True,
    "gptOk": True,
    "gptPercent": 39,
    "gptTodayPercent": 2,
    "gptTodayPartial": True,
})
assert _codex_today(partial) == "≥2%"
assert _codex_today(snapshot_from_dict({"ok": True, "gptTodayPartial": True})) == "—"

previous = snapshot_from_dict({
    "ok": True,
    "gptOk": True,
    "gptPercent": 3,
    "gptFetchedAt": datetime.now(timezone.utc).isoformat(),
    "gptTodayPercent": 1,
})
failed = snapshot_from_dict({
    "ok": True,
    "gptOk": False,
    "gptTransient": True,
    "gptError": "timeout",
    "gptTodayPercent": 4,
})
stale = preserve_last_good_gpt(failed, previous)
assert stale.gpt_ok is True
assert stale.gpt_percent == 3.0
assert stale.gpt_stale is True
assert stale.gpt_error == "timeout"
assert stale.gpt_today_percent == 4.0, "the local ledger survives a failed refresh"

print("Python checks passed.")

# Render through the actual painter and inspect text, so hidden data cannot leak
# into the collapsed view when labels or layout change.
import cairo
from agentbudget.app import LedgerWindow
from agentbudget.fetch import Snapshot
from agentbudget.settings import BASE_W

class PaintApp:
    settings = Settings(theme="dark")
    fetching = False
    last_updated = "12:00"
    snap = Snapshot(ok=True, api_percent=45, auto_percent=23, gpt_ok=True,
                    gpt_percent=67, cycle_end="2026-11-01T00:00:00Z",
                    gpt_reset_at="2026-10-09T00:00:00Z", gpt_cycle_estimated=True)

class TextRecorder:
    def __init__(self, context):
        self.context = context
        self.text = []
    def __getattr__(self, key):
        return getattr(self.context, key)
    def show_text(self, text):
        self.text.append(text)
        self.context.show_text(text)

for expanded in (False, True):
    window = LedgerWindow.__new__(LedgerWindow)
    window.app = PaintApp()
    window.details_expanded = expanded
    context = TextRecorder(cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, BASE_W, DETAIL_H)))
    window._paint_logical(context)
    shown = "\n".join(context.text)
    assert "今日" not in shown
    assert ("C" in context.text) == expanded
    assert ("订阅周期" in shown) == expanded
    if not expanded:
        assert "$" not in shown
        assert sum(text.startswith("重置 ") for text in context.text) == 2
print("UI content checks passed.")
