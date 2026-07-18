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


class EditorTabStateMixin:
    def _active_editor_data(self):
        if not hasattr(self, "editor_tabs"):
            return None
        selected = self.editor_tabs.select()
        if not selected:
            return None
        for editor_data in self.open_file_tabs.values():
            if str(editor_data["frame"]) == selected:
                return editor_data
        return None

    def _activate_editor_tab(self, editor_data):
        if editor_data.get("preview_type"):
            self.current_file = editor_data["path"]
            self.current_file_text = ""
            self.current_file_dirty = False
            self.editor = None
            self.line_numbers = None
            self.editor_y_scroll = None
            self.file_label.configure(text=self._editor_tab_title(editor_data).upper())
            self._set_save_file_enabled(False)
            self._set_close_file_enabled(True)
            return
        self.current_file = editor_data["path"]
        self.current_file_text = editor_data["original_text"]
        self.current_file_dirty = editor_data["dirty"]
        self.editor = editor_data["editor"]
        self.line_numbers = editor_data["line_numbers"]
        self.editor_y_scroll = editor_data["editor_y_scroll"]
        label = self._editor_tab_title(editor_data)
        self.file_label.configure(text=label.upper())
        self._set_save_file_enabled(editor_data["dirty"])
        self._set_close_file_enabled(True)
        self._sync_line_numbers()
        self._highlight_syntax()
        self._highlight_search()

    def _on_editor_tab_changed(self, _event=None):
        editor_data = self._active_editor_data()
        if not editor_data:
            self._clear_active_editor()
            return
        self._activate_editor_tab(editor_data)

    def _editor_tab_title(self, editor_data):
        name = editor_data["path"].name
        return f"* {name}" if editor_data["dirty"] else name

    def _update_editor_tab_title(self, editor_data):
        self.editor_tabs.tab(editor_data["frame"], text=self._editor_tab_title(editor_data))
        if editor_data is self._active_editor_data():
            self.file_label.configure(text=self._editor_tab_title(editor_data).upper())

    def _clear_active_editor(self):
        self.current_file = None
        self.current_file_text = ""
        self.current_file_dirty = False
        self.editor = None
        self.line_numbers = None
        self.editor_y_scroll = None
        self.file_label.configure(text="OPEN SELECTED FILE")
        self._set_save_file_enabled(False)
        self._set_close_file_enabled(False)
