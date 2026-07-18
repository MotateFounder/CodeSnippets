import csv
import json
import os
import re
import shutil
import threading
import tkinter as tk
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.config.constants import MAX_SEARCH_BYTES, TEXT_EXTENSIONS


class LayoutMainMixin:
    def _build_ui(self):
        top = ttk.Frame(self, style="Header.TFrame")
        top.pack(fill=tk.X)

        # ttk.Button(top, text="Open Folder", command=self.choose_folder).pack(
        #     side=tk.LEFT, padx=(12, 8), pady=10
        # )
        ttk.Button(top, text="Write Report", command=self.open_write_report_dialog).pack(
            side=tk.RIGHT, padx=(8, 12), pady=10
        )
        ttk.Button(top, text="Settings", command=lambda: self.open_settings_window(parent=self)).pack(
            side=tk.RIGHT, padx=(8, 0), pady=10
        )
        workspace_header = tk.Frame(top, bg=self.colors["panel2"])
        workspace_header.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(16, 12), pady=8)
        self.workspace_name_label = tk.Label(
            workspace_header,
            text="No workspace",
            bg=self.colors["panel2"],
            fg=self.colors["text"],
            anchor="w",
            font=self.ui_font("title", "bold") if hasattr(self, "ui_font") else ("Segoe UI", 12, "bold"),
            padx=0,
            pady=2,
        )
        self.workspace_name_label.pack(side=tk.LEFT, padx=(0, 16), pady=0)
        self.folder_label = tk.Label(
            workspace_header,
            text="No folder selected",
            bg=self.colors["panel2"],
            fg=self.colors["muted"],
            anchor="w",
            font=self.ui_font("base") if hasattr(self, "ui_font") else ("Segoe UI", 10),
            padx=0,
            pady=2,
        )
        self.folder_label.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=0)
        self.folder_label.bind("<Button-1>", lambda _event: self.open_workspace_folder())
        # ttk.Button(top, text="Import Session", command=self.import_session).pack(
        #     side=tk.LEFT, padx=(0, 8), pady=10
        # )
        # ttk.Button(top, text="Open code snippets", command=self.open_saved_snippets).pack(
        #     side=tk.LEFT, padx=(0, 8), pady=10
        # )
        # ttk.Button(top, text="Save code snippets", command=self.save_snippets).pack(
        #     side=tk.LEFT, padx=(0, 8), pady=10
        # )
        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        left = self._left_pane(body)
        middle_tabs = ttk.Notebook(body, style="Middle.TNotebook")
        self.middle_tabs = middle_tabs
        center = self._center_pane(middle_tabs)
        self.open_file_tab_frame = center
        right = self._right_pane(middle_tabs)
        notebook = self._notebook_pane(middle_tabs)
        prompt_manager = self._prompt_manager_pane(middle_tabs)
        middle_tabs.add(center, text="Open File")
        middle_tabs.add(right, text="Snippet Clipboard")
        middle_tabs.add(notebook, text="Notebook")
        middle_tabs.add(prompt_manager, text="Prompt Manager")
        chat = self._chat_pane(body)

        body.add(left, weight=1)
        body.add(middle_tabs, weight=5)
        body.add(chat, weight=2)

        self.status = tk.Label(
            self,
            text="Open a folder to begin collecting snippets.",
            bg=self.colors["editor"],
            fg=self.colors["muted"],
            anchor="w",
            padx=10,
            pady=5,
        )
        self.status.pack(fill=tk.X)

    def _title(self, parent, text):
        return tk.Label(
            parent,
            text=text,
            bg=self.colors["panel"] if str(parent).endswith("!frame") else self.colors["panel2"],
            fg="#f0f3f6",
            anchor="w",
            font=self.ui_font("title", "bold") if hasattr(self, "ui_font") else ("Segoe UI", 10, "bold"),
        )

    def _bind_shortcuts(self):
        self.bind("<Control-o>", lambda _event: self.choose_folder())
        self.bind("<Control-f>", self.focus_search_entry)
        self.bind("<Control-Shift-C>", lambda _event: self.copy_all())
        self.bind("<Control-s>", lambda _event: self.save_current_file() if self.current_file else self.save_snippets())
        self.bind("<Control-l>", lambda _event: self.open_saved_snippets())
