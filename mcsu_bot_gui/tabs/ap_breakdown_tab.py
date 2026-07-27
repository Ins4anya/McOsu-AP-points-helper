import customtkinter as ctk


class APBreakdownTab(ctk.CTkFrame):
    def __init__(self, master, last_score_tab, **kwargs):
        super().__init__(master, **kwargs)
        self.last_score_tab = last_score_tab
        self._setup_ui()

    def _setup_ui(self):
        ctk.CTkLabel(self, text="AP Breakdown", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ccc").pack(anchor="w", pady=(0, 12))

        self.refresh_btn = ctk.CTkButton(self, text="Refresh from Last Score",
                                          command=self._on_refresh,
                                          fg_color="#4A9BE8", hover_color="#6CB4EE",
                                          text_color="#0f0f1a",
                                          font=ctk.CTkFont(size=13, weight="bold"))
        self.refresh_btn.pack(anchor="w", pady=(0, 16))

        scroll = ctk.CTkScrollableFrame(self, fg_color="#1a1a2e",
                                         border_color="#2a2a3e", border_width=1)
        scroll.pack(fill="both", expand=True)

        self.content = scroll

        self.no_data = ctk.CTkLabel(scroll, text="No score data.\nFetch a score in 'Last Score' tab first.",
                                     font=ctk.CTkFont(size=14), text_color="#555")
        self.no_data.pack(expand=True, pady=60)

        self.rows_widgets = []

    def _on_refresh(self):
        bd = self.last_score_tab.get_last_breakdown()
        if bd is None:
            return
        self._populate(bd)

    def _clear(self):
        for w in self.rows_widgets:
            w.destroy()
        self.rows_widgets.clear()
        self.no_data.pack_forget()

    def _add_row(self, param: str, value: str, contrib: str,
                 param_color="#888", value_color="#ddd", contrib_color="#ddd",
                 bold=False, bg=None):
        frame = ctk.CTkFrame(self.content, fg_color=bg or "transparent", height=28)
        frame.pack(fill="x", padx=8, pady=1)

        font = ctk.CTkFont(size=13, weight="bold" if bold else "normal")

        p = ctk.CTkLabel(frame, text=param, font=font, text_color=param_color, anchor="w")
        p.pack(side="left", padx=(8, 16))
        v = ctk.CTkLabel(frame, text=value, font=font, text_color=value_color, anchor="w")
        v.pack(side="left", padx=(16, 16))
        c = ctk.CTkLabel(frame, text=contrib, font=font, text_color=contrib_color, anchor="e")
        c.pack(side="right", padx=(16, 8))

        self.rows_widgets.extend([frame, p, v, c])

    def _add_sep(self):
        sep = ctk.CTkFrame(self.content, fg_color="#2a2a3e", height=1)
        sep.pack(fill="x", padx=8, pady=4)
        self.rows_widgets.append(sep)

    def _populate(self, bd):
        self._clear()

        self._add_row("total_hits", f"{bd.total_hits}",
                       f"× {bd.star_rating}★ × 0.1", param_color="#666")
        self._add_row("Base_AP", f"{bd.total_hits} × {bd.star_rating} × 0.1",
                       f"= {bd.base_value:.1f}", param_color="#888")
        self._add_sep()

        self._add_row("Accuracy", f"{bd.accuracy*100:.2f}%",
                       f"× {bd.acc_mult:.4f}")
        self._add_row("Accuracy²", f"{bd.accuracy:.4f}²",
                       f"= {bd.acc_mult:.4f}", param_color="#888")
        self._add_sep()

        self._add_row("Combo Ratio", f"{bd.combo_ratio:.4f}",
                       f"× {bd.combo_ratio:.4f}")
        self._add_sep()

        self._add_row("Miss Penalty", f"{bd.miss_penalty:.4f}",
                       f"× {bd.miss_penalty:.4f}")
        self._add_sep()

        self._add_row("Mods", bd.mods_str, f"× {bd.mod_mult:.4f}")
        self._add_row("Mod Multiplier", "1.0 + bonuses",
                       f"= {bd.mod_mult:.4f}", param_color="#888")
        self._add_sep()

        self._add_row("Density", f"{bd.density:.1f} obj/s",
                       f"+{bd.density_bonus*100:.1f}%")
        self._add_row("Density Bonus", "(density − 2.0) × 0.04",
                       f"× {1+bd.density_bonus:.4f}", param_color="#888")
        self._add_sep()

        self._add_row("Stars (aim / speed)", f"{bd.stars_aim:.2f} / {bd.stars_speed:.2f}",
                       f"ratio = {bd.aim_ratio:.2f}")
        self._add_row("Aim Ratio", f"{bd.stars_aim:.2f} / {bd.stars_speed:.2f}",
                       f"= {bd.aim_ratio:.2f}", param_color="#888")
        self._add_row("Aim Bonus", f"(ratio − 1.0) × 0.08",
                       f"+{bd.aim_bonus*100:.1f}%", param_color="#888")
        self._add_sep()

        self._add_row("Grade", bd.grade, f"+{bd.rank_bonus*100:.0f}%")
        self._add_row("Rank Bonus", f"{bd.grade} bonus",
                       f"× {1+bd.rank_bonus:.4f}", param_color="#888")
        self._add_sep()

        self._add_row("TOTAL AP", "", f"= {bd.ap:.0f} AP",
                        param_color="#4A9BE8", value_color="#4A9BE8",
                        contrib_color="#4A9BE8", bold=True)
