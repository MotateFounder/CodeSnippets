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


class MarkdownRenderMixin:
    def _render_plain_message(self, parent, text, bg, italic=False):
        widget = tk.Text(
            parent,
            height=max(2, text.count("\n") + 2),
            bg=bg,
            fg=self.colors["text"],
            selectbackground=self.colors["select"],
            selectforeground="#ffffff",
            wrap=tk.WORD,
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10, "italic" if italic else "normal"),
            padx=10,
            pady=4,
        )
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)
        widget.pack(fill=tk.X, padx=0, pady=(0, 8))
        if hasattr(self, "register_chat_text_widget"):
            self.register_chat_text_widget(widget)

    def _render_assistant_content(self, parent, text, bg):
        parts = self.split_markdown_code_blocks(text)
        for kind, language, content in parts:
            if kind == "code":
                self._render_code_block(parent, language, content)
            elif content.strip():
                self._render_markdown_text(parent, content, bg)

    def split_markdown_code_blocks(self, text):
        pattern = re.compile(r"```([A-Za-z0-9_+.#-]*)\s*\n(.*?)```", re.DOTALL)
        parts = []
        cursor = 0
        for match in pattern.finditer(text):
            if match.start() > cursor:
                parts.append(("text", "", text[cursor:match.start()]))
            parts.append(("code", match.group(1).strip(), match.group(2).rstrip("\n")))
            cursor = match.end()
        if cursor < len(text):
            parts.append(("text", "", text[cursor:]))
        return parts or [("text", "", text)]

    def _render_markdown_text(self, parent, text, bg):
        for kind, content in self.split_markdown_tables(text):
            if kind == "table":
                self._render_markdown_table(parent, content, bg)
            elif content.strip():
                self._render_markdown_text_block(parent, content, bg)

    def split_markdown_tables(self, text):
        lines = text.strip("\n").splitlines()
        parts = []
        buffer = []
        index = 0

        while index < len(lines):
            if self._is_markdown_table_start(lines, index):
                if buffer:
                    parts.append(("text", "\n".join(buffer).strip("\n")))
                    buffer = []

                table_lines = [lines[index], lines[index + 1]]
                index += 2
                while index < len(lines) and self._is_markdown_table_row(lines[index]):
                    table_lines.append(lines[index])
                    index += 1
                parts.append(("table", "\n".join(table_lines)))
                continue

            buffer.append(lines[index])
            index += 1

        if buffer:
            parts.append(("text", "\n".join(buffer).strip("\n")))
        return parts or [("text", text)]

    def _is_markdown_table_start(self, lines, index):
        if index + 1 >= len(lines):
            return False
        return self._is_markdown_table_row(lines[index]) and self._is_markdown_table_separator(lines[index + 1])

    def _is_markdown_table_row(self, line):
        stripped = line.strip()
        return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2

    def _is_markdown_table_separator(self, line):
        cells = self._split_markdown_table_row(line)
        if not cells:
            return False
        for cell in cells:
            normalized = cell.strip().replace(":", "")
            if len(normalized) < 3 or set(normalized) != {"-"}:
                return False
        return True

    def _split_markdown_table_row(self, line):
        stripped = line.strip()
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        return [cell.strip() for cell in stripped.split("|")]

    def _render_markdown_text_block(self, parent, text, bg):
        widget = tk.Text(
            parent,
            height=max(2, text.count("\n") + 2),
            bg=bg,
            fg=self.colors["text"],
            selectbackground=self.colors["select"],
            selectforeground="#ffffff",
            wrap=tk.WORD,
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            padx=10,
            pady=4,
        )
        widget.tag_configure("heading", foreground="#f4f7fb", font=("Segoe UI", 10, "bold"))
        widget.tag_configure("bullet", lmargin1=18, lmargin2=30)
        widget.tag_configure("inline_code", foreground="#9be7ff", font=("Consolas", 10))
        widget.insert("1.0", text.strip())
        self._style_markdown_text(widget)
        widget.configure(state=tk.DISABLED)
        widget.pack(fill=tk.X, padx=0, pady=(0, 8))
        if hasattr(self, "register_chat_text_widget"):
            self.register_chat_text_widget(widget)

    def _render_markdown_table(self, parent, table_text, bg):
        rows = self.parse_markdown_table(table_text)
        if not rows:
            self._render_markdown_text_block(parent, table_text, bg)
            return

        table = tk.Frame(
            parent,
            bg="#151922",
            highlightbackground="#465166",
            highlightthickness=1,
        )
        table.pack(fill=tk.X, padx=10, pady=(0, 10))

        column_count = max(len(row) for row in rows)
        for column in range(column_count):
            table.grid_columnconfigure(column, weight=1, uniform="markdown_table")

        for row_index, row in enumerate(rows):
            for column_index in range(column_count):
                value = row[column_index] if column_index < len(row) else ""
                is_header = row_index == 0
                cell_bg = "#202633" if is_header else ("#171b22" if row_index % 2 else "#1b202a")
                border = tk.Frame(table, bg="#343c4c")
                border.grid(row=row_index, column=column_index, sticky="nsew", padx=(0, 1), pady=(0, 1))
                label = tk.Label(
                    border,
                    text=self.clean_markdown_table_cell(value),
                    bg=cell_bg,
                    fg="#f4f7fb" if is_header else self.colors["text"],
                    anchor="nw",
                    justify=tk.LEFT,
                    wraplength=280,
                    font=("Segoe UI", 9, "bold" if is_header else "normal"),
                    padx=8,
                    pady=7,
                )
                label.pack(fill=tk.BOTH, expand=True)

    def parse_markdown_table(self, table_text):
        lines = [line for line in table_text.splitlines() if self._is_markdown_table_row(line)]
        if len(lines) < 2:
            return []
        rows = [self._split_markdown_table_row(line) for line in lines]
        if len(rows) >= 2 and self._is_markdown_table_separator(lines[1]):
            rows.pop(1)
        return rows

    def clean_markdown_table_cell(self, text):
        cleaned = text.strip()
        cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</li>\s*<li>", "\n- ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<li>", "- ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</?(?:ul|ol|li)>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
        cleaned = re.sub(r"`([^`\n]+)`", r"\1", cleaned)
        cleaned = re.sub(r"\s*\n\s*", "\n", cleaned)
        return cleaned

    def _style_markdown_text(self, widget):
        content = widget.get("1.0", "end-1c")
        for match in re.finditer(r"(?m)^#{1,6}\s+.*$", content):
            widget.tag_add("heading", f"1.0+{match.start()}c", f"1.0+{match.end()}c")
        for match in re.finditer(r"(?m)^\s*(?:[-*]|\d+\.)\s+.*$", content):
            widget.tag_add("bullet", f"1.0+{match.start()}c", f"1.0+{match.end()}c")
        for match in re.finditer(r"`([^`\n]+)`", content):
            widget.tag_add("inline_code", f"1.0+{match.start()}c", f"1.0+{match.end()}c")

    def _render_code_block(self, parent, language, code):
        box = tk.Frame(
            parent,
            bg="#111318",
            highlightbackground="#465166",
            highlightthickness=1,
        )
        box.pack(fill=tk.X, padx=10, pady=(0, 10))

        header = tk.Frame(box, bg="#171b22")
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text=language or "code",
            bg="#171b22",
            fg=self.colors["muted"],
            anchor="w",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=5,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(
            header,
            text="Copy",
            command=lambda value=code: self.copy_text_to_clipboard(value),
            bg="#2b3240",
            fg="#f4f7fb",
            activebackground=self.colors["accent"],
            activeforeground="#ffffff",
            relief=tk.FLAT,
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=3,
        ).pack(side=tk.RIGHT, padx=6, pady=4)

        lines = max(3, code.count("\n") + 2)
        code_widget = tk.Text(
            box,
            height=lines,
            bg="#111318",
            fg="#d4d4d4",
            selectbackground=self.colors["select"],
            selectforeground="#ffffff",
            wrap=tk.NONE,
            borderwidth=0,
            highlightthickness=0,
            font=("Consolas", 9),
            padx=8,
            pady=6,
        )
        code_widget.tag_configure("keyword", foreground=self.colors["keyword"], font=("Consolas", 9, "bold"))
        code_widget.tag_configure("string", foreground=self.colors["string"])
        code_widget.tag_configure("comment", foreground=self.colors["comment"])
        code_widget.tag_configure("number", foreground=self.colors["number"])
        code_widget.insert("1.0", code)
        self._highlight_code_widget(code_widget)
        code_widget.configure(state=tk.DISABLED)
        code_widget.pack(fill=tk.X)
        if hasattr(self, "register_chat_text_widget"):
            self.register_chat_text_widget(code_widget)
