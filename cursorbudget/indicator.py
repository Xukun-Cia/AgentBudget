"""GNOME top-bar item via StatusNotifierItem + dbusmenu."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

import cairo
from gi.repository import Gio, GLib

from . import __app_name__, __version__
from .icon import paint_app_icon

SNI_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
WATCHERS = (
    "org.kde.StatusNotifierWatcher",
    "org.freedesktop.StatusNotifierWatcher",
    "org.ayatana.StatusNotifierWatcher",
)

SNI_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionMovieName" type="s" access="read"/>
    <property name="XAyatanaLabel" type="s" access="read"/>
    <property name="XAyatanaLabelGuide" type="s" access="read"/>
    <method name="ContextMenu">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="Activate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="XAyatanaSecondaryActivate">
      <arg name="timestamp" type="u" direction="in"/>
    </method>
    <method name="Scroll">
      <arg name="delta" type="i" direction="in"/>
      <arg name="orientation" type="s" direction="in"/>
    </method>
    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewAttentionIcon"/>
    <signal name="NewOverlayIcon"/>
    <signal name="NewStatus">
      <arg name="status" type="s"/>
    </signal>
    <signal name="NewIconThemePath">
      <arg type="s" name="icon_theme_path"/>
    </signal>
    <signal name="NewMenu"/>
    <signal name="XAyatanaNewLabel">
      <arg type="s" name="label"/>
      <arg type="s" name="guide"/>
    </signal>
  </interface>
</node>
"""

MENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg type="i" name="parentId" direction="in"/>
      <arg type="i" name="recursionDepth" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="u" name="revision" direction="out"/>
      <arg type="(ia{sv}av)" name="layout" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="a(ia{sv})" name="properties" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="name" direction="in"/>
      <arg type="v" name="value" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="eventId" direction="in"/>
      <arg type="v" name="data" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg type="a(isvu)" name="events" direction="in"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" name="id" direction="in"/>
      <arg type="b" name="needUpdate" direction="out"/>
    </method>
    <method name="AboutToShowGroup">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="ai" name="updatesNeeded" direction="out"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>
    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{sv})" name="updatedProps"/>
      <arg type="a(ias)" name="removedProps"/>
    </signal>
    <signal name="LayoutUpdated">
      <arg type="u" name="revision"/>
      <arg type="i" name="parent"/>
    </signal>
    <signal name="ItemActivationRequested">
      <arg type="i" name="id"/>
      <arg type="u" name="timestamp"/>
    </signal>
  </interface>
</node>
"""

ID_WINDOW = 1
ID_PANEL = 2
ID_SEP1 = 3
ID_DASHBOARD = 4
ID_GPT_DASHBOARD = 11
ID_REFRESH = 5
ID_SEP2 = 6
ID_SETTINGS = 7
ID_ABOUT = 8
ID_SEP3 = 9
ID_QUIT = 10
# Stable width guide for the three core quota signals.
LABEL_GUIDE = "A 100.00% · C 100.00% · G 100%"


def panel_label(api, cursor, gpt=None) -> str:
    """Top bar text: Cursor API, Cursor Models, GPT weekly quota."""
    api_txt = f"{api:.2f}%" if isinstance(api, (int, float)) else "—"
    cursor_txt = f"{cursor:.2f}%" if isinstance(cursor, (int, float)) else "—"
    if isinstance(gpt, (int, float)):
        gpt_txt = f"{gpt:.0f}%" if abs(gpt - round(gpt)) < 1e-9 else f"{gpt:.2f}".rstrip("0") + "%"
    else:
        gpt_txt = "—"
    return f"A {api_txt} · C {cursor_txt} · G {gpt_txt}"


def _icon_theme_path() -> str:
    here = Path(__file__).resolve().parents[1] / "data" / "icons" / "hicolor"
    if here.is_dir():
        return str(here)
    system = Path("/usr/share/icons/hicolor")
    return str(system) if system.is_dir() else ""


def _icon_pixmap(size: int = 22, tone: str = "ok") -> tuple[int, int, bytes]:
    """Square app logo for the panel (daybook mark)."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)
    paint_app_icon(cr, float(size), tone=tone)
    raw = bytes(surface.get_data())
    out = bytearray(len(raw))
    for i in range(0, len(raw), 4):
        b, g, r, a = raw[i : i + 4]
        out[i : i + 4] = bytes((a, r, g, b))
    return size, size, bytes(out)


