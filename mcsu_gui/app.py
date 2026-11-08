from nicegui import app, ui

from mcsu_bot.paths import resource_dir
from mcsu_gui.state import AppState, bus
from mcsu_gui.tabs.ap_breakdown import APBreakdownTab
from mcsu_gui.tabs.control import ControlTab
from mcsu_gui.tabs.last_score import LastScoreTab
from mcsu_gui.tabs.ranked import RankedTab
from mcsu_gui.theme import MUTED, apply_theme
from mcsu_gui.widgets import paint_badge, status_badge

state = AppState()

_control = None
_last = None
_ranked = None
_ranked_page = "game"

SIDEBAR_WIDTH = 190
SUBMENU_MAX_WIDTH = 150


def prepare(config):
    """Called once at startup (before ui.run): set up shared state."""
    global _control, _last, _ranked, _ranked_page
    _control = _last = _ranked = None
    _ranked_page = "game"
    state.config = config
    state.source = config.source
    state.username = config.osu_username
    state.server_url = config.server_url or ""
    app.on_shutdown(_on_shutdown)


def page():
    """Root function passed to ui.run(root=page). Builds the UI.

    Using a root function (instead of plain script mode) is required for
    PyInstaller-packaged apps: NiceGUI otherwise re-runs sys.argv[0], which
    is a binary in frozen mode and fails to render.
    """
    global _control, _last, _ranked, _ranked_page

    apply_theme()

    ui.add_head_html(
        '<meta http-equiv="Content-Security-Policy" '
        "content=\"frame-src 'self' http://127.0.0.1:8001 http://localhost:8001;\">"
    )
    ui.add_head_html(
        "<style>iframe{background:transparent !important;"
        "background-color:transparent !important;}</style>"
    )

    _header()

    ranked_submenu = None
    game_btn = None
    rating_btn = None
    t_ranked = None

    active_sub = (
        "background: #1d2142; border: 1px solid #5aa0e6; color: #8cc0f5; "
        "border-radius: 6px; box-sizing: border-box; width: 100%; "
        "min-width: 0; justify-content: flex-start; text-align: left; "
        "font-size: 13px; font-weight: 600; text-transform: uppercase; "
        "letter-spacing: 0.08em; min-height: 34px; padding: 10px 12px;"
    )
    idle_sub = (
        "background: transparent; border: 1px solid transparent; color: #a3a9cf; "
        "border-radius: 6px; box-sizing: border-box; width: 100%; "
        "min-width: 0; justify-content: flex-start; text-align: left; "
        "font-size: 13px; font-weight: 600; text-transform: uppercase; "
        "letter-spacing: 0.08em; min-height: 34px; padding: 10px 12px;"
    )

    def _paint_submenu(active: str):
        for key, button in (("game", game_btn), ("rating", rating_btn)):
            if button is not None:
                button.style(replace=active_sub if key == active else idle_sub)

    def _select_ranked_page(name: str):
        global _ranked_page
        _ranked_page = name
        _paint_submenu(name)
        if _ranked is not None:
            _ranked.show_page(name)

    def _on_tab_change(event):
        value = event.value
        name = getattr(value, "name", None)
        if name is None and isinstance(value, str):
            name = value
        is_ranked = (
            value is t_ranked
            or name == getattr(t_ranked, "name", None)
            or name == "Ranked"
        )
        if ranked_submenu is not None:
            ranked_submenu.set_visibility(is_ranked)
        if is_ranked and _ranked is not None:
            _ranked.show_page(_ranked_page)

    with ui.row().classes("w-full flex-1 overflow-hidden gap-0"):
        with ui.column().classes("sidebar h-full pt-2").style(
            f"min-width: {SIDEBAR_WIDTH}px; width: {SIDEBAR_WIDTH}px; "
            "flex-shrink: 0; box-sizing: border-box; "
            "border-right: 1px solid #333865;"
        ):
            with ui.tabs().props("vertical dense").classes("sidebar-tabs") as tabs:
                t_control = ui.tab("Control", icon="tune")
                t_last = ui.tab("Last Score", icon="history")
                t_break = ui.tab("AP Breakdown", icon="pie_chart")
                t_ranked = ui.tab("Ranked", icon="emoji_events")

            ranked_submenu = ui.column().style(
                "margin: 4px 0 8px 14px; padding: 0 0 0 10px; "
                "border-left: 2px solid #333865; box-sizing: border-box; "
                f"width: calc(100% - 14px); max-width: {SUBMENU_MAX_WIDTH}px; "
                "gap: 4px;"
            )
            with ranked_submenu:
                game_btn = (
                    ui.button(
                        "Игра",
                        color=None,
                        on_click=lambda: _select_ranked_page("game"),
                    )
                    .props("flat no-caps align=left")
                    .classes("mono ranked-submenu-btn")
                    .style(idle_sub)
                )
                rating_btn = (
                    ui.button(
                        "Рейтинг",
                        color=None,
                        on_click=lambda: _select_ranked_page("rating"),
                    )
                    .props("flat no-caps align=left")
                    .classes("mono ranked-submenu-btn")
                    .style(idle_sub)
                )
            ranked_submenu.set_visibility(False)
            _paint_submenu(_ranked_page)
            tabs.on_value_change(_on_tab_change)

        with ui.tab_panels(tabs, value="Control").classes("flex-1 overflow-auto p-4"):
            with ui.tab_panel(t_control):
                _control = ControlTab(state)
            with ui.tab_panel(t_last):
                _last = LastScoreTab(state)
            with ui.tab_panel(t_break):
                APBreakdownTab(state, _last)
            with ui.tab_panel(t_ranked):
                _ranked = RankedTab(state, _last)
                _ranked.show_page(_ranked_page)

    ui.timer(0.15, bus.drain)


