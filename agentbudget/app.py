"""AgentBudget day-ledger: floating window or GNOME top-bar figures."""

from __future__ import annotations

import math
import threading
from datetime import datetime
from typing import Optional

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import __app_name__, __version__
from .fetch import Snapshot, fetch_snapshot, preserve_last_good_gpt
from .fmt import fmt_pct, fmt_pct_fine, fmt_usd, fmt_when
from .icon import paint_mark
from .indicator import PanelIndicator
from .settings import (
    BASE_H,
    BASE_W,
    DETAIL_H,
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

def _rgba(cr: cairo.Context, rgb, a: float = 1.0) -> None:
    cr.set_source_rgba(rgb[0], rgb[1], rgb[2], a)


def _match_font(query: str, fallback: str) -> str:
    try:
        import subprocess as _subprocess
        matched = _subprocess.check_output(
            ["fc-match", "-f", "%{family}", query],
            text=True,
            timeout=2,
        ).strip()
        return matched.split(",")[0].strip() or fallback
    except Exception:
        return fallback


_BODY_FONT = _match_font("Noto Sans CJK SC:lang=zh-cn", "Sans")
_DISPLAY_FONT = _match_font("Noto Serif CJK SC:lang=zh-cn", "Serif")
_FIGURE_FONT = _match_font("DejaVu Sans Mono", "Monospace")


def _set_font(
    cr: cairo.Context,
    *,
    bold: bool = False,
    size: float = 11,
    family: str = "body",
) -> None:
    weight = cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL
    font = {
        "body": _BODY_FONT,
        "display": _DISPLAY_FONT,
        "figure": _FIGURE_FONT,
    }.get(family, _BODY_FONT)
    cr.select_font_face(font, cairo.FONT_SLANT_NORMAL, weight)
    cr.set_font_size(size)


def _rounded_rect(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
    r = max(0.0, min(r, w / 2, h / 2))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, math.pi * 1.5)
    cr.close_path()


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


def _cursor_today(
    percent: Optional[float],
    cents: Optional[float],
    events: Optional[int],
    truncated: bool,
) -> str:
    """Today's spend in one Cursor pool: share of the pool, dollars, events."""
    parts = []
    if percent is not None:
        parts.append(fmt_pct_fine(percent))
    if cents is not None:
        parts.append(fmt_usd(cents))
    if not parts:
        return "—"
    if events is not None:
        parts.append(f"{events} 笔")
    if truncated:
        parts.append("未拉全")
    return " · ".join(parts)


def _codex_today(snap: Snapshot) -> str:
    """Codex has no per-day figure upstream, only what this machine sampled."""
    percent = snap.gpt_today_percent
    if percent is None:
        return "—"
    if snap.gpt_today_partial:
        return "—" if percent <= 0 else f"≥{fmt_pct(percent)}"
    return fmt_pct(percent)


def _cycle_text(start: Optional[str], end: Optional[str]) -> str:
    if not start and not end:
        return "—"
    return f"{fmt_when(start)} → {fmt_when(end)}"


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

        grid.attach(Gtk.Label(label="外观", xalign=0), 0, 3, 1, 1)
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
            label="顶栏与主界面显示 A / G；展开查看 C 与订阅周期。",
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
    item_refresh = Gtk.MenuItem(label="立即刷新")
    item_refresh.connect("activate", lambda *_: app.refresh_now())
    menu.append(item_refresh)
    item_settings = Gtk.MenuItem(label="设置…")
    item_settings.connect("activate", lambda *_: app.open_settings())
    menu.append(item_settings)

    menu.append(Gtk.SeparatorMenuItem())
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
        self.details_expanded = False
        self._hover = None
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
        self.drawing.set_can_focus(True)
        self.drawing.connect("key-press-event", self._on_key_press)
        self.drawing.connect("focus-in-event", lambda *_: self.redraw())
        self.drawing.connect("focus-out-event", lambda *_: self.redraw())
        self.add(self.drawing)

        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.connect("button-press-event", self._on_button_press)
        self.connect("button-release-event", self._on_button_release)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("leave-notify-event", self._on_leave)
        self.connect("delete-event", lambda *_: app.quit() or True)

        self.menu = _build_menu(app, show_always_on_top=True)

    def apply_geometry(self) -> None:
        win_w, win_h = self.app.settings.window_size(self.logical_height)
        self.drawing.set_size_request(win_w, win_h)
        self.resize(win_w, win_h)
        self.set_size_request(win_w, win_h)
        self.set_keep_above(self.app.settings.always_on_top)

    def place_default(self) -> None:
        screen = Gdk.Screen.get_default()
        if screen is None:
            return
        geo = screen.get_monitor_geometry(screen.get_primary_monitor())
        ww, hh = self.app.settings.window_size(self.logical_height)
        self.move(geo.x + geo.width - ww - 36, geo.y + geo.height - hh - 80)

    @property
    def logical_height(self) -> int:
        return DETAIL_H if self.details_expanded else BASE_H

    def toggle_details(self) -> None:
        self.details_expanded = not self.details_expanded
        self.apply_geometry()
        self.redraw()

    def redraw(self) -> None:
        self.drawing.queue_draw()

    def _on_button_press(self, _w, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            self.menu.popup_at_pointer(event)
            return True
        if event.button == 1:
            alloc = self.drawing.get_allocation()
            logical_x = event.x * BASE_W / max(1, alloc.width)
            logical_y = event.y * self.logical_height / max(1, alloc.height)
            self.drawing.grab_focus()
            if logical_x >= BASE_W - 48 and 12 <= logical_y <= 48:
                self.app.quit()
                return True
            if 24 <= logical_x <= BASE_W - 24 and 376 <= logical_y <= 414:
                self.toggle_details()
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

    def _on_key_press(self, _w, event) -> bool:
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_space):
            self.toggle_details()
            return True
        if event.keyval == Gdk.KEY_F5:
            self.app.refresh_now()
            return True
        if event.keyval == Gdk.KEY_Menu:
            self.menu.popup_at_widget(self.drawing, Gdk.Gravity.SOUTH_WEST,
                                      Gdk.Gravity.NORTH_WEST, event)
            return True
        return False

    def _on_leave(self, *_args) -> bool:
        self._hover = None
        self.redraw()
        return False

    def _on_motion(self, _w, event: Gdk.EventMotion) -> bool:
        alloc = self.drawing.get_allocation()
        x = event.x * BASE_W / max(1, alloc.width)
        y = event.y * self.logical_height / max(1, alloc.height)
        hover = ("close" if x >= BASE_W - 48 and 12 <= y <= 48 else
                 "details" if 24 <= x <= BASE_W - 24 and 376 <= y <= 414 else None)
        if hover != self._hover:
            self._hover = hover
            self.redraw()
            if self.get_window():
                self.get_window().set_cursor(Gdk.Cursor.new_from_name(
                    self.get_display(), "pointer" if hover else "default"))
        if self._dragging and (event.state & Gdk.ModifierType.BUTTON1_MASK):
            dx = int(event.x_root) - self._drag_ox
            dy = int(event.y_root) - self._drag_oy
            self.move(self._origin_x + dx, self._origin_y + dy)
            return True
        return False

    def _on_draw(self, _widget, cr: cairo.Context) -> bool:
        alloc = self.drawing.get_allocation()
        cr.save()
        cr.scale(alloc.width / BASE_W, alloc.height / self.logical_height)
        self._paint_logical(cr)
        cr.restore()
        return False

    def _text(self, cr, text, x, y, color, size=11, bold=False, family="body", width=None):
        _set_font(cr, bold=bold, size=size, family=family)
        value = str(text)
        if width is not None:
            while value and cr.text_extents(value).width > width:
                value = value[:-2] + "…" if len(value) > 1 else ""
        _rgba(cr, color)
        cr.move_to(x, y)
        cr.show_text(value)

    def _paint_logical(self, cr: cairo.Context) -> None:
        """Two large quota instruments, with secondary information on demand."""
        snap = self.app.snap
        w, h = BASE_W, self.logical_height
        paper, ink, muted, rule, accent, alert, _ = self.app.settings.colors()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        # An inset frame gives the native window a quiet, machined edge.
        _rounded_rect(cr, 4, 4, w - 8, h - 8, 22)
        cr.save()
        cr.clip()
        _rgba(cr, paper)
        cr.paint()
        light = cairo.RadialGradient(30, 0, 0, 30, 0, 440)
        light.add_color_stop_rgba(0, *accent, 0.12)
        light.add_color_stop_rgba(1, *accent, 0)
        cr.set_source(light)
        cr.paint()
        cr.restore()
        _rounded_rect(cr, 4.5, 4.5, w - 9, h - 9, 22)
        _rgba(cr, accent, 0.3)
        cr.set_line_width(1)
        cr.stroke()
        self._text(cr, "AGENT / BUDGET", 26, 33, ink, 12, True, "figure")
        _rgba(cr, accent if not self.app.fetching else muted)
        cr.arc(27, 49, 2, 0, math.tau)
        cr.fill()
        updated = getattr(self.app, "last_updated", None)
        status = "正在同步" if self.app.fetching else (f"更新于 {updated}" if updated else "等待同步")
        self._text(cr, status, 36, 53, muted, 9)
        if getattr(self, "_hover", None) == "close":
            _rgba(cr, alert, 0.14)
            _rounded_rect(cr, w - 46, 14, 30, 30, 9)
            cr.fill()
        self._text(cr, "×", w - 37, 35, muted, 19)

        for top, letter, label, pct, reset, error, stale in (
            (76, "A", "Cursor API", snap.api_percent if snap else None,
             snap.cycle_end if snap else None, (snap.error if snap and not snap.ok else None), False),
            (222, "G", "Codex 周额度", snap.gpt_percent if snap and snap.gpt_ok else None,
             snap.gpt_reset_at if snap else None, (snap.gpt_error if snap and not snap.gpt_ok else None),
             bool(snap and snap.gpt_stale)),
        ):
            color = alert if _usage_tone(pct, self.app.settings.warning_threshold,
                                        self.app.settings.critical_threshold) != "ok" else accent
            self._metric_row(cr, top, letter, label, pct, reset, error, stale,
                             color, ink, muted, rule)
        self._rule(cr, 26, 207, w - 26, rule)

        hover = getattr(self, "_hover", None) == "details"
        _rounded_rect(cr, 24, 376, w - 48, 38, 10)
        _rgba(cr, accent, 0.17 if hover else 0.08)
        cr.fill_preserve()
        if getattr(self, "drawing", None) is not None and self.drawing.has_focus():
            _rgba(cr, accent, 0.8)
            cr.set_line_width(1.2)
            cr.stroke()
        else:
            cr.new_path()
        self._text(cr, "收起详情" if self.details_expanded else "展开详情", 38, 400, ink, 11, True)
        self._chevron(cr, w - 41, 395, up=self.details_expanded, color=accent)
        if self.details_expanded:
            self._paint_details(cr, snap, ink, muted, rule, accent)

    def _meter(self, cr, x, y, width, pct, color, rule):
        _rgba(cr, rule, 0.6)
        _rounded_rect(cr, x, y, width, 5, 2.5)
        cr.fill()
        if pct is not None and math.isfinite(pct) and pct > 0:
            fill = max(5, min(width, width * pct / 100))
            gradient = cairo.LinearGradient(x, y, x + width, y)
            gradient.add_color_stop_rgba(0, *color, 0.5)
            gradient.add_color_stop_rgba(1, *color, 1)
            cr.set_source(gradient)
            _rounded_rect(cr, x, y, fill, 5, 2.5)
            cr.fill()
        for tick in range(11):
            _rgba(cr, rule, 0.7)
            cr.rectangle(x + tick * width / 10, y + 10, 1, 3 if tick % 5 else 5)
            cr.fill()

    def _metric_row(self, cr, top, letter, label, pct, reset, error, stale,
                    color, ink, muted, rule):
        self._text(cr, letter, 26, top + 19, color, 17, True, "figure")
        self._text(cr, label, 51, top + 18, muted, 11)
        self._text(cr, "已用" + (" · 缓存" if stale else ""), BASE_W - (89 if stale else 50),
                   top + 18, muted, 9)
        value = fmt_pct(pct)
        number = value.rstrip("%")
        self._text(cr, number, 24, top + 77, ink, 58, True, "figure")
        number_width = cr.text_extents(number).width
        if value.endswith("%"):
            self._text(cr, "%", 32 + number_width, top + 76, color, 24, False, "figure")
        self._meter(cr, 27, top + 88, BASE_W - 54, pct, color, rule)
        sub = error or ("正在读取用量" if self.app.snap is None else
                        f"重置 {fmt_when(reset)}" if reset else "重置时间暂不可用")
        self._text(cr, sub, 27, top + 125, muted, 10, width=BASE_W - 54)

    def _paint_details(self, cr, snap, ink, muted, rule, accent) -> None:
        snap = snap or Snapshot(ok=False)
        self._text(cr, "C", 27, 447, accent, 14, True, "figure")
        self._text(cr, "Cursor Models", 49, 447, muted, 11)
        pct = fmt_pct(snap.auto_percent)
        _set_font(cr, size=23, bold=True, family="figure")
        self._text(cr, pct, BASE_W - 27 - cr.text_extents(pct).width, 477,
                   ink, 23, True, "figure")
        self._text(cr, f"{fmt_usd(snap.auto_used_cents)} / {fmt_usd(snap.auto_limit_cents)}",
                   27, 476, muted, 10, width=BASE_W - 155)
        self._meter(cr, 27, 490, BASE_W - 54, snap.auto_percent, accent, rule)
        self._rule(cr, 27, 522, BASE_W - 27, rule)
        for y, label, start, end, estimated in (
            (548, "Cursor 订阅周期", snap.cycle_start, snap.cycle_end, False),
            (612, "Codex 订阅周期", snap.gpt_cycle_start, snap.gpt_cycle_end,
             snap.gpt_cycle_estimated),
        ):
            self._text(cr, label + (" · 预计" if estimated else ""), 27, y, muted, 10)
            value = _cycle_text(start, end) if start or end else "暂不可用"
            self._text(cr, value, 27, y + 24, ink, 12, True, width=BASE_W - 54)

    def _chevron(self, cr, x, y, *, up: bool, color) -> None:
        _rgba(cr, color)
        cr.set_line_width(1.4)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        if up:
            cr.move_to(x - 4, y + 2)
            cr.line_to(x, y - 2)
            cr.line_to(x + 4, y + 2)
        else:
            cr.move_to(x - 4, y - 2)
            cr.line_to(x, y + 2)
            cr.line_to(x + 4, y - 2)
        cr.stroke()

    def _rule(self, cr: cairo.Context, x: float, y: float, right: float, rule) -> None:
        _rgba(cr, rule)
        cr.set_line_width(0.9)
        cr.move_to(x, y)
        cr.line_to(right, y)
        cr.stroke()

class LedgerApp:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.snap: Optional[Snapshot] = None
        self.fetching = False
        self.last_updated: Optional[str] = None
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
        figures = [p for p in (self.snap.api_percent, self.snap.gpt_percent) if p is not None]
        return _usage_tone(max(figures) if figures else None,
                           self.settings.warning_threshold, self.settings.critical_threshold)

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
            "Cursor 走本机编辑器登录；Codex 走本机 ~/.codex 登录。\n"
            "窗口：左键拖动，点「展开详情」查看 C 与订阅周期，右键打开菜单。"
        )
        dialog.run()
        dialog.destroy()

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
        snap = preserve_last_good_gpt(snap, self.snap)
        self.snap = snap
        self.fetching = False
        self.last_updated = _clock_now()[:5]
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
            self.indicator.set_figures(
                snap.api_percent if snap else None,
                snap.gpt_percent if snap else None,
                tone="warn",
                gpt_stale=bool(snap and snap.gpt_stale),
            )
            return
        self.indicator.set_figures(
            snap.api_percent,
            snap.gpt_percent if snap.gpt_ok else None,
            tone=self.tone(),
            gpt_stale=snap.gpt_stale,
        )

    def quit(self) -> None:
        self.indicator.stop()
        Gtk.main_quit()


def run() -> None:
    from pathlib import Path

    GLib.set_prgname("agentbudget")
    icon_png = Path(__file__).resolve().parents[1] / "data" / "icons" / "agentbudget.png"
    if icon_png.is_file():
        Gtk.Window.set_default_icon_from_file(str(icon_png))
    else:
        Gtk.Window.set_default_icon_name("agentbudget")
    LedgerApp()
    Gtk.main()
