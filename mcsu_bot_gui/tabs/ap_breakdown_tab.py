import customtkinter as ctk

from mcsu_bot.ap_calculator import AIM_FOCUSED_RATIO
from mcsu_bot_gui.widgets import (
    GlassTile,
    GlassPanel,
    ACCENT,
    GLASS_BG,
    GLASS_BORDER,
)


class APBreakdownTab(ctk.CTkFrame):
    def __init__(self, master, last_score_tab, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.last_score_tab = last_score_tab
        self._setup_ui()

    def _setup_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(header, text="AP Breakdown", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ccc").pack(side="left")

        self.refresh_btn = ctk.CTkButton(header, text="Refresh from Last Score",
                                          command=self._on_refresh,
                                          fg_color=ACCENT, hover_color="#6CB4EE",
                                          text_color="#0f0f1a",
                                          font=ctk.CTkFont(size=13, weight="bold"))
        self.refresh_btn.pack(side="right")

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                         border_color=GLASS_BORDER, border_width=1)
        scroll.pack(fill="both", expand=True)

        self.content = scroll

        self.no_data = ctk.CTkLabel(scroll, text="No score data.\nFetch a score in 'Last Score' tab first.",
                                     font=ctk.CTkFont(size=14), text_color="#555")
        self.no_data.pack(expand=True, pady=60)

        self._tiles = {}
        self._grids = []
        self._build_ui()

    def _build_ui(self):
        self._base_panel = self._build_panel("Base")
        self._perf_panel = self._build_panel("Performance")
        self._bonus_panel = self._build_panel("Bonuses")
        self._total_panel = self._build_total_panel()
        self._verdict_panel = self._build_verdict_panel()

        self._hide_all()

    def _build_panel(self, title):
        panel = GlassPanel(self.content, title)
        panel.pack(fill="x", pady=(0, 10))
        return panel

    def _build_total_panel(self):
        frame = ctk.CTkFrame(self.content, fg_color=GLASS_BG, border_color=ACCENT,
                             border_width=2, corner_radius=12)
        frame.pack(fill="x", pady=(0, 10))

        self._tiles["TOTAL"] = GlassTile(frame, "TOTAL AP", "—", value_color=ACCENT)
        self._tiles["TOTAL"].pack(fill="x", padx=12, pady=12)
        return frame

    def _build_verdict_panel(self):
        frame = ctk.CTkFrame(self.content, fg_color=GLASS_BG, border_color=GLASS_BORDER,
                             border_width=1, corner_radius=12)
        frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(frame, text="Review", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#ccc").pack(anchor="w", padx=16, pady=(12, 4))

        self._verdict_type = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(size=15, weight="bold"),
                                           text_color="#fff", anchor="w")
        self._verdict_type.pack(anchor="w", padx=16, pady=(0, 2))

        self._verdict_desc = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(size=12),
                                           text_color="#aaa", anchor="w", wraplength=780,
                                           justify="left")
        self._verdict_desc.pack(anchor="w", padx=16, pady=(0, 12))
        return frame

    def _build_tile_grid(self, panel, definitions):
        grid = ctk.CTkFrame(panel.content, fg_color="transparent")
        grid.pack(fill="x")
        self._grids.append(grid)

        tiles = {}
        for i, (label, default, color) in enumerate(definitions):
            tile = GlassTile(grid, label, default, value_color=color)
            tile.grid(row=0, column=i, padx=(0 if i == 0 else 6, 0), sticky="nsew")
            grid.grid_columnconfigure(i, weight=1, uniform="tile")
            tiles[label] = tile
        return tiles

    def _clear_tiles(self):
        for grid in self._grids:
            grid.destroy()
        self._grids.clear()
        self._tiles["TOTAL"].set_value("—", color=ACCENT)

    def _hide_all(self):
        self._base_panel.pack_forget()
        self._perf_panel.pack_forget()
        self._bonus_panel.pack_forget()
        self._total_panel.pack_forget()
        self._verdict_panel.pack_forget()

    def _show_all(self):
        self._base_panel.pack(fill="x", pady=(0, 10))
        self._perf_panel.pack(fill="x", pady=(0, 10))
        self._bonus_panel.pack(fill="x", pady=(0, 10))
        self._total_panel.pack(fill="x", pady=(0, 10))
        self._verdict_panel.pack(fill="x", pady=(0, 10))

    def _on_refresh(self):
        bd = self.last_score_tab.get_last_breakdown()
        if bd is None:
            return
        self._populate(bd)

    def _populate(self, bd):
        self._clear_tiles()

        base = self._build_tile_grid(self._base_panel, [
            ("Objects", "—", "#e0e0e0"),
            ("Star Rating", "—", "#66bbff"),
            ("Base AP", "—", "#66bbff"),
        ])
        base["Objects"].set_value(str(bd.total_hits))
        base["Star Rating"].set_value(f"{bd.star_rating:.2f}★")
        base["Base AP"].set_value(f"{bd.base_value:.1f}")

        perf = self._build_tile_grid(self._perf_panel, [
            ("Accuracy", "—", "#e0e0e0"),
            ("Combo", "—", "#e0e0e0"),
            ("Misses", "—", "#ff6666"),
            ("Mods", "—", "#e0e0e0"),
            ("Grade", "—", "#e0e0e0"),
        ])
        perf["Accuracy"].set_value(f"{bd.accuracy*100:.2f}%")
        perf["Combo"].set_value(f"{bd.combo_ratio*100:.1f}%")
        perf["Misses"].set_value(str(bd.count_miss))
        perf["Mods"].set_value(bd.mods_str)
        grade_color = {"X": "#ffd700", "XH": "#ffd700", "S": "#ff69b4",
                       "SH": "#ff69b4", "A": "#00ff7f", "B": "#1e90ff",
                       "C": "#ff4500", "D": "#ff0000"}.get(bd.grade, "#fff")
        perf["Grade"].set_value(bd.grade, color=grade_color)

        bonus = self._build_tile_grid(self._bonus_panel, [
            ("Density", "—", "#e0e0e0"),
            ("Density Bonus", "—", "#e0e0e0"),
            ("Aim Ratio", "—", "#e0e0e0"),
            ("Aim Bonus", "—", "#e0e0e0"),
            ("Score Bonus", "—", "#e0e0e0"),
        ])
        bonus["Density"].set_value(f"{bd.density:.1f} obj/s")
        bonus["Density Bonus"].set_value(f"+{bd.density_bonus*100:.1f}%",
                                          color="#66ff99" if bd.density_bonus > 0 else "#888")
        bonus["Aim Ratio"].set_value(f"{bd.aim_ratio:.2f}")
        bonus["Aim Bonus"].set_value(f"+{bd.aim_bonus*100:.1f}%",
                                      color="#66ff99" if bd.aim_bonus > 0 else "#888")
        bonus["Score Bonus"].set_value(f"+{bd.score_bonus*100:.1f}%",
                                        color="#66ff99" if bd.score_bonus > 0 else "#888")

        self._tiles["TOTAL"].set_value(f"{bd.ap:.0f} AP", color=ACCENT)

        self._set_verdict(bd)
        self.no_data.pack_forget()
        self._show_all()

    def _set_verdict(self, bd):
        if bd.aim_ratio >= AIM_FOCUSED_RATIO:
            vtype, color = "Aim-focused map", "#66bbff"
        elif bd.aim_ratio <= 0.85:
            vtype, color = "Speed / stream-focused map", "#ff69b4"
        elif bd.density >= 6:
            vtype, color = "Dense map", "#ffaa44"
        else:
            vtype, color = "Balanced map", "#e0e0e0"

        sr = bd.star_rating
        if sr < 3:
            diff = "easy"
        elif sr < 5:
            diff = "moderate"
        elif sr < 7:
            diff = "hard"
        else:
            diff = "very hard"

        acc = bd.accuracy * 100
        if acc >= 97:
            acc_word = "excellent accuracy"
        elif acc >= 93:
            acc_word = "good accuracy"
        elif acc >= 88:
            acc_word = "average accuracy"
        else:
            acc_word = "low accuracy"

        bonuses = []
        if bd.aim_bonus > 0:
            bonuses.append(f"+{bd.aim_bonus*100:.0f}% aim")
        if bd.density_bonus > 0:
            bonuses.append(f"+{bd.density_bonus*100:.0f}% density")
        if bd.score_bonus > 0:
            bonuses.append(f"+{bd.score_bonus*100:.0f}% score")
        if bd.rank_bonus > 0:
            bonuses.append(f"+{bd.rank_bonus*100:.0f}% {bd.grade}")
        if bd.mod_mult > 1:
            bonuses.append(f"+{(bd.mod_mult-1)*100:.0f}% mods")

        desc = f"{vtype} · {diff} difficulty · {acc_word}."
        if bonuses:
            desc += " Active bonuses: " + ", ".join(bonuses) + "."
        else:
            desc += " No active bonuses."

        self._verdict_type.configure(text=vtype, text_color=color)
        self._verdict_desc.configure(text=desc)