def _ap_badge():
    """Project favicon used as the AP badge in the header."""
    try:
        svg = (resource_dir() / "server" / "static" / "favicon.svg").read_text(
            encoding="utf-8"
        )
    except OSError:
        svg = ""
    if not svg:
        ui.label("AP").classes("mono").style(
            "width:42px;height:42px;display:flex;align-items:center;"
            "justify-content:center;border-radius:9px;border:1px solid #0d1220;"
            "background:linear-gradient(135deg,#1b3a5c,#4A9BE8);"
            "color:#e6edf5;font-weight:700;font-size:14px;flex-shrink:0;"
        )
        return
    ui.html(svg, sanitize=False).classes("ap-badge")


def _header():
    with ui.row().classes("w-full header-bar items-center justify-between no-wrap"):
        with ui.row().classes("items-center gap-3 no-wrap"):
            _ap_badge()
            with ui.column().classes("gap-0").style("line-height: 1.0;"):
                ui.label("McOsu").classes("mono").style(
                    "font-size: 20px; font-weight: 800; color: #e6edf5;"
                )
                ui.label("TRACKER").classes("mono").style(
                    "font-size: 10px; font-weight: 600; letter-spacing: 0.32em; "
                    "text-transform: uppercase; color: #8cc0f5;"
                )
            ui.label("desktop").style(
                "font-size: 10px; text-transform: uppercase; "
                "border: 1px solid #2c3158; border-radius: 6px; "
                "padding: 2px 7px; color: #a3a9cf;"
            )
        with ui.row().classes("items-center gap-2 no-wrap"):
            server_chip = status_badge("Server: Offline", MUTED)
            bot_chip = status_badge("Bot: Idle", MUTED)
            web_chip = status_badge("Web: Idle", MUTED)

    bus.subscribe(
        "server_status",
        lambda p: paint_badge(server_chip, p["text"], p["color"]),
        key="header:server_status",
    )
    bus.subscribe(
        "bot_status",
        lambda p: paint_badge(bot_chip, "Bot: " + p["text"], p["color"]),
        key="header:bot_status",
    )
    bus.subscribe(
        "web_status",
        lambda p: paint_badge(web_chip, "Web: " + p["text"], p["color"]),
        key="header:web_status",
    )


def _on_shutdown():
    if _control is not None:
        _control.stop_all()
    if _last is not None:
        _last.stop_autoscan()