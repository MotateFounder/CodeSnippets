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


class LayoutSnippetsMixin:
    def _right_pane(self, parent):
        frame = ttk.Frame(parent, style="Panel.TFrame")
        title_row = ttk.Frame(frame, style="Panel.TFrame")
        title_row.pack(fill=tk.X, padx=12, pady=(12, 7))
        self._title(title_row, "ADDITIVE TEMPORARY CLIPBOARD").pack(side=tk.LEFT, fill=tk.X, expand=True)
        actions = ttk.Frame(frame, style="Panel.TFrame")
        actions.pack(fill=tk.X, padx=12, pady=(0, 10))
        ttk.Button(
            actions,
            text="New Card",
            command=self.add_blank_card,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        #ttk.Button(
        #    actions,
        #    text="New Snippets",
        #    command=self.open_new_snippet_clipboard_window,
        #).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        ttk.Button(
            actions,
            text="Manage",
            command=self.open_snippet_clipboard_manager,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        self.snippet_clipboard_status_var = tk.StringVar(value="General / Snippets 1")
        tk.Label(
            actions,
            textvariable=self.snippet_clipboard_status_var,
            bg=self.colors["panel"],
            fg=self.colors["muted"],
            anchor="e",
            font=("Segoe UI", 8, "bold"),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        #ttk.Button(actions, text="Clear", command=self.clear_snippets).pack(side=tk.LEFT, fill=tk.X, expand=True)
        #ttk.Button(actions, text="Open", command=self.open_saved_snippets).pack(
        #    side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0)
        #)
        #ttk.Button(actions, text="Copy All", style="Accent.TButton", command=self.copy_all).pack(
        #    side=tk.LEFT, fill=tk.X, expand=True, padx=8
        #)
        #ttk.Button(actions, text="Save", style="Accent.TButton", command=self.save_snippets).pack(
        #    side=tk.LEFT, fill=tk.X, expand=True
        #)

        selection_actions = ttk.Frame(frame, style="Panel.TFrame")
        self.exclude_repolens_generated_context_var = tk.BooleanVar(value=False)
        exclude_repolens_check = tk.Checkbutton(
            selection_actions,
            text="Do not attach generated RepoLens context",
            variable=self.exclude_repolens_generated_context_var,
            command=self.refresh_token_count,
            bg=self.colors["panel"],
            fg=self.colors["text"],
            activebackground=self.colors["panel"],
            activeforeground=self.colors["text"],
            selectcolor=self.colors["editor"],
            borderwidth=0,
            anchor="w",
        )
        self.attach_tooltip(
            exclude_repolens_check,
            "Generated RepoLens context can be large. Its automatic token usage is not reflected in the clipboard token counter.",
        )

        self.show_context_cards_var = tk.BooleanVar(value=False)
        self.show_context_cards_check = tk.Checkbutton(
            selection_actions,
            text="Show context cards",
            variable=self.show_context_cards_var,
            command=self.render_active_snippet_clipboard,
            bg=self.colors["panel"],
            fg=self.colors["text"],
            activebackground=self.colors["panel"],
            activeforeground=self.colors["text"],
            selectcolor=self.colors["editor"],
            borderwidth=0,
            anchor="w",
        )
        self.attach_tooltip(
            self.show_context_cards_check,
            "Show or hide generated context cards in the clipboard without removing them from the context pool.",
        )
        #ttk.Button(selection_actions, text="Select All Context", command=lambda: self.set_all_snippets_selected(True)).pack(
        #    side=tk.LEFT, fill=tk.X, expand=True
        #)
        #ttk.Button(selection_actions, text="Select None", command=lambda: self.set_all_snippets_selected(False)).pack(
        #    side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0)
        #)

        self.snippet_canvas = tk.Canvas(
            frame,
            bg=self.colors["panel"],
            borderwidth=0,
            highlightthickness=0,
        )
        snippet_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.snippet_canvas.yview)
        self.snippet_scroll_content = ttk.Frame(self.snippet_canvas, style="Panel.TFrame")
        self.snippet_scroll_content.bind(
            "<Configure>",
            lambda _event: self.snippet_canvas.configure(scrollregion=self.snippet_canvas.bbox("all")),
        )
        self.snippet_window = self.snippet_canvas.create_window((0, 0), window=self.snippet_scroll_content, anchor="nw")
        self.snippet_canvas.configure(yscrollcommand=snippet_scroll.set)
        self.snippet_canvas.bind(
            "<Configure>",
            lambda event: self.snippet_canvas.itemconfigure(self.snippet_window, width=event.width),
        )
        self.snippet_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0), pady=(0, 12))
        snippet_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 12))

        context_card = tk.Frame(
            self.snippet_scroll_content,
            bg=self.colors["panel2"],
            highlightbackground="#343c4c",
            highlightthickness=1,
        )
        context_card.pack(fill=tk.X, padx=(0, 10), pady=(0, 10))

        context_header = tk.Frame(context_card, bg=self.colors["panel2"])
        context_header.pack(fill=tk.X)

        tk.Label(
            context_header,
            text="File Tree Structure",
            bg=self.colors["panel2"],
            fg="#f4f7fb",
            anchor="w",
            font=("Segoe UI", 9, "bold"),
            padx=9,
            pady=6,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.include_context_tree_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            context_header,
            text="Attach",
            variable=self.include_context_tree_var,
            command=self.refresh_token_count,
            bg=self.colors["panel2"],
            fg=self.colors["text"],
            activebackground=self.colors["panel2"],
            selectcolor=self.colors["editor"],
            borderwidth=0,
            font=("Segoe UI", 8, "bold"),
        ).pack(side=tk.RIGHT, padx=(0, 8))

        self.context_tree_timestamp_label = tk.Label(
            context_header,
            text=f"Updated {self.display_timestamp(self.current_timestamp())}",
            bg=self.colors["panel2"],
            fg=self.colors["muted"],
            anchor="e",
            font=("Segoe UI", 8),
            padx=9,
            pady=6,
        )
        self.context_tree_timestamp_label.pack(side=tk.RIGHT)

        self.context_tree_text = tk.Text(
            context_card,
            height=7,
            bg=self.colors["editor"],
            fg="#d4d4d4",
            selectbackground=self.colors["select"],
            selectforeground="#ffffff",
            wrap=tk.NONE,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            font=("Consolas", 9),
            padx=8,
            pady=6,
        )
        self.context_tree_text.pack(fill=tk.X, padx=9, pady=(0, 9))
        self.context_tree_text.insert("1.0", "(no snippet references yet)")
        self.context_tree_text.configure(state=tk.DISABLED)

        self.snippet_holder = ttk.Frame(self.snippet_scroll_content, style="Panel.TFrame")
        self.snippet_holder.pack(fill=tk.X, padx=(0, 10))
        self.refresh_snippet_clipboard_selector()
        self.refresh_context_cards_visibility_toggle()

        return frame
