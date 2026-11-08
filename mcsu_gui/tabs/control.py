from nicegui import ui

from mcsu_bot.local_library import scan_songs
from mcsu_bot.paths import ap_db_file
from mcsu_bot.server_client import (
    check_auth,
    get_server_url,
    get_saved_token,
    parse_login_link,
    save_server_token,
    sync_all_scores,
    sync_local_beatmaps,
)
from mcsu_gui.state import bus
from mcsu_gui.theme import MUTED, PINK, SUCCESS
from mcsu_gui.widgets import paint_badge, status_badge
from mcsu_gui.workers import ProcessWorker, free_port


def _status_badge(text: str = "Idle", color: str = MUTED):
    return status_badge(text, color)


class ControlTab:
    def __init__(self, state):
        self.state = state
        free_port(8080)

        self.bot_process = ProcessWorker(
            on_output=lambda m: bus.emit("log", m),
            on_started=lambda: bus.emit("bot_status", {"text": "Active", "color": SUCCESS}),
            on_stopped=lambda: bus.emit("bot_status", {"text": "Idle", "color": MUTED}),
        )
        self.web_process = ProcessWorker(
            on_output=lambda m: bus.emit("log", m),
            on_started=lambda: bus.emit("web_status", {"text": "Active :8080", "color": SUCCESS}),
            on_stopped=lambda: bus.emit("web_status", {"text": "Idle", "color": MUTED}),
        )
        self.overlay_process = ProcessWorker(
            on_output=lambda m: bus.emit("log", m),
            on_started=lambda: bus.emit("overlay_status", {"text": "Active :8001", "color": SUCCESS}),
            on_stopped=lambda: bus.emit("overlay_status", {"text": "Idle", "color": MUTED}),
        )

        self._setup_ui()

        bus.subscribe("log", self._on_log, key="control:log")
        bus.subscribe("bot_status", lambda p: self._paint(self.bot_badge, p), key="control:bot")
        bus.subscribe("web_status", lambda p: self._paint(self.web_badge, p), key="control:web")
        bus.subscribe("overlay_status", lambda p: self._paint(self.overlay_badge, p), key="control:overlay")
        bus.subscribe("sync_done", self._sync_all_done, key="control:sync_done")

    def _setup_ui(self):
        with ui.column().classes("w-full gap-0"):
            self._build_source_selector()
            self._build_server_section()
            self._build_bot_section()
            self._build_web_section()
            self._build_overlay_section()
            self._build_console()

    def _build_source_selector(self):
        with ui.card().classes("w-full tile"):
            with ui.row().classes("items-center w-full gap-3 no-wrap"):
                ui.label("Source:").classes("mono").style("color: #aaa; font-size: 13px")
                self.source_radio = ui.radio(
                    {"mcsu": "McOsu", "api": "osu! API"}, value=self.state.source
                ).props("inline")
                ui.label("Username:").classes("mono").style("color: #888; font-size: 13px")
                self.username_input = ui.input(
                    value=self.state.username, on_change=self._on_username_change
                ).props("dense outlined").classes("w-48")
                self._on_source_change(self.state.source)
                self.source_radio.on_value_change(self._on_source_change)

    def _on_source_change(self, value):
        self.state.source = value
        if value == "api":
            self.username_input.enable()
        else:
            self.username_input.disable()

    def _on_username_change(self, e):
        self.state.username = e.value
        self.state.overlay_osu_id = None
        self.state.overlay_url = ""

    def _build_server_section(self):
        config = self.state.config
        with ui.card().classes("w-full tile"):
            ui.label("Server Sync").classes("mono").style(
                "font-size: 14px; font-weight: 700; color: #ccc"
            )
            with ui.row().classes("items-center w-full gap-3 no-wrap"):
                saved_url = config.server_url or get_server_url()
                self.state.server_url = saved_url
                ui.label("Server URL:").classes("mono").style("color: #888; font-size: 13px")
                self.server_url_input = ui.input(
                    value=saved_url, placeholder="https://ins4anya.fun",
                    on_change=self._on_server_url_change,
                ).props("dense outlined").classes("flex-1")
                ui.button("Login via osu!").props("dense flat").style(
                    f"background: {PINK}; color: #fff;"
                ).on("click", self._on_server_login)

            with ui.row().classes("items-center w-full gap-3 no-wrap"):
                saved_token = config.server_token or get_saved_token()
                ui.label("Token / link:").classes("mono").style("color: #888; font-size: 13px")
                self.token_input = ui.input(
                    value=saved_token,
                    placeholder="Paste the token from your profile page",
                ).props("dense outlined").classes("flex-1")
                ui.button("Save").props("dense flat").style(
                    f"background: #2a2a3e; color: #aaa;"
                ).on("click", self._on_save_token)

            ui.label(
                "After login, click \u201cCopy token\u201d on your profile page and paste it here"
            ).style("color: #8b95a7; font-size: 11px")

            self.share_library_checkbox = ui.checkbox(
                "Share my Songs folder list with the server (for Daily Challenge)",
                value=config.share_local_beatmaps,
            ).props("dense").style("color: #8b95a7; font-size: 12px")
            self.share_library_checkbox.on_value_change(self._on_share_library_change)

            with ui.row().classes("items-center w-full justify-between no-wrap"):
                self.server_badge = _status_badge("Not connected", MUTED)
                self.sync_all_btn = ui.button("Sync Local Scores").props("dense flat").style(
                    "background: #2a2a3e; color: #aaa;"
                ).on("click", self._on_sync_all)
                self.sync_all_btn.disable()

            if config.server_url and config.server_token:
                save_server_token(config.server_url, config.server_token)

            self._update_server_status()

    def _on_server_url_change(self, e):
        self.state.server_url = e.value.strip()
        self._update_server_status()

    def _on_server_login(self):
        server_url = self.state.server_url
        if not server_url:
            bus.emit("log", "Enter server URL first")
            return
        import webbrowser
        webbrowser.open(f"{server_url.rstrip('/')}/auth/login")

    def _on_save_token(self):
        text = self.token_input.value.strip()
        if not text:
            bus.emit("log", "Paste the profile link or token first")
            return
        server_url, token = parse_login_link(text)
        if not token:
            bus.emit("log", "Could not parse token — paste the link or the JWT token")
            return
        if not server_url:
            server_url = self.state.server_url
        if not server_url:
            bus.emit("log", "Could not detect server URL — fill the Server URL field")
            return
        self.server_url_input.set_value(server_url)
        self.state.server_url = server_url
        save_server_token(server_url, token)
        bus.emit("log", f"Saved token for {server_url}")
        self._update_server_status()

    def _update_server_status(self):
        url = self.state.server_url
        if url and check_auth(url):
            self._paint(self.server_badge, {"text": "Connected", "color": SUCCESS})
            self.sync_all_btn.enable()
            bus.emit("server_status", {"text": "Server: Connected", "color": SUCCESS})
        else:
            self._paint(self.server_badge, {"text": "Not connected", "color": MUTED})
            self.sync_all_btn.disable()
            bus.emit("server_status", {"text": "Server: Offline", "color": MUTED})

    def _on_share_library_change(self, e):
        if not e.value:
            return
        server_url = self.state.server_url
        if not server_url or not check_auth(server_url):
            bus.emit("log", "Songs library: connect to the server first, then press Sync Local Scores")
            return
        self._sync_library(server_url)

    def _sync_library(self, server_url: str):
        songs_dir = self.state.config.songs_dir
        if not songs_dir or not songs_dir.is_dir():
            bus.emit("log", "Songs library: songs_dir is not set or missing, skipped")
            return

        def _run():
            beatmaps = scan_songs(songs_dir)
            _, msg = sync_local_beatmaps(server_url, beatmaps)
            bus.emit("log", f"Songs library: {msg}")

        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _on_sync_all(self):
        server_url = self.state.server_url
        if not server_url or not check_auth(server_url):
            bus.emit("log", "Not connected — save the token first")
            return
        self.sync_all_btn.disable()
        self.sync_all_btn.set_text("Syncing...")
        bus.emit("log", "Starting full sync...")
        ap_db_path = self.state.config.ap_db_path or _default_ap_db()
        source = self.state.source
        share_library = self.share_library_checkbox.value
        songs_dir = self.state.config.songs_dir

        def _run():
            if share_library and songs_dir and songs_dir.is_dir():
                beatmaps = scan_songs(songs_dir)
                _, msg = sync_local_beatmaps(server_url, beatmaps)
                bus.emit("log", f"Songs library: {msg}")
            elif share_library:
                bus.emit("log", "Songs library: songs_dir is not set or missing, skipped")
            synced, duplicate, failed, errors = sync_all_scores(
                server_url, ap_db_path, source,
                on_progress=lambda i, total: (
                    bus.emit("log", f"Syncing... {i}/{total}")
                    if (i % 20 == 0 or i == total)
                    else None
                ),
            )
            bus.emit("sync_done", {"synced": synced, "duplicate": duplicate,
                                   "failed": failed, "errors": errors})

        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _sync_all_done(self, payload):
        synced = payload["synced"]
        duplicate = payload["duplicate"]
        failed = payload["failed"]
        errors = payload["errors"]
        self.sync_all_btn.enable()
        self.sync_all_btn.set_text("Sync Local Scores")
        bus.emit("log", f"Sync finished: {synced} synced, {duplicate} already on server, {failed} failed")
        for err in errors[:10]:
            bus.emit("log", f"  ! {err}")
        if len(errors) > 10:
            bus.emit("log", f"  ... and {len(errors) - 10} more errors")

    def _build_bot_section(self):
        with ui.card().classes("w-full tile"):
            with ui.row().classes("items-center w-full justify-between no-wrap"):
                self.bot_switch = ui.switch("Launch Discord Bot", on_change=self._on_bot_toggle)
                self.bot_badge = _status_badge()

    def _build_web_section(self):
        with ui.card().classes("w-full tile"):
            with ui.row().classes("items-center w-full justify-between no-wrap"):
                self.web_switch = ui.switch("Launch Web Server  (:8080)", on_change=self._on_web_toggle)
                self.web_badge = _status_badge()

    def _build_console(self):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Console Log").classes("mono").style(
                "font-size: 16px; font-weight: 700; color: #ccc"
            )
            ui.button("Copy Log").props("dense flat").style(
                "background: #2a2a3e; color: #aaa;"
            ).on("click", self._copy_log)
        self.console = ui.log(max_lines=500).classes("w-full flex-1 log-widget")

    def _copy_log(self):
        import json as _json
        text = self.console._props.get("log", "")
        if not text:
            return
        ui.run_javascript(f"navigator.clipboard.writeText({_json.dumps(text.strip())})")
        bus.emit("log", "📋 Log copied to clipboard")

    def _on_bot_toggle(self, e):
        if e.value:
            self.bot_switch.disable()
            self.bot_switch.set_text("Starting...")
            ui.timer(0.1, lambda: (self._start_bot(), self._restore_switch(self.bot_switch, "Launch Discord Bot")), once=True)
        else:
            self.bot_process.stop()
            self.bot_switch.enable()

    def _start_bot(self):
        self.state.config.source = self.state.source
        self.bot_process.start_bot(self.state.config)

    def _on_web_toggle(self, e):
        if e.value:
            self.web_switch.disable()
            self.web_switch.set_text("Starting...")
            ui.timer(0.1, lambda: (self._start_web(), self._restore_switch(self.web_switch, "Launch Web Server  (:8080)")), once=True)
        else:
            self.web_process.stop()
            self.web_switch.enable()

    def _start_web(self):
        free_port(8080)
        self.web_process.start_web(self.state.config)

    def _build_overlay_section(self):
        with ui.card().classes("w-full tile"):
            with ui.row().classes("items-center w-full justify-between no-wrap"):
                self.overlay_switch = ui.switch(
                    "Launch Overlay  (:8001)", on_change=self._on_overlay_toggle
                )
                self.overlay_badge = _status_badge()

    def _on_overlay_toggle(self, e):
        self.state.overlay_enabled = bool(e.value)
        if e.value:
            free_port(8001)
            self.overlay_process.start_overlay(self.state.config)
        else:
            self.overlay_process.stop()
        bus.emit(
            "overlay_status",
            {
                "text": "Active :8001" if e.value else "Idle",
                "color": SUCCESS if e.value else MUTED,
            },
        )

    def _restore_switch(self, switch, text):
        switch.enable()
        switch.set_text(text)

    def _on_log(self, text):
        self.console.push(text)

    def _paint(self, badge, payload):
        paint_badge(badge, payload["text"], payload["color"])

    def stop_all(self):
        self.bot_process.stop()
        self.web_process.stop()
        self.overlay_process.stop()


def _default_ap_db():
    return ap_db_file()