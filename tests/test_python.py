#!/usr/bin/env python3
"""Small compatibility checks for the GTK-facing data boundary."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cursorbudget.app import _fmt_gpt_pct  # noqa: E402
from cursorbudget.fetch import snapshot_from_dict  # noqa: E402
from cursorbudget.indicator import panel_label  # noqa: E402
from cursorbudget.settings import BASE_H, DETAIL_H, Settings  # noqa: E402


assert _fmt_gpt_pct(1) == "1%"
assert _fmt_gpt_pct(1.5) == "1.5%"
assert panel_label(9.464, 7.332, 1) == "A 9.46% · C 7.33% · G 1%"

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

print("Python checks passed.")
