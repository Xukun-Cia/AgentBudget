"""CursorBudget day-ledger: floating card or GNOME top-bar figures."""

from __future__ import annotations

import math
import threading
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import __app_name__, __version__
from .fetch import Snapshot, fetch_snapshot
from .icon import paint_mark
from .indicator import PanelIndicator
from .settings import (
    BASE_H,
    BASE_W,
    DISPLAY_MODE_LABELS,
    DISPLAY_MODES,
    REFRESH_MAX,
    REFRESH_MIN,
    SCALE_MAX,
    SCALE_MIN,
    SIZE_PRESETS,
    THEME_PRESETS,
    Settings,
    load_settings,
    save_settings,
)

DASHBOARD_URL = "https://cursor.com/dashboard/usage"


def _rgba(cr: cairo.Context, rgb, a: float = 1.0) -> None:
    cr.set_source_rgba(rgb[0], rgb[1], rgb[2], a)


def _fmt_pct(value: Optional[float]) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return f"{value:.2f}%"


def _fmt_days(value: Optional[float]) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return f"{value:.2f}"


def _fmt_usd(cents: Optional[float]) -> str:
    if cents is None or not math.isfinite(cents):
        return "—"
    return f"${cents / 100:,.2f}"


def _fmt_when(value: Optional[str]) -> str:
    if not value:
        return "—"
    try:
        raw = str(value).strip()
        if raw.isdigit():
            ms = int(raw)
            if ms > 10_000_000_000:
                ms /= 1000.0
            dt = datetime.fromtimestamp(ms).astimezone()
        else:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone()
        return f"{dt.month}/{dt.day} {dt.hour:02d}:{dt.minute:02d}"
    except (ValueError, TypeError, OSError, OverflowError):
        return str(value)[:16]


# Ink Ledger: one serif family only (CJK-capable).
try:
    import subprocess as _subprocess

    _matched = _subprocess.check_output(
        ["fc-match", "-f", "%{family}", "Noto Serif CJK SC:lang=zh-cn"],
        text=True,
        timeout=2,
    ).strip()
    _UI_FONT = _matched.split(",")[0].strip() or "Noto Serif CJK SC"
except Exception:
    _UI_FONT = "Noto Serif CJK SC"


def _set_font(cr: cairo.Context, *, bold: bool = False, size: float = 11) -> None:
    weight = cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL
    cr.select_font_face(_UI_FONT, cairo.FONT_SLANT_NORMAL, weight)
    cr.set_font_size(size)


def _clock_now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _usage_tone(percent: Optional[float], warning: float, critical: float) -> str:
    if percent is None:
        return "ok"
    if percent >= critical:
        return "critical"
    if percent >= warning:
        return "warn"
    return "ok"


class SettingsDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, settings: Settings) -> None:
        super().__init__(title="设置", transient_for=parent, modal=True, flags=0)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_resizable(False)

        box = self.get_content_area()
        box.set_border_width(14)
        box.set_spacing(10)
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        box.add(grid)

        grid.attach(Gtk.Label(label="卡片大小", xalign=0), 0, 0, 1, 1)
        self.size_combo = Gtk.ComboBoxText()
        for key in ("small", "medium", "large", "xlarge"):
            self.size_combo.append(key, SIZE_PRESETS[key][1])
        self.size_combo.set_active_id(settings.size_preset)
        grid.attach(self.size_combo, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="界面缩放", xalign=0), 0, 1, 1, 1)
        scale_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.scale_adj = Gtk.Adjustment(
            value=settings.ui_scale,
            lower=SCALE_MIN,
            upper=SCALE_MAX,
            step_increment=0.05,
            page_increment=0.25,
        )
        self.scale_spin = Gtk.SpinButton(adjustment=self.scale_adj, digits=2)
        self.scale_spin.set_width_chars(5)
        self.scale_label = Gtk.Label(xalign=0)
        self.scale_adj.connect("value-changed", self._on_scale_changed)
        scale_box.pack_start(self.scale_spin, False, False, 0)
        scale_box.pack_start(self.scale_label, False, False, 0)
        grid.attach(scale_box, 1, 1, 1, 1)
        self._on_scale_changed(self.scale_adj)

        grid.attach(Gtk.Label(label="刷新间隔", xalign=0), 0, 2, 1, 1)
        refresh_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.refresh_adj = Gtk.Adjustment(
            value=settings.refresh_sec,
            lower=REFRESH_MIN,
            upper=REFRESH_MAX,
            step_increment=10,
            page_increment=30,
        )
        self.refresh_spin = Gtk.SpinButton(adjustment=self.refresh_adj, digits=0)
        self.refresh_spin.set_width_chars(5)
        refresh_box.pack_start(self.refresh_spin, False, False, 0)
        refresh_box.pack_start(Gtk.Label(label="秒", xalign=0), False, False, 0)
        grid.attach(refresh_box, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label="纸色", xalign=0), 0, 3, 1, 1)
        self.theme_combo = Gtk.ComboBoxText()
        for key in ("light", "dark"):
            self.theme_combo.append(key, THEME_PRESETS[key])
        self.theme_combo.set_active_id(settings.theme)
        grid.attach(self.theme_combo, 1, 3, 1, 1)

        grid.attach(Gtk.Label(label="警告阈值", xalign=0), 0, 4, 1, 1)
        self.warn_adj = Gtk.Adjustment(
            value=settings.warning_threshold, lower=0, upper=100,
            step_increment=1, page_increment=5,
        )
        self.warn_spin = Gtk.SpinButton(adjustment=self.warn_adj, digits=0)
        grid.attach(self.warn_spin, 1, 4, 1, 1)

        grid.attach(Gtk.Label(label="严重阈值", xalign=0), 0, 5, 1, 1)
        self.crit_adj = Gtk.Adjustment(
            value=settings.critical_threshold, lower=0, upper=100,
            step_increment=1, page_increment=5,
        )
        self.crit_spin = Gtk.SpinButton(adjustment=self.crit_adj, digits=0)
        grid.attach(self.crit_spin, 1, 5, 1, 1)

        hint = Gtk.Label(
            label="顶栏只显示时长与两个用量百分比。完整日账在悬浮卡。",
            xalign=0,
        )
        hint.set_line_wrap(True)
        hint.get_style_context().add_class("dim-label")
        box.add(hint)
        self.show_all()

    def _on_scale_changed(self, adj: Gtk.Adjustment) -> None:
        self.scale_label.set_text(f"{adj.get_value() * 100:.0f}%")

    def result_settings(self, base: Settings) -> Settings:
        preset = self.size_combo.get_active_id() or base.size_preset
        theme = self.theme_combo.get_active_id() or base.theme
        return Settings(
            size_preset=preset,
            ui_scale=self.scale_spin.get_value(),
            refresh_sec=self.refresh_spin.get_value(),
            theme=theme,
            always_on_top=base.always_on_top,
            display_mode=base.display_mode,
            warning_threshold=self.warn_spin.get_value(),
            critical_threshold=self.crit_spin.get_value(),
        ).clamp()


def _build_menu(app: "LedgerApp", *, show_always_on_top: bool) -> Gtk.Menu:
    menu = Gtk.Menu()
    group = None
    for mode in DISPLAY_MODES:
        item = Gtk.RadioMenuItem.new_with_label(group, DISPLAY_MODE_LABELS[mode])
        group = item.get_group()
        item.set_active(app.settings.display_mode == mode)
        item.connect("toggled", app._on_mode_item, mode)
        menu.append(item)
        app._mode_items.append((mode, item))

    if show_always_on_top:
        menu.append(Gtk.SeparatorMenuItem())
        item_top = Gtk.CheckMenuItem(label="始终置顶")
        item_top.set_active(app.settings.always_on_top)
        item_top.connect("toggled", app._on_toggle_top)
        menu.append(item_top)
        app._item_top = item_top

    menu.append(Gtk.SeparatorMenuItem())
    item_dash = Gtk.MenuItem(label="打开用量页")
    item_dash.connect("activate", lambda *_: app.open_dashboard())
    menu.append(item_dash)
    item_refresh = Gtk.MenuItem(label="立即刷新")
    item_refresh.connect("activate", lambda *_: app.refresh_now())
    menu.append(item_refresh)

    menu.append(Gtk.SeparatorMenuItem())
    item_settings = Gtk.MenuItem(label="设置…")
    item_settings.connect("activate", lambda *_: app.open_settings())
    menu.append(item_settings)
    item_about = Gtk.MenuItem(label=f"关于 {__app_name__} {__version__}")
    item_about.connect("activate", lambda *_: app.show_about())
    menu.append(item_about)
    item_quit = Gtk.MenuItem(label="退出")
    item_quit.connect("activate", lambda *_: app.quit())
    menu.append(item_quit)
    menu.show_all()
    return menu


