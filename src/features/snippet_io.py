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


class SnippetIOMixin:
    def copy_all(self):
        text = self.formatted_snippets()
        if not text:
            self.status.configure(text="The temporary clipboard is empty.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.configure(text="All snippets copied to the system clipboard.")

    def save_snippets(self):
        text = self.formatted_snippets()
        if not text:
            self.status.configure(text="The temporary clipboard is empty.")
            return

        path = filedialog.asksaveasfilename(
            title="Save snippets",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("Markdown files", "*.md"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            Path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save file:\n{exc}")
            return
        self.refresh_file_browser()
        self.status.configure(text="Snippets saved.")


    def open_saved_snippets(self):
        path = filedialog.askopenfilename(
            title="Open saved snippets",
            filetypes=[("Snippet files", "*.txt *.md"), ("Text files", "*.txt"), ("Markdown files", "*.md"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            messagebox.showerror("Open failed", f"Could not open snippets file:\n{exc}")
            return

        loaded = self.parse_saved_snippets(text)
        if not loaded:
            messagebox.showwarning(
                "No snippets found",
                "This file does not look like a saved Code Snippet Collector file.",
            )
            return

        if self.snippets:
            append = messagebox.askyesnocancel(
                "Open saved snippets",
                "Append loaded snippets to the current temporary clipboard?\n\nChoose No to replace the current snippets.",
            )
            if append is None:
                return
            if not append:
                self.clear_snippets(show_status=False)

        for snippet in loaded:
            self.snippets.append(snippet)
            self._render_snippet(snippet)

        self.refresh_token_count()
        count = len(loaded)
        suffix = "" if count == 1 else "s"
        self.status.configure(text=f"Loaded {count} snippet{suffix} from {Path(path).name}.")

    def parse_saved_snippets(self, text):
        marker = re.compile(r"^=====\s*(.*?)\s*=====\s*$", re.MULTILINE)
        matches = list(marker.finditer(text))
        snippets = []

        for index, match in enumerate(matches):
            source = match.group(1).strip()
            body_start = match.end()
            body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[body_start:body_end].strip("\r\n")
            if source.lower() == "file tree structure":
                continue
            if source and body.strip():
                metadata, snippet_text = self.parse_snippet_metadata(body)
                snippet = {
                    "id": self.create_snippet_id(),
                    "description": "",
                    "source": Path(source),
                    "text": snippet_text,
                    "selected": False,
                    "created_at": metadata.get("created_at", ""),
                    "updated_at": metadata.get("updated_at", ""),
                }
                self.ensure_created_at(snippet)
                self.ensure_snippet_id(snippet)
                snippets.append(snippet)

        return snippets

    def parse_snippet_metadata(self, body):
        metadata = {}
        lines = body.splitlines()
        content_start = 0
        for index, line in enumerate(lines[:3]):
            if line.startswith("Timestamp: "):
                metadata["created_at"] = self.normalize_timestamp(line.split(":", 1)[1])
                content_start = index + 1
                continue
            if line.startswith("Edited: "):
                metadata["updated_at"] = self.normalize_timestamp(line.split(":", 1)[1])
                content_start = index + 1
                continue
            if not line.strip() and metadata:
                content_start = index + 1
                break
            break
        return metadata, "\n".join(lines[content_start:]).strip("\r\n")

    def clear_snippets(self, show_status=True):
        self.snippets.clear()
        self.snippet_cards.clear()
        for child in self.snippet_holder.winfo_children():
            child.destroy()
        self.refresh_token_count()
        if show_status:
            self.status.configure(text="Temporary clipboard cleared.")
