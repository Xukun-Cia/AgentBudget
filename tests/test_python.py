#!/usr/bin/env python3
"""Small compatibility checks for the GTK-facing data boundary."""

from pathlib import Path
from datetime import datetime, timezone
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cursorbudget.app import _fmt_gpt_pct  # noqa: E402
from cursorbudget.fetch import preserve_last_good_gpt, snapshot_from_dict  # noqa: E402
from cursorbudget.indicator import panel_label  # noqa: E402
from cursorbudget.settings import BASE_H, DETAIL_H, Settings  # noqa: E402


assert _fmt_gpt_pct(1) == "1%"
assert _fmt_gpt_pct(1.5) == "1.5%"
assert panel_label(9.464, 7.332, 1) == "A 9.46% · C 7.33% · G 1%"
assert panel_label(9.464, 7.332, 3, True).endswith("G ~3%")

settings = Settings()
assert settings.window_size(BASE_H)[1] < settings.window_size(DETAIL_H)[1]

snap = snapshot_from_dict({
    "ok": True,
    "gptOk": True,
    "gptPercent": 1,
    "gptWindows": [{
        "label": "GPT 周额度",
        "percent": 1,
        "windowSeconds": 604800,
        "isMain": True,
    }],
})
assert snap.gpt_percent == 1.0
assert snap.gpt_windows[0]["is_main"] is True

previous = snapshot_from_dict({
    "ok": True,
    "gptOk": True,
    "gptPercent": 3,
    "gptFetchedAt": datetime.now(timezone.utc).isoformat(),
})
failed = snapshot_from_dict({
    "ok": True,
    "gptOk": False,
    "gptTransient": True,
    "gptError": "timeout",
})
stale = preserve_last_good_gpt(failed, previous)
assert stale.gpt_ok is True
assert stale.gpt_percent == 3.0
assert stale.gpt_stale is True
assert stale.gpt_error == "timeout"

print("Python checks passed.")
