import customtkinter as ctk


GLASS_BG = "#16162a"
GLASS_BORDER = "#2d2d48"
TILE_BG = "#1e1e38"
TILE_BORDER = "#33335a"
ACCENT = "#4A9BE8"


class GlassTile(ctk.CTkFrame):
    def __init__(self, master, label_text, value_text="—", value_color="#e0e0e0", **kwargs):
        super().__init__(master, fg_color=TILE_BG, border_color=TILE_BORDER,
                         border_width=1, corner_radius=10, **kwargs)
        self._label = ctk.CTkLabel(self, text=label_text, font=ctk.CTkFont(size=10),
                                    text_color="#888")
        self._label.pack(anchor="w", padx=12, pady=(10, 0))
        self._value = ctk.CTkLabel(self, text=value_text, font=ctk.CTkFont(size=20, weight="bold"),
                                    text_color=value_color)
        self._value.pack(anchor="w", padx=12, pady=(0, 10))

    def set_value(self, text: str, color: str = None):
        self._value.configure(text=text)
        if color:
            self._value.configure(text_color=color)


class GlassPanel(ctk.CTkFrame):
    def __init__(self, master, title, **kwargs):
        super().__init__(master, fg_color=GLASS_BG, border_color=GLASS_BORDER,
                         border_width=1, corner_radius=12, **kwargs)
        self._title = ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=13, weight="bold"),
                                    text_color="#ccc")
        self._title.pack(anchor="w", padx=16, pady=(12, 8))
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="x", padx=12, pady=(0, 12))
