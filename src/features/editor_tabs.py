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


class EditorTabsMixin:
    def open_file(self, path):
        path = Path(path)
        if not self.is_displayable_tree_entry(path):
            self.open_file_preview(path)
            return
        existing = self.open_file_tabs.get(path)
        if existing:
            self.editor_tabs.select(existing["frame"])
            self._activate_editor_tab(existing)
            self.status.configure(text=str(path))
            return

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            messagebox.showerror("Open failed", f"Could not open file:\n{exc}")
            return

        editor_data = self._create_editor_tab(path, content)
        self.open_file_tabs[path] = editor_data
        self.editor_tabs.select(editor_data["frame"])
        self._activate_editor_tab(editor_data)
        self._sync_line_numbers()
        self._highlight_syntax()
        self._highlight_search()
        self.status.configure(text=str(path))

    def open_file_preview(self, path):
        path = Path(path)
        existing = self.open_file_tabs.get(path)
        if existing:
            self.editor_tabs.select(existing["frame"])
            self._activate_editor_tab(existing)
            self.status.configure(text=str(path))
            return
        suffix = path.suffix.lower()
        if suffix in {".png", ".gif"}:
            editor_data = self._create_image_preview_tab(path)
        elif suffix in {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}:
            editor_data = self._create_attachment_info_tab(path, "audio")
        elif suffix in {".jpg", ".jpeg", ".webp", ".bmp"}:
            editor_data = self._create_attachment_info_tab(path, "image")
        else:
            editor_data = self._create_attachment_info_tab(path, "file")
        self.open_file_tabs[path] = editor_data
        self.editor_tabs.select(editor_data["frame"])
        self._activate_editor_tab(editor_data)
        self.status.configure(text="Previewing {0}.".format(path.name))

    def _create_image_preview_tab(self, path):
        tab = ttk.Frame(self.editor_tabs, style="TFrame")
        canvas = tk.Canvas(tab, bg=self.colors["editor"], highlightthickness=0, borderwidth=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        try:
            image = tk.PhotoImage(file=str(path))
            canvas.image = image
            canvas.create_image(24, 24, image=image, anchor="nw")
            canvas.create_text(24, image.height() + 44, text=str(path), fill=self.colors["muted"], anchor="nw")
        except tk.TclError:
            canvas.create_text(
                24,
                24,
                text="Image preview is not available for this format.\n{0}".format(path),
                fill=self.colors["text"],
                anchor="nw",
            )
        editor_data = {
            "path": path,
            "frame": tab,
            "editor": None,
            "line_numbers": None,
            "editor_y_scroll": None,
            "original_text": "",
            "dirty": False,
            "preview_type": "image",
        }
        self.editor_tabs.add(tab, text=path.name)
        return editor_data

    def _create_attachment_info_tab(self, path, kind):
        tab = ttk.Frame(self.editor_tabs, style="TFrame")
        text = tk.Text(
            tab,
            bg=self.colors["editor"],
            fg=self.colors["text"],
            selectbackground=self.colors["select"],
            selectforeground="#ffffff",
            wrap=tk.WORD,
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            padx=14,
            pady=14,
        )
        details = [
            "{0} attachment".format(kind.capitalize()),
            "",
            str(path),
        ]
        if path.exists():
            details.append("")
            details.append("Size: {0:,} bytes".format(path.stat().st_size))
        if kind == "audio":
            details.append("")
            details.append("Inline audio playback is not implemented yet, but the file is attached and indexed here.")
        elif kind == "image":
            details.append("")
            details.append("Tk can preview PNG/GIF directly. This format may need an external viewer later.")
        text.insert("1.0", "\n".join(details))
        text.configure(state=tk.DISABLED)
        text.pack(fill=tk.BOTH, expand=True)
        editor_data = {
            "path": path,
            "frame": tab,
            "editor": None,
            "line_numbers": None,
            "editor_y_scroll": None,
            "original_text": "",
            "dirty": False,
            "preview_type": kind,
        }
        self.editor_tabs.add(tab, text=path.name)
        return editor_data

    def _create_editor_tab(self, path, content):
        tab = ttk.Frame(self.editor_tabs, style="TFrame")
        editor_frame = ttk.Frame(tab, style="TFrame")
        editor_frame.pack(fill=tk.BOTH, expand=True)

        line_numbers = tk.Text(
            editor_frame,
            width=5,
            padx=6,
            pady=8,
            bg=self.colors["panel"],
            fg="#5f6b7a",
            borderwidth=0,
            highlightthickness=0,
            state=tk.DISABLED,
            font=("Consolas", 10),
        )
        line_numbers.pack(side=tk.LEFT, fill=tk.Y)

        editor = tk.Text(
            editor_frame,
            bg=self.colors["editor"],
            fg="#d4d4d4",
            insertbackground=self.colors["text"],
            selectbackground=self.colors["select"],
            selectforeground="#ffffff",
            wrap=tk.NONE,
            undo=False,
            borderwidth=0,
            highlightthickness=0,
            padx=10,
            pady=8,
            font=("Consolas", 10),
        )
        editor_y_scroll = ttk.Scrollbar(
            editor_frame,
            orient=tk.VERTICAL,
            command=lambda *args, text_widget=editor, numbers=line_numbers: self._scroll_editor_y(
                *args, editor=text_widget, line_numbers=numbers
            ),
        )
        x_scroll = ttk.Scrollbar(tab, orient=tk.HORIZONTAL, command=editor.xview)
        editor.configure(
            yscrollcommand=lambda first, last, scroll=editor_y_scroll, text_widget=editor, numbers=line_numbers: self._editor_yview(
                first, last, scroll, text_widget, numbers
            ),
            xscrollcommand=x_scroll.set,
        )
        editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        editor_y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        x_scroll.pack(fill=tk.X)

        editor.tag_configure("search", background=self.colors["highlight"], foreground=self.colors["highlight_text"])
        editor.tag_configure("persistent_selection", background=self.colors["select"], foreground="#ffffff")
        editor.tag_configure("keyword", foreground=self.colors["keyword"], font=("Consolas", 10, "bold"))
        editor.tag_configure("string", foreground=self.colors["string"])
        editor.tag_configure("comment", foreground=self.colors["comment"])
        editor.tag_configure("number", foreground=self.colors["number"])
        editor.bind(
            "<MouseWheel>",
            lambda _event, text_widget=editor, numbers=line_numbers: self._sync_line_numbers(text_widget, numbers),
        )
        editor.bind(
            "<ButtonRelease-1>",
            lambda _event, data=None, text_widget=editor, numbers=line_numbers: self._on_editor_button_release(
                _event,
                text_widget,
                numbers,
            ),
        )
        editor.bind("<ButtonPress-1>", lambda event, text_widget=editor: self._on_editor_button_press(event, text_widget))
        editor.bind("<Button-3>", self.show_editor_context_menu)
        editor.bind("<F12>", lambda _event: (self.go_to_definition(), "break")[1])
        editor.bind("<<Modified>>", lambda event, data=None: self._on_editor_modified(event))
        editor.bind("<KeyRelease>", self._on_editor_key_release)
        editor.insert("1.0", content)
        editor.edit_modified(False)

        editor_data = {
            "path": path,
            "frame": tab,
            "editor": editor,
            "line_numbers": line_numbers,
            "editor_y_scroll": editor_y_scroll,
            "original_text": content,
            "dirty": False,
            "persistent_selection_start": None,
            "persistent_selection_end": None,
            "persistent_selection_text": "",
        }
        self.editor_tabs.add(tab, text=path.name)
        return editor_data
