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

assert panel_label(34.22, 13.11, 39) == " A 34% · C 13% · G 39%"
assert panel_label(None, None, None) == " A — · C — · G —"
assert panel_label(9.46, 7.33, 3, True).endswith("G ~3%")
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
    "gptCycleStart": "2026-09-07T09:31:51+08:00",
    "gptCycleEnd": "2026-10-07T09:31:51+08:00",
    "gptTodayPercent": 2,
})
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
