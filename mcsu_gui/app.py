from nicegui import app, ui

from mcsu_gui.state import AppState, bus
from mcsu_gui.tabs.ap_breakdown import APBreakdownTab
from mcsu_gui.tabs.control import ControlTab
from mcsu_gui.tabs.last_score import LastScoreTab
from mcsu_gui.theme import ACCENT, MUTED, apply_theme
from mcsu_gui.widgets import paint_badge, status_badge

state = AppState()

_control = None
_last = None


def prepare(config):
    """Called once at startup (before ui.run): set up shared state."""
    global _control, _last
    _control = _last = None
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
    global _control, _last

    apply_theme()

    _header()

    with ui.row().classes("w-full flex-1 overflow-hidden gap-0"):
        with ui.column().classes("sidebar h-full pt-2").style(
            "min-width: 190px; flex-shrink: 0;"
        ):
            with ui.tabs().props("vertical dense").classes("sidebar-tabs") as tabs:
                t_control = ui.tab("Control", icon="tune")
                t_last = ui.tab("Last Score", icon="history")
                t_break = ui.tab("AP Breakdown", icon="pie_chart")

        with ui.tab_panels(tabs, value="Control").classes("flex-1 overflow-auto p-4"):
            with ui.tab_panel(t_control):
                _control = ControlTab(state)
            with ui.tab_panel(t_last):
                _last = LastScoreTab(state)
            with ui.tab_panel(t_break):
                APBreakdownTab(state, _last)

    ui.timer(0.15, bus.drain)


def _header():
    with ui.row().classes("w-full header-bar items-center justify-between no-wrap"):
        with ui.row().classes("items-center gap-3 no-wrap"):
            ui.icon("music_note").style(f"color: {ACCENT}; font-size: 26px")
            ui.label("McOsu AP Tracker").classes("mono").style(
                "font-size: 16px; font-weight: 700; color: #fff; letter-spacing: 0.3px"
            )
            ui.label("desktop").style("color: #8b95a7; font-size: 11px")
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