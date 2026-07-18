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


class LayoutLeftMixin:
    def _left_pane(self, parent):
        frame = ttk.Frame(parent, style="Panel.TFrame")

        tree_frame = ttk.Frame(frame, style="Panel.TFrame")
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 0))
        self.file_tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=tree_scroll.set)
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self.file_tree.bind("<Double-1>", self._on_tree_double_click)
        self.file_tree.bind("<Button-3>", self._show_file_tree_context_menu)
        self.file_tree.bind("<Control-Button-1>", self._show_file_tree_context_menu)

        browser_actions = ttk.Frame(frame, style="Panel.TFrame")
        browser_actions.pack(fill=tk.X, padx=12, pady=(8, 0))
        ttk.Button(browser_actions, text="Refresh", command=self.refresh_file_browser).pack(side=tk.LEFT)
        ttk.Button(browser_actions, text="New File", command=self.create_file_in_selected_folder).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self._title(frame, "SEARCH ENGINE").pack(fill=tk.X, padx=12, pady=(16, 7))

        search_row = ttk.Frame(frame, style="Panel.TFrame")
        search_row.pack(fill=tk.X, padx=12)
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            search_row,
            textvariable=self.search_var,
            bg=self.colors["editor"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            highlightcolor=self.colors["accent"],
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)
        ttk.Button(search_row, text="Search", command=self.search_folder).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self.search_entry.bind("<Return>", lambda _event: self.search_folder())
        self.search_entry.bind("<KeyRelease>", self.on_search_query_changed)

        result_frame = ttk.Frame(frame, style="Panel.TFrame")
        result_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(8, 12))
        self.results_tree = ttk.Treeview(result_frame, show="tree", selectmode="browse")
        result_scroll = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=result_scroll.set)
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        result_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_tree.bind("<Double-1>", self._open_selected_result)

        return frame
