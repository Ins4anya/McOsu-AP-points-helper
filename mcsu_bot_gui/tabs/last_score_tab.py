import customtkinter as ctk
import threading

from mcsu_bot.server_client import (
    check_auth,
    get_server_url,
    sync_score,
)
from mcsu_bot_gui.workers.score_worker import (
    ScoreFetcher,
    OsuApiScoreFetcher,
    AutoScanWorker,
    OsuApiAutoScanWorker,
)
from mcsu_bot.profile import calculate_profile
from mcsu_bot_gui.widgets import GlassTile, GLASS_BG, GLASS_BORDER, TILE_BG, ACCENT


GRADE_COLORS = {
    "XH": "#ffd700", "X": "#ffd700",
    "SH": "#ff69b4", "S": "#ff69b4",
    "A": "#00ff7f", "B": "#1e90ff",
    "C": "#ff4500", "D": "#ff0000",
}
GRADE_ORDER = ["XH", "X", "SH", "S", "A", "B", "C", "D"]


class LastScoreTab(ctk.CTkFrame):
    def __init__(self, master, config, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.config = config
        self._result = None
        self._auto_scanner = None
        self._setup_ui()

    def _setup_ui(self):
        self._build_header()
        self._build_source_row()
        self._build_title_tile()
        self._build_stats_grid()
        self._build_hits_row()
        self._build_profile_area()
        self._build_status()

    def _build_header(self):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(row, text="Last Score", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ccc").pack(side="left")

        controls = ctk.CTkFrame(row, fg_color="transparent")
        controls.pack(side="right")

        ctk.CTkButton(controls, text="Copy Log", font=ctk.CTkFont(size=11),
                      fg_color="#2a2a3e", hover_color="#3a3a5e", text_color="#aaa",
                      width=70, command=self._copy_log).pack(side="left", padx=(0, 6))

        self.profile_var = ctk.BooleanVar(value=False)
        self.profile_cb = ctk.CTkCheckBox(controls, text="Profile", variable=self.profile_var,
                                           command=self._on_profile_toggle,
                                           font=ctk.CTkFont(size=12), text_color="#aaa",
                                           fg_color=ACCENT, hover_color="#6CB4EE")
        self.profile_cb.pack(side="left", padx=(0, 6))

        self.autoscan_var = ctk.BooleanVar(value=False)
        self.autoscan_cb = ctk.CTkCheckBox(controls, text="Auto-scan", variable=self.autoscan_var,
                                            command=self._on_autoscan_toggle,
                                            font=ctk.CTkFont(size=12), text_color="#aaa",
                                            fg_color=ACCENT, hover_color="#6CB4EE")
        self.autoscan_cb.pack(side="left", padx=(0, 6))

        self.autosync_var = ctk.BooleanVar(value=False)
        self.autosync_cb = ctk.CTkCheckBox(controls, text="Auto-sync", variable=self.autosync_var,
                                            font=ctk.CTkFont(size=12), text_color="#aaa",
                                            fg_color=ACCENT, hover_color="#6CB4EE")
        self.autosync_cb.pack(side="left", padx=(0, 6))

        self.fetch_btn = ctk.CTkButton(controls, text="Get Last Score",
                                        command=self._on_fetch,
                                        fg_color=ACCENT, hover_color="#6CB4EE",
                                        text_color="#fff",
                                        font=ctk.CTkFont(size=13, weight="bold"))
        self.fetch_btn.pack(side="right")

        self.sync_btn = ctk.CTkButton(controls, text="Sync to Server",
                                       command=self._on_sync,
                                       fg_color="#2a2a3e", hover_color="#3a3a5e",
                                       text_color="#aaa",
                                       font=ctk.CTkFont(size=11),
                                       state="disabled")
        self.sync_btn.pack(side="right", padx=(0, 6))

    def _build_source_row(self):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(row, text="Source:", font=ctk.CTkFont(size=12),
                     text_color="#888").pack(side="left")

        self.source_var = ctk.StringVar(value=self.config.source)
        self.username_var = ctk.StringVar(value=self.config.osu_username)

        def _on_source_change():
            self.config.source = self.source_var.get()
            if self.source_var.get() == "api":
                self.username_entry.configure(state="normal")
            else:
                self.username_entry.configure(state="disabled")

        def _on_username_change():
            self.config.osu_username = self.username_var.get()

        for val, label in [("mcsu", "McOsu"), ("api", "osu! API")]:
            rb = ctk.CTkRadioButton(row, text=label, variable=self.source_var,
                                     value=val, font=ctk.CTkFont(size=12),
                                     fg_color=ACCENT, hover_color="#6CB4EE",
                                     text_color="#aaa", command=_on_source_change)
            rb.pack(side="left", padx=(8, 4))

        ctk.CTkLabel(row, text="User:", font=ctk.CTkFont(size=12),
                     text_color="#888").pack(side="left", padx=(16, 4))
        self.username_entry = ctk.CTkEntry(row, textvariable=self.username_var,
                                            font=ctk.CTkFont(size=12), width=130,
                                            fg_color="#0f0f1a", border_color="#2a2a3e")
        self.username_entry.pack(side="left")
        self.username_entry.bind("<KeyRelease>", lambda e: _on_username_change())

        if self.source_var.get() != "api":
            self.username_entry.configure(state="disabled")

    def _build_title_tile(self):
        self.title_frame = ctk.CTkFrame(self, fg_color=GLASS_BG, border_color=GLASS_BORDER,
                                         border_width=1, corner_radius=12)
        self.title_frame.pack(fill="x", pady=(0, 14))

        self.title_label = ctk.CTkLabel(self.title_frame, text="No score loaded",
                                         font=ctk.CTkFont(size=15, weight="bold"),
                                         text_color="#fff", wraplength=800)
        self.title_label.pack(anchor="w", padx=16, pady=(14, 4))

        self.detail_label = ctk.CTkLabel(self.title_frame, text="",
                                          font=ctk.CTkFont(size=12), text_color="#999")
        self.detail_label.pack(anchor="w", padx=16, pady=(0, 14))

    def _build_stats_grid(self):
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", pady=(0, 14))

        tiles_data = [
            ("Accuracy", "—", "#e0e0e0"),
            ("PP", "—", "#66bbff"),
            ("AP", "—", ACCENT),
            ("Grade", "—", "#e0e0e0"),
            ("Combo", "—", "#e0e0e0"),
            ("Mods", "—", "#e0e0e0"),
        ]

        self._tiles = {}
        for i, (label, default, color) in enumerate(tiles_data):
            col = i % 3
            row = i // 3
            tile = GlassTile(grid, label, default, value_color=color)
            tile.grid(row=row, column=col, padx=(0 if col == 0 else 6, 6 if col < 2 else 0),
                      pady=(0, 6), sticky="nsew")
            grid.grid_columnconfigure(col, weight=1, uniform="stats")
            self._tiles[label] = tile

    def _build_hits_row(self):
        self.hits_frame = ctk.CTkFrame(self, fg_color=GLASS_BG, border_color=GLASS_BORDER,
                                        border_width=1, corner_radius=10)
        self.hits_frame.pack(fill="x", pady=(0, 14))

        self.hits_label = ctk.CTkLabel(self.hits_frame, text="300: —  |  100: —  |  50: —  |  Miss: —",
                                        font=ctk.CTkFont(size=13, weight="bold"),
                                        text_color="#e0e0e0")
        self.hits_label.pack(anchor="w", padx=16, pady=12)

    def _build_profile_area(self):
        self.profile_frame = ctk.CTkFrame(self, fg_color=GLASS_BG, border_color=GLASS_BORDER,
                                           border_width=1, corner_radius=12)
        inner = ctk.CTkFrame(self.profile_frame, fg_color="transparent")

        header = ctk.CTkLabel(inner, text="Player Profile",
                               font=ctk.CTkFont(size=14, weight="bold"), text_color="#ccc")
        header.pack(anchor="w", pady=(0, 2))

        self.profile_name = ctk.CTkLabel(inner, text="",
                                          font=ctk.CTkFont(size=18, weight="bold"),
                                          text_color="#fff")
        self.profile_name.pack(anchor="w", pady=(0, 12))

        stats_row = ctk.CTkFrame(inner, fg_color="transparent")
        stats_row.pack(fill="x", pady=(0, 10))

        self._profile_stat_tiles = {}
        stat_defs = [
            ("Weighted PP", "—", "#e0e0e0"),
            ("Plays", "—", "#e0e0e0"),
            ("Avg Acc", "—", "#e0e0e0"),
            ("Max Combo", "—", "#e0e0e0"),
        ]
        for i, (label, default, color) in enumerate(stat_defs):
            tile = GlassTile(stats_row, label, default, value_color=color,
                             width=120)
            tile.grid(row=0, column=i, padx=(0 if i == 0 else 8, 0), sticky="nsew")
            stats_row.grid_columnconfigure(i, weight=1, uniform="pstats")
            self._profile_stat_tiles[label] = tile

        self._grade_tiles = []
        grades_row = ctk.CTkFrame(inner, fg_color="transparent")
        grades_row.pack(fill="x")

        for grade in GRADE_ORDER:
            tile = self._build_grade_badge(grades_row, grade, 0)
            tile.pack(side="left", padx=(0, 6))
            self._grade_tiles.append(tile)

        inner.pack(fill="x", padx=16, pady=14)
        self.profile_frame.pack_forget()

    def _build_grade_badge(self, parent, grade, count):
        color = GRADE_COLORS.get(grade, "#888")
        frame = ctk.CTkFrame(parent, fg_color=TILE_BG, border_color=color,
                              border_width=2, corner_radius=10, width=64, height=60)
        frame.pack_propagate(False)

        frame.letter_label = ctk.CTkLabel(frame, text=grade, font=ctk.CTkFont(size=16, weight="bold"),
                                           text_color=color)
        frame.letter_label.pack(anchor="center", pady=(5, 0))

        frame.count_label = ctk.CTkLabel(frame, text=str(count), font=ctk.CTkFont(size=16, weight="bold"),
                                          text_color="#fff")
        frame.count_label.pack(anchor="center", pady=(0, 5))

        frame.plus_label = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(size=13, weight="bold"),
                                         text_color=color)
        frame.plus_label.place(relx=0.5, rely=0.45, anchor="center")

        return frame

    def _build_status(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="x", pady=(4, 0))
        self._status_container = container

        self.status_label = ctk.CTkLabel(container, text="", font=ctk.CTkFont(size=12))
        self.status_label.pack(anchor="w")

        self.log_text = ctk.CTkTextbox(container, fg_color="#0a0a14", text_color="#88cc88",
                                        font=ctk.CTkFont(family="Consolas", size=11),
                                        border_color="#2a2a3e", border_width=1,
                                        height=80)
        self.log_text.pack(fill="x", pady=(4, 0))

    def _copy_log(self):
        text = self.log_text.get("0.0", "end")
        if not text.strip():
            return
        self.clipboard_clear()
        self.clipboard_append(text.strip())
        self._set_status("Log copied to clipboard", "#888")

    def _set_status(self, msg: str, color: str = "#888"):
        self.status_label.configure(text=msg, text_color=color)
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def _on_autoscan_toggle(self):
        if self.autoscan_var.get():
            self._start_autoscan()
        else:
            self._stop_autoscan()

    def _start_autoscan(self):
        if self._auto_scanner:
            return

        source = self.source_var.get()

        if source == "mcsu":
            from mcsu_bot_gui.workers.score_worker import _get_latest_score
            initial = None
            try:
                initial = _get_latest_score(self.config).timestamp
            except Exception:
                pass

            self._auto_scanner = AutoScanWorker(
                poll_fn=lambda: _get_latest_score(self.config).timestamp,
                on_new_score=self._on_auto_update,
                last_marker=initial,
            )
        elif source == "api":
            username = self.username_var.get().strip()
            if not username:
                self._set_status("Auto-scan: enter an osu! username first", "#ffaa44")
                self.autoscan_var.set(False)
                return

            self._auto_scanner = OsuApiAutoScanWorker(
                self.config,
                username,
                on_new_score=self._on_auto_update,
            )
        else:
            self._set_status("Auto-scan: unknown source", "#ffaa44")
            self.autoscan_var.set(False)
            return

        self._auto_scanner.start()
        self._set_status(
            f"Auto-scan ({source}): polling every 3s...", "#66ff99"
        )

    def stop_autoscan(self):
        if self._auto_scanner:
            self._auto_scanner.stop()
            self._auto_scanner = None

    def _stop_autoscan(self):
        self.stop_autoscan()
        self._set_status("Auto-scan stopped", "#888")

    def _on_auto_update(self):
        if self.fetch_btn.cget("state") == "disabled":
            return
        self.after(0, self._on_fetch)

    def _on_profile_toggle(self):
        if not self.profile_var.get():
            self.profile_frame.pack_forget()
            return
        if self.source_var.get() != "mcsu":
            self._set_status("Profile is only available in McOsu source mode", "#ffaa44")
            self.profile_var.set(False)
            return
        self._load_profile()

    def _load_profile(self, animate_grade=None):
        try:
            profile = calculate_profile(self.config.scores_db_path, self.config.cfg_dir)
        except Exception as e:
            self._set_status(f"Profile error: {e}", "#ff6666")
            return

        name = profile.player_name or "Unknown"
        self.profile_name.configure(text=name)

        self._profile_stat_tiles["Weighted PP"].set_value(f"{profile.weighted_pp:,.0f}")
        self._profile_stat_tiles["Plays"].set_value(f"{profile.play_count:,}")
        self._profile_stat_tiles["Avg Acc"].set_value(f"{profile.avg_accuracy*100:.2f}%")
        self._profile_stat_tiles["Max Combo"].set_value(f"{profile.max_combo:,}x")

        g = profile.grades
        grade_counts = {"XH": g.xh, "X": g.x, "SH": g.sh, "S": g.s,
                        "A": g.a, "B": g.b, "C": g.c, "D": g.d}
        for tile, grade in zip(self._grade_tiles, GRADE_ORDER):
            self._update_grade_badge(tile, grade, grade_counts[grade])

        self.profile_frame.pack(fill="x", pady=(0, 14), before=self._status_container)

        if animate_grade:
            self._show_grade_plus_one(animate_grade)

    def _update_grade_badge(self, frame, grade, count):
        frame.letter_label.configure(text=grade)
        frame.count_label.configure(text=str(count))

    def _show_grade_plus_one(self, grade):
        for tile, g in zip(self._grade_tiles, GRADE_ORDER):
            if g == grade:
                lbl = tile.plus_label
                color = GRADE_COLORS.get(grade, "#fff")
                lbl.configure(text="+1", text_color=color)
                self.after(1500, lambda l=lbl: l.configure(text=""))
                break

    def _on_fetch(self):
        self.fetch_btn.configure(state="disabled", text="Loading...")
        source = self.source_var.get()
        if source == "api":
            username = self.username_var.get()
            if not username:
                self._set_status("Enter an osu! username first", "#ff6666")
                self.fetch_btn.configure(state="normal", text="Get Last Score")
                return
            self._set_status(f"Fetching latest score for '{username}'...", "#888")
            self.fetcher = OsuApiScoreFetcher(
                self.config, username,
                on_done=self._on_result,
                on_status=lambda msg: self.after(0, lambda: self._set_status(msg, "#888")),
            )
        else:
            self._set_status("Fetching latest score...", "#888")
            self.fetcher = ScoreFetcher(
                self.config,
                on_done=self._on_result,
                on_status=lambda msg: self.after(0, lambda: self._set_status(msg, "#888")),
            )
        self.fetcher.start()

    def _on_result(self, result):
        self.fetch_btn.configure(state="normal", text="Get Last Score")

        if not result.success:
            self._set_status(f"Error: {result.error}", "#ff6666")
            return

        self._result = result
        self._display_score(result)

        server_url = get_server_url()
        if server_url and check_auth(server_url):
            self.sync_btn.configure(state="normal")
        else:
            self.sync_btn.configure(state="disabled")

        if self.autosync_var.get() and result.inserted:
            if server_url and check_auth(server_url):
                self._auto_sync(server_url)
            else:
                self._set_status("Auto-sync: server not configured", "#ffaa44")

        if self.profile_var.get():
            self._load_profile(animate_grade=result.grade)

    def _on_sync(self):
        if not self._result:
            return
        self.sync_btn.configure(state="disabled", text="Syncing...")
        server_url = get_server_url()
        self._send_score(server_url)

    def _auto_sync(self, server_url: str):
        self._set_status("Auto-sync: sending to server...", "#888")
        self._send_score(server_url)

    def _send_score(self, server_url: str):
        if not self._result:
            return
        score_data = self._build_score_payload(self._result)

        def _do_sync():
            ok, msg = sync_score(server_url, score_data)
            self.after(0, lambda: self._sync_done(ok, msg))

        threading.Thread(target=_do_sync, daemon=True).start()

    def _build_score_payload(self, r) -> dict:
        from datetime import datetime, timezone
        played_at = datetime.fromtimestamp(r.score.timestamp, tz=timezone.utc).isoformat()
        return {
            "beatmap_id": r.meta.beatmap_id or 0,
            "beatmap_title": f"{r.meta.artist} - {r.meta.title} [{r.meta.difficulty}]",
            "beatmap_url": r.meta.map_url or "",
            "mods": r.breakdown.mods_str if r.breakdown else "NM",
            "source": self.source_var.get(),
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
            "played_at": played_at,
        }

    def _sync_done(self, ok: bool, msg: str):
        self.sync_btn.configure(state="normal", text="Sync to Server")
        self._set_status(f"Server: {msg}", "#66ff99" if ok else "#ff6666")

    def _display_score(self, r):
        title = f"{r.meta.artist} - {r.meta.title} [{r.meta.difficulty}]"
        self.title_label.configure(text=title)
        self.detail_label.configure(text=f"★{r.meta.star_rating:.2f}  |  {r.meta.length}s  |  {int(r.meta.bpm)} BPM")

        acc_pct = r.pp_result.accuracy * 100
        self._tiles["Accuracy"].set_value(f"{acc_pct:.2f}%")
        self._tiles["PP"].set_value(f"{r.pp_result.pp:.1f} pp")
        self._tiles["AP"].set_value(f"{r.ap:.0f} AP", color=ACCENT)

        grade_color = GRADE_COLORS.get(r.grade, "#fff")
        self._tiles["Grade"].set_value(r.grade, color=grade_color)
        self._tiles["Combo"].set_value(f"x{r.score.max_combo}/{r.pp_result.max_combo}")
        mods_str = r.breakdown.mods_str if r.breakdown else "NM"
        self._tiles["Mods"].set_value(mods_str)

        self.hits_label.configure(
            text=f"300: {r.score.count300}  |  100: {r.score.count100}  "
                 f"|  50: {r.score.count50}  |  Miss: {r.score.count_miss}"
        )

        if r.duplicate:
            self._set_status("⚠ Duplicate score — not saved to database", "#ffaa44")
        elif r.inserted:
            self._set_status("✓ Saved to database", "#66ff99")
        else:
            self._set_status("Score loaded but not saved", "#888")

    def get_last_breakdown(self):
        if self._result and self._result.breakdown:
            return self._result.breakdown
        return None

    def destroy(self):
        self._stop_autoscan()
        super().destroy()
