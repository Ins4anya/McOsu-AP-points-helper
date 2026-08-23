import threading

from nicegui import ui

from mcsu_bot.osu_api import OsuAPI
from mcsu_bot.profile import calculate_profile
from mcsu_bot.server_client import check_auth, get_server_url, sync_score
from mcsu_gui.state import bus
from mcsu_gui.theme import (
    ACCENT,
    ERROR,
    GRADE_COLORS,
    GRADE_ORDER,
    MUTED,
    SUCCESS,
    TEXT,
    WARN,
)
from mcsu_gui.widgets import GradeBadge, Tile
from mcsu_gui.workers import OsuApiScoreFetcher, ScoreFetcher, _get_latest_score


class LastScoreTab:
    def __init__(self, state):
        self.state = state
        self._result = None
        self._fetching = False
        self._auto_timer = None
        self._autoscan_mode = None
        self._autoscan_username = None
        self._autoscan_marker = None
        self._autoscan_api = None
        self._profile_loaded = False

        self._setup_ui()

        bus.subscribe("score_result", self._on_result, key="last:score_result")
        bus.subscribe("ls_status", self._on_status_event, key="last:ls_status")
        bus.subscribe("profile_result", self._on_profile_result, key="last:profile_result")
        bus.subscribe("score_sync_done", self._sync_done, key="last:score_sync_done")

    def _setup_ui(self):
        self._build_header()
        self._build_source_row()
        self._build_title_tile()
        self._build_stats_grid()
        self._build_hits_row()
        self._build_profile_area()
        self._build_status()

    def _build_header(self):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Last Score").classes("mono").style(
                "font-size: 16px; font-weight: 700; color: #ccc"
            )
            with ui.row().classes("items-center gap-2 no-wrap"):
                ui.button("Copy Log").props("dense flat").style(
                    "background: #2a2a3e; color: #aaa;"
                ).on("click", self._copy_log)

                self.profile_checkbox = ui.checkbox("Profile", on_change=self._on_profile_toggle)
                self.autoscan_checkbox = ui.checkbox("Auto-scan", on_change=self._on_autoscan_toggle)
                self.autosync_checkbox = ui.checkbox("Auto-sync")

                self.sync_btn = ui.button("Sync to Server").props("dense flat").style(
                    "background: #2a2a3e; color: #aaa;"
                ).on("click", self._on_sync)
                self.sync_btn.disable()

                self.fetch_btn = ui.button("Get Last Score").props("dense").style(
                    f"background: {ACCENT}; color: #fff; font-weight: 700;"
                ).on("click", self._on_fetch)

    def _build_source_row(self):
        with ui.row().classes("w-full items-center gap-3 no-wrap"):
            ui.label("Source:").classes("mono").style("color: #888; font-size: 12px")
            self.source_radio = ui.radio(
                {"mcsu": "McOsu", "api": "osu! API"}, value=self.state.source
            ).props("inline")
            ui.label("User:").classes("mono").style("color: #888; font-size: 12px")
            self.username_input = ui.input(
                value=self.state.username, on_change=self._on_username_change
            ).props("dense outlined").classes("w-40")
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

    def _build_title_tile(self):
        with ui.column().classes("w-full panel"):
            self.title_label = ui.label("No score loaded").style(
                "font-size: 15px; font-weight: 700; color: #fff"
            )
            self.detail_label = ui.label("").style("font-size: 12px; color: #999")

    def _build_stats_grid(self):
        with ui.grid(columns=3).classes("w-full gap-2"):
            self._tiles = {}
            definitions = [
                ("Accuracy", TEXT),
                ("PP", "#66bbff"),
                ("AP", ACCENT),
                ("Grade", TEXT),
                ("Combo", TEXT),
                ("Mods", TEXT),
            ]
            for label, color in definitions:
                self._tiles[label] = Tile(label, "—", color)

    def _build_hits_row(self):
        with ui.column().classes("w-full panel"):
            self.hits_label = ui.label("300: —  |  100: —  |  50: —  |  Miss: —").style(
                "font-size: 13px; font-weight: 700; color: #e0e0e0"
            )

    def _build_profile_area(self):
        self.profile_el = ui.column().classes("w-full panel")
        self.profile_el.visible = False
        with self.profile_el:
            ui.label("Player Profile").classes("panel-title mono")
            self.profile_name = ui.label("").style(
                "font-size: 18px; font-weight: 700; color: #fff"
            )
            with ui.grid(columns=4).classes("w-full gap-2"):
                self._profile_tiles = {}
                for label in ["Weighted PP", "Plays", "Avg Acc", "Max Combo"]:
                    self._profile_tiles[label] = Tile(label, "—")
            with ui.row().classes("gap-2"):
                self._grade_badges = {}
                for grade in GRADE_ORDER:
                    self._grade_badges[grade] = GradeBadge(grade, 0)

    def _build_status(self):
        with ui.column().classes("w-full gap-1"):
            self.status_label = ui.label("").style("font-size: 12px")
            self.log = ui.log(max_lines=200).classes("w-full log-widget")

    def _on_status_event(self, payload):
        self._set_status(payload["msg"], payload.get("color", MUTED))

    def _set_status(self, msg: str, color: str = MUTED):
        self.status_label.set_text(msg)
        self.status_label.style(replace=f"color: {color}; font-size: 12px;")
        self.log.push(msg)

    def _copy_log(self):
        import json as _json
        text = self.log._props.get("log", "")
        if not text:
            return
        ui.run_javascript(f"navigator.clipboard.writeText({_json.dumps(text.strip())})")
        self._set_status("Log copied to clipboard", MUTED)

    def _on_autoscan_toggle(self, e):
        if e.value:
            self._start_autoscan()
        else:
            self._stop_autoscan()

    def _start_autoscan(self):
        if self._auto_timer:
            return
        source = self.state.source
        if source == "mcsu":
            try:
                self._autoscan_marker = _get_latest_score(self.state.config).timestamp
            except Exception:
                self._autoscan_marker = None
            self._autoscan_mode = "mcsu"
        elif source == "api":
            username = self.state.username.strip()
            if not username:
                self._set_status("Auto-scan: enter an osu! username first", WARN)
                self.autoscan_checkbox.set_value(False)
                return
            self._autoscan_mode = "api"
            self._autoscan_username = username
            self._autoscan_marker = None
        else:
            self._set_status("Auto-scan: unknown source", WARN)
            self.autoscan_checkbox.set_value(False)
            return

        self._auto_timer = ui.timer(3.0, self._autoscan_poll)
        self._set_status(f"Auto-scan ({source}): polling every 3s...", SUCCESS)

    async def _autoscan_poll(self):
        if self._fetching:
            return
        mode = self._autoscan_mode
        if mode == "mcsu":
            try:
                marker = _get_latest_score(self.state.config).timestamp
            except Exception:
                return
            if marker is None:
                return
        else:
            if self._autoscan_api is None:
                self._autoscan_api = OsuAPI(
                    self.state.config.osu_client_id,
                    self.state.config.osu_client_secret,
                    self.state.config.osu_cache_dir,
                    self.state.config.songs_dir,
                )
            scores = await self._autoscan_api.get_recent_scores(self._autoscan_username)
            if not scores:
                return
            marker = scores[0].get("id")

        if self._autoscan_marker is not None and marker != self._autoscan_marker:
            self._autoscan_marker = marker
            self._on_fetch()
        elif self._autoscan_marker is None:
            self._autoscan_marker = marker

    def _stop_autoscan(self):
        if self._auto_timer:
            self._auto_timer.cancel()
            self._auto_timer = None
        if self._autoscan_api is not None:
            api = self._autoscan_api
            self._autoscan_api = None

            async def _close():
                try:
                    await api.close()
                except Exception:
                    pass

            ui.timer(0.1, _close, once=True)
        self._set_status("Auto-scan stopped", MUTED)

    def stop_autoscan(self):
        self._stop_autoscan()

    def _on_profile_toggle(self, e):
        if not e.value:
            self.profile_el.visible = False
            return
        if self.state.source != "mcsu":
            self._set_status("Profile is only available in McOsu source mode", WARN)
            self.profile_checkbox.set_value(False)
            return
        self._load_profile()

    def _load_profile(self, animate_grade=None):
        config = self.state.config

        def _run():
            try:
                profile = calculate_profile(config.scores_db_path, config.cfg_dir)
            except Exception as err:
                bus.emit("ls_status", {"msg": f"Profile error: {err}", "color": ERROR})
                return
            bus.emit("profile_result", {"profile": profile, "animate_grade": animate_grade})

        threading.Thread(target=_run, daemon=True).start()

    def _on_profile_result(self, payload):
        profile = payload["profile"]
        self.profile_name.set_text(profile.player_name or "Unknown")
        self._profile_tiles["Weighted PP"].set(f"{profile.weighted_pp:,.0f}")
        self._profile_tiles["Plays"].set(f"{profile.play_count:,}")
        self._profile_tiles["Avg Acc"].set(f"{profile.avg_accuracy * 100:.2f}%")
        self._profile_tiles["Max Combo"].set(f"{profile.max_combo:,}x")

        g = profile.grades
        counts = {"XH": g.xh, "X": g.x, "SH": g.sh, "S": g.s,
                  "A": g.a, "B": g.b, "C": g.c, "D": g.d}
        for grade in GRADE_ORDER:
            self._grade_badges[grade].set_count(counts[grade])

        self.profile_el.visible = True

    def _on_fetch(self):
        if self._fetching:
            return
        self._fetching = True
        self.fetch_btn.disable()
        self.fetch_btn.set_text("Loading...")

        source = self.state.source
        if source == "api":
            username = self.state.username.strip()
            if not username:
                self._set_status("Enter an osu! username first", ERROR)
                self._reset_fetch_btn()
                return
            self._set_status(f"Fetching latest score for '{username}'...", MUTED)
            self.fetcher = OsuApiScoreFetcher(
                self.state.config, username,
                on_done=lambda r: bus.emit("score_result", r),
                on_status=lambda m: bus.emit("ls_status", {"msg": m, "color": MUTED}),
            )
        else:
            self._set_status("Fetching latest score...", MUTED)
            self.fetcher = ScoreFetcher(
                self.state.config,
                on_done=lambda r: bus.emit("score_result", r),
                on_status=lambda m: bus.emit("ls_status", {"msg": m, "color": MUTED}),
            )
        self.fetcher.start()

    def _reset_fetch_btn(self):
        self._fetching = False
        self.fetch_btn.enable()
        self.fetch_btn.set_text("Get Last Score")

    def _on_result(self, result):
        self._reset_fetch_btn()

        if not result.success:
            self._set_status(f"Error: {result.error}", ERROR)
            return

        self._result = result
        self._display_score(result)

        server_url = get_server_url()
        if server_url and check_auth(server_url):
            self.sync_btn.enable()
        else:
            self.sync_btn.disable()

        if self.autosync_checkbox.value and result.inserted:
            if server_url and check_auth(server_url):
                self._auto_sync(server_url)
            else:
                self._set_status("Auto-sync: server not configured", WARN)

        if self.profile_checkbox.value:
            self._load_profile(animate_grade=result.grade)

    def _display_score(self, r):
        title = f"{r.meta.artist} - {r.meta.title} [{r.meta.difficulty}]"
        self.title_label.set_text(title)
        self.detail_label.set_text(f"★{r.meta.star_rating:.2f}  |  {r.meta.length}s  |  {int(r.meta.bpm)} BPM")

        acc_pct = r.pp_result.accuracy * 100
        self._tiles["Accuracy"].set(f"{acc_pct:.2f}%")
        self._tiles["PP"].set(f"{r.pp_result.pp:.1f} pp")
        self._tiles["AP"].set(f"{r.ap:.0f} AP", ACCENT)

        grade_color = GRADE_COLORS.get(r.grade, "#fff")
        self._tiles["Grade"].set(r.grade, grade_color)
        self._tiles["Combo"].set(f"x{r.score.max_combo}/{r.pp_result.max_combo}")
        mods_str = r.breakdown.mods_str if r.breakdown else "NM"
        self._tiles["Mods"].set(mods_str)

        self.hits_label.set_text(
            f"300: {r.score.count300}  |  100: {r.score.count100}  "
            f"|  50: {r.score.count50}  |  Miss: {r.score.count_miss}"
        )

        if r.duplicate:
            self._set_status("⚠ Duplicate score — not saved to database", WARN)
        elif r.inserted:
            self._set_status("✓ Saved to database", SUCCESS)
        else:
            self._set_status("Score loaded but not saved", MUTED)

    def _on_sync(self):
        if not self._result:
            return
        self.sync_btn.disable()
        self.sync_btn.set_text("Syncing...")
        self._send_score(get_server_url())

    def _auto_sync(self, server_url: str):
        self._set_status("Auto-sync: sending to server...", MUTED)
        self._send_score(server_url)

    def _send_score(self, server_url: str):
        if not self._result:
            return
        score_data = self._build_score_payload(self._result)

        def _do_sync():
            ok, msg = sync_score(server_url, score_data)
            bus.emit("score_sync_done", {"ok": ok, "msg": msg})

        threading.Thread(target=_do_sync, daemon=True).start()

    def _sync_done(self, payload):
        self.sync_btn.enable()
        self.sync_btn.set_text("Sync to Server")
        color = SUCCESS if payload["ok"] else ERROR
        self._set_status(f"Server: {payload['msg']}", color)

    def _build_score_payload(self, r) -> dict:
        from datetime import datetime, timezone
        played_at = datetime.fromtimestamp(r.score.timestamp, tz=timezone.utc).isoformat()
        return {
            "beatmap_id": r.meta.beatmap_id or 0,
            "beatmap_title": f"{r.meta.artist} - {r.meta.title} [{r.meta.difficulty}]",
            "beatmap_url": r.meta.map_url or "",
            "mods": r.breakdown.mods_str if r.breakdown else "NM",
            "source": self.state.source,
            "md5": r.score.beatmap_md5,
            "accuracy": r.pp_result.accuracy,
            "max_combo": r.score.max_combo,
            "max_possible_combo": r.score.max_possible_combo,
            "pp": r.pp_result.pp,
            "ap": r.ap,
            "rank": r.grade,
            "density": r.breakdown.density if r.breakdown else 0.0,
            "aim": r.breakdown.stars_aim if r.breakdown else 0.0,
            "stars": r.breakdown.star_rating if r.breakdown else r.meta.star_rating,
            "ar": r.meta.ar,
            "speed_mult": r.score.speed_mult if r.score.speed_mult else 1.0,
            "eff_cs": r.score.cs,
            "eff_ar": r.score.ar,
            "eff_od": r.score.od,
            "eff_hp": r.score.hp,
            "played_at": played_at,
        }

    def get_last_breakdown(self):
        if self._result and self._result.breakdown:
            return self._result.breakdown
        return None