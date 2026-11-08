import json
import threading
from datetime import datetime

from nicegui import ui

from mcsu_bot.server_client import (
    check_auth,
    get_ranked,
    get_ranked_history,
    get_ranked_leaderboard,
    get_ranked_stats,
    get_server_url,
    ranked_new,
    ranked_reroll,
    ranked_surrender,
)
from mcsu_gui.state import bus
from mcsu_gui.tabs.ranked_view import (
    ACCENT,
    CARD_BG,
    CARD_BORDER,
    INSET_BG,
    MUTED,
    NEGATIVE,
    PAGE_BG,
    POSITIVE,
    TEXT,
    TRACK_BG,
    delta_color,
    format_accuracy,
    format_delta,
    format_stars,
    is_me_row,
    outcome_icon,
    place_color,
    pretty_title,
    progress_detail,
    shape_states,
    star_range_text,
    tier_color,
    tier_shape_svg,
    wld_values,
    window_geometry,
    window_text,
)


def _css() -> str:
    return f"""
.ranked-page {{ color: {TEXT}; }}
.ranked-card {{
    background: {CARD_BG};
    border: 1px solid {CARD_BORDER};
    border-radius: 12px;
    padding: 18px 20px;
}}
.ranked-card + .ranked-card {{ margin-top: 20px; }}
.ranked-card-title {{
    font-size: 13px;
    font-weight: 700;
    color: {TEXT};
    letter-spacing: 0.3px;
    margin-bottom: 14px;
    text-transform: uppercase;
}}
.ranked-label {{
    color: {MUTED};
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
}}
.ranked-tier {{
    font-size: 28px;
    font-weight: 700;
    line-height: 1.1;
}}
.ranked-elo {{
    font-size: 34px;
    font-weight: 700;
    color: {ACCENT};
    line-height: 1.1;
}}
.ranked-subrank {{
    display: inline-flex;
    gap: 5px;
    align-items: center;
}}
.ranked-shape {{
    display: inline-flex;
    line-height: 0;
    align-items: center;
}}
.ranked-shape svg {{ display: block; }}
.ranked-window-value {{
    font-size: 24px;
    font-weight: 700;
    color: {TEXT};
}}
.ranked-scale {{
    position: relative;
    height: 10px;
    background: {TRACK_BG};
    border-radius: 999px;
    margin: 12px 0 6px;
}}
.ranked-scale-window {{
    position: absolute;
    top: 0;
    bottom: 0;
    background: {ACCENT};
    border-radius: 999px;
    opacity: 0.9;
}}
.ranked-scale-marker {{
    position: absolute;
    top: -3px;
    width: 2px;
    height: 16px;
    background: {TEXT};
    opacity: 0.85;
}}
.ranked-scale-labels {{
    display: flex;
    justify-content: space-between;
    gap: 8px;
    color: {MUTED};
    font-size: 10px;
}}
.ranked-progress {{
    height: 8px;
    background: {TRACK_BG};
    border-radius: 999px;
    overflow: hidden;
    margin-top: 8px;
}}
.ranked-progress-fill {{
    height: 100%;
    border-radius: 999px;
}}
.ranked-row {{
    display: grid;
    grid-template-columns: 26px minmax(0, 1fr) 64px 76px 72px;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 7px 0;
    border-bottom: 1px solid {CARD_BORDER};
}}
.ranked-row:last-child {{ border-bottom: none; }}
.ranked-row-title {{
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}
.ranked-num {{
    text-align: right;
    white-space: nowrap;
}}
.ranked-board-row {{
    display: grid;
    grid-template-columns: 34px minmax(0, 1fr) 150px 80px;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 8px 10px;
    border-radius: 8px;
}}
.ranked-board-row.me {{ background: {INSET_BG}; }}
.ranked-board-name {{
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
}}
.ranked-me {{
    font-size: 10px;
    color: {ACCENT};
    border: 1px solid {ACCENT};
    border-radius: 999px;
    padding: 1px 6px;
    margin-left: 6px;
}}
.ranked-empty {{ color: {MUTED}; font-size: 13px; }}
.ranked-dashed {{
    border: 1px dashed {CARD_BORDER};
    border-radius: 10px;
    padding: 16px;
    text-align: center;
}}
.ranked-rank-grid {{
    display: grid;
    grid-template-columns: minmax(260px, 1fr) minmax(300px, 1.15fr);
    gap: 24px;
    align-items: start;
}}
.ranked-title-badge {{
    display: inline-block;
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: {TEXT};
    border: 2px solid {ACCENT};
    border-radius: 10px;
    background: #161a38;
    padding: 8px 16px;
    margin-left: 4px;
    box-shadow: 0 0 0 3px {PAGE_BG}, 0 0 0 4px #333865;
}}
.ranked-refresh {{
    width: 44px !important;
    height: 44px !important;
    min-width: 44px !important;
    min-height: 44px !important;
    padding: 0 !important;
    border: 1px solid {ACCENT} !important;
    color: #8cc0f5 !important;
    background: transparent !important;
}}
.ranked-refresh.loading .q-icon {{
    animation: ranked-spin 0.9s linear infinite;
}}
@keyframes ranked-spin {{
    from {{ transform: rotate(0deg); }}
    to {{ transform: rotate(360deg); }}
}}
.ranked-btn {{
    min-height: 44px !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    padding: 0 16px !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}
.ranked-icon-btn {{
    width: 44px !important;
    height: 44px !important;
    min-width: 44px !important;
    min-height: 44px !important;
    padding: 0 !important;
    border-radius: 8px !important;
    position: relative !important;
    overflow: visible !important;
}}
.ranked-btn-svg {{ display: inline-flex; line-height: 0; }}
.ranked-btn-svg svg {{ display: block; }}
.ranked-surrender .q-btn__content {{ gap: 8px; }}
.ranked-reroll-badge {{
    position: absolute;
    top: -7px;
    right: -7px;
    min-width: 22px;
    padding: 0 4px;
    border-radius: 7px;
    background: {INSET_BG};
    border: 1px solid #2c3158;
    color: {TEXT};
    font-size: 9px;
    line-height: 16px;
    text-align: center;
}}
.ranked-btn.disabled,
.ranked-btn.q-btn--disabled,
.ranked-btn[disabled],
.ranked-icon-btn.disabled,
.ranked-icon-btn.q-btn--disabled,
.ranked-icon-btn[disabled] {{
    opacity: 0.4 !important;
}}
.ranked-surrender.disabled,
.ranked-surrender.q-btn--disabled,
.ranked-surrender[disabled] {{
    opacity: 0.55 !important;
}}
.ranked-progress-detail {{
    text-align: right;
    white-space: nowrap;
}}
@media (max-width: 800px) {{
    .ranked-rank-grid {{ grid-template-columns: 1fr; }}
}}
"""


SHUFFLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" '
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M16 3h5v5M4 20L21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg>'
)
DOWNLOAD_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" '
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>'
)
FLAG_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" '
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/></svg>'
)


class RankedTab:
    def __init__(self, state, last_score_tab):
        self.state = state
        self.last_score_tab = last_score_tab
        self._data = None
        self._busy = False
        self._deadline = None
        self._download_url = ""
        self._fallback_window = ""
        self._surrender_penalty = None
        self._surrender_text = None
        self._surrender_dialog = None
        self._stats = {}
        self.active_countdown = None

        self._setup_ui()

        bus.subscribe("ranked_state", self._on_state, key="ranked:state")
        bus.subscribe("score_sync_done", self._on_sync_done, key="ranked:sync_done")
        bus.subscribe("score_result", self._on_score_result, key="ranked:score_result")

        ui.timer(10.0, self._refresh)
        ui.timer(1.0, self._tick)
        self._refresh()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        ui.add_head_html(f"<style>{_css()}</style>")

        with ui.column().classes("ranked-page w-full").style("gap: 0;"):
            with ui.row().classes("w-full items-center justify-between no-wrap").style(
                "margin-bottom: 12px;"
            ):
                ui.label("Ranked").classes("ranked-title-badge mono")
                self.refresh_btn = (
                    ui.button(icon="refresh", on_click=self._refresh, color=None)
                    .props("round unelevated")
                    .classes("ranked-refresh")
                    .tooltip("Обновить")
                    .props('aria-label="Обновить"')
                )

            self.status_label = ui.label("").style(
                f"font-size: 12px; color: {MUTED}; margin-bottom: 12px;"
            )

            # ---------------------------------------------------------- #
            # Game page
            # ---------------------------------------------------------- #
            self.game_page = ui.column().classes("w-full").style("gap: 0;")
            with self.game_page:
                # ------------------------------------------------------ #
                # Rank card
                # ------------------------------------------------------ #
                with ui.element("div").classes("ranked-card w-full"):
                    ui.label("Ранг").classes("ranked-card-title mono")

                    with ui.element("div").classes("ranked-rank-grid w-full"):
                        # Left: tier + shape progress + ELO.
                        with ui.column().classes("gap-2"):
                            ui.label("Звание").classes("ranked-label mono")
                            with ui.row().classes("items-center gap-2 no-wrap"):
                                self.tier_label = ui.label("—").classes(
                                    "ranked-tier mono"
                                )
                                self.subrank_box = ui.row().classes(
                                    "ranked-subrank items-center"
                                )
                            with ui.row().classes("items-end gap-2 no-wrap"):
                                self.elo_label = ui.label("—").classes(
                                    "ranked-elo mono"
                                )
                                ui.label("ELO").classes("ranked-label mono").style(
                                    "margin-bottom: 6px;"
                                )

                        # Right: continuous window + tier-range scale.
                        with ui.column().classes("gap-2 w-full"):
                            with ui.row().classes(
                                "w-full items-center justify-between no-wrap"
                            ):
                                ui.label("Окно сложности сейчас").classes(
                                    "ranked-label mono"
                                )
                                self.window_label = ui.label("—").classes(
                                    "ranked-window-value mono"
                                )
                            self.scale_box = ui.element("div").classes("w-full")

                    # Full-width progress line.
                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ).style("margin-top: 14px; gap: 12px;"):
                        self.progress_tier_label = ui.label("").classes(
                            "mono"
                        ).style(f"font-size: 12px; color: {TEXT}; font-weight: 700;")
                        self.progress_detail_label = ui.label("").classes(
                            "ranked-progress-detail mono"
                        ).style(f"font-size: 12px; color: {MUTED};")
                    self.progress_track = ui.element("div").classes(
                        "ranked-progress w-full"
                    )
                    with self.progress_track:
                        self.progress_fill = ui.element("div").classes(
                            "ranked-progress-fill"
                        )

                    # Bottom right: W/L/D and win rate (no reward chips here).
                    with ui.row().classes("w-full items-end justify-end").style(
                        "margin-top: 12px;"
                    ):
                        with ui.column().classes("gap-1 items-end"):
                            self.wld_row = ui.row().classes(
                                "items-center gap-1 mono"
                            )
                            self.winrate_label = ui.label("").classes("mono").style(
                                f"font-size: 12px; color: {MUTED};"
                            )

                # ------------------------------------------------------ #
                # Active challenge card
                # ------------------------------------------------------ #
                with ui.element("div").classes("ranked-card w-full"):
                    ui.label("Активное задание").classes("ranked-card-title mono")
                    self.active_body = ui.column().classes("w-full gap-2")
                    self._render_active(None)

                    with ui.row().classes(
                        "w-full items-center justify-between"
                    ).style("gap: 10px; flex-wrap: wrap; margin-top: 14px;"):
                        with ui.row().classes("items-center gap-2").style(
                            "flex-wrap: wrap;"
                        ):
                            self.new_btn = self._button(
                                "Новое задание",
                                self._on_new,
                                style=f"background: {ACCENT}; color: {PAGE_BG}; "
                                f"border: 1px solid {ACCENT};",
                            )
                            self.check_btn = self._button(
                                "Проверить сейчас",
                                self._on_check_now,
                                style=f"background: transparent; color: {ACCENT}; "
                                f"border: 1px solid {ACCENT};",
                            )
                        with ui.row().classes("items-center gap-2").style(
                            "flex-wrap: wrap;"
                        ):
                            self.reroll_btn = (
                                ui.button(
                                    on_click=self._on_reroll, color=None
                                )
                                .props("unelevated no-caps")
                                .classes("ranked-icon-btn")
                                .style(
                                    f"background: transparent; color: {ACCENT}; "
                                    f"border: 1px solid {CARD_BORDER};"
                                )
                            )
                            with self.reroll_btn:
                                ui.html(SHUFFLE_SVG, sanitize=False).classes(
                                    "ranked-btn-svg"
                                )
                                self.reroll_badge = ui.label("").classes(
                                    "ranked-reroll-badge mono"
                                )
                                self.reroll_tooltip = ui.tooltip("Реролл")

                            self.download_btn = (
                                ui.button(
                                    on_click=self._on_download, color=None
                                )
                                .props("unelevated no-caps")
                                .classes("ranked-icon-btn")
                                .style(
                                    f"background: transparent; color: {TEXT}; "
                                    f"border: 1px solid {CARD_BORDER};"
                                )
                            )
                            with self.download_btn:
                                ui.html(DOWNLOAD_SVG, sanitize=False).classes(
                                    "ranked-btn-svg"
                                )
                                ui.tooltip("Скачать карту")

                            self.surrender_btn = (
                                ui.button(
                                    on_click=self._on_surrender, color=None
                                )
                                .props("unelevated no-caps")
                                .classes("ranked-btn ranked-surrender")
                                .style(
                                    f"background: transparent; color: {NEGATIVE}; "
                                    f"border: 1px solid {NEGATIVE};"
                                )
                            )
                            with self.surrender_btn:
                                ui.html(FLAG_SVG, sanitize=False).classes(
                                    "ranked-btn-svg"
                                )
                                ui.label("Сдаться")
                                self.surrender_tooltip = ui.tooltip("Сдаться")
                    self._render_buttons({})

                # ------------------------------------------------------ #
                # History card
                # ------------------------------------------------------ #
                with ui.element("div").classes("ranked-card w-full"):
                    ui.label("История").classes("ranked-card-title mono")
                    self.history_content = ui.column().classes("w-full").style(
                        "gap: 0;"
                    )
                    with self.history_content:
                        ui.label("Пока нет завершённых заданий").classes(
                            "ranked-empty mono"
                        )

            # ---------------------------------------------------------- #
            # Rating page (leaderboard only)
            # ---------------------------------------------------------- #
            self.rating_page = ui.column().classes("w-full").style("gap: 0;")
            with self.rating_page:
                with ui.element("div").classes("ranked-card w-full"):
                    ui.label("Лидерборд").classes("ranked-card-title mono")
                    self.board_content = ui.column().classes("w-full").style(
                        "gap: 2px;"
                    )
                    with self.board_content:
                        ui.label("Лидерборд пуст").classes("ranked-empty mono")
            self.show_page("game")

        self._build_surrender_dialog()

    def show_page(self, name: str):
        """Switch between the «Игра» and «Рейтинг» Ranked pages."""
        if name not in ("game", "rating"):
            name = "game"
        self._page = name
        if hasattr(self, "game_page"):
            self.game_page.set_visibility(name == "game")
        if hasattr(self, "rating_page"):
            self.rating_page.set_visibility(name == "rating")

    def _button(self, text: str, on_click, style: str):
        return (
            ui.button(text, on_click=on_click, color=None)
            .props("unelevated no-caps")
            .classes("ranked-btn mono")
            .style(style)
        )

    def _build_surrender_dialog(self):
        self._surrender_dialog = ui.dialog()
        with self._surrender_dialog, ui.card().style(
            f"background: {CARD_BG}; border: 1px solid {CARD_BORDER}; "
            "border-radius: 12px; min-width: 320px; max-width: 420px;"
        ):
            self._surrender_text = ui.label("Сдаться?").classes("mono").style(
                f"font-size: 15px; color: {TEXT};"
            )
            with ui.row().classes("w-full justify-end items-center").style("gap: 8px;"):
                self._button(
                    "Отмена",
                    self._surrender_dialog.close,
                    style=f"background: transparent; color: {TEXT}; "
                    f"border: 1px solid {CARD_BORDER};",
                )
                self._button(
                    "Сдаться",
                    self._confirm_surrender,
                    style=f"background: {NEGATIVE}; color: {PAGE_BG}; "
                    f"border: 1px solid {NEGATIVE};",
                )

    # ------------------------------------------------------------------ #
    # Server interactions (unchanged behaviour)
    # ------------------------------------------------------------------ #

    def _set_status(self, msg: str, color: str = MUTED):
        self.status_label.set_text(msg)
        self.status_label.style(replace=f"color: {color}; font-size: 12px;")

    def _set_loading(self, loading: bool):
        button = getattr(self, "refresh_btn", None)
        if button is None:
            return
        if loading:
            button.disable()
            button.classes(add="loading")
        else:
            button.enable()
            button.classes(remove="loading")

    def _refresh(self):
        if self._busy:
            return
        self._busy = True
        self._set_loading(True)
        server_url = get_server_url()
        if not server_url or not check_auth(server_url):
            self._busy = False
            self._set_loading(False)
            self._set_status(
                "Нет входа на сервер — войдите в Control → Server Sync (Login via osu!)",
                NEGATIVE,
            )
            return
        self._set_status("Загрузка...", MUTED)

        def _run():
            ok, data = get_ranked(server_url)
            if not ok:
                bus.emit("ranked_state", {"error": str(data)})
                return
            _, history = get_ranked_history(server_url, limit=10)
            _, leaderboard = get_ranked_leaderboard(server_url, limit=10)
            try:
                ok_stats, stats = get_ranked_stats(server_url)
            except Exception as exc:  # never silently lose the W/L/D source
                ok_stats, stats = False, str(exc)
            stats_payload = stats if ok_stats and isinstance(stats, dict) else None
            stats_error = None if stats_payload is not None else str(stats)
            bus.emit(
                "ranked_state",
                {
                    "data": data,
                    "history": history if isinstance(history, list) else [],
                    "leaderboard": leaderboard if isinstance(leaderboard, list) else [],
                    "stats": stats_payload,
                    "stats_error": stats_error,
                },
            )

        threading.Thread(target=_run, daemon=True).start()

    def _action(self, fn):
        server_url = get_server_url()
        if not server_url or not check_auth(server_url):
            self._set_status("Нет входа на сервер", NEGATIVE)
            return

        def _run():
            ok, msg = fn(server_url)
            if not ok:
                bus.emit("ranked_state", {"error": str(msg)})
            else:
                bus.emit("ranked_state", {"data": msg})

        threading.Thread(target=_run, daemon=True).start()

    def _on_new(self):
        self._action(ranked_new)

    def _on_reroll(self):
        self._action(ranked_reroll)

    def _on_surrender(self):
        if self._data is None or not self._data.get("active"):
            return
        if self._surrender_text is not None:
            penalty = self._surrender_penalty
            if penalty is None:
                self._surrender_text.set_text("Сдаться?")
            else:
                self._surrender_text.set_text(
                    f"Сдаться и потерять {abs(int(penalty))} ELO?"
                )
        if self._surrender_dialog is not None:
            self._surrender_dialog.open()

    def _confirm_surrender(self):
        if self._surrender_dialog is not None:
            self._surrender_dialog.close()
        self._action(ranked_surrender)

    def _on_check_now(self):
        server_url = get_server_url()
        if not server_url or not check_auth(server_url):
            self._set_status("Нет входа на сервер", NEGATIVE)
            return
        result = getattr(self.last_score_tab, "_result", None)
        if result is not None and getattr(result, "inserted", False):
            # Sync the last score so the server settles the active challenge.
            self.last_score_tab._send_score(server_url)
        else:
            self._refresh()

    def _on_download(self):
        if self._download_url:
            ui.run_javascript(f"window.open({json.dumps(self._download_url)})")

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #

    def _on_state(self, payload):
        self._busy = False
        self._set_loading(False)
        if "error" in payload:
            self._set_status(str(payload["error"]), NEGATIVE)
            return
        data = payload["data"]
        if not data.get("enabled", False):
            self._data = None
            self._set_status("Режим Ranked выключен на сервере", NEGATIVE)
            return
        stats = payload.get("stats")
        if isinstance(stats, dict):
            self._stats = stats
        merged = dict(data)
        if isinstance(self._stats, dict):
            for key in (
                "wins",
                "losses",
                "draws",
                "win_rate",
                "passed",
                "failed",
                "total_settled",
            ):
                if key in self._stats:
                    merged[key] = self._stats[key]
        self._data = merged
        self._render(
            merged, payload.get("history", []), payload.get("leaderboard", [])
        )
        stats_error = payload.get("stats_error")
        if stats_error:
            self._set_status(f"Статистика W/L/D недоступна: {stats_error}", NEGATIVE)
        else:
            self._set_status("", MUTED)

    def _on_sync_done(self, payload):
        if payload.get("ok"):
            self._refresh()

    def _on_score_result(self, result):
        # A new score was fetched locally. If there is an active challenge and
        # auto-sync is off, send it so the server can settle the challenge.
        if not getattr(result, "inserted", False):
            return
        if self._data is None or not self._data.get("active"):
            return
        server_url = get_server_url()
        if not server_url or not check_auth(server_url):
            return
        autosync = getattr(self.last_score_tab, "autosync_checkbox", None)
        if autosync is not None and autosync.value:
            return  # last_score.py will auto-sync; score_sync_done refreshes us
        self.last_score_tab._send_score(server_url)

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #

    def _render(self, data, history, leaderboard):
        tier = str(data.get("tier") or "—")
        color = tier_color(tier)

        self.elo_label.set_text(str(data.get("elo", "—")))
        self.elo_label.style(replace=f"color: {ACCENT};")
        self.tier_label.set_text(tier)
        self.tier_label.style(replace=f"color: {color};")

        self._render_subrank(tier, data.get("sub_rank"))
        self._render_window(data)
        self._render_progress(data, tier, color)
        self._render_wld(data)

        self._surrender_penalty = data.get("fail_delta")
        self._render_active(data.get("active"))
        self._render_buttons(data)
        self._render_history(history)
        self._render_board(leaderboard)

    def _render_subrank(self, tier: str, sub):
        self.subrank_box.clear()
        states = shape_states(tier, sub)
        with self.subrank_box:
            for filled in states:
                ui.html(
                    tier_shape_svg(tier, filled=filled, size=20),
                    sanitize=False,
                ).classes("ranked-shape")

    def _render_window(self, data):
        star_window = data.get("star_window") or {}
        star_range = data.get("star_range") or {}
        text = window_text(star_window) or star_range_text(star_range)
        self._fallback_window = text
        self.window_label.set_text(text or "—")

        self.scale_box.clear()
        geometry = window_geometry(
            star_window, star_range.get("min"), star_range.get("max")
        )
        with self.scale_box:
            if geometry is None:
                span_text = star_range_text(star_range)
                reason = (
                    "открытый диапазон без верхней границы"
                    if star_range.get("max") is None and star_range.get("min") is not None
                    else "нет данных для шкалы"
                )
                message = reason + (f" · {span_text}" if span_text else "")
                ui.label(message).classes("ranked-empty mono").style(
                    "font-size: 11px;"
                )
                return
            with ui.element("div").classes("ranked-scale w-full"):
                ui.element("div").classes("ranked-scale-window").style(
                    f"left: {geometry['left']:.3f}%; "
                    f"width: {geometry['width']:.3f}%;"
                )
                ui.element("div").classes("ranked-scale-marker").style(
                    f"left: {geometry['marker']:.3f}%;"
                )
            with ui.element("div").classes("ranked-scale-labels mono"):
                ui.label(f"{float(star_range['min']):.2f}★")
                ui.label("диапазон звания")
                ui.label(f"{float(star_range['max']):.2f}★")

    def _render_progress(self, data, tier: str, color: str):
        progress = data.get("progress") or {}
        self.progress_tier_label.set_text(tier)
        self.progress_detail_label.set_text(progress_detail(progress))

        if progress.get("next_tier"):
            try:
                percent = max(0.0, min(100.0, float(progress.get("percent") or 0.0)))
            except (TypeError, ValueError):
                percent = 0.0
            self.progress_track.set_visibility(True)
            self.progress_fill.style(
                replace=f"width: {percent:.2f}%; background: {color};"
            )
        else:
            self.progress_track.set_visibility(False)

    def _render_wld(self, data):
        values = wld_values(data)
        wins = values["wins"]
        losses = values["losses"]
        draws = values["draws"]
        rows = (
            ("W", wins, POSITIVE),
            ("/", None, MUTED),
            ("L", losses, NEGATIVE),
            ("/", None, MUTED),
            ("D", draws, MUTED),
        )
        self.wld_row.clear()
        with self.wld_row:
            for token, value, token_color in rows:
                label = ui.label(token).classes("mono").style(
                    f"font-size: 12px; color: {token_color}; font-weight: 700;"
                )
                if value is not None:
                    label.set_text(f"{token} {int(value or 0)}")

        self.winrate_label.set_text(f"{values['win_rate'] * 100:.1f}% win rate")

    def _render_active(self, active):
        self.active_body.clear()
        self.active_countdown = None
        with self.active_body:
            if not active:
                self._deadline = None
                self._download_url = ""
                with ui.element("div").classes("ranked-dashed w-full"):
                    ui.label("Нет активного задания").classes("mono").style(
                        f"font-size: 14px; font-weight: 700; color: {TEXT};"
                    )
                    window = self._fallback_window
                    hint = "Нажми «Новое задание»"
                    if window:
                        hint += f": карта подберётся по окну {window}"
                    ui.label(hint).classes("mono").style(
                        f"font-size: 12px; color: {MUTED}; margin-top: 4px;"
                    )
                return

            self.active_title = ui.label(active.get("title", "")).classes(
                "mono"
            ).style(f"font-size: 15px; font-weight: 700; color: {TEXT};")
            meta = "  •  ".join(
                item
                for item in (
                    format_stars(active.get("stars")) if active.get("stars") is not None else "",
                    f"{int(active.get('length_sec') or 0)} с"
                    if active.get("length_sec")
                    else "",
                    str(active.get("version") or ""),
                )
                if item
            )
            if meta:
                ui.label(meta).classes("mono").style(
                    f"font-size: 12px; color: {MUTED};"
                )
            condition = str(active.get("condition") or "").strip()
            if condition:
                ui.label(f"Условие: {condition}").classes("mono").style(
                    f"font-size: 12px; color: {TEXT};"
                )
            self.active_countdown = ui.label("").classes("mono").style(
                f"font-size: 12px; color: {ACCENT}; font-weight: 700;"
            )
            self._deadline = active.get("deadline_at")
            self._download_url = active.get("download_url", "") or ""
            self._tick()

            if getattr(self.last_score_tab, "_auto_timer", None) is None:
                ui.label(
                    "⚠ Автоскан выключен — включите его, чтобы новые скоры "
                    "отправлялись автоматически"
                ).classes("mono").style(
                    f"font-size: 11px; color: {NEGATIVE};"
                )

    def _render_buttons(self, data):
        active = bool(data.get("active"))
        self.new_btn.set_enabled(not active)
        self.check_btn.set_enabled(True)

        left = data.get("rerolls_left")
        used = data.get("rerolls_used_today")
        penalty = data.get("reroll_penalty")
        surrender_penalty = data.get("fail_delta")

        if left is not None and used is not None:
            limit = int(left or 0) + int(used or 0)
            badge = f"{int(left or 0)}/{limit}"
        else:
            badge = ""
        self.reroll_badge.set_text(badge)
        self.reroll_badge.set_visibility(bool(badge))

        reroll_ready = active and (left is None or int(left or 0) > 0)
        download_ready = active and bool(self._download_url)
        self._paint_icon_button(self.reroll_btn, reroll_ready)
        self._paint_icon_button(self.download_btn, download_ready)

        reroll_tip = "Реролл"
        if badge:
            reroll_tip += f" · {badge}"
        if penalty is not None:
            reroll_tip += f" · {format_delta(penalty)} ELO"
        self.reroll_tooltip.set_text(reroll_tip)
        self._set_aria(self.reroll_btn, reroll_tip)
        self.reroll_btn.set_enabled(reroll_ready)

        self.download_btn.set_enabled(download_ready)
        self._set_aria(self.download_btn, "Скачать карту")

        surrender_tip = "Сдаться"
        if surrender_penalty is not None:
            surrender_tip += f" · {format_delta(surrender_penalty)} ELO"
        self.surrender_tooltip.set_text(surrender_tip)
        self._set_aria(self.surrender_btn, surrender_tip)
        self.surrender_btn.set_enabled(active)

    def _paint_icon_button(self, button, enabled: bool):
        color = ACCENT if enabled else "#8187ad"
        border = ACCENT if enabled else "#2c3158"
        button.style(
            replace=f"background: transparent; color: {color}; "
            f"border: 1px solid {border};"
        )

    def _set_aria(self, button, text: str):
        button._props["aria-label"] = text
        button.update()

    def _render_history(self, history):
        self.history_content.clear()
        rows = history if isinstance(history, list) else []
        with self.history_content:
            if not rows:
                ui.label("Пока нет завершённых заданий").classes(
                    "ranked-empty mono"
                )
                return
            for item in rows[:10]:
                self._history_row(item)

    def _history_row(self, item):
        status = item.get("status", "?")
        delta = item.get("elo_delta", 0)
        outcome = outcome_icon(status, delta)

        with ui.element("div").classes("ranked-row w-full mono"):
            with ui.element("div").classes("flex items-center justify-center"):
                ui.icon(outcome["icon"]).style(
                    f"color: {outcome['color']}; font-size: 18px;"
                ).tooltip(outcome["tooltip"])
            title = pretty_title(item.get("title"))
            title_label = ui.label(title).classes("ranked-row-title").style(
                f"color: {TEXT}; font-size: 12px;"
            )
            if title:
                title_label.tooltip(title)
            ui.label(format_stars(item.get("stars"))).classes("ranked-num").style(
                f"color: {MUTED}; font-size: 12px;"
            )
            ui.label(format_accuracy(item.get("accuracy"))).classes(
                "ranked-num"
            ).style(f"color: {MUTED}; font-size: 12px;")
            ui.label(f"{format_delta(delta)} ELO").classes("ranked-num").style(
                f"color: {delta_color(delta)}; font-size: 12px; font-weight: 700;"
            )

    def _render_board(self, leaderboard):
        self.board_content.clear()
        rows = leaderboard if isinstance(leaderboard, list) else []
        with self.board_content:
            if not rows:
                ui.label("Лидерборд пуст").classes("ranked-empty mono")
                return
            for row in rows[:10]:
                rank = row.get("rank")
                tier = str(row.get("tier") or "—")
                color = tier_color(tier)
                me = is_me_row(row, self.state.username)
                classes = "ranked-board-row w-full mono" + (" me" if me else "")
                with ui.element("div").classes(classes):
                    ui.label(f"#{rank}").style(
                        f"color: {place_color(rank)}; font-size: 12px; "
                        "font-weight: 700;"
                    )
                    with ui.element("div").classes("flex items-center min-w-0"):
                        ui.label(str(row.get("username") or "?")).classes(
                            "ranked-board-name"
                        ).style(f"font-size: 13px; color: {TEXT};")
                        if me:
                            ui.label("вы").classes("ranked-me mono")
                    with ui.row().classes("items-center gap-1 no-wrap"):
                        ui.label(tier).style(
                            f"color: {color}; font-size: 10px; font-weight: 600;"
                        )
                        for filled in shape_states(tier, row.get("sub_rank")):
                            ui.html(
                                tier_shape_svg(tier, filled=filled, size=18),
                                sanitize=False,
                            ).classes("ranked-shape")
                    ui.label(str(row.get("elo", 0))).style(
                        f"color: {TEXT}; font-size: 13px; font-weight: 700; "
                        "text-align: right;"
                    )

    def _tick(self):
        if self._deadline is None or self.active_countdown is None:
            return
        try:
            dl = datetime.fromisoformat(self._deadline)
        except Exception:
            return
        if dl.tzinfo is not None:
            now = datetime.now(dl.tzinfo)
        else:
            now = datetime.utcnow()
        remaining = max(0, int((dl - now).total_seconds()))
        m, s = divmod(remaining, 60)
        self.active_countdown.set_text(f"Осталось: {m}:{s:02d}")
