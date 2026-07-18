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


class LayoutChatMixin:
    def _chat_pane(self, parent):
        frame = ttk.Frame(parent, style="Panel.TFrame")

        chat_title_row = ttk.Frame(frame, style="Panel.TFrame")
        chat_title_row.pack(fill=tk.X, padx=12, pady=(12, 7))
        self._title(chat_title_row, "CodeSnippets Assistant").pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.set_context_enabled_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            chat_title_row,
            text="Set context",
            variable=self.set_context_enabled_var,
            bg=self.colors["panel"],
            fg=self.colors["text"],
            activebackground=self.colors["panel"],
            activeforeground=self.colors["text"],
            selectcolor=self.colors["editor"],
            borderwidth=0,
            padx=8,
        ).pack(side=tk.RIGHT)

        chat_toolbar = ttk.Frame(frame, style="Panel.TFrame")
        chat_toolbar.pack(fill=tk.X, padx=12, pady=(0, 8))
        self.chat_thread_var = tk.StringVar(value=self.chat_threads[0]["title"])
        self.chat_thread_combo = ttk.Combobox(
            chat_toolbar,
            textvariable=self.chat_thread_var,
            state="readonly",
            values=[thread["title"] for thread in self.chat_threads],
        )
        self.chat_thread_combo.bind("<<ComboboxSelected>>", self.switch_chat_thread)
        ttk.Button(chat_toolbar, text="Chat Manager", command=self.open_chat_manager).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.reasoning_enabled_var = tk.BooleanVar(value=False)
        self.prompt_controls_visible = False
        self.prompt_combo = ttk.Combobox(
            chat_toolbar,
            textvariable=self.prompt_preset_var,
            state="readonly",
            values=[],
        )
        self.prompt_combo.bind("<<ComboboxSelected>>", self.append_selected_prompt_preset)

        context_quality_frame = ttk.Frame(frame, style="Panel.TFrame")
        context_quality_frame.pack(fill=tk.X, padx=12, pady=(0, 8))

        transcript_frame = ttk.Frame(frame, style="Panel.TFrame")
        transcript_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        self.chat_canvas = tk.Canvas(
            transcript_frame,
            bg=self.colors["editor"],
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
        )
        chat_scroll = ttk.Scrollbar(transcript_frame, orient=tk.VERTICAL, command=self.chat_canvas.yview)
        self.chat_cards = ttk.Frame(self.chat_canvas, style="TFrame")
        self.chat_cards.bind(
            "<Configure>",
            lambda _event: self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all")),
        )
        self.chat_cards_window = self.chat_canvas.create_window((0, 0), window=self.chat_cards, anchor="nw")
        self.chat_canvas.configure(yscrollcommand=chat_scroll.set)
        self.chat_canvas.bind(
            "<Configure>",
            lambda event: (
                self.chat_canvas.itemconfigure(self.chat_cards_window, width=event.width),
                self.after_idle(self.resize_chat_text_widgets) if hasattr(self, "resize_chat_text_widgets") else None,
            ),
        )
        self.chat_canvas.bind("<Enter>", lambda _event: self.chat_canvas.bind_all("<MouseWheel>", self._on_chat_mousewheel))
        self.chat_canvas.bind("<Leave>", lambda _event: self.chat_canvas.unbind_all("<MouseWheel>"))
        self.chat_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        chat_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.chat_command_hint = "Use / for chat modes, @ for snippets, # for files or selections, and #filetree for the open-file tree. Ctrl+Enter sends."
        self.chat_input_placeholder = "New local chat ready.\n{0}".format(self.chat_command_hint)
        self.chat_input_placeholder_visible = False
        self.chat_input = tk.Text(
            frame,
            height=5,
            bg=self.colors["editor"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            selectbackground=self.colors["select"],
            selectforeground="#ffffff",
            wrap=tk.WORD,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            font=("Segoe UI", 10),
            padx=10,
            pady=8,
        )
        self.chat_input.tag_configure(
            "placeholder",
            foreground=self.colors["muted"],
            font=("Segoe UI", 10, "italic"),
        )
        self.chat_input.pack(fill=tk.X, padx=12, pady=(0, 8))
        self.chat_input.bind("<FocusIn>", lambda _event: self._hide_chat_input_placeholder())
        self.chat_input.bind("<FocusOut>", lambda _event: self._show_chat_input_placeholder())
        self.chat_input.bind("<KeyPress>", self._on_chat_input_key_press)
        self.chat_input.bind("<Up>", self._on_chat_input_navigation)
        self.chat_input.bind("<Down>", self._on_chat_input_navigation)
        self.chat_input.bind("<Return>", self._on_chat_input_navigation)
        self.chat_input.bind("<Tab>", self._on_chat_input_navigation)
        self.chat_input.bind("<Escape>", self._on_chat_input_navigation)
        self.chat_input.bind("<Control-Return>", lambda _event: self.send_chat_message())
        self.chat_input.bind("<KeyRelease>", self._on_chat_input_key_release)

        self.send_chat_button = ttk.Button(frame, text="Send", style="Accent.TButton", command=self.send_chat_message)
        self.send_chat_button.pack(fill=tk.X, padx=12, pady=(0, 12))

        self.render_current_chat()
        self.update_chat_input_placeholder()
        return frame

    def _on_chat_mousewheel(self, event):
        self.chat_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"