class LedgerWindow(Gtk.Window):
    def __init__(self, app: "LedgerApp") -> None:
        super().__init__(title=__app_name__)
        self.app = app
        win_w, win_h = app.settings.window_size()

        self.set_default_size(win_w, win_h)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_keep_above(app.settings.always_on_top)
        self.set_skip_taskbar_hint(False)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_border_width(0)
        self.set_app_paintable(True)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None and screen.is_composited():
            self.set_visual(visual)

        self._drag_ox = 0
        self._drag_oy = 0
        self._dragging = False
        self._origin_x = 0
        self._origin_y = 0

        self.drawing = Gtk.DrawingArea()
        self.drawing.set_size_request(win_w, win_h)
        self.drawing.connect("draw", self._on_draw)
        self.add(self.drawing)

        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("button-press-event", self._on_button_press)
        self.connect("button-release-event", self._on_button_release)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("delete-event", lambda *_: app.quit() or True)

        self.menu = _build_menu(app, show_always_on_top=True)

    def apply_geometry(self) -> None:
        win_w, win_h = self.app.settings.window_size()
        self.drawing.set_size_request(win_w, win_h)
        self.resize(win_w, win_h)
        self.set_size_request(win_w, win_h)
        self.set_keep_above(self.app.settings.always_on_top)

    def place_default(self) -> None:
        screen = Gdk.Screen.get_default()
        if screen is None:
            return
        geo = screen.get_monitor_geometry(screen.get_primary_monitor())
        ww, hh = self.app.settings.window_size()
        self.move(geo.x + geo.width - ww - 36, geo.y + geo.height - hh - 80)

    def redraw(self) -> None:
        self.drawing.queue_draw()

    def _on_button_press(self, _w, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            self.menu.popup_at_pointer(event)
            return True
        if event.button == 1:
            alloc = self.drawing.get_allocation()
            if event.x >= alloc.width - 28 and event.y <= 26:
                self.app.quit()
                return True
            self._dragging = True
            self._drag_ox = int(event.x_root)
            self._drag_oy = int(event.y_root)
            ox, oy = self.get_position()
            self._origin_x = ox
            self._origin_y = oy
            return True
        return False

    def _on_button_release(self, _w, event: Gdk.EventButton) -> bool:
        if event.button == 1:
            self._dragging = False
        return False

    def _on_motion(self, _w, event: Gdk.EventMotion) -> bool:
        if self._dragging and (event.state & Gdk.ModifierType.BUTTON1_MASK):
            dx = int(event.x_root) - self._drag_ox
            dy = int(event.y_root) - self._drag_oy
            self.move(self._origin_x + dx, self._origin_y + dy)
            return True
        return False

    def _on_draw(self, _widget, cr: cairo.Context) -> bool:
        alloc = self.drawing.get_allocation()
        cr.save()
        cr.scale(alloc.width / BASE_W, alloc.height / BASE_H)
        self._paint_logical(cr)
        cr.restore()
        return False

    def _paint_logical(self, cr: cairo.Context) -> None:
        """Ink Ledger card: peer pools, clear air under rules, one serif family."""
        snap = self.app.snap
        w, h = BASE_W, BASE_H
        paper, ink, ink_soft, rule, ochre, cinnabar, moss = self.app.settings.colors()
        tone = self.app.tone()
        api_accent = cinnabar if tone == "critical" else ochre if tone == "warn" else moss

        pad_l = 24
        pad_r = w - 22
        content_w = pad_r - pad_l

        _rgba(cr, paper)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        _rgba(cr, ochre)
        cr.rectangle(0, 0, 8, h)
        cr.fill()

        _rgba(cr, ink, 0.12)
        cr.set_line_width(1.0)
        cr.rectangle(8.5, 0.5, w - 9, h - 1)
        cr.stroke()

        paint_mark(cr, pad_l + 10, 24, 10, tone=tone)
        _set_font(cr, bold=False, size=12)
        _rgba(cr, ochre)
        cr.move_to(pad_l + 28, 28)
        cr.show_text("CursorBudget")
        _set_font(cr, bold=False, size=14)
        _rgba(cr, ink_soft, 0.55)
        tw = cr.text_extents("×").width
        cr.move_to(pad_r - tw, 27)
        cr.show_text("×")

        y = 42
        self._rule(cr, pad_l, y, pad_r, rule)

        if snap is None:
            _set_font(cr, bold=False, size=13)
            _rgba(cr, ink_soft)
            cr.move_to(pad_l, 88)
            cr.show_text("正在翻开今日账本…")
            return

        if not snap.ok:
            _set_font(cr, bold=False, size=13)
            self._wrapped_text(cr, snap.error or "无法读取用量", pad_l, 80, content_w, ink=cinnabar)
            if snap.fetch_error:
                self._wrapped_text(cr, snap.fetch_error, pad_l, 128, content_w, ink=ink_soft)
            return

        # Hero — remaining workdays
        y = 68
        _set_font(cr, bold=False, size=11)
        _rgba(cr, ink_soft)
        cr.move_to(pad_l, y)
        cr.show_text("剩余工作日")
        _set_font(cr, bold=True, size=44)
        _rgba(cr, ink)
        cr.move_to(pad_l, y + 48)
        cr.show_text(_fmt_days(snap.remaining_days))
        _set_font(cr, bold=False, size=12)
        _rgba(cr, ochre)
        cr.move_to(pad_l, y + 72)
        cr.show_text(f"重置  {_fmt_when(snap.cycle_end)}")
        y = y + 90

        # Peer pool: API
        api_sub = f"{_fmt_usd(snap.api_used_cents)}  /  {_fmt_usd(snap.api_limit_cents)}"
        y = self._pool_section(
            cr, pad_l, pad_r, y, content_w,
            "API 池", _fmt_pct(snap.api_percent), api_sub,
            snap.api_percent, api_accent, ink, ink_soft, rule,
        )

        # Peer pool: Cursor Models
        cursor_sub = f"{_fmt_usd(snap.auto_used_cents)}  /  {_fmt_usd(snap.auto_limit_cents)}"
        y = self._pool_section(
            cr, pad_l, pad_r, y, content_w,
            "Cursor 池", _fmt_pct(snap.auto_percent), cursor_sub,
            snap.auto_percent, ochre, ink, ink_soft, rule,
        )

        # Today — quieter, no meter
        self._rule(cr, pad_l, y, pad_r, rule)
        base = y + 30
        today_sub = _fmt_usd(snap.today_cents)
        if snap.today_events is not None:
            today_sub = f"{today_sub}  ·  {snap.today_events} 笔"
        if snap.today_truncated:
            today_sub += "  ·  未拉全"
        _set_font(cr, bold=False, size=11)
        _rgba(cr, ink_soft)
        cr.move_to(pad_l, base)
        cr.show_text("今日 API")
        _set_font(cr, bold=True, size=22)
        _rgba(cr, ink)
        pct = _fmt_pct(snap.today_percent)
        tw = cr.text_extents(pct).width
        cr.move_to(pad_r - tw, base)
        cr.show_text(pct)
        _set_font(cr, bold=False, size=12)
        _rgba(cr, ink_soft)
        cr.move_to(pad_l, base + 24)
        cr.show_text(today_sub)
        hint = "9:00 → 9:00"
        hw = cr.text_extents(hint).width
        cr.move_to(pad_r - hw, base + 24)
        cr.show_text(hint)
        y = base + 24 + 28

        # Judgment footer
        self._rule(cr, pad_l, y, pad_r, rule)
        base = y + 32
        daily_label = "剩余额度" if snap.is_last_stretch else "日估"
        daily_value = _fmt_pct(snap.daily_budget)
        if not snap.is_last_stretch and snap.daily_budget is not None:
            daily_value = f"{snap.daily_budget:.2f}%/d"
        _set_font(cr, bold=False, size=13)
        _rgba(cr, ink_soft)
        cr.move_to(pad_l, base)
        cr.show_text(daily_label)
        _set_font(cr, bold=True, size=16)
        _rgba(cr, ink)
        tw = cr.text_extents(daily_value).width
        cr.move_to(pad_r - tw, base)
        cr.show_text(daily_value)

        _set_font(cr, bold=False, size=12)
        _rgba(cr, ink_soft)
        plan = snap.membership_type or "—"
        if snap.included_limit_cents is not None:
            plan = (
                f"套餐  {snap.membership_type}  "
                f"{_fmt_usd(snap.included_used_cents)} / {_fmt_usd(snap.included_limit_cents)}"
            )
        else:
            plan = f"套餐  {snap.membership_type}"
        cr.move_to(pad_l, base + 26)
        cr.show_text(plan)
        if snap.bonus_cents:
            bonus = f"bonus {_fmt_usd(snap.bonus_cents)}"
            bw = cr.text_extents(bonus).width
            cr.move_to(pad_r - bw, base + 26)
            cr.show_text(bonus)

        cr.move_to(pad_l, base + 50)
        cr.show_text(f"周期  {_fmt_when(snap.cycle_start)}  →  {_fmt_when(snap.cycle_end)}")

        clock = _clock_now()
        footer = snap.workday_label or clock
        if snap.workday_label and "（" in snap.workday_label:
            footer = clock + snap.workday_label[snap.workday_label.find("（"):]
        if self.app.fetching:
            footer = f"{footer}  ·  刷新中"
        # Keep a full line step below 周期; never clamp into that row.
        cr.move_to(pad_l, base + 74)
        cr.show_text(footer)

    def _rule(self, cr: cairo.Context, x: float, y: float, right: float, rule) -> None:
        _rgba(cr, rule)
        cr.set_line_width(0.9)
        cr.move_to(x, y)
        cr.line_to(right, y)
        cr.stroke()

    def _pool_section(
        self, cr, pad_l, pad_r, y_rule, content_w,
        label, value, dollars, pct, accent, ink, ink_soft, rule,
    ) -> float:
        """Hairline at y_rule, then label/% with clearance, dollars, meter. Returns next y."""
        self._rule(cr, pad_l, y_rule, pad_r, rule)
        # Clearance below rule must exceed display-figure ascent (~20px for 22pt).
        base = y_rule + 32
        _set_font(cr, bold=False, size=11)
        _rgba(cr, ink_soft)
        cr.move_to(pad_l, base)
        cr.show_text(label)
        _set_font(cr, bold=True, size=22)
        _rgba(cr, ink)
        tw = cr.text_extents(value).width
        cr.move_to(pad_r - tw, base)
        cr.show_text(value)
        _set_font(cr, bold=False, size=12)
        _rgba(cr, ink_soft)
        cr.move_to(pad_l, base + 24)
        cr.show_text(dollars)
        by = base + 38
        _rgba(cr, rule)
        cr.rectangle(pad_l, by, content_w, 7)
        cr.fill()
        fill = 0.0 if pct is None else max(0.0, min(1.0, pct / 100.0)) * content_w
        _rgba(cr, accent)
        cr.rectangle(pad_l, by, fill, 7)
        cr.fill()
        return by + 7 + 20

    def _wrapped_text(self, cr, text: str, x: float, y: float, max_w: float, ink) -> None:
        _set_font(cr, bold=False, size=12)
        _rgba(cr, ink)
        line = ""
        cy = y
        for ch in text:
            trial = line + ch
            if cr.text_extents(trial).width > max_w and line:
                cr.move_to(x, cy)
                cr.show_text(line)
                line = ch
                cy += 18
            else:
                line = trial
        if line:
            cr.move_to(x, cy)
            cr.show_text(line)


class LedgerApp:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.snap: Optional[Snapshot] = None
        self.fetching = False
        self._tick_id = 0
        self._clock_id = 0
        self._settings_open = False
        self._applying_mode = False
        self._item_top: Optional[Gtk.CheckMenuItem] = None
        self._mode_items: list = []
        self._placed_window = False
        self._ready = False

        self.window = LedgerWindow(self)
        self.indicator = PanelIndicator(
            on_mode=self.set_mode,
            on_dashboard=self.open_dashboard,
            on_refresh=self.refresh_now,
            on_settings=self.open_settings,
            on_about=self.show_about,
            on_quit=self.quit,
            get_mode=lambda: self.settings.display_mode,
        )
        self.indicator.start()
        self.refresh_now()
        self._restart_timer()
        self._clock_id = GLib.timeout_add(1000, self._clock_tick)
        self.apply_mode()
        self._ready = True
        GLib.timeout_add(1800, self._ensure_panel)

    def tone(self) -> str:
        if self.snap is None:
            return "ok"
        return _usage_tone(
            self.snap.api_percent,
            self.settings.warning_threshold,
            self.settings.critical_threshold,
        )

    def apply_mode(self) -> None:
        mode = self.settings.display_mode
        self._sync_mode_items(mode)
        if mode == "panel":
            self.window.hide()
            self._push_panel()
            self.indicator.set_visible(True)
        else:
            self.indicator.set_visible(False)
            self.window.apply_geometry()
            self.window.show_all()
            if not self._placed_window:
                self.window.place_default()
                self._placed_window = True
            self.window.redraw()

    def _ensure_panel(self) -> bool:
        if self.settings.display_mode == "panel" and not self.indicator.available:
            self.settings.display_mode = "window"
            save_settings(self.settings)
            self.apply_mode()
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text="顶栏不可用",
            )
            dialog.format_secondary_text(
                "GNOME 顶栏没有 StatusNotifier 宿主。\n"
                "Ubuntu 请确认已启用 AppIndicator 扩展，然后重新选择「顶栏」。"
            )
            dialog.run()
            dialog.destroy()
        return False

    def set_mode(self, mode: str) -> None:
        if mode not in DISPLAY_MODES or mode == self.settings.display_mode:
            return
        self.settings.display_mode = mode
        save_settings(self.settings)
        self.apply_mode()

    def _on_mode_item(self, item: Gtk.RadioMenuItem, mode: str) -> None:
        if not self._ready or self._applying_mode or not item.get_active():
            return
        self.set_mode(mode)

    def _sync_mode_items(self, mode: str) -> None:
        self._applying_mode = True
        try:
            for key, item in self._mode_items:
                item.set_active(key == mode)
        finally:
            self._applying_mode = False
        self.indicator.sync_mode(mode)

    def _on_toggle_top(self, item: Gtk.CheckMenuItem) -> None:
        self.settings.always_on_top = item.get_active()
        save_settings(self.settings)
        self.window.set_keep_above(self.settings.always_on_top)
        self.window.redraw()

    def apply_settings(self, settings: Settings) -> None:
        self.settings = settings.clamp()
        save_settings(self.settings)
        self.window.apply_geometry()
        if self._item_top is not None:
            self._item_top.set_active(self.settings.always_on_top)
        self._restart_timer()
        self.apply_mode()
        self._push_panel()

    def open_settings(self) -> None:
        if self._settings_open:
            return
        self._settings_open = True
        dialog = SettingsDialog(self.window, self.settings)
        try:
            if dialog.run() == Gtk.ResponseType.OK:
                self.apply_settings(dialog.result_settings(self.settings))
        finally:
            dialog.destroy()
            self._settings_open = False

    def show_about(self) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=f"{__app_name__} {__version__}",
        )
        dialog.format_secondary_text(
            "本机日账。登录态与用量只留在这台电脑上，不经过第三方服务器。\n"
            "悬浮卡：左键拖动，右键切换顶栏。\n"
            "顶栏三项为时长、API 用量、今日用量，只用小图标和数字，不含名称。"
        )
        dialog.run()
        dialog.destroy()

    def open_dashboard(self) -> None:
        parsed = urlparse(DASHBOARD_URL)
        if parsed.scheme != "https" or parsed.netloc != "cursor.com":
            return
        Gtk.show_uri_on_window(self.window, DASHBOARD_URL, Gdk.CURRENT_TIME)

    def refresh_now(self) -> None:
        if self.fetching:
            return
        self.fetching = True
        self.window.redraw()

        def work() -> None:
            snap = fetch_snapshot()
            GLib.idle_add(self._on_snapshot, snap)

        threading.Thread(target=work, daemon=True).start()

    def _on_snapshot(self, snap: Snapshot) -> bool:
        self.snap = snap
        self.fetching = False
        if self.settings.display_mode == "panel":
            self._push_panel()
        else:
            self.window.redraw()
        return False

    def _restart_timer(self) -> None:
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = 0
        self._tick_id = GLib.timeout_add(self.settings.refresh_ms, self._tick)

    def _tick(self) -> bool:
        self.refresh_now()
        return True

    def _clock_tick(self) -> bool:
        if self.settings.display_mode == "window":
            self.window.redraw()
        return True

    def _push_panel(self) -> None:
        snap = self.snap
        if snap is None or not snap.ok:
            self.indicator.set_figures(None, None, None, tone="warn")
            return
        self.indicator.set_figures(
            snap.remaining_days,
            snap.api_percent,
            snap.today_percent,
            tone=self.tone(),
        )

    def quit(self) -> None:
        self.indicator.stop()
        Gtk.main_quit()


def run() -> None:
    from pathlib import Path

    GLib.set_prgname("cursorbudget")
    icon_png = Path(__file__).resolve().parents[1] / "data" / "icons" / "cursorbudget.png"
    if icon_png.is_file():
        Gtk.Window.set_default_icon_from_file(str(icon_png))
    else:
        Gtk.Window.set_default_icon_name("cursorbudget")
    LedgerApp()
    Gtk.main()
