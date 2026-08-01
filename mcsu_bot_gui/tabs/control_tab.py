import customtkinter as ctk
import threading
import webbrowser
from pathlib import Path

from mcsu_bot.server_client import (
    check_auth,
    get_server_url,
    get_saved_token,
    open_login,
    parse_login_link,
    save_server_token,
)
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
        self._build_server_section()
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

    def _build_server_section(self):
        card = ctk.CTkFrame(self, fg_color="#1a1a2e", border_color="#2a2a3e", border_width=1)
        card.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(card, text="Server Sync", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#ccc").pack(anchor="w", padx=16, pady=(8, 4))

        url_row = ctk.CTkFrame(card, fg_color="transparent")
        url_row.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(url_row, text="Server URL:", font=ctk.CTkFont(size=13),
                     text_color="#888").pack(side="left")

        saved_url = self.config.server_url or get_server_url()
        self.server_url_var = ctk.StringVar(value=saved_url)
        self.server_url_entry = ctk.CTkEntry(url_row, textvariable=self.server_url_var,
                                              font=ctk.CTkFont(size=13), width=250,
                                              fg_color="#0f0f1a", border_color="#2a2a3e",
                                              placeholder_text="https://ins4anya.fun")
        self.server_url_entry.pack(side="left", padx=(8, 8), fill="x", expand=True)

        self.login_btn = ctk.CTkButton(url_row, text="Login via osu!",
                                        command=self._on_server_login,
                                        fg_color="#ff66aa", hover_color="#ff4d9a",
                                        text_color="#fff",
                                        font=ctk.CTkFont(size=12))
        self.login_btn.pack(side="right")

        token_row = ctk.CTkFrame(card, fg_color="transparent")
        token_row.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(token_row, text="Token / link:", font=ctk.CTkFont(size=13),
                     text_color="#888").pack(side="left")

        saved_token = self.config.server_token or get_saved_token()
        self.token_var = ctk.StringVar(value=saved_token)
        self.token_entry = ctk.CTkEntry(token_row, textvariable=self.token_var,
                                        font=ctk.CTkFont(size=13), width=250,
                                        fg_color="#0f0f1a", border_color="#2a2a3e",
                                        placeholder_text="Paste the token from your profile page")
        self.token_entry.pack(side="left", padx=(8, 8), fill="x", expand=True)

        self.save_token_btn = ctk.CTkButton(token_row, text="Save",
                                            command=self._on_save_token,
                                            fg_color="#2a2a3e", hover_color="#3a3a5e",
                                            text_color="#aaa",
                                            font=ctk.CTkFont(size=12), width=60)
        self.save_token_btn.pack(side="right")

        ctk.CTkLabel(card, text="After login, click \u201cCopy token\u201d on your profile page and paste it here",
                     font=ctk.CTkFont(size=11), text_color="#555").pack(anchor="w", padx=16, pady=(0, 8))

        status_row = ctk.CTkFrame(card, fg_color="transparent")
        status_row.pack(fill="x", padx=16, pady=(0, 8))

        self.server_status = ctk.CTkLabel(status_row, text="● Not connected",
                                           text_color="#666", font=ctk.CTkFont(size=12))
        self.server_status.pack(side="left")

        self.sync_all_btn = ctk.CTkButton(status_row, text="Sync Local Scores",
                                           command=self._on_sync_all,
                                           fg_color="#2a2a3e", hover_color="#3a3a5e",
                                           text_color="#aaa", font=ctk.CTkFont(size=11),
                                           state="disabled")
        self.sync_all_btn.pack(side="right")

        if self.config.server_url and self.config.server_token:
            save_server_token(self.config.server_url, self.config.server_token)

        self._update_server_status()

    def _on_server_login(self):
        server_url = self.server_url_var.get().strip()
        if not server_url:
            self._on_output("Enter server URL first")
            return
        webbrowser.open(f"{server_url.rstrip('/')}/auth/login")

    def _on_save_token(self):
        text = self.token_var.get().strip()
        if not text:
            self._on_output("Paste the profile link or token first")
            return
        server_url, token = parse_login_link(text)
        if not token:
            self._on_output("Could not parse token — paste the link or the JWT token")
            return
        if not server_url:
            server_url = self.server_url_var.get().strip()
        if not server_url:
            self._on_output("Could not detect server URL — fill the Server URL field")
            return
        self.server_url_var.set(server_url)
        save_server_token(server_url, token)
        self._on_output(f"Saved token for {server_url}")
        self._update_server_status()

    def _on_sync_all(self):
        server_url = self.server_url_var.get().strip()
        if not server_url or not check_auth(server_url):
            self._on_output("Not connected — save the token first")
            return
        self.sync_all_btn.configure(state="disabled", text="Syncing...")
        self._on_output("Starting full sync...")
        ap_db_path = self.config.ap_db_path or (
            Path(__file__).resolve().parent.parent.parent / "scores_ap.db"
        )
        source = self.source_var.get()

        def _progress(i, total):
            if i % 20 == 0 or i == total:
                self.after(0, lambda: self._on_output(f"Syncing... {i}/{total}"))

        def _run():
            from mcsu_bot.server_client import sync_all_scores

            synced, duplicate, failed, errors = sync_all_scores(
                server_url, ap_db_path, source, on_progress=_progress
            )
            self.after(
                0,
                lambda: self._sync_all_done(synced, duplicate, failed, errors),
            )

        threading.Thread(target=_run, daemon=True).start()

    def _sync_all_done(self, synced, duplicate, failed, errors):
        self.sync_all_btn.configure(state="normal", text="Sync Local Scores")
        self._on_output(
            f"Sync finished: {synced} synced, {duplicate} already on server, {failed} failed"
        )
        for err in errors[:10]:
            self._on_output(f"  ! {err}")
        if len(errors) > 10:
            self._on_output(f"  ... and {len(errors) - 10} more errors")

    def _update_server_status(self):
        url = self.server_url_var.get().strip()
        if url and check_auth(url):
            self.server_status.configure(text="● Connected", text_color="#66ff99")
            self.sync_all_btn.configure(state="normal")
        else:
            self.server_status.configure(text="● Not connected", text_color="#666")
            self.sync_all_btn.configure(state="disabled")

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
