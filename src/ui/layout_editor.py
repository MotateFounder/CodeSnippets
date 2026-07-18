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


class LayoutEditorMixin:
    def _center_pane(self, parent):
        frame = ttk.Frame(parent, style="TFrame")

        header = ttk.Frame(frame, style="Header.TFrame")
        header.pack(fill=tk.X)
        self.file_label = self._title(header, "OPEN SELECTED FILE")
        self.file_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12, pady=9)
        self.close_file_button = ttk.Button(
            header,
            text="Close File",
            command=self.close_current_file,
            state=tk.DISABLED,
        )
        self.close_file_button.pack(side=tk.RIGHT, padx=(0, 8), pady=8)
        ttk.Button(header, text="Add Selection", style="Accent.TButton", command=self.add_selection).pack(
            side=tk.RIGHT, padx=12, pady=8
        )

        self.editor_tabs = ttk.Notebook(frame, style="Middle.TNotebook")
        self.editor_tabs.pack(fill=tk.BOTH, expand=True)
        self.editor_tabs.bind("<<NotebookTabChanged>>", self._on_editor_tab_changed)
        self.editor = None
        self.line_numbers = None
        self.editor_y_scroll = None

        footer = ttk.Frame(frame, style="Header.TFrame")
        footer.pack(fill=tk.X)
        self.save_file_button = ttk.Button(
            footer,
            text="Save File",
            style="Accent.TButton",
            command=self.save_current_file,
            state=tk.DISABLED,
        )
        self.save_file_button.pack(side=tk.RIGHT, padx=12, pady=8)

        return frame
