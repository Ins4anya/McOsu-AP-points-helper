import sys
import customtkinter as ctk

from mcsu_bot.config import load_config
from mcsu_bot_gui.tabs.control_tab import ControlTab
from mcsu_bot_gui.tabs.last_score_tab import LastScoreTab
from mcsu_bot_gui.tabs.ap_breakdown_tab import APBreakdownTab


class App(ctk.CTk):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self._setup_window()
        self._setup_tabs()

    ACCENT = "#4A9BE8"
    ACCENT_HOVER = "#6CB4EE"

    def _setup_window(self):
        self.title("McOsu AP Tracker")
        self.geometry("950x680")
        self.minsize(800, 560)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        original_font_init = ctk.CTkFont.__init__
        def _patched_font_init(self, family=None, *args, **kwargs):
            if family is None:
                family = "JetBrains Mono"
            original_font_init(self, family=family, *args, **kwargs)
        ctk.CTkFont.__init__ = _patched_font_init

    def _setup_tabs(self):
        self.tab_view = ctk.CTkTabview(self, fg_color="#0f0f1a")
        self.tab_view.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_view._segmented_button.configure(
            selected_color=self.ACCENT,
            selected_hover_color=self.ACCENT_HOVER,
            unselected_color="#1a1a2e",
            text_color="#fff",
        )
        self.tab_view._segmented_button._selected_color = self.ACCENT
        self.tab_view._segmented_button._unselected_color = "#1a1a2e"

        control_tab = self.tab_view.add("Control")
        last_score_tab = self.tab_view.add("Last Score")
        breakdown_tab = self.tab_view.add("AP Breakdown")

        self.control = ControlTab(control_tab, self.config)
        self.control.pack(fill="both", expand=True)

        self.last_score = LastScoreTab(last_score_tab, self.config)
        self.last_score.pack(fill="both", expand=True)

        self.breakdown = APBreakdownTab(breakdown_tab, self.last_score)
        self.breakdown.pack(fill="both", expand=True)

    def destroy(self):
        if hasattr(self, "control"):
            self.control.stop_all()
        if hasattr(self, "last_score"):
            self.last_score.stop_autoscan()
        super().destroy()


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Config error: {e}")
        sys.exit(1)

    app = App(config)
    app.mainloop()


if __name__ == "__main__":
    main()
