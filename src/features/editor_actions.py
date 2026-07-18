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
from src.services.repoLens.service import RepoLensService


class EditorActionsMixin:
    def _on_editor_modified(self, _event):
        editor_data = self._active_editor_data()
        if not editor_data:
            return
        editor = editor_data["editor"]
        if not editor.edit_modified():
            return
        editor.edit_modified(False)

        current_text = editor.get("1.0", "end-1c")
        editor_data["dirty"] = current_text != editor_data["original_text"]
        self.current_file_dirty = editor_data["dirty"]
        self.current_file_text = editor_data["original_text"]
        self._set_save_file_enabled(editor_data["dirty"])
        self._update_editor_tab_title(editor_data)

    def _on_editor_key_release(self, _event):
        self._sync_line_numbers()
        editor_data = self._active_editor_data()
        if editor_data:
            self._store_editor_selection(editor_data, clear_when_empty=False)
        if self.syntax_after_id:
            self.after_cancel(self.syntax_after_id)
        self.syntax_after_id = self.after(250, self._refresh_editor_highlights)

    def _refresh_editor_highlights(self):
        self.syntax_after_id = None
        self._highlight_syntax()
        self._highlight_search()
        for editor_data in getattr(self, "open_file_tabs", {}).values():
            self._apply_persistent_editor_selection(editor_data)

    def _on_editor_button_press(self, _event, editor):
        editor_data = self._editor_data_for_widget(editor)
        if editor_data:
            self._clear_persistent_editor_selection(editor_data)

    def _on_editor_button_release(self, _event, editor, line_numbers):
        self._sync_line_numbers(editor, line_numbers)
        editor_data = self._editor_data_for_widget(editor)
        if editor_data:
            self._store_editor_selection(editor_data, clear_when_empty=True)

    def _editor_data_for_widget(self, editor):
        for editor_data in getattr(self, "open_file_tabs", {}).values():
            if editor_data.get("editor") == editor:
                return editor_data
        return None

    def _store_editor_selection(self, editor_data, clear_when_empty=True):
        editor = editor_data.get("editor")
        if not editor:
            return False
        try:
            start_index = editor.index(tk.SEL_FIRST)
            end_index = editor.index(tk.SEL_LAST)
            selected = editor.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            if clear_when_empty:
                self._clear_persistent_editor_selection(editor_data)
            return False
        if not selected.strip():
            if clear_when_empty:
                self._clear_persistent_editor_selection(editor_data)
            return False

        start_line = self._line_from_text_index(start_index)
        end_line = self._line_from_text_index(end_index)
        if str(end_index).split(".", 1)[1] == "0" and end_line and end_line > start_line:
            end_line -= 1
        editor_data["persistent_selection_start"] = start_line
        editor_data["persistent_selection_end"] = end_line
        editor_data["persistent_selection_text"] = selected
        self._apply_persistent_editor_selection(editor_data)
        return True

    def _apply_persistent_editor_selection(self, editor_data):
        editor = editor_data.get("editor")
        if not editor:
            return
        editor.tag_remove("persistent_selection", "1.0", tk.END)
        start_line = editor_data.get("persistent_selection_start")
        end_line = editor_data.get("persistent_selection_end")
        if not start_line or not end_line:
            return
        editor.tag_add("persistent_selection", "{0}.0".format(start_line), "{0}.end".format(end_line))

    def _clear_persistent_editor_selection(self, editor_data):
        editor = editor_data.get("editor")
        if editor:
            editor.tag_remove("persistent_selection", "1.0", tk.END)
        editor_data["persistent_selection_start"] = None
        editor_data["persistent_selection_end"] = None
        editor_data["persistent_selection_text"] = ""

    def _set_save_file_enabled(self, enabled):
        if hasattr(self, "save_file_button"):
            self.save_file_button.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def _set_close_file_enabled(self, enabled):
        if hasattr(self, "close_file_button"):
            self.close_file_button.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def save_current_file(self):
        editor_data = self._active_editor_data()
        if not editor_data:
            self.status.configure(text="Open a file before saving.")
            return
        if not editor_data["dirty"]:
            self.status.configure(text="The current file has no unsaved changes.")
            return

        new_text = editor_data["editor"].get("1.0", "end-1c")
        path = editor_data["path"]
        backup_path = self._backup_path_for(path)

        try:
            shutil.copy2(path, backup_path)
            path.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save file:\n{exc}")
            return

        editor_data["original_text"] = new_text
        editor_data["dirty"] = False
        self.current_file_text = new_text
        self.current_file_dirty = False
        editor_data["editor"].edit_modified(False)
        self._set_save_file_enabled(False)
        self._update_editor_tab_title(editor_data)
        self.refresh_file_browser()
        self._highlight_syntax()
        self._highlight_search()
        self.status.configure(text=f"Saved {path.name}; backup created as {backup_path.name}.")

    def close_current_file(self):
        editor_data = self._active_editor_data()
        if editor_data:
            self.close_editor_tab(editor_data)

    def show_editor_context_menu(self, event):
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Copy", command=lambda: event.widget.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: event.widget.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Add selection to clipboard", command=self.add_selection)
        menu.add_command(label="Go to definition", command=self.go_to_definition)
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def go_to_definition(self):
        symbol = self.symbol_under_cursor()
        if not symbol:
            self.status.configure(text="Place the cursor on a symbol before using Go to definition.")
            return
        target = self.find_definition_with_repolens(symbol) or self.find_definition_by_scan(symbol)
        if not target:
            self.status.configure(text="Definition not found for {0}.".format(symbol))
            return
        path, line = target
        self.open_file(path)
        self.jump_to_line(line)
        self.status.configure(text="Opened definition for {0}.".format(symbol))

    def symbol_under_cursor(self):
        editor_data = self._active_editor_data()
        editor = editor_data.get("editor") if editor_data else None
        if not editor:
            return ""
        try:
            text = editor.get("insert wordstart", "insert wordend").strip()
        except tk.TclError:
            return ""
        return re.sub(r"[^A-Za-z0-9_.-]+", "", text)

    def find_definition_with_repolens(self, symbol):
        if not getattr(self, "root_folder", None) or not hasattr(self, "_repolens_index_dir"):
            return None
        try:
            service = RepoLensService()
            result = service.search(self._repolens_index_dir(), symbol, limit=8, partial=True)
        except Exception:
            return None
        for item in result.get("results", []) if isinstance(result, dict) else result if isinstance(result, list) else []:
            path = item.get("file") or item.get("path") or item.get("file_path")
            line = item.get("line") or item.get("start_line") or item.get("line_start") or 1
            if path and Path(path).exists():
                try:
                    return Path(path), int(line)
                except (TypeError, ValueError):
                    return Path(path), 1
        return None

    def find_definition_by_scan(self, symbol):
        if not getattr(self, "root_folder", None):
            return None
        patterns = [
            re.compile(r"\b(class|def|function|interface|struct|enum)\s+" + re.escape(symbol) + r"\b"),
            re.compile(r"\b" + re.escape(symbol) + r"\s*[:=(]"),
        ]
        for path in self.root_folder.rglob("*"):
            if not self._is_searchable_file(path):
                continue
            try:
                for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                    if any(pattern.search(line) for pattern in patterns):
                        return path, line_number
            except OSError:
                continue
        return None

    def jump_to_line(self, line):
        editor_data = self._active_editor_data()
        editor = editor_data.get("editor") if editor_data else None
        if not editor:
            return
        index = "{0}.0".format(max(1, int(line or 1)))
        editor.mark_set(tk.INSERT, index)
        editor.tag_remove(tk.SEL, "1.0", tk.END)
        editor.tag_add(tk.SEL, index, "{0}.end".format(max(1, int(line or 1))))
        editor.see(index)
        editor.focus_set()

    def close_editor_tab(self, editor_data):
        if editor_data["dirty"]:
            keep_open = not messagebox.askyesno(
                "Unsaved file changes",
                f"{editor_data['path'].name} has unsaved changes. Close without saving?",
            )
            if keep_open:
                return False

        path = editor_data["path"]
        self.editor_tabs.forget(editor_data["frame"])
        editor_data["frame"].destroy()
        self.open_file_tabs.pop(path, None)
        next_tab = self._active_editor_data()
        if next_tab:
            self._activate_editor_tab(next_tab)
        else:
            self._clear_active_editor()
        self.status.configure(text=f"Closed {path.name}.")
        return True

    def _backup_path_for(self, path):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = path.with_name(f"{path.stem}_OLD_{stamp}{path.suffix}")
        if not base.exists():
            return base

        counter = 2
        while True:
            candidate = path.with_name(f"{path.stem}_OLD_{stamp}_{counter}{path.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1


    def _scroll_editor_y(self, *args, editor=None, line_numbers=None):
        editor = editor or self.editor
        line_numbers = line_numbers or self.line_numbers
        if not editor or not line_numbers:
            return
        editor.yview(*args)
        line_numbers.yview_moveto(editor.yview()[0])

    def _editor_yview(self, first, last, scrollbar=None, editor=None, line_numbers=None):
        scrollbar = scrollbar or self.editor_y_scroll
        if scrollbar:
            scrollbar.set(first, last)
        self._sync_line_numbers(editor, line_numbers)

    def _sync_line_numbers(self, editor=None, line_numbers=None):
        editor = editor or self.editor
        line_numbers = line_numbers or self.line_numbers
        if not editor or not line_numbers:
            return
        line_count = int(editor.index("end-1c").split(".")[0])
        numbers = "\n".join(str(i) for i in range(1, line_count + 1))
        line_numbers.configure(state=tk.NORMAL)
        line_numbers.delete("1.0", tk.END)
        line_numbers.insert("1.0", numbers)
        line_numbers.configure(state=tk.DISABLED)
        line_numbers.yview_moveto(editor.yview()[0])
