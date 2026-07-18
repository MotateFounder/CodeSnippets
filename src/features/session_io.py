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


class SessionIOMixin:
    def save_session(self):
        path = getattr(self, "current_session_path", None)
        if not path:
            session_dir = self.session_manager.sessions_dir if hasattr(self, "session_manager") else Path.cwd()
            Path(session_dir).mkdir(parents=True, exist_ok=True)
            path = filedialog.asksaveasfilename(
                title="Save full session",
                defaultextension=".json",
                initialdir=os.fspath(session_dir),
                filetypes=[("CodeSnippet sessions", "*.json"), ("All files", "*.*")],
            )
            if not path:
                return

        session = self.session_payload(path)

        try:
            self.write_session_payload(path, session)
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save session:\n{exc}")
            return
        self.current_session_path = Path(path)
        self.current_session_info = session.get("session_info", {})
        self.start_session_autosave()
        self.status.configure(text=f"Session saved to {self.current_session_info.get('name', Path(path).name)}.")

    def session_payload(self, path):
        def serialize_snippet(snippet):
            return {
                "id": snippet.get("id", ""),
                "description": snippet.get("description", ""),
                "source": os.fspath(snippet["source"]),
                "text": snippet["text"],
                "selected": bool(snippet.get("selected", False)),
                "start_line": snippet.get("start_line"),
                "end_line": snippet.get("end_line"),
                "reason": snippet.get("reason", ""),
                "card_type": snippet.get("card_type", ""),
                "generated_context": bool(snippet.get("generated_context", False)),
                "collapsed": bool(snippet.get("collapsed", False)),
                "created_at": snippet.get("created_at", ""),
                "updated_at": snippet.get("updated_at", ""),
            }

        session_info = dict(getattr(self, "current_session_info", {}) or {})
        if not session_info.get("name"):
            session_info["name"] = Path(path).stem
        if not session_info.get("repo_path"):
            session_info["repo_path"] = os.fspath(self.root_folder) if self.root_folder else ""
        if hasattr(self, "session_manager") and path:
            session_dir = self.session_manager.session_dir_from_path(path)
            database_dir = session_dir / "database"
            session_info.setdefault("session_dir", os.fspath(session_dir))
            session_info.setdefault("database_dir", os.fspath(database_dir))
            session_info.setdefault("include_file", os.fspath(database_dir / "include.txt"))
            session_info.setdefault("exclude_file", os.fspath(database_dir / "exclude.txt"))
            session_info.setdefault("repolens_executable", os.fspath(database_dir / "repolens.exe"))
            session_info.setdefault("repolens_enabled", True)

        def serialize_chat_message(message):
            serialized = {
                "role": message.get("role", "user"),
                "content": message.get("content", ""),
                "created_at": message.get("created_at", ""),
            }
            if message.get("prompt_content"):
                serialized["prompt_content"] = message.get("prompt_content", "")
            if message.get("intent"):
                serialized["intent"] = message.get("intent")
            return serialized

        def serialize_chat_thread(thread, index):
            messages = list(thread.get("messages", []))
            pending = getattr(self, "pending_user_card", None)
            if pending and index == self.current_chat_index:
                pending_message = pending.get("message")
                if pending_message and pending_message not in messages:
                    messages.append(pending_message)
            return {
                "title": thread.get("title", f"Chat {index + 1}"),
                "category": thread.get("category", "General"),
                "created_at": thread.get("created_at", ""),
                "updated_at": thread.get("updated_at", ""),
                "messages": [
                    serialize_chat_message(message)
                    for message in messages
                    if message.get("role") in {"user", "assistant"}
                ],
            }

        session = {
            "version": 2,
            "session_info": session_info,
            "settings": self.settings,
            "root_folder": os.fspath(self.root_folder) if self.root_folder else "",
            "current_file": os.fspath(self.current_file) if self.current_file else "",
            "open_files": [
                os.fspath(editor_data["path"])
                for editor_data in self.open_file_tabs.values()
            ],
            "active_snippet_clipboard": self.active_snippet_clipboard_index,
            "snippet_clipboards": [
                {
                    "id": clipboard.get("id", ""),
                    "name": clipboard.get("name", f"Snippets {index + 1}"),
                    "category": clipboard.get("category", "General"),
                    "snippets": [
                        serialize_snippet(snippet)
                        for snippet in clipboard.get("snippets", [])
                    ],
                }
                for index, clipboard in enumerate(self.snippet_clipboards)
            ],
            "snippets": [
                serialize_snippet(snippet)
                for snippet in self.snippets
            ],
            "chat": {
                "current_thread": self.current_chat_index,
                "threads": [
                    serialize_chat_thread(thread, index)
                    for index, thread in enumerate(self.chat_threads)
                ],
                "prompt_csv_path": self.prompt_csv_path,
                "prompt_presets": self.prompt_presets,
                "selected_prompt_preset": self.prompt_combo.current() if hasattr(self, "prompt_combo") else -1,
                "reasoning_enabled": bool(
                    hasattr(self, "reasoning_enabled_var") and self.reasoning_enabled_var.get()
                ),
            },
        }
        if hasattr(self, "session_manager"):
            self.session_manager.update_session_metadata(session, path)
        return session

    def write_session_payload(self, path, session):
        lock = getattr(self, "session_save_lock", None)
        if lock:
            with lock:
                self._write_session_payload_unlocked(path, session)
            return
        self._write_session_payload_unlocked(path, session)

    def _write_session_payload_unlocked(self, path, session):
        if hasattr(self, "session_manager"):
            self.session_manager.save_session(path, session)
        else:
            Path(path).write_text(json.dumps(session, indent=2), encoding="utf-8")

    def start_session_autosave(self):
        if getattr(self, "autosave_after_id", None):
            return
        self.autosave_after_id = self.after(self.session_autosave_interval_ms(), self.autosave_session)

    def stop_session_autosave(self):
        after_id = getattr(self, "autosave_after_id", None)
        if not after_id:
            return
        try:
            self.after_cancel(after_id)
        except tk.TclError:
            pass
        self.autosave_after_id = None

    def session_autosave_interval_ms(self):
        return 15000

    def autosave_session(self):
        self.autosave_after_id = None
        path = getattr(self, "current_session_path", None)
        if not path:
            self.start_session_autosave()
            return
        try:
            session = self.session_payload(path)
        except (OSError, tk.TclError, KeyError, TypeError, ValueError) as exc:
            self.status.configure(text=f"Autosave skipped: {exc}")
            self.start_session_autosave()
            return

        def worker(save_path, payload):
            try:
                self.write_session_payload(save_path, payload)
            except OSError as exc:
                self.post_ui(lambda error=str(exc): self.status.configure(text=f"Autosave failed: {error}"))

        threading.Thread(target=worker, args=(Path(path), session), daemon=True).start()
        self.current_session_info = session.get("session_info", {})
        self.start_session_autosave()

    def import_session(self):
        if not self.confirm_discard_unsaved():
            return

        session_dir = self.session_manager.sessions_dir if hasattr(self, "session_manager") else Path.cwd()
        Path(session_dir).mkdir(parents=True, exist_ok=True)
        path = filedialog.askopenfilename(
            title="Import full session",
            initialdir=os.fspath(session_dir),
            filetypes=[("CodeSnippet sessions", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            session = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Import failed", f"Could not import session:\n{exc}")
            return

        self.current_session_path = Path(path)
        self.load_session_data(session)
        self.start_session_autosave()
        self.status.configure(text=f"Session imported from {Path(path).name}.")
