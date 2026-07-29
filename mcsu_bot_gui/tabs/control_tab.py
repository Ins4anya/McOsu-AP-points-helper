import customtkinter as ctk

from mcsu_bot_gui.workers.process_worker import ProcessWorker, free_port


class ControlTab(ctk.CTkFrame):
    def __init__(self, master, config, **kwargs):
        super().__init__(master, **kwargs)
        self.config = config
        free_port(8080)
        self.bot_process = ProcessWorker(
            on_output=self._on_output,
            on_started=lambda: self._set_bot_status("Active", "#66ff99"),
            on_stopped=lambda: self._set_bot_status("Idle", "#666"),
        )
        self.web_process = ProcessWorker(
            on_output=self._on_output,
            on_started=lambda: self._set_web_status("Active :8080", "#66ff99"),
            on_stopped=lambda: self._set_web_status("Idle", "#666"),
        )
        self._setup_ui()

    def _setup_ui(self):
        ctk.CTkLabel(self, text="Control Panel", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ccc").pack(anchor="w", pady=(0, 12))

        self._build_source_selector()
        self._build_bot_section()
        self._build_web_section()
        self._build_console()

    def _build_source_selector(self):
        card = ctk.CTkFrame(self, fg_color="#1a1a2e", border_color="#2a2a3e", border_width=1)
        card.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(card, text="Source:", font=ctk.CTkFont(size=14),
                     text_color="#aaa").pack(side="left", padx=(16, 8), pady=12)

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
            rb = ctk.CTkRadioButton(card, text=label, variable=self.source_var,
                                     value=val, font=ctk.CTkFont(size=13),
                                     fg_color="#4A9BE8", hover_color="#6CB4EE",
                                     command=_on_source_change)
            rb.pack(side="left", padx=(4, 12), pady=12)

        ctk.CTkLabel(card, text="Username:", font=ctk.CTkFont(size=13),
                     text_color="#888").pack(side="left", padx=(20, 6))
        self.username_entry = ctk.CTkEntry(card, textvariable=self.username_var,
                                            font=ctk.CTkFont(size=13), width=150,
                                            fg_color="#0f0f1a", border_color="#2a2a3e")
        self.username_entry.pack(side="left", padx=(0, 16), pady=12)
        self.username_entry.bind("<KeyRelease>", lambda e: _on_username_change())

        if self.source_var.get() != "api":
            self.username_entry.configure(state="disabled")

    def _build_bot_section(self):
        card = ctk.CTkFrame(self, fg_color="#1a1a2e", border_color="#2a2a3e", border_width=1)
        card.pack(fill="x", pady=(0, 16))

        self.bot_var = ctk.BooleanVar(value=False)
        self.bot_cb = ctk.CTkCheckBox(card, text="Launch Discord Bot",
                                       variable=self.bot_var, command=self._on_bot_toggle,
                                       font=ctk.CTkFont(size=14))
        self.bot_cb.pack(side="left", padx=16, pady=12)

        self.bot_status = ctk.CTkLabel(card, text="● Idle", text_color="#666",
                                        font=ctk.CTkFont(size=12))
        self.bot_status.pack(side="right", padx=16, pady=12)

    def _build_web_section(self):
        card = ctk.CTkFrame(self, fg_color="#1a1a2e", border_color="#2a2a3e", border_width=1)
        card.pack(fill="x", pady=(0, 16))

        self.web_var = ctk.BooleanVar(value=False)
        self.web_cb = ctk.CTkCheckBox(card, text="Launch Web Server  (:8080)",
                                       variable=self.web_var, command=self._on_web_toggle,
                                       font=ctk.CTkFont(size=14))
        self.web_cb.pack(side="left", padx=16, pady=12)

        self.web_status = ctk.CTkLabel(card, text="● Idle", text_color="#666",
                                        font=ctk.CTkFont(size=12))
        self.web_status.pack(side="right", padx=16, pady=12)

    def _build_console(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(header, text="Console Log", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ccc").pack(side="left")
        ctk.CTkButton(header, text="Copy Log", font=ctk.CTkFont(size=11),
                      fg_color="#2a2a3e", hover_color="#3a3a5e", text_color="#aaa",
                      width=80, command=self._copy_log).pack(side="right")

        self.console = ctk.CTkTextbox(self, fg_color="#0a0a14", text_color="#88cc88",
                                       font=ctk.CTkFont(family="Consolas", size=12),
                                       border_color="#2a2a3e", border_width=1)
        self.console.pack(fill="both", expand=True)

    def _copy_log(self):
        text = self.console.get("0.0", "end")
        if not text.strip():
            return
        self.clipboard_clear()
        self.clipboard_append(text.strip())
        self._on_output("📋 Log copied to clipboard")

    def _on_bot_toggle(self):
        if self.bot_var.get():
            self.bot_cb.configure(state="disabled", text="Starting...")
            self.after(100, lambda: self._start_bot())
        else:
            self.bot_process.stop()
            self.bot_cb.configure(state="normal")

    def _start_bot(self):
        self.config.source = self.source_var.get()
        self.bot_process.start_bot(self.config)
        self.bot_cb.configure(state="normal")

    def _on_web_toggle(self):
        if self.web_var.get():
            self.web_cb.configure(state="disabled", text="Starting...")
            self.after(100, lambda: self._start_web())
        else:
            self.web_process.stop()
            self.web_cb.configure(state="normal")

    def _start_web(self):
        free_port(8080)
        self.web_process.start_web(self.config)
        self.web_cb.configure(state="normal")

    def _on_output(self, text: str):
        self.console.insert("end", text + "\n")
        self.console.see("end")

    def _set_bot_status(self, text: str, color: str):
        self.bot_status.configure(text=f"● {text}", text_color=color)

    def _set_web_status(self, text: str, color: str):
        self.web_status.configure(text=f"● {text}", text_color=color)

    def stop_all(self):
        self.bot_process.stop()
        self.web_process.stop()
