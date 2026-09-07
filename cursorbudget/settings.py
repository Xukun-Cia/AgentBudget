"""Persistent local settings. No account data lives here."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Tuple

CONFIG_DIR = Path.home() / ".config" / "cursorbudget"
CONFIG_PATH = CONFIG_DIR / "config.json"

# Logical design sizes. The default card stays deliberately compact; secondary
# accounting details are revealed in place on demand.
BASE_W = 348
BASE_H = 430
DETAIL_H = 694

DISPLAY_MODES = ("window", "panel")
DISPLAY_MODE_LABELS = {
    "window": "悬浮卡",
    "panel": "顶栏",
}

SIZE_PRESETS = {
    "small": (0.85, "小"),
    "medium": (1.0, "中"),
    "large": (1.25, "大"),
    "xlarge": (1.55, "更大"),
}

THEME_PRESETS = {
    "light": "宣纸",
    "dark": "砚台",
}

# paper, ink, ink_soft, rule, ochre, cinnabar, moss
ThemeColors = Tuple[Tuple[float, float, float], ...]

THEMES: Dict[str, ThemeColors] = {
    "light": (
        (0.965, 0.956, 0.936),  # warm porcelain
        (0.105, 0.100, 0.090),  # charcoal
        (0.405, 0.390, 0.355),
        (0.820, 0.800, 0.755),
        (0.595, 0.435, 0.205),  # restrained brass
        (0.650, 0.255, 0.210),  # muted alert
        (0.595, 0.435, 0.205),  # one-accent system
    ),
    "dark": (
        (0.075, 0.073, 0.068),  # warm graphite
        (0.945, 0.928, 0.890),
        (0.625, 0.600, 0.545),
        (0.235, 0.225, 0.205),
        (0.805, 0.610, 0.305),
        (0.825, 0.390, 0.320),
        (0.805, 0.610, 0.305),
    ),
}

DEFAULT_SIZE = "medium"
DEFAULT_SCALE = 1.0
DEFAULT_REFRESH_SEC = 60.0
DEFAULT_THEME = "light"
DEFAULT_DISPLAY_MODE = "window"
DEFAULT_WARNING = 80.0
DEFAULT_CRITICAL = 95.0

SCALE_MIN, SCALE_MAX = 0.75, 2.0
REFRESH_MIN, REFRESH_MAX = 10.0, 600.0


@dataclass
class Settings:
    size_preset: str = DEFAULT_SIZE
    ui_scale: float = DEFAULT_SCALE
    refresh_sec: float = DEFAULT_REFRESH_SEC
    theme: str = DEFAULT_THEME
    always_on_top: bool = True
    display_mode: str = DEFAULT_DISPLAY_MODE
    warning_threshold: float = DEFAULT_WARNING
    critical_threshold: float = DEFAULT_CRITICAL

    def clamp(self) -> "Settings":
        if self.size_preset not in SIZE_PRESETS:
            self.size_preset = DEFAULT_SIZE
        if self.theme not in THEME_PRESETS:
            self.theme = DEFAULT_THEME
        if self.display_mode not in DISPLAY_MODES:
            self.display_mode = DEFAULT_DISPLAY_MODE
        self.ui_scale = max(SCALE_MIN, min(SCALE_MAX, float(self.ui_scale)))
        self.refresh_sec = max(REFRESH_MIN, min(REFRESH_MAX, float(self.refresh_sec)))
        self.warning_threshold = max(0.0, min(100.0, float(self.warning_threshold)))
        self.critical_threshold = max(0.0, min(100.0, float(self.critical_threshold)))
        if self.critical_threshold < self.warning_threshold:
            self.critical_threshold = self.warning_threshold
        return self

    @property
    def size_factor(self) -> float:
        return SIZE_PRESETS[self.size_preset][0]

    @property
    def pixel_scale(self) -> float:
        return self.size_factor * self.ui_scale

    def window_size(self, logical_height: int = BASE_H) -> Tuple[int, int]:
        s = self.pixel_scale
        return max(240, int(round(BASE_W * s))), max(360, int(round(logical_height * s)))

    @property
    def refresh_ms(self) -> int:
        return max(10_000, int(round(self.refresh_sec * 1000)))

    def colors(self) -> ThemeColors:
        return THEMES[self.theme]


def load_settings() -> Settings:
    if not CONFIG_PATH.is_file():
        return Settings().clamp()
    try:
        CONFIG_DIR.chmod(0o700)
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return Settings(
            size_preset=str(data.get("size_preset", DEFAULT_SIZE)),
            ui_scale=float(data.get("ui_scale", DEFAULT_SCALE)),
            refresh_sec=float(data.get("refresh_sec", DEFAULT_REFRESH_SEC)),
            theme=str(data.get("theme", DEFAULT_THEME)),
            always_on_top=bool(data.get("always_on_top", True)),
            display_mode=str(data.get("display_mode", DEFAULT_DISPLAY_MODE)),
            warning_threshold=float(data.get("warning_threshold", DEFAULT_WARNING)),
            critical_threshold=float(data.get("critical_threshold", DEFAULT_CRITICAL)),
        ).clamp()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return Settings().clamp()


def save_settings(settings: Settings) -> None:
    settings.clamp()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        CONFIG_DIR.chmod(0o700)
    except OSError:
        pass
    CONFIG_PATH.write_text(
        json.dumps(asdict(settings), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    try:
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass
