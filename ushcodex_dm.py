"""
Ushcodex Download Manager (UDM) Pro
===================================
A High-Performance, Multi-Stream Download Manager with:
- Smart Direct Link Resolution (Mediafire, Google Drive, Direct files)
- Strict Byte-Boundary Chunking & Integrity Assembly (Zero Hash Errors)
- Persistent Download History & SHA-256 Hash Auditing
- Live Process Logging & Diagnostics
- Integrated Cloudflare WARP Turbo Tunnel (Hidden Drawer Mode)

Author: Ushcodex
"""

import os
import sys
import time
import math
import subprocess
import threading
from urllib.parse import urlparse, unquote
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests

from url_resolver import resolve_download_url, DEFAULT_UA
from downloader import StreamWorker, verify_and_assemble_chunks, human_size, BUFFER_SIZE
from logger import logger
from history_manager import history_manager, compute_file_sha256
import warp_manager

# Design Tokens (High-Contrast Professional Dark Theme)
COLOR_BG_DARK = "#0d1117"        # Deep Obsidian
COLOR_CARD = "#161b22"           # Elevated panel surface
COLOR_CARD_BORDER = "#30363d"    # Crisp high-visibility border
COLOR_TEXT_PRIMARY = "#ffffff"   # Pure white for high contrast
COLOR_TEXT_MUTED = "#8b949e"     # Silver-gray
COLOR_ACCENT_BLUE = "#38bdf8"    # High-visibility electric cyan
COLOR_BTN_START = "#0284c7"      # Vibrant cyan-blue
COLOR_BTN_PAUSE = "#f59e0b"      # Amber
COLOR_BTN_STOP = "#ef4444"       # High-visibility crimson
COLOR_BTN_SECONDARY = "#21262d"  # Slate button
COLOR_SUCCESS = "#22c55e"        # Vivid emerald green


class WarpInstallDialog(tk.Toplevel):
    """Dominant, prominent visual modal for Cloudflare WARP installation."""
    def __init__(self, parent, on_complete_cb):
        super().__init__(parent)
        self.title("Installing Cloudflare WARP Accelerator")
        self.geometry("540x360")
        self.resizable(False, False)
        self.configure(bg=COLOR_BG_DARK)
        self.transient(parent)
        self.grab_set()

        self.on_complete_cb = on_complete_cb

        # Center on parent window
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        self.geometry(f"+{px + (pw - 540)//2}+{py + (ph - 360)//2}")

        self.setup_ui()
        self.start_installation()

    def setup_ui(self):
        container = tk.Frame(self, bg=COLOR_BG_DARK, padx=20, pady=20)
        container.pack(fill="both", expand=True)

        lbl_icon = tk.Label(container, text="🛡️", bg=COLOR_BG_DARK, fg=COLOR_ACCENT_BLUE, font=("Segoe UI", 32))
        lbl_icon.pack(pady=(0, 4))

        lbl_title = tk.Label(container, text="INSTALLING CLOUDFLARE WARP", bg=COLOR_BG_DARK, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 14, "bold"))
        lbl_title.pack()

        lbl_desc = tk.Label(container, text="Enables UDP WireGuard tunneling to bypass campus QoS download throttles.", bg=COLOR_BG_DARK, fg=COLOR_TEXT_MUTED, font=("Segoe UI", 9))
        lbl_desc.pack(pady=(2, 10))

        # Alert banner
        banner = tk.Frame(container, bg="#3b1d11", padx=12, pady=8, highlightbackground="#f97316", highlightthickness=1)
        banner.pack(fill="x", pady=(0, 12))

        lbl_alert = tk.Label(banner, text="⚠️ ACTION REQUIRED: Click 'YES' when the Windows prompt appears!", bg="#3b1d11", fg="#fdba74", font=("Segoe UI", 9, "bold"))
        lbl_alert.pack()

        self.prog = ttk.Progressbar(container, mode="indeterminate", length=480)
        self.prog.pack(fill="x", pady=(0, 10))
        self.prog.start(15)

        self.txt_out = tk.Text(container, height=6, bg="#070b14", fg="#cbd5e1", relief="flat", font=("Consolas", 8))
        self.txt_out.pack(fill="both", expand=True, pady=(0, 10))

        self.lbl_step = tk.Label(container, text="Initializing package installer...", bg=COLOR_BG_DARK, fg=COLOR_ACCENT_BLUE, font=("Segoe UI", 9))
        self.lbl_step.pack()

    def log_msg(self, text):
        self.txt_out.insert("end", f"{text}\n")
        self.txt_out.see("end")
        self.lbl_step.config(text=text[:60])

    def start_installation(self):
        def worker():
            warp_manager.install_warp_async(progress_cb=self.log_msg)
            for _ in range(30):
                time.sleep(3)
                if warp_manager.is_warp_installed():
                    self.prog.stop()
                    self.prog.configure(mode="determinate", value=100)
                    self.lbl_step.config(text="✅ Installation Complete! Connecting WARP...", fg=COLOR_SUCCESS)
                    warp_manager.connect_warp()
                    time.sleep(2)
                    self.destroy()
                    self.on_complete_cb()
                    return

            self.lbl_step.config(text="Installation completed or waiting for manual confirmation.", fg="#f59e0b")
            time.sleep(3)
            self.destroy()
            self.on_complete_cb()

        threading.Thread(target=worker, daemon=True).start()


class UshcodexDownloadManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ushcodex Download Manager (UDM) Pro")
        self.geometry("920x720")
        self.minsize(820, 600)
        self.configure(bg=COLOR_BG_DARK)

        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        # Configure High-Contrast styles
        self.style.configure(".", background=COLOR_BG_DARK, foreground=COLOR_TEXT_PRIMARY)
        self.style.configure("TNotebook", background=COLOR_BG_DARK, borderwidth=0)
        self.style.configure("TNotebook.Tab", background=COLOR_CARD, foreground=COLOR_TEXT_PRIMARY, padding=[16, 6], font=("Segoe UI", 9, "bold"))
        self.style.map("TNotebook.Tab", background=[("selected", COLOR_BTN_START)], foreground=[("selected", "#ffffff")])

        self.style.configure("Treeview", background="#0c1017", foreground=COLOR_TEXT_PRIMARY, fieldbackground="#0c1017", font=("Consolas", 9), rowheight=24)
        self.style.configure("Treeview.Heading", background=COLOR_CARD_BORDER, foreground=COLOR_ACCENT_BLUE, font=("Segoe UI", 9, "bold"))
        self.style.map("Treeview", background=[("selected", COLOR_BTN_START)])
        self.style.configure("TProgressbar", troughcolor="#21262d", background=COLOR_ACCENT_BLUE, thickness=22)

        # State management
        self.is_downloading = False
        self.stop_event = threading.Event()
        self.workers = []
        self.dest_folder = os.path.abspath(r"c:\Users\PC\Documents\ABU WiFi")
        self.active_raw_url = ""
        self.active_out_path = ""
        self.total_file_size = 0
        self.bytes_lock = threading.Lock()
        self.total_bytes_downloaded = 0
        self.last_measure_time = time.time()
        self.last_measure_bytes = 0
        self.active_speed_str = "0.00 KB/s"

        self.warp_panel_visible = False

        self.setup_ui()
        logger.add_listener(self.on_log_event)
        self.update_warp_indicator()
        self.refresh_history_table()

    def setup_ui(self):
        # 1. Header Banner
        header = tk.Frame(self, bg=COLOR_BG_DARK)
        header.pack(fill="x", padx=18, pady=(14, 6))

        lbl_brand = tk.Label(header, text="⚡ Ushcodex Download Manager", bg=COLOR_BG_DARK, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 16, "bold"))
        lbl_brand.pack(side="left")

        # Hidden Mode / Turbo Settings toggle button
        self.btn_toggle_warp = tk.Button(
            header,
            text="⚙️ Turbo Mode (WARP)",
            bg=COLOR_BTN_SECONDARY,
            fg=COLOR_TEXT_PRIMARY,
            activebackground=COLOR_CARD_BORDER,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=10,
            pady=3,
            command=self.toggle_warp_panel
        )
        self.btn_toggle_warp.pack(side="right")

        self.lbl_warp_badge = tk.Label(header, text="● Checking WARP...", bg=COLOR_BG_DARK, fg=COLOR_TEXT_MUTED, font=("Segoe UI", 9))
        self.lbl_warp_badge.pack(side="right", padx=(0, 10))

        # 2. Hidden Drawer: Turbo Mode / Cloudflare WARP Accelerator
        self.warp_drawer = tk.Frame(self, bg="#132337", padx=14, pady=10, highlightbackground=COLOR_ACCENT_BLUE, highlightthickness=1)
        # Default hidden (not packed until toggled)

        lbl_warp_drawer_title = tk.Label(self.warp_drawer, text="🛡️ Cloudflare WARP Turbo Tunnel (Hidden Mode)", bg="#132337", fg=COLOR_ACCENT_BLUE, font=("Segoe UI", 10, "bold"))
        lbl_warp_drawer_title.pack(anchor="w")

        lbl_warp_info = tk.Label(self.warp_drawer, text="Enforces WireGuard UDP encapsulation to bypass campus Layer-7 download throttles.", bg="#132337", fg="#cbd5e1", font=("Segoe UI", 9))
        lbl_warp_info.pack(anchor="w", pady=(2, 6))

        warp_btn_row = tk.Frame(self.warp_drawer, bg="#132337")
        warp_btn_row.pack(fill="x")

        self.lbl_warp_details = tk.Label(warp_btn_row, text="Checking status...", bg="#132337", fg=COLOR_TEXT_PRIMARY, font=("Consolas", 9))
        self.lbl_warp_details.pack(side="left")

        self.btn_warp_action = tk.Button(warp_btn_row, text="Enable WARP", bg=COLOR_BTN_START, fg="#ffffff", font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=3, command=self.handle_warp_action)
        self.btn_warp_action.pack(side="right")

        # 3. Main Tabs Container (Active Download | History | Process Logs)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=18, pady=(4, 10))

        self.tab_download = tk.Frame(self.notebook, bg=COLOR_BG_DARK)
        self.tab_history = tk.Frame(self.notebook, bg=COLOR_BG_DARK)
        self.tab_logs = tk.Frame(self.notebook, bg=COLOR_BG_DARK)

        self.notebook.add(self.tab_download, text="📥 Active Downloader")
        self.notebook.add(self.tab_history, text="📜 Download History")
        self.notebook.add(self.tab_logs, text="📋 Process Logs")

        self.setup_download_tab()
        self.setup_history_tab()
        self.setup_logs_tab()

        # Periodic UI update ticker
        self.after(300, self.ui_tick)
        self.after(4000, self.periodic_warp_check)

    def setup_download_tab(self):
        # Hero Card for URL & Settings
        self.hero_card = tk.Frame(self.tab_download, bg=COLOR_CARD, padx=16, pady=12, highlightbackground=COLOR_CARD_BORDER, highlightthickness=1)
        self.hero_card.pack(fill="x", pady=6)

        url_header = tk.Frame(self.hero_card, bg=COLOR_CARD)
        url_header.pack(fill="x", pady=(0, 6))

        lbl_url = tk.Label(url_header, text="Download Link (Mediafire, Google Drive, Direct File, Video):", bg=COLOR_CARD, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 10, "bold"))
        lbl_url.pack(side="left")

        btn_paste = tk.Button(url_header, text="📋 Paste URL", bg=COLOR_BTN_SECONDARY, fg=COLOR_TEXT_PRIMARY, activebackground=COLOR_CARD_BORDER, relief="flat", padx=10, pady=2, font=("Segoe UI", 9, "bold"), command=self.paste_from_clipboard)
        btn_paste.pack(side="right")

        self.ent_url = tk.Entry(self.hero_card, bg="#0b0e14", fg="#ffffff", insertbackground=COLOR_ACCENT_BLUE, relief="flat", font=("Consolas", 10), highlightbackground=COLOR_CARD_BORDER, highlightthickness=1)
        self.ent_url.pack(fill="x", pady=(0, 10), ipady=5)

        # Settings row (Streams + Destination folder)
        cfg_row = tk.Frame(self.hero_card, bg=COLOR_CARD)
        cfg_row.pack(fill="x", pady=(0, 10))

        lbl_streams = tk.Label(cfg_row, text="Parallel Streams:", bg=COLOR_CARD, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 9, "bold"))
        lbl_streams.pack(side="left")

        self.spin_streams = tk.Spinbox(cfg_row, from_=2, to=32, width=4, bg="#0b0e14", fg="#ffffff", buttonbackground=COLOR_BTN_SECONDARY, relief="flat", font=("Consolas", 10))
        self.spin_streams.delete(0, "end")
        self.spin_streams.insert(0, "16")
        self.spin_streams.pack(side="left", padx=(6, 20))

        lbl_folder = tk.Label(cfg_row, text="Save To:", bg=COLOR_CARD, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 9, "bold"))
        lbl_folder.pack(side="left")

        self.lbl_folder_val = tk.Label(cfg_row, text=os.path.basename(self.dest_folder), bg="#21262d", fg="#e6edf3", padx=8, pady=3, font=("Segoe UI", 9))
        self.lbl_folder_val.pack(side="left", padx=(6, 8))

        btn_browse = tk.Button(cfg_row, text="📂 Browse...", bg=COLOR_BTN_SECONDARY, fg=COLOR_TEXT_PRIMARY, activebackground=COLOR_CARD_BORDER, relief="flat", padx=10, pady=3, font=("Segoe UI", 9), command=self.browse_dest_folder)
        btn_browse.pack(side="left", padx=(0, 6))

        btn_open_folder = tk.Button(cfg_row, text="📁 Open Folder", bg=COLOR_BTN_SECONDARY, fg=COLOR_TEXT_PRIMARY, activebackground=COLOR_CARD_BORDER, relief="flat", padx=10, pady=3, font=("Segoe UI", 9), command=self.open_dest_folder)
        btn_open_folder.pack(side="left")

        # Action Buttons Row
        btn_row = tk.Frame(self.hero_card, bg=COLOR_CARD)
        btn_row.pack(fill="x", pady=(2, 2))

        self.btn_start = tk.Button(btn_row, text="🚀 START DOWNLOAD", bg=COLOR_BTN_START, fg="#ffffff", activebackground="#0369a1", font=("Segoe UI", 11, "bold"), relief="flat", padx=22, pady=6, command=self.start_download)
        self.btn_start.pack(side="left", padx=(0, 8))

        self.btn_pause = tk.Button(btn_row, text="⏸ PAUSE", bg=COLOR_BTN_PAUSE, fg="#000000", activebackground="#d97706", font=("Segoe UI", 11, "bold"), relief="flat", padx=16, pady=6, state="disabled", command=self.pause_download)
        self.btn_pause.pack(side="left", padx=(0, 8))

        self.btn_stop = tk.Button(btn_row, text="🛑 CANCEL", bg=COLOR_BTN_STOP, fg="#ffffff", activebackground="#dc2626", font=("Segoe UI", 11, "bold"), relief="flat", padx=16, pady=6, state="disabled", command=self.stop_download)
        self.btn_stop.pack(side="left", padx=(0, 8))

        # Status & Progress Display
        status_card = tk.Frame(self.tab_download, bg=COLOR_BG_DARK, padx=4, pady=4)
        status_card.pack(fill="x", pady=(6, 2))

        meta_row = tk.Frame(status_card, bg=COLOR_BG_DARK)
        meta_row.pack(fill="x", pady=(0, 4))

        self.lbl_target_name = tk.Label(meta_row, text="Ready. Paste URL above to begin.", bg=COLOR_BG_DARK, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 11, "bold"))
        self.lbl_target_name.pack(side="left")

        self.lbl_pct = tk.Label(meta_row, text="0.0%", bg=COLOR_BG_DARK, fg=COLOR_ACCENT_BLUE, font=("Segoe UI", 12, "bold"))
        self.lbl_pct.pack(side="right")

        self.progress_bar = ttk.Progressbar(status_card, style="TProgressbar", mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 6))

        self.lbl_metrics = tk.Label(
            status_card,
            text="⚡ Speed: 0.00 KB/s  |  Downloaded: 0 B / 0 B  |  ETA: --:--  |  Streams: 0/16",
            bg=COLOR_BG_DARK,
            fg=COLOR_ACCENT_BLUE,
            font=("Consolas", 10, "bold")
        )
        self.lbl_metrics.pack(anchor="w")

        # Streams Inspector Table
        streams_card = tk.Frame(self.tab_download, bg=COLOR_CARD, padx=12, pady=8, highlightbackground=COLOR_CARD_BORDER, highlightthickness=1)
        streams_card.pack(fill="both", expand=True, pady=6)

        lbl_table_title = tk.Label(streams_card, text="Active Multi-Stream Inspector (Parallel Thread Slices):", bg=COLOR_CARD, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 9, "bold"))
        lbl_table_title.pack(anchor="w", pady=(0, 4))

        cols = ("stream_id", "range", "downloaded", "percent", "status")
        self.tree = ttk.Treeview(streams_card, columns=cols, show="headings", height=5)
        self.tree.heading("stream_id", text="Stream #")
        self.tree.heading("range", text="Byte Range")
        self.tree.heading("downloaded", text="Chunk Size")
        self.tree.heading("percent", text="Progress")
        self.tree.heading("status", text="Status")

        self.tree.column("stream_id", width=80, anchor="center")
        self.tree.column("range", width=180, anchor="w")
        self.tree.column("downloaded", width=140, anchor="w")
        self.tree.column("percent", width=90, anchor="center")
        self.tree.column("status", width=220, anchor="w")

        scroll = ttk.Scrollbar(streams_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def setup_history_tab(self):
        container = tk.Frame(self.tab_history, bg=COLOR_CARD, padx=14, pady=10, highlightbackground=COLOR_CARD_BORDER, highlightthickness=1)
        container.pack(fill="both", expand=True, pady=6)

        top_row = tk.Frame(container, bg=COLOR_CARD)
        top_row.pack(fill="x", pady=(0, 8))

        lbl_h_title = tk.Label(top_row, text="Completed & Managed Downloads History", bg=COLOR_CARD, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 11, "bold"))
        lbl_h_title.pack(side="left")

        btn_refresh_h = tk.Button(top_row, text="🔄 Refresh", bg=COLOR_BTN_SECONDARY, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 9), relief="flat", padx=8, pady=2, command=self.refresh_history_table)
        btn_refresh_h.pack(side="right", padx=(6, 0))

        btn_clear_h = tk.Button(top_row, text="🧹 Clear All Records", bg=COLOR_BTN_SECONDARY, fg=COLOR_BTN_STOP, font=("Segoe UI", 9), relief="flat", padx=8, pady=2, command=self.clear_all_history)
        btn_clear_h.pack(side="right")

        cols = ("date", "filename", "size", "speed", "sha256", "status")
        self.tree_history = ttk.Treeview(container, columns=cols, show="headings", height=10)
        self.tree_history.heading("date", text="Date")
        self.tree_history.heading("filename", text="File Name")
        self.tree_history.heading("size", text="Size")
        self.tree_history.heading("speed", text="Avg Speed")
        self.tree_history.heading("sha256", text="SHA-256 Hash")
        self.tree_history.heading("status", text="Status")

        self.tree_history.column("date", width=120, anchor="center")
        self.tree_history.column("filename", width=220, anchor="w")
        self.tree_history.column("size", width=100, anchor="w")
        self.tree_history.column("speed", width=110, anchor="w")
        self.tree_history.column("sha256", width=220, anchor="w")
        self.tree_history.column("status", width=90, anchor="center")

        h_scroll = ttk.Scrollbar(container, orient="vertical", command=self.tree_history.yview)
        self.tree_history.configure(yscrollcommand=h_scroll.set)

        self.tree_history.pack(side="left", fill="both", expand=True)
        h_scroll.pack(side="right", fill="y")

        # History action buttons
        h_actions = tk.Frame(self.tab_history, bg=COLOR_BG_DARK)
        h_actions.pack(fill="x", pady=(4, 0))

        btn_open_file = tk.Button(h_actions, text="🚀 Open File", bg=COLOR_BTN_START, fg="#ffffff", font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=4, command=self.open_selected_history_file)
        btn_open_file.pack(side="left", padx=(0, 8))

        btn_show_in_folder = tk.Button(h_actions, text="📂 Show in Folder", bg=COLOR_BTN_SECONDARY, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 9), relief="flat", padx=12, pady=4, command=self.show_selected_in_folder)
        btn_show_in_folder.pack(side="left", padx=(0, 8))

        btn_copy_hash = tk.Button(h_actions, text="📋 Copy Hash", bg=COLOR_BTN_SECONDARY, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 9), relief="flat", padx=12, pady=4, command=self.copy_selected_hash)
        btn_copy_hash.pack(side="left", padx=(0, 8))

        btn_delete_rec = tk.Button(h_actions, text="🗑️ Delete Entry", bg=COLOR_BTN_SECONDARY, fg=COLOR_BTN_STOP, font=("Segoe UI", 9), relief="flat", padx=12, pady=4, command=self.delete_selected_history_entry)
        btn_delete_rec.pack(side="right")

    def setup_logs_tab(self):
        container = tk.Frame(self.tab_logs, bg=COLOR_CARD, padx=14, pady=10, highlightbackground=COLOR_CARD_BORDER, highlightthickness=1)
        container.pack(fill="both", expand=True, pady=6)

        top_row = tk.Frame(container, bg=COLOR_CARD)
        top_row.pack(fill="x", pady=(0, 6))

        lbl_l_title = tk.Label(top_row, text="Live Process Diagnostics & Connection Logs", bg=COLOR_CARD, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 11, "bold"))
        lbl_l_title.pack(side="left")

        btn_open_logfile = tk.Button(top_row, text="📂 Open Log File", bg=COLOR_BTN_SECONDARY, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 9), relief="flat", padx=8, pady=2, command=self.open_raw_logfile)
        btn_open_logfile.pack(side="right", padx=(6, 0))

        btn_clear_log = tk.Button(top_row, text="🧹 Clear Logs", bg=COLOR_BTN_SECONDARY, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 9), relief="flat", padx=8, pady=2, command=self.clear_logs_view)
        btn_clear_log.pack(side="right")

        self.txt_full_log = tk.Text(container, bg="#070b14", fg="#cbd5e1", relief="flat", font=("Consolas", 9), highlightbackground=COLOR_CARD_BORDER, highlightthickness=1)
        self.txt_full_log.pack(fill="both", expand=True)

        # Pre-populate with existing logs
        existing_logs = logger.get_recent_logs()
        for line in existing_logs:
            self.txt_full_log.insert("end", line + "\n")
        self.txt_full_log.see("end")

    def on_log_event(self, text):
        def _append():
            self.txt_full_log.insert("end", text + "\n")
            self.txt_full_log.see("end")
        self.after(0, _append)

    def clear_logs_view(self):
        logger.clear()
        self.txt_full_log.delete("1.0", "end")

    def open_raw_logfile(self):
        if os.path.exists(logger.log_path):
            os.startfile(logger.log_path)
        else:
            messagebox.showinfo("Log File", "No log file found yet.")

    def paste_from_clipboard(self):
        try:
            cb = self.clipboard_get().strip()
            if cb:
                self.ent_url.delete(0, "end")
                self.ent_url.insert(0, cb)
        except Exception:
            pass

    def browse_dest_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.dest_folder)
        if chosen:
            self.dest_folder = os.path.abspath(chosen)
            self.lbl_folder_val.config(text=os.path.basename(self.dest_folder) or self.dest_folder)

    def open_dest_folder(self):
        if os.path.exists(self.dest_folder):
            os.startfile(self.dest_folder)
        else:
            messagebox.showerror("Error", "Download folder does not exist.")

    def toggle_warp_panel(self):
        """Hidden Mode drawer toggle."""
        if self.warp_panel_visible:
            self.warp_drawer.pack_forget()
            self.warp_panel_visible = False
            self.btn_toggle_warp.config(bg=COLOR_BTN_SECONDARY)
        else:
            self.warp_drawer.pack(fill="x", padx=18, pady=(0, 6), before=self.notebook)
            self.warp_panel_visible = True
            self.btn_toggle_warp.config(bg=COLOR_BTN_START)
            self.update_warp_indicator()

    def update_warp_indicator(self):
        status, desc = warp_manager.get_warp_status()
        if status == "Connected":
            self.lbl_warp_badge.config(text="🟢 WARP Active (UDP Bypass)", fg=COLOR_SUCCESS)
            self.lbl_warp_details.config(text="Status: Connected (UDP WireGuard Active)", fg=COLOR_SUCCESS)
            self.btn_warp_action.config(text="Disconnect WARP", bg=COLOR_BTN_SECONDARY)
        elif status == "Disconnected":
            self.lbl_warp_badge.config(text="🔴 WARP Off", fg=COLOR_BTN_STOP)
            self.lbl_warp_details.config(text="Status: Installed but Disconnected", fg=COLOR_TEXT_PRIMARY)
            self.btn_warp_action.config(text="⚡ Connect WARP", bg=COLOR_BTN_START)
        else:
            self.lbl_warp_badge.config(text="⚪ WARP Not Installed", fg=COLOR_TEXT_MUTED)
            self.lbl_warp_details.config(text="Status: Not Installed on this PC", fg=COLOR_TEXT_MUTED)
            self.btn_warp_action.config(text="📥 1-Click Install WARP", bg=COLOR_BTN_START)

    def periodic_warp_check(self):
        self.update_warp_indicator()
        self.after(4000, self.periodic_warp_check)

    def handle_warp_action(self):
        status, _ = warp_manager.get_warp_status()
        if status == "Connected":
            logger.log("Disconnecting Cloudflare WARP...")
            ok, msg = warp_manager.disconnect_warp()
            logger.log(msg)
            self.update_warp_indicator()
        elif status == "Disconnected":
            logger.log("Connecting Cloudflare WARP UDP tunnel...")
            self.btn_warp_action.config(text="Connecting...", state="disabled")
            def do_connect():
                ok, msg = warp_manager.connect_warp()
                logger.log(msg)
                self.btn_warp_action.config(state="normal")
                self.update_warp_indicator()
            threading.Thread(target=do_connect, daemon=True).start()
        else:
            WarpInstallDialog(self, on_complete_cb=self.update_warp_indicator)

    def refresh_history_table(self):
        for item in self.tree_history.get_children():
            self.tree_history.delete(item)

        records = history_manager.get_all()
        for r in records:
            short_hash = (r.get("sha256")[:16] + "...") if r.get("sha256") and len(r.get("sha256")) > 16 else r.get("sha256", "--")
            self.tree_history.insert("", "end", iid=r["id"], values=(
                r.get("date", "--"),
                r.get("filename", "--"),
                human_size(r.get("size", 0)),
                r.get("speed", "--"),
                short_hash,
                r.get("status", "--")
            ))

    def clear_all_history(self):
        if messagebox.askyesno("Confirm Clear", "Clear all download history records? (Files on disk will remain untouched)"):
            history_manager.clear_all()
            self.refresh_history_table()

    def get_selected_history_item(self):
        sel = self.tree_history.selection()
        if not sel:
            messagebox.showwarning("Selection Required", "Please select an item from the history table first.")
            return None
        item_id = sel[0]
        for r in history_manager.get_all():
            if r["id"] == item_id:
                return r
        return None

    def open_selected_history_file(self):
        r = self.get_selected_history_item()
        if r and os.path.exists(r["filepath"]):
            os.startfile(r["filepath"])
        elif r:
            messagebox.showerror("File Missing", f"File does not exist on disk:\n{r['filepath']}")

    def show_selected_in_folder(self):
        r = self.get_selected_history_item()
        if r and os.path.exists(r["filepath"]):
            subprocess.run(["explorer.exe", f"/select,{r['filepath']}"])
        elif r:
            messagebox.showerror("File Missing", f"File does not exist:\n{r['filepath']}")

    def copy_selected_hash(self):
        r = self.get_selected_history_item()
        if r and r.get("sha256"):
            self.clipboard_clear()
            self.clipboard_append(r["sha256"])
            messagebox.showinfo("Copied", f"SHA-256 Hash copied to clipboard:\n\n{r['sha256']}")

    def delete_selected_history_entry(self):
        r = self.get_selected_history_item()
        if not r:
            return
        del_disk = messagebox.askyesno("Delete File?", f"Do you also want to permanently delete the file from your computer?\n\n{r['filename']}")
        history_manager.delete_entry(r["id"], delete_disk_file=del_disk)
        self.refresh_history_table()

    def start_download(self):
        if self.is_downloading:
            return

        raw_url = self.ent_url.get().strip()
        if not raw_url:
            messagebox.showwarning("Missing URL", "Please enter or paste a download link first.")
            return

        try:
            streams_count = int(self.spin_streams.get())
        except ValueError:
            streams_count = 16

        self.is_downloading = True
        self.stop_event.clear()
        self.active_raw_url = raw_url

        self.btn_start.config(state="disabled", text="Resolving...")
        self.btn_pause.config(state="normal")
        self.btn_stop.config(state="normal")

        for row in self.tree.get_children():
            self.tree.delete(row)

        logger.log(f"Resolving download target: {raw_url}")
        self.lbl_target_name.config(text="Resolving URL and inspecting stream...")

        t = threading.Thread(target=self.orchestrator, args=(raw_url, streams_count), daemon=True)
        t.start()

    def pause_download(self):
        if not self.is_downloading:
            return
        logger.log("Pausing download streams... partial byte progress saved.")
        self.lbl_target_name.config(text="Pausing streams...")
        self.stop_event.set()
        self.is_downloading = False
        self.btn_start.config(state="normal", text="▶ RESUME", bg=COLOR_BTN_START)
        self.btn_pause.config(state="disabled")

    def stop_download(self):
        if not self.is_downloading:
            return
        logger.log("Stopping and canceling download...")
        self.stop_event.set()
        self.is_downloading = False
        self.btn_start.config(state="normal", text="🚀 START DOWNLOAD", bg=COLOR_BTN_START)
        self.btn_pause.config(state="disabled")
        self.btn_stop.config(state="disabled")
        self.lbl_target_name.config(text="Download canceled.")

    def orchestrator(self, raw_url, connections):
        try:
            # 1. Resolve raw URL using Smart URL Resolver
            final_url, filename, total_size, accepts_ranges, err = resolve_download_url(raw_url)
            if err and not final_url:
                logger.log(f"Resolution error: {err}", level="ERROR")
                messagebox.showerror("Resolution Error", err)
                self.finish_paused()
                return

            if "webpage.html" in filename:
                logger.log(f"Warning: {err}", level="WARN")
                if not messagebox.askyesno("Webpage Detected", f"{err}\n\nDo you want to download this HTML page anyway?"):
                    self.finish_paused()
                    return

            self.active_out_path = os.path.join(self.dest_folder, filename)
            self.total_file_size = total_size

            self.lbl_target_name.config(text=f"Downloading: {filename} ({human_size(total_size)})")
            logger.log(f"Resolved endpoint : {final_url[:75]}...")
            logger.log(f"Target filename   : {filename}")
            logger.log(f"Total stream size : {human_size(total_size)} ({total_size} bytes)")
            logger.log(f"Range chunking    : {'Supported' if accepts_ranges else 'Single Stream Only'}")

            self.btn_start.config(text="Downloading...")
            headers = {"User-Agent": DEFAULT_UA}

            if total_size == 0 or not accepts_ranges:
                logger.log("Range requests not supported. Falling back to single stream mode...")
                self.single_stream_download(final_url, headers)
                return

            # Multi-Connection Segmented Download
            connections = min(connections, 32)
            chunk_size = math.ceil(total_size / connections)
            temp_dir = f"{self.active_out_path}.udm_parts"
            os.makedirs(temp_dir, exist_ok=True)

            self.tree_items = {}
            for i in range(connections):
                sb = i * chunk_size
                eb = min((i + 1) * chunk_size - 1, total_size - 1)
                item_id = self.tree.insert("", "end", values=(
                    f"Stream {i+1:02d}",
                    f"{human_size(sb)} - {human_size(eb)}",
                    f"{human_size(eb - sb + 1)}",
                    "0.0%",
                    "Ready"
                ))
                self.tree_items[i] = item_id

            self.workers = []
            self.last_measure_time = time.time()
            self.last_measure_bytes = 0

            # Calculate existing bytes for resume
            existing_total = 0
            for i in range(connections):
                part_f = os.path.join(temp_dir, f"part_{i:03d}.tmp")
                if os.path.exists(part_f):
                    existing_total += os.path.getsize(part_f)

            with self.bytes_lock:
                self.total_bytes_downloaded = existing_total

            def worker_update(w_id, downloaded, total_chunk, status, delta=0):
                if delta > 0:
                    with self.bytes_lock:
                        self.total_bytes_downloaded += delta

                pct = (downloaded / total_chunk) * 100 if total_chunk > 0 else 0
                item_id = self.tree_items.get(w_id)
                if item_id:
                    self.tree.item(item_id, values=(
                        f"Stream {w_id+1:02d}",
                        self.tree.item(item_id)["values"][1],
                        f"{human_size(downloaded)} / {human_size(total_chunk)}",
                        f"{pct:.1f}%",
                        status
                    ))

            for i in range(connections):
                sb = i * chunk_size
                eb = min((i + 1) * chunk_size - 1, total_size - 1)
                part_f = os.path.join(temp_dir, f"part_{i:03d}.tmp")
                w = StreamWorker(i, final_url, headers, sb, eb, part_f, worker_update, self.stop_event)
                self.workers.append(w)
                w.start()

            for w in self.workers:
                w.join()

            if self.stop_event.is_set():
                self.finish_paused()
                return

            if not all(w.success for w in self.workers):
                logger.log("Some worker streams timed out. Click RESUME to continue.", level="WARN")
                self.finish_paused()
                return

            # Assembly phase with strict chunk boundary & integrity validation
            self.lbl_target_name.config(text=f"Verifying chunk boundaries & assembling {filename}...")
            verify_and_assemble_chunks(temp_dir, self.active_out_path, connections, total_size)

            # Automated SHA-256 Hash Computation
            self.lbl_target_name.config(text="Computing SHA-256 integrity hash...")
            logger.log("Computing SHA-256 hash of assembled file...")
            computed_hash = compute_file_sha256(self.active_out_path)
            logger.log(f"SHA-256 Hash Verified: {computed_hash}")

            # Save to Download History
            history_manager.add_entry(
                url=raw_url,
                filename=filename,
                filepath=self.active_out_path,
                size=total_size,
                speed=self.active_speed_str,
                sha256=computed_hash,
                status="Completed"
            )
            self.refresh_history_table()

            self.finish_success(self.active_out_path, computed_hash)

        except Exception as e:
            logger.log(f"Execution error: {e}", level="ERROR")
            messagebox.showerror("Download Error", str(e))
            self.finish_paused()

    def single_stream_download(self, final_url, headers):
        with requests.get(final_url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(self.active_out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=BUFFER_SIZE):
                    if self.stop_event.is_set():
                        return
                    if chunk:
                        f.write(chunk)
                        with self.bytes_lock:
                            self.total_bytes_downloaded += len(chunk)

        # Hash computation for single stream
        computed_hash = compute_file_sha256(self.active_out_path)
        history_manager.add_entry(
            url=self.active_raw_url,
            filename=os.path.basename(self.active_out_path),
            filepath=self.active_out_path,
            size=os.path.getsize(self.active_out_path),
            speed=self.active_speed_str,
            sha256=computed_hash,
            status="Completed"
        )
        self.refresh_history_table()
        self.finish_success(self.active_out_path, computed_hash)

    def ui_tick(self):
        if self.is_downloading and self.total_file_size > 0:
            now = time.time()
            dt = now - self.last_measure_time
            with self.bytes_lock:
                current_bytes = self.total_bytes_downloaded

            if dt >= 0.5:
                delta_b = current_bytes - self.last_measure_bytes
                speed = delta_b / dt if dt > 0 else 0
                self.last_measure_bytes = current_bytes
                self.last_measure_time = now

                pct = (current_bytes / self.total_file_size) * 100
                rem_bytes = max(0, self.total_file_size - current_bytes)
                eta_s = int(rem_bytes / speed) if speed > 1024 else 0
                eta_str = f"{eta_s // 60:02d}:{eta_s % 60:02d}" if speed > 1024 else "--:--"

                active_count = sum(1 for w in self.workers if w.is_alive())
                self.active_speed_str = f"{human_size(speed)}/s"

                self.progress_bar["value"] = pct
                self.lbl_pct.config(text=f"{pct:.1f}%")
                self.lbl_metrics.config(
                    text=f"⚡ Speed: {self.active_speed_str}  |  Downloaded: {human_size(current_bytes)} / {human_size(self.total_file_size)}  |  ETA: {eta_str}  |  Streams: {active_count}/{len(self.workers)}"
                )

        self.after(300, self.ui_tick)

    def finish_success(self, path, sha256_hash=""):
        self.is_downloading = False
        self.progress_bar["value"] = 100
        self.lbl_pct.config(text="100.0%")
        self.lbl_target_name.config(text=f"🎉 Completed & Verified: {os.path.basename(path)}")
        logger.log(f"[SUCCESS] Download completed and verified: {path}")

        self.btn_start.config(state="normal", text="🚀 START DOWNLOAD", bg=COLOR_BTN_START)
        self.btn_pause.config(state="disabled")
        self.btn_stop.config(state="disabled")

        hash_display = f"\nSHA-256 Hash:\n{sha256_hash}\n" if sha256_hash else ""
        messagebox.showinfo(
            "Download Complete & Verified",
            f"File downloaded and verified 100% intact!\n\nFile:\n{os.path.basename(path)}\n{hash_display}\nLocation:\n{path}"
        )

    def finish_paused(self):
        self.is_downloading = False
        self.btn_start.config(state="normal", text="▶ RESUME", bg=COLOR_BTN_START)
        self.btn_pause.config(state="disabled")
        self.btn_stop.config(state="disabled")


if __name__ == "__main__":
    app = UshcodexDownloadManager()
    app.mainloop()
