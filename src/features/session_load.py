import copy
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


class SessionLoadMixin:
    def load_session_data(self, session):
        self.current_session_info = dict(session.get("session_info", {}) or {})
        if hasattr(self, "session_manager") and getattr(self, "current_session_path", None):
            session_dir = self.session_manager.session_dir_from_path(self.current_session_path)
            database_dir = session_dir / "database"
            self.current_session_info.setdefault("session_dir", os.fspath(session_dir))
            self.current_session_info.setdefault("database_dir", os.fspath(database_dir))
            self.current_session_info.setdefault("include_file", os.fspath(database_dir / "include.txt"))
            self.current_session_info.setdefault("exclude_file", os.fspath(database_dir / "exclude.txt"))
            self.current_session_info.setdefault("repolens_executable", os.fspath(database_dir / "repolens.exe"))
            self.current_session_info.setdefault("repolens_enabled", True)
        session_settings = session.get("settings", {})
        current_global_settings = copy.deepcopy(getattr(self, "settings", {}) or {})
        if session_settings:
            self.merge_settings(session_settings)
            self.merge_settings(current_global_settings)
        else:
            self.merge_settings({})
        root = session.get("root_folder") or ""
        self.root_folder = Path(root) if root else None
        if not self.current_session_info.get("repo_path") and self.root_folder:
            self.current_session_info["repo_path"] = os.fspath(self.root_folder)
        self.folder_label.configure(text=os.fspath(self.root_folder) if self.root_folder else "No folder selected")
        self.current_file = None
        self.current_file_text = ""
        self.current_file_dirty = False
        self.close_all_editor_tabs(confirm=False)
        self._set_save_file_enabled(False)
        if self.root_folder and self.root_folder.exists():
            self.refresh_file_browser()
        else:
            self.file_items.clear()
            self.file_tree.delete(*self.file_tree.get_children())

        self.clear_search_results()
        self.search_results.clear()
        self.search_match_positions.clear()

        def deserialize_snippet(snippet_data):
            return {
                "id": snippet_data.get("id", ""),
                "description": snippet_data.get("description", ""),
                "source": Path(snippet_data.get("source", "")),
                "text": snippet_data.get("text", ""),
                "selected": bool(snippet_data.get("selected", False)),
                "start_line": snippet_data.get("start_line"),
                "end_line": snippet_data.get("end_line"),
                "reason": snippet_data.get("reason", ""),
                "card_type": snippet_data.get("card_type", ""),
                "generated_context": bool(snippet_data.get("generated_context", False)),
                "collapsed": bool(snippet_data.get("collapsed", False)),
                "created_at": snippet_data.get("created_at", ""),
                "updated_at": snippet_data.get("updated_at", ""),
            }

        self.clear_snippets(show_status=False)
        clipboard_data = session.get("snippet_clipboards") or []
        if clipboard_data:
            self.snippet_clipboards = []
            for index, clipboard in enumerate(clipboard_data):
                clipboard_id = str(clipboard.get("id", "")).strip()
                existing_clipboard_ids = {
                    str(existing.get("id"))
                    for existing in self.snippet_clipboards
                    if existing.get("id")
                }
                if not self.is_snippet_id(clipboard_id) or clipboard_id in existing_clipboard_ids:
                    clipboard_id = self.create_clipboard_id()
                self.snippet_clipboards.append(
                    {
                        "id": clipboard_id,
                        "name": clipboard.get("name", f"Snippets {index + 1}"),
                        "category": clipboard.get("category", "General"),
                        "snippets": [
                            deserialize_snippet(snippet_data)
                            for snippet_data in clipboard.get("snippets", [])
                        ],
                    }
                )
        else:
            self.snippet_clipboards = [
                {
                    "id": self.create_clipboard_id(),
                    "name": "Snippets 1",
                    "category": "General",
                    "snippets": [
                        deserialize_snippet(snippet_data)
                        for snippet_data in session.get("snippets", [])
                    ],
                }
            ]

        if not self.snippet_clipboards:
            self.snippet_clipboards = [self.create_snippet_clipboard("Snippets 1")]

        self.active_snippet_clipboard_index = min(
            max(0, int(session.get("active_snippet_clipboard", 0) or 0)),
            len(self.snippet_clipboards) - 1,
        )
        self.snippets = self.snippet_clipboards[self.active_snippet_clipboard_index]["snippets"]
        for clipboard in self.snippet_clipboards:
            for snippet in clipboard.get("snippets", []):
                self.ensure_created_at(snippet)
                self.ensure_snippet_id(snippet)
        self.render_active_snippet_clipboard()
        self.refresh_snippet_clipboard_selector()
        self.refresh_token_count()
        chat = session.get("chat", {})
        if not session_settings and chat.get("api_url"):
            self.migrate_legacy_chat_api_url(chat.get("api_url", ""))
        self.prompt_csv_path = chat.get("prompt_csv_path", "")
        if self.prompt_csv_path:
            self.set_nested_setting(self.settings, "prompt_presets.csv_path", self.prompt_csv_path)
        self.prompt_presets = chat.get("prompt_presets", [])
        self.refresh_prompt_preset_dropdown()
        selected_prompt = int(chat.get("selected_prompt_preset", -1))
        if hasattr(self, "prompt_combo") and 0 <= selected_prompt < len(self.prompt_presets):
            self.prompt_combo.current(selected_prompt)
        if hasattr(self, "reasoning_enabled_var"):
            self.reasoning_enabled_var.set(bool(chat.get("reasoning_enabled", False)))

        threads = chat.get("threads") or [{"title": "Chat 1", "messages": []}]
        self.chat_threads = [
            {
                "title": str(thread.get("title", f"Chat {index + 1}")),
                "category": str(thread.get("category", "General") or "General"),
                "created_at": thread.get("created_at", ""),
                "updated_at": thread.get("updated_at", ""),
                "messages": [
                    {
                        "role": message.get("role", "user"),
                        "content": message.get("content", ""),
                        "prompt_content": message.get("prompt_content", ""),
                        "intent": message.get("intent", {}),
                        "created_at": message.get("created_at", ""),
                    }
                    for message in thread.get("messages", [])
                    if message.get("role") in {"user", "assistant"}
                ],
            }
            for index, thread in enumerate(threads)
        ]
        for thread in self.chat_threads:
            self.ensure_created_at(thread)
            for message in thread["messages"]:
                self.ensure_created_at(message)
        if not self.chat_threads:
            self.chat_threads = [{"title": "Chat 1", "messages": []}]
        self.current_chat_index = min(max(0, int(chat.get("current_thread", 0))), len(self.chat_threads) - 1)
        self.chat_messages = self.chat_threads[self.current_chat_index]["messages"]
        self.refresh_chat_thread_selector()
        self.render_current_chat()

        open_files = [Path(path) for path in session.get("open_files", []) if path]
        current_file = session.get("current_file") or ""
        if current_file:
            current_path = Path(current_file)
            if current_path not in open_files:
                open_files.append(current_path)
        for open_path in open_files:
            if open_path.exists():
                self.open_file(open_path)
        if current_file and Path(current_file).exists():
            self.open_file(Path(current_file))
        if hasattr(self, "refresh_workspace_header"):
            self.refresh_workspace_header()