def _leaf(item_id: int, props: dict) -> GLib.Variant:
    return GLib.Variant("(ia{sv}av)", (item_id, props, []))


class PanelIndicator:
    def __init__(
        self,
        *,
        on_mode: Callable[[str], None],
        on_dashboard: Callable[[], None],
        on_gpt_dashboard: Callable[[], None],
        on_refresh: Callable[[], None],
        on_settings: Callable[[], None],
        on_about: Callable[[], None],
        on_quit: Callable[[], None],
        get_mode: Callable[[], str],
    ) -> None:
        self._on_mode = on_mode
        self._on_dashboard = on_dashboard
        self._on_gpt_dashboard = on_gpt_dashboard
        self._on_refresh = on_refresh
        self._on_settings = on_settings
        self._on_about = on_about
        self._on_quit = on_quit
        self._get_mode = get_mode
        self._conn: Optional[Gio.DBusConnection] = None
        self._sni_reg = 0
        self._menu_reg = 0
        self._owner_id = 0
        self._watch_ids: list[int] = []
        self._registered = False
        self._status = "Passive"
        self._label = panel_label(None, None, None)
        self._tone = "ok"
        self._revision = 1
        self._icon_theme = _icon_theme_path()
        self._pixmap = _icon_pixmap(tone=self._tone)
        self._sni_info = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
        self._menu_info = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]

    @property
    def available(self) -> bool:
        return self._registered

    def start(self) -> None:
        self._owner_id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            f"org.kde.StatusNotifierItem.cursorbudget-{os.getpid()}",
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired,
            self._on_name_acquired,
            None,
        )

    def stop(self) -> None:
        if self._conn is not None:
            if self._sni_reg:
                self._conn.unregister_object(self._sni_reg)
                self._sni_reg = 0
            if self._menu_reg:
                self._conn.unregister_object(self._menu_reg)
                self._menu_reg = 0
        for wid in self._watch_ids:
            Gio.bus_unwatch_name(wid)
        self._watch_ids.clear()
        if self._owner_id:
            Gio.bus_unown_name(self._owner_id)
            self._owner_id = 0
        self._registered = False

    def set_visible(self, visible: bool) -> None:
        self._status = "Active" if visible else "Passive"
        self._emit_sni("NewStatus", GLib.Variant("(s)", (self._status,)))
        self._emit_props({"Status": GLib.Variant("s", self._status)})

    def set_figures(self, api, cursor, gpt=None, tone: str = "ok") -> None:
        label = panel_label(api, cursor, gpt)
        tone_changed = tone != self._tone
        if label == self._label and not tone_changed:
            return
        self._label = label
        if tone_changed:
            self._tone = tone
            self._pixmap = _icon_pixmap(tone=tone)
            self._emit_sni("NewIcon", None)
            self._emit_props({"IconPixmap": GLib.Variant("a(iiay)", [self._pixmap])})
        self._emit_sni("XAyatanaNewLabel", GLib.Variant("(ss)", (self._label, LABEL_GUIDE)))
        self._emit_props({"XAyatanaLabel": GLib.Variant("s", self._label)})

    def sync_mode(self, mode: str) -> None:
        self._revision += 1
        if self._conn is None:
            return
        self._conn.emit_signal(
            None,
            MENU_PATH,
            "com.canonical.dbusmenu",
            "LayoutUpdated",
            GLib.Variant("(ui)", (self._revision, 0)),
        )
        updated = [
            (ID_WINDOW, {"toggle-state": GLib.Variant("i", 1 if mode == "window" else 0)}),
            (ID_PANEL, {"toggle-state": GLib.Variant("i", 1 if mode == "panel" else 0)}),
        ]
        self._conn.emit_signal(
            None,
            MENU_PATH,
            "com.canonical.dbusmenu",
            "ItemsPropertiesUpdated",
            GLib.Variant("(a(ia{sv})a(ias))", (updated, [])),
        )

    def _on_bus_acquired(self, conn: Gio.DBusConnection, _name: str) -> None:
        self._conn = conn
        self._sni_reg = conn.register_object(
            SNI_PATH, self._sni_info, self._sni_method, self._sni_get, None
        )
        self._menu_reg = conn.register_object(
            MENU_PATH, self._menu_info, self._menu_method, self._menu_get, None
        )
        for watcher in WATCHERS:
            self._watch_ids.append(
                Gio.bus_watch_name_on_connection(
                    conn,
                    watcher,
                    Gio.BusNameWatcherFlags.NONE,
                    lambda *_a, w=watcher: self._register(w),
                    None,
                )
            )

    def _on_name_acquired(self, _conn: Gio.DBusConnection, _name: str) -> None:
        for watcher in WATCHERS:
            if self._register(watcher):
                break

    def _register(self, watcher: str) -> bool:
        if self._conn is None:
            return False
        try:
            Gio.DBusProxy.new_sync(
                self._conn,
                Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
                None,
                watcher,
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                None,
            ).call_sync(
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", (SNI_PATH,)),
                Gio.DBusCallFlags.NONE,
                3000,
                None,
            )
            self._registered = True
            return True
        except GLib.Error:
            return False

    def _emit_sni(self, signal: str, params) -> None:
        if self._conn is None:
            return
        self._conn.emit_signal(None, SNI_PATH, "org.kde.StatusNotifierItem", signal, params)

    def _emit_props(self, changed: dict) -> None:
        if self._conn is None:
            return
        self._conn.emit_signal(
            None,
            SNI_PATH,
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            GLib.Variant("(sa{sv}as)", ("org.kde.StatusNotifierItem", changed, [])),
        )

    def _sni_get(self, _c, _s, _p, _i, name: str):
        mapping = {
            "Category": GLib.Variant("s", "SystemServices"),
            "Id": GLib.Variant("s", "cursorbudget"),
            "Title": GLib.Variant("s", __app_name__),
            "Status": GLib.Variant("s", self._status),
            "WindowId": GLib.Variant("i", 0),
            "IconThemePath": GLib.Variant("s", self._icon_theme),
            "Menu": GLib.Variant("o", MENU_PATH),
            "ItemIsMenu": GLib.Variant("b", True),
            "IconName": GLib.Variant("s", "cursorbudget"),
            "IconPixmap": GLib.Variant("a(iiay)", [self._pixmap]),
            "OverlayIconName": GLib.Variant("s", ""),
            "OverlayIconPixmap": GLib.Variant("a(iiay)", []),
            "AttentionIconName": GLib.Variant("s", ""),
            "AttentionIconPixmap": GLib.Variant("a(iiay)", []),
            "AttentionMovieName": GLib.Variant("s", ""),
            "XAyatanaLabel": GLib.Variant("s", self._label),
            "XAyatanaLabelGuide": GLib.Variant("s", LABEL_GUIDE),
        }
        return mapping.get(name)

    def _sni_method(self, _c, _s, _p, _i, method: str, _params, invocation):
        if method == "Activate":
            GLib.idle_add(self._on_dashboard)
        invocation.return_value(None)

    def _menu_get(self, _c, _s, _p, _i, name: str):
        mapping = {
            "Version": GLib.Variant("u", 3),
            "TextDirection": GLib.Variant("s", "ltr"),
            "Status": GLib.Variant("s", "normal"),
            "IconThemePath": GLib.Variant("as", []),
        }
        return mapping.get(name)

    def _item_props(self, item_id: int) -> dict:
        mode = self._get_mode()
        if item_id == ID_WINDOW:
            return {
                "label": GLib.Variant("s", "悬浮卡"),
                "toggle-type": GLib.Variant("s", "radio"),
                "toggle-state": GLib.Variant("i", 1 if mode == "window" else 0),
                "enabled": GLib.Variant("b", True),
                "visible": GLib.Variant("b", True),
            }
        if item_id == ID_PANEL:
            return {
                "label": GLib.Variant("s", "顶栏"),
                "toggle-type": GLib.Variant("s", "radio"),
                "toggle-state": GLib.Variant("i", 1 if mode == "panel" else 0),
                "enabled": GLib.Variant("b", True),
                "visible": GLib.Variant("b", True),
            }
        if item_id in (ID_SEP1, ID_SEP2, ID_SEP3):
            return {"type": GLib.Variant("s", "separator"), "visible": GLib.Variant("b", True)}
        labels = {
            ID_DASHBOARD: "打开 Cursor 用量页",
            ID_GPT_DASHBOARD: "打开 GPT 用量页",
            ID_REFRESH: "立即刷新",
            ID_SETTINGS: "设置…",
            ID_ABOUT: f"关于 {__app_name__} {__version__}",
            ID_QUIT: "退出",
        }
        if item_id in labels:
            return {
                "label": GLib.Variant("s", labels[item_id]),
                "enabled": GLib.Variant("b", True),
                "visible": GLib.Variant("b", True),
            }
        return {}

    def _layout(self) -> GLib.Variant:
        children = [
            _leaf(i, self._item_props(i))
            for i in (
                ID_WINDOW, ID_PANEL, ID_SEP1, ID_DASHBOARD, ID_GPT_DASHBOARD, ID_REFRESH,
                ID_SEP2, ID_SETTINGS, ID_ABOUT, ID_SEP3, ID_QUIT,
            )
        ]
        return GLib.Variant(
            "(ia{sv}av)",
            (0, {"children-display": GLib.Variant("s", "submenu")}, children),
        )

    def _menu_method(self, _c, _s, _p, _i, method: str, params, invocation):
        if method == "GetLayout":
            invocation.return_value(
                GLib.Variant.new_tuple(GLib.Variant("u", self._revision), self._layout())
            )
            return
        if method == "GetGroupProperties":
            ids, names = params.unpack()
            rows = []
            for item_id in ids:
                props = self._item_props(int(item_id))
                if names:
                    props = {k: v for k, v in props.items() if k in names}
                rows.append((int(item_id), props))
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (rows,)))
            return
        if method == "GetProperty":
            item_id, name = params.unpack()
            props = self._item_props(int(item_id))
            value = props.get(name, GLib.Variant("s", ""))
            invocation.return_value(GLib.Variant("(v)", (value,)))
            return
        if method == "Event":
            item_id, event_id, _data, _ts = params.unpack()
            if event_id == "clicked":
                GLib.idle_add(self._handle_click, int(item_id))
            invocation.return_value(None)
            return
        if method == "EventGroup":
            events = params.unpack()[0]
            for item_id, event_id, _data, _ts in events:
                if event_id == "clicked":
                    GLib.idle_add(self._handle_click, int(item_id))
            invocation.return_value(GLib.Variant("(ai)", ([],)))
            return
        if method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (True,)))
            return
        if method == "AboutToShowGroup":
            invocation.return_value(GLib.Variant("(aiai)", ([], [])))
            return
        invocation.return_dbus_error(
            "org.freedesktop.DBus.Error.UnknownMethod", f"Unknown method {method}"
        )

    def _handle_click(self, item_id: int) -> bool:
        if item_id == ID_WINDOW:
            self._on_mode("window")
        elif item_id == ID_PANEL:
            self._on_mode("panel")
        elif item_id == ID_DASHBOARD:
            self._on_dashboard()
        elif item_id == ID_GPT_DASHBOARD:
            self._on_gpt_dashboard()
        elif item_id == ID_REFRESH:
            self._on_refresh()
        elif item_id == ID_SETTINGS:
            self._on_settings()
        elif item_id == ID_ABOUT:
            self._on_about()
        elif item_id == ID_QUIT:
            self._on_quit()
        return False
