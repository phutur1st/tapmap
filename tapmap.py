from __future__ import annotations

import logging
import platform
import sys
import threading
import webbrowser
from datetime import datetime
from typing import Any

import psutil
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

from config import GEO_DATA_DIR, MY_LOCATION, POLL_INTERVAL_MS
from model.geoinfo import GeoInfo
from model.model import Model
from model.netinfo import NetInfo
from model.public_ip import get_public_ip
from ui.cache_view import CacheViewBuilder
from ui.map_ui import MapUI
from ui.modal_text import ModalTextBuilder
from ui.status_cache import StatusCache

LonLat = tuple[float, float]


class TapMap:
    """
    Dash controller and UI wiring.

    - Model provides live snapshots (candidates + live stats).
    - UI cache aggregates endpoints and builds map view data.
    - Map shows one marker per grouped coordinate.
    """

    MENU_ACTIONS: set[str] = {
        "menu_open_ports",
        "menu_unmapped",
        "menu_cache_terminal",
        "menu_clear",
        "menu_help",
        "menu_about",
    }

    DASH_DEBUG = False
    DEBUG_COORDS = False
    DEBUG_COORDS_EVERY_N_TICKS = 6

    APP_NAME = "TapMap"
    APP_VERSION = "v1.0"
    APP_AUTHOR = "Ola Lie"

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.app = Dash(__name__, title="TapMap", suppress_callback_exceptions=True)

        self.ui = MapUI(debug=self.DEBUG_COORDS)
        self.view_builder = CacheViewBuilder(coord_precision=2, debug=self.DEBUG_COORDS)
        self.modal_text = ModalTextBuilder(
            self.APP_NAME,
            self.APP_VERSION,
            self.APP_AUTHOR,
        )


        self.model = Model(
            netinfo=NetInfo(),
            geoinfo=GeoInfo(data_dir=GEO_DATA_DIR),
        )

        # Cached values for "My info" (no repeated network calls).
        self._public_ip_cached: str | None = None
        self._auto_geo_cached: dict[str, Any] = {}

        self.my_location = self._resolve_my_location()

        if not self.model.geoinfo.enabled:
            self.logger.warning("GeoInfo: databases not found, running without geolocation.")

        self.graph_config = {
            "displaylogo": False,
            "scrollZoom": False,
            "modeBarButtonsToRemove": [
                "toImage",
                "select2d",
                "lasso2d",
                "hoverClosestGeo",
                "toggleHover",
            ],
        }

        start_fig = self.ui.create_figure(([], self.my_location))
        self.app.layout = self._build_layout(start_fig)
        self._register_callbacks()

    # ---------- Layout ----------

    def _build_layout(self, start_fig: Any) -> html.Div:
        return html.Div(
            className="app",
            children=[
                dcc.Store(id="modal_open", data=(not self.model.geoinfo.enabled)),
                dcc.Store(id="menu_open", data=False),
                dcc.Store(id="key_action", data=None),
                dcc.Store(id="status_flash", data=None),
                dcc.Store(id="model_snapshot", data=None),
                dcc.Store(id="ui_cache", data={}),
                dcc.Store(id="status_cache", data={}),
                dcc.Store(id="ui_view", data={"points": [], "summaries": {}, "details": {}}),
                dcc.Input(
                    id="key_capture",
                    type="text",
                    value="",
                    autoFocus=False,
                    style={
                        "position": "fixed",
                        "left": "0",
                        "top": "0",
                        "width": "1px",
                        "height": "1px",
                        "opacity": "0",
                        "zIndex": "1000",
                        "pointerEvents": "none",
                    },
                ),
                dcc.Interval(id="tick_status", interval=POLL_INTERVAL_MS, n_intervals=0),
                dcc.Graph(
                    id="map",
                    figure=start_fig,
                    className="map",
                    config=self.graph_config,
                    clear_on_unhover=True,
                ),
                html.Div(self.APP_NAME, className="app-title"),
                html.Button("☰", id="btn_menu", n_clicks=0, className="mx-btn mx-btn--icon", type="button"),
                html.Div(id="menu_overlay", n_clicks=0, className="mx-overlay", style={"display": "none"}),
                html.Nav(
                    id="menu_panel",
                    className="mx-panel",
                    style={"display": "none"},
                    children=[
                        html.Div("Actions", className="mx-panel__title"),
                        self._menu_button("Show unmapped endpoints (U)", "menu_unmapped"),
                        self._menu_button("Show open ports (O)", "menu_open_ports"),
                        self._menu_button("Show cache in terminal (T)", "menu_cache_terminal"),
                        self._menu_button("Clear cache (C)", "menu_clear"),
                        html.Div(style={"height": "14px"}),
                        self._menu_button("Help (H)", "menu_help"),
                        self._menu_button("About (A)", "menu_about"),
                    ],
                ),
                html.Div(
                    id="modal_overlay",
                    className="modal-overlay",
                    style={"display": "none"},
                    children=[
                        html.Div(
                            className="modal-card",
                            children=[
                                html.Div(
                                    id="modal_body",
                                    className=("modal-body mx-sticky-title" if not self.model.geoinfo.enabled else "modal-body"),
                                    children=(self.modal_text.missing_geo_db() if not self.model.geoinfo.enabled else []),
                                ),
                                html.Button(
                                    "Close",
                                    id="btn_close",
                                    n_clicks=0,
                                    className="mx-btn mx-btn--floating",
                                    type="button",
                                ),
                            ],
                        )
                    ],
                ),
                html.Div(
                    id="status_bar",
                    className="status-bar",
                    children=(
                        "STATUS: WAIT | LIVE: CON 0 EST 0 LST 0 | "
                        "CACHE: EST 0 - LOC 0 - NON_GEO 0 = GEO 0 -> RIP 0 -> RLOC 0 | "
                        "UPDATED: --:--:--"
                    ),
                ),
            ],
        )

    def _menu_button(self, label: str, btn_id: str) -> html.Button:
        return html.Button(label, id=btn_id, n_clicks=0, className="mx-btn mx-btn--menu", type="button")

    # ---------- Helpers ----------

    @staticmethod
    def _ensure_dict(value: object) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _ensure_list(value: object) -> list[Any]:
        return value if isinstance(value, list) else []

    @staticmethod
    def _to_int(value: object, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _is_clear_action(trigger: str | None, key_action: object) -> bool:
        if trigger == "menu_clear":
            return True
        if trigger == "key_action" and isinstance(key_action, dict):
            return key_action.get("action") == "menu_clear"
        return False

    def _myloc_label(self) -> str:
        """
        Return a status label for MY_LOCATION and resolved local marker.

        OFF: MY_LOCATION == "none"
        FIXED: MY_LOCATION is (lon, lat)
        AUTO: MY_LOCATION == "auto" and resolved
        AUTO (NO GEO): MY_LOCATION == "auto" but could not resolve
        """
        if isinstance(MY_LOCATION, tuple):
            return "FIXED"
        if MY_LOCATION == "none":
            return "OFF"
        if MY_LOCATION == "auto":
            return "AUTO" if self.my_location else "AUTO (NO GEO)"
        return "OFF"

    def _resolve_my_location(self) -> list[LonLat]:
        """
        Resolve the local marker location based on config.

        Returns:
            [] if disabled or unavailable, otherwise [(lon, lat)].
        """
        if isinstance(MY_LOCATION, tuple):
            return [MY_LOCATION]

        if MY_LOCATION == "none":
            return []

        if MY_LOCATION == "auto":
            ip = get_public_ip(timeout_s=2.0)
            if not ip:
                return []

            self._public_ip_cached = ip

            geo = self.model.geoinfo.lookup(ip)
            self._auto_geo_cached = geo if isinstance(geo, dict) else {}

            lat = self._auto_geo_cached.get("lat")
            lon = self._auto_geo_cached.get("lon")

            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                return [(float(lon), float(lat))]

            return []

        return []

    def _build_app_info(self) -> dict[str, Any]:
        """
        Build the app_info payload consumed by ModalTextBuilder._render_info().

        Must not trigger network calls. Uses cached values only.
        """
        # Import inside to avoid circular imports and keep TapMap as the single source.
        from config import (  # type: ignore[attr-defined]
            BASE_DIR,
            COORD_PRECISION,
            ZOOM_NEAR_KM,
        )

        return {
            "version": self.APP_VERSION,
            "poll_interval_ms": POLL_INTERVAL_MS,
            "coord_precision": COORD_PRECISION,
            "zoom_near_km": ZOOM_NEAR_KM,
            "geoinfo_enabled": bool(self.model.geoinfo.enabled),
            "geo_data_dir": str(GEO_DATA_DIR),
            "base_dir": str(BASE_DIR),
            "myloc_mode": self._myloc_label(),
            "my_location": MY_LOCATION,
            "public_ip_cached": self._public_ip_cached,
            "auto_geo_cached": self._auto_geo_cached,
            "os": f"{platform.system()} {platform.release()}",
            "python": sys.version.split()[0],
            "psutil": getattr(psutil, "__version__", "-"),
        }

    def _handle_clear_cache(self, status_cache: StatusCache) -> tuple[dict, dict, dict, dict, dict]:
        snap = self.model.snapshot()
        status_cache.clear()

        empty_cache: dict[str, Any] = {}
        view = self.view_builder.build_view_from_cache(empty_cache)

        flash = {
            "message": "CLEARING CACHE...",
            "until": (datetime.now().timestamp() + 3.0),
        }
        return snap, empty_cache, status_cache.to_store(), view, flash
    

    def _open_browser(self, url: str, delay_s: float = 0.8) -> None:
        """
        Open a browser tab after a short delay.
        """
        import threading
        import webbrowser

        try:
            delay = float(delay_s)
        except (TypeError, ValueError):
            delay = 0.8

        def _worker() -> None:
            try:
                webbrowser.open(url, new=2)
            except Exception:
                pass

        timer = threading.Timer(delay, _worker)
        timer.daemon = True
        timer.start()



    # ---------- Callbacks ----------

    def _register_callbacks(self) -> None:
        @self.app.callback(
            Output("key_action", "data"),
            Output("key_capture", "value"),
            Input("key_capture", "value"),
            prevent_initial_call=True,
        )
        def on_key(value: str) -> tuple[Any, str]:
            if not value:
                return no_update, ""

            token = value.split("|", 1)[0]
            key_map = {
                "__o__": "menu_open_ports",
                "__u__": "menu_unmapped",
                "__t__": "menu_cache_terminal",
                "__c__": "menu_clear",
                "__h__": "menu_help",
                "__a__": "menu_about",
                "__esc__": "escape",
            }

            action = key_map.get(token)
            if not action:
                return no_update, ""
            return {"action": action, "t": datetime.now().isoformat()}, ""

        @self.app.callback(
            Output("model_snapshot", "data"),
            Output("ui_cache", "data"),
            Output("status_cache", "data"),
            Output("ui_view", "data"),
            Output("status_flash", "data"),
            Input("tick_status", "n_intervals"),
            Input("menu_clear", "n_clicks"),
            Input("menu_cache_terminal", "n_clicks"),
            Input("key_action", "data"),
            State("ui_cache", "data"),
            State("status_cache", "data"),
            prevent_initial_call=True,
        )
        def poll_model(_n, _clear_clicks, _cache_terminal_clicks, key_action, ui_cache, status_cache_data):
            trigger = ctx.triggered_id

            status_cache = StatusCache.from_store(status_cache_data)
            ui_cache_dict = self._ensure_dict(ui_cache)

            # Clear cache action (menu or keyboard)
            if self._is_clear_action(trigger, key_action):
                return self._handle_clear_cache(status_cache)

            # Show cache in terminal (menu click)
            if trigger == "menu_cache_terminal":
                status_cache.log_cache(ui_cache_dict, title="UI CACHE")
                flash = {"message": "CACHE SHOWN IN TERMINAL", "until": (datetime.now().timestamp() + 3.0)}
                return no_update, no_update, no_update, no_update, flash

            # Show cache in terminal (keyboard)
            if trigger == "key_action" and isinstance(key_action, dict):
                if key_action.get("action") == "menu_cache_terminal":
                    status_cache.log_cache(ui_cache_dict, title="UI CACHE")
                    flash = {"message": "CACHE SHOWN IN TERMINAL", "until": (datetime.now().timestamp() + 3.0)}
                    return no_update, no_update, no_update, no_update, flash

            # Normal polling
            snap = self.model.snapshot()

            if isinstance(snap, dict) and snap.get("error"):
                view = self.view_builder.build_view_from_cache(ui_cache_dict)
                snap["app_info"] = self._build_app_info()
                return snap, ui_cache_dict, status_cache.to_store(), view, no_update

            map_candidates = snap.get("map_candidates")
            candidates = map_candidates if isinstance(map_candidates, list) else []
            updated_cache = self.view_builder.merge_map_candidates(ui_cache_dict, candidates)

            cache_items = snap.get("cache_items")
            items = cache_items if isinstance(cache_items, list) else []
            status_cache.update(items)

            if self.DEBUG_COORDS and (_n % self.DEBUG_COORDS_EVERY_N_TICKS == 0):
                self.view_builder.debug_coords(updated_cache)

            view = self.view_builder.build_view_from_cache(updated_cache)

            # Attach app_info for My info (no network calls)
            if isinstance(snap, dict):
                snap["app_info"] = self._build_app_info()

            return snap, updated_cache, status_cache.to_store(), view, no_update

        @self.app.callback(
            Output("map", "figure"),
            Input("ui_view", "data"),
        )
        def update_figure(ui_view: Any) -> Any:
            view = self._ensure_dict(ui_view)
            points = self._ensure_list(view.get("points"))
            summaries = self._ensure_dict(view.get("summaries"))

            return self.ui.create_figure((points, self.my_location), summaries=summaries)

        @self.app.callback(
            Output("status_bar", "children"),
            Input("model_snapshot", "data"),
            Input("status_cache", "data"),
            Input("status_flash", "data"),
            Input("ui_view", "data"),
        )
        def render_status(snapshot: Any, status_cache_data: Any, status_flash: Any, ui_view: Any) -> str:
            if isinstance(status_flash, dict):
                message = status_flash.get("message")
                until = status_flash.get("until")
                if isinstance(message, str) and message and isinstance(until, (int, float)):
                    if datetime.now().timestamp() < float(until):
                        return message

            status_cache = StatusCache.from_store(status_cache_data)

            view = self._ensure_dict(ui_view)
            points = self._ensure_list(view.get("points"))
            rloc_map = len(points)

            cache_chain = status_cache.format_chain(rloc_map=rloc_map)

            live_con = 0
            live_est = 0
            live_lst = 0
            updated = "--:--:--"
            status = "WAIT"
            note = ""

            if isinstance(snapshot, dict):
                if snapshot.get("error"):
                    status = "ERROR"
                    note = " (see terminal)"
                else:
                    stats = snapshot.get("stats")
                    if isinstance(stats, dict):
                        online = bool(stats.get("online", True))
                        status = "OK" if online else "OFFLINE"

                        live_con = self._to_int(stats.get("live_con"))
                        live_est = self._to_int(stats.get("live_est"))
                        live_lst = self._to_int(stats.get("live_lst"))
                        updated = stats.get("updated") or updated

            myloc = self._myloc_label()
            return (
                f"STATUS: {status}{note} | "
                f"LIVE: CON {live_con} EST {live_est} LST {live_lst} | "
                f"CACHE: {cache_chain} | "
                f"UPDATED: {updated} | "
                f"MYLOC: {myloc}"
            )

        @self.app.callback(
            Output("menu_panel", "style"),
            Output("menu_overlay", "style"),
            Input("menu_open", "data"),
        )
        def show_hide_menu(is_open: Any) -> tuple[dict[str, str], dict[str, str]]:
            display = "block" if bool(is_open) else "none"
            return {"display": display}, {"display": display}

        @self.app.callback(
            Output("modal_overlay", "style"),
            Input("modal_open", "data"),
        )
        def show_hide_modal(modal_open: Any) -> dict[str, str]:
            return {"display": "flex"} if bool(modal_open) else {"display": "none"}

        @self.app.callback(
            Output("menu_open", "data"),
            Input("btn_menu", "n_clicks"),
            Input("menu_overlay", "n_clicks"),
            Input("key_action", "data"),
            Input("menu_open_ports", "n_clicks"),
            Input("menu_unmapped", "n_clicks"),
            Input("menu_cache_terminal", "n_clicks"),
            Input("menu_about", "n_clicks"),
            Input("menu_help", "n_clicks"),
            Input("menu_clear", "n_clicks"),
            State("menu_open", "data"),
            prevent_initial_call=True,
        )
        def menu_controller(
            _btn: int,
            _overlay: int,
            key_action: Any,
            _open_ports: int,
            _unmapped: int,
            _cache_terminal: int,
            _info: int,
            _help: int,
            _clear: int,
            menu_open: Any,
        ) -> Any:
            trigger = ctx.triggered_id

            if trigger == "btn_menu":
                return not bool(menu_open)

            if trigger == "menu_overlay":
                return False

            if trigger == "key_action" and isinstance(key_action, dict):
                if key_action.get("action") == "escape" and menu_open:
                    return False

            if trigger in self.MENU_ACTIONS:
                return False

            return no_update

        @self.app.callback(
            Output("modal_open", "data"),
            Output("modal_body", "children"),
            Output("modal_body", "className"),
            Input("menu_open_ports", "n_clicks"),
            Input("menu_unmapped", "n_clicks"),
            Input("menu_about", "n_clicks"),
            Input("menu_help", "n_clicks"),
            Input("toggle_unmapped_lan_local", "value", allow_optional=True),  # key
            Input("map", "clickData"),
            Input("btn_close", "n_clicks"),
            Input("key_action", "data"),
            State("modal_open", "data"),
            State("ui_view", "data"),
            State("model_snapshot", "data"),
            prevent_initial_call=True,
        )
        def modal_controller(
            _open_ports_clicks,
            _unmapped_clicks,
            _info_clicks,
            _help_clicks,
            toggle_value,
            click_data,
            _close_clicks,
            key_action,
            modal_open,
            ui_view,
            snapshot,
        ):
            trigger = ctx.triggered_id

            def _as_children(value: Any) -> list[Any]:
                if value is None:
                    return []
                if isinstance(value, (list, tuple)):
                    return list(value)
                return [value]

            def _open_with(body_children: Any, body_class: str) -> tuple[bool, list[Any], str]:
                return True, _as_children(body_children), body_class

            def _close_modal() -> tuple[bool, Any, Any]:
                return False, no_update, no_update

            def _class_for_action(action: str) -> str:
                if action in {"menu_help", "menu_open_ports", "menu_unmapped", "menu_about"}:
                    return "modal-body mx-sticky-title"
                return "modal-body"

            def _toggle_on(val: Any) -> bool:
                return isinstance(val, list) and "on" in val

            show_lan_local = _toggle_on(toggle_value)

            # Close button
            if trigger == "btn_close":
                return _close_modal()

            # Keyboard actions
            if trigger == "key_action" and isinstance(key_action, dict):
                action = key_action.get("action")

                if action == "escape" and modal_open:
                    return _close_modal()

                if isinstance(action, str):
                    if action == "menu_cache_terminal":
                        return no_update, no_update, no_update

                    if action in self.MENU_ACTIONS and action != "menu_clear":
                        body = self.modal_text.for_action(action, snapshot=snapshot, show_lan_local=show_lan_local)
                        return _open_with(body, _class_for_action(action))

            # Toggle changed: rerender unmapped if modal is open
            if trigger == "toggle_unmapped_lan_local":
                if not modal_open:
                    return no_update, no_update, no_update
                body = self.modal_text.for_action("menu_unmapped", snapshot=snapshot, show_lan_local=show_lan_local)
                return _open_with(body, _class_for_action("menu_unmapped"))

            # Menu button clicks
            if trigger in {"menu_open_ports", "menu_unmapped", "menu_help", "menu_about"}:
                action = str(trigger)
                body = self.modal_text.for_action(action, snapshot=snapshot, show_lan_local=show_lan_local)
                return _open_with(body, _class_for_action(action))

            # Map click
            if trigger == "map":
                body = self.modal_text.for_click(click_data, ui_view)
                if body is None:
                    return no_update, no_update, no_update
                return True, _as_children(body), "modal-body"

            return no_update, no_update, no_update



    # ---------- Lifecycle ----------

    def run(self) -> None:
        host = "127.0.0.1"
        port = 8050
        url = f"http://{host}:{port}/"

        self._open_browser(url)

        # skal slette
        import os
        import sys
        from pathlib import Path

        print("CWD:", Path.cwd())
        print("EXE:", Path(sys.executable).resolve())
        print("FROZEN:", getattr(sys, "frozen", False))
        print("Dash assets_folder:", self.app.config.assets_folder)

        assets_dir = Path(self.app.config.assets_folder)
        try:
            print("assets exists:", assets_dir.exists())
            if assets_dir.exists():
                print("assets files:", [p.name for p in assets_dir.iterdir() if p.is_file()][:20])
        except Exception as e:
            print("assets check failed:", e)

        # over skal slettes


        self.app.run(
            host=host,
            port=port,
            debug=self.DASH_DEBUG,
            use_reloader=False,
        )


    def close(self) -> None:
        close_fn = getattr(self.model.geoinfo, "close", None)
        if callable(close_fn):
            close_fn()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if TapMap.DEBUG_COORDS else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    app = TapMap()
    try:
        app.run()
    finally:
        app.close()
