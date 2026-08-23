from nicegui import ui

from mcsu_bot.ap_calculator import AIM_FOCUSED_RATIO
from mcsu_gui.theme import ACCENT
from mcsu_gui.widgets import Panel, Tile

GRADE_COLORS = {
    "X": "#ffd700", "XH": "#ffd700", "S": "#ff69b4", "SH": "#ff69b4",
    "A": "#00ff7f", "B": "#1e90ff", "C": "#ff4500", "D": "#ff0000",
}


class APBreakdownTab:
    def __init__(self, state, last_score_tab):
        self.state = state
        self.last_score_tab = last_score_tab
        self._grids = []
        self._setup_ui()

    def _setup_ui(self):
        with ui.column().classes("w-full gap-3"):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                ui.label("AP Breakdown").classes("mono").style(
                    "font-size: 16px; font-weight: 700; color: #ccc"
                )
                ui.button("Refresh from Last Score").props("dense").style(
                    f"background: {ACCENT}; color: #0f0f1a; font-weight: 700;"
                ).on("click", self._on_refresh)

            self._base = Panel("Base")
            self._perf = Panel("Performance")
            self._bonus = Panel("Bonuses")
            self._total = Panel("TOTAL AP", accent=True)
            with self._total.content:
                self._total_tile = Tile("TOTAL AP", "—", ACCENT)
            self._review = Panel("Review")
            with self._review.content:
                self._verdict_type = ui.label("").style(
                    "font-size: 15px; font-weight: 700; color: #fff"
                )
                self._verdict_desc = ui.label("").style(
                    "font-size: 12px; color: #aaa"
                )

            self._placeholder = ui.label(
                "No score data.\nFetch a score in 'Last Score' tab first."
            ).style("color: #555; font-size: 14px; text-align: center; padding: 60px 0")

            self._panels = [self._base, self._perf, self._bonus, self._total, self._review]
            self._hide_all()

    def _hide_all(self):
        for panel in self._panels:
            panel.el.visible = False

    def _show_all(self):
        for panel in self._panels:
            panel.el.visible = True

    def _on_refresh(self):
        bd = self.last_score_tab.get_last_breakdown()
        if bd is None:
            return
        self._populate(bd)

    def _build_tile_grid(self, panel, definitions):
        with panel.content:
            grid = ui.grid(columns=len(definitions)).classes("w-full gap-2")
            with grid:
                tiles = {}
                for label, default, color in definitions:
                    tiles[label] = Tile(label, default, color)
        self._grids.append(grid)
        return tiles

    def _clear_tiles(self):
        for grid in self._grids:
            grid.delete()
        self._grids.clear()
        self._total_tile.set("—", ACCENT)

    def _populate(self, bd):
        self._clear_tiles()

        base = self._build_tile_grid(self._base, [
            ("Objects", "—", "#e0e0e0"),
            ("Star Rating", "—", "#66bbff"),
            ("Base AP", "—", "#66bbff"),
        ])
        if bd.object_weight > 0:
            objects_txt = str(bd.object_weight)
            if bd.num_sliders:
                objects_txt += f"  ({bd.num_circles}+2×{bd.num_sliders})"
        else:
            objects_txt = str(bd.total_hits)
        base["Objects"].set(objects_txt)
        base["Star Rating"].set(f"{bd.star_rating:.2f}★")
        base["Base AP"].set(f"{bd.base_value:.1f}")

        perf = self._build_tile_grid(self._perf, [
            ("Accuracy", "—", "#e0e0e0"),
            ("Combo", "—", "#e0e0e0"),
            ("Misses", "—", "#ff6666"),
            ("Mods", "—", "#e0e0e0"),
            ("Grade", "—", "#e0e0e0"),
        ])
        perf["Accuracy"].set(f"{bd.accuracy * 100:.2f}%")
        perf["Combo"].set(f"{bd.combo_ratio * 100:.1f}%")
        perf["Misses"].set(str(bd.count_miss))
        perf["Mods"].set(bd.mods_str)
        grade_color = GRADE_COLORS.get(bd.grade, "#fff")
        perf["Grade"].set(bd.grade, grade_color)

        bonus = self._build_tile_grid(self._bonus, [
            ("Density", "—", "#e0e0e0"),
            ("Density Bonus", "—", "#e0e0e0"),
            ("Aim Ratio", "—", "#e0e0e0"),
            ("Aim Bonus", "—", "#e0e0e0"),
            ("Score Bonus", "—", "#e0e0e0"),
        ])
        bonus["Density"].set(f"{bd.density:.1f} obj/s")
        bonus["Density Bonus"].set(f"+{bd.density_bonus * 100:.1f}%",
                                   "#66ff99" if bd.density_bonus > 0 else "#888")
        bonus["Aim Ratio"].set(f"{bd.aim_ratio:.2f}")
        bonus["Aim Bonus"].set(f"+{bd.aim_bonus * 100:.1f}%",
                               "#66ff99" if bd.aim_bonus > 0 else "#888")
        bonus["Score Bonus"].set(f"+{bd.score_bonus * 100:.1f}%",
                                 "#66ff99" if bd.score_bonus > 0 else "#888")

        self._total_tile.set(f"{bd.ap:.0f} AP", ACCENT)

        self._set_verdict(bd)
        self._placeholder.visible = False
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
            bonuses.append(f"+{bd.aim_bonus * 100:.0f}% aim")
        if bd.density_bonus > 0:
            bonuses.append(f"+{bd.density_bonus * 100:.0f}% density")
        if bd.score_bonus > 0:
            bonuses.append(f"+{bd.score_bonus * 100:.0f}% score")
        if bd.rank_bonus > 0:
            bonuses.append(f"+{bd.rank_bonus * 100:.0f}% {bd.grade}")
        if bd.mod_mult > 1:
            bonuses.append(f"+{(bd.mod_mult - 1) * 100:.0f}% mods")

        desc = f"{vtype} · {diff} difficulty · {acc_word}."
        if bonuses:
            desc += " Active bonuses: " + ", ".join(bonuses) + "."
        else:
            desc += " No active bonuses."

        self._verdict_type.set_text(vtype)
        self._verdict_type.style(replace=f"font-size: 15px; font-weight: 700; color: {color}")
        self._verdict_desc.set_text(desc)