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
from src.services.chat_intents import SLASH_COMMANDS, snippet_mention_slug


class ChatInputMixin:
    def chat_input_text(self):
        if not hasattr(self, "chat_input") or self.chat_input_placeholder_visible:
            return ""
        return self.chat_input.get("1.0", "end-1c")

    def update_chat_input_placeholder(self, text=None):
        if text is not None:
            command_hint = getattr(self, "chat_command_hint", "")
            self.chat_input_placeholder = "{0}\n{1}".format(text, command_hint) if command_hint else text
        self._show_chat_input_placeholder()

    def _show_chat_input_placeholder(self):
        if not hasattr(self, "chat_input"):
            return
        current = self.chat_input.get("1.0", "end-1c")
        if current.strip() and not self.chat_input_placeholder_visible:
            return
        self.chat_input.delete("1.0", tk.END)
        self.chat_input.insert("1.0", self.chat_input_placeholder, "placeholder")
        self.chat_input_placeholder_visible = True

    def _hide_chat_input_placeholder(self):
        if not getattr(self, "chat_input_placeholder_visible", False):
            return
        self.chat_input.delete("1.0", tk.END)
        self.chat_input_placeholder_visible = False

    def _on_chat_input_key_press(self, _event=None):
        self._hide_chat_input_placeholder()

    def _on_chat_input_key_release(self, event=None):
        if not self.chat_input.get("1.0", "end-1c").strip():
            self._show_chat_input_placeholder()
            self._hide_chat_completion_menu()
        else:
            self._refresh_chat_completion_menu(event)
        self.refresh_token_count()

    def _on_chat_input_navigation(self, event):
        if getattr(self, "chat_completion_popup", None):
            if event.keysym in {"Up", "Down"}:
                self._move_chat_completion_selection(-1 if event.keysym == "Up" else 1)
                return "break"
            if event.keysym in {"Return", "Tab"}:
                self._accept_chat_completion()
                return "break"
            if event.keysym == "Escape":
                self._hide_chat_completion_menu()
                return "break"
        return None

    def _refresh_chat_completion_menu(self, event=None):
        if event and event.keysym in {
            "Up", "Down", "Return", "Tab", "Escape", "Control_L", "Control_R", "Shift_L", "Shift_R",
        }:
            return
        trigger = self._current_chat_completion_trigger()
        if not trigger:
            self._hide_chat_completion_menu()
            return
        kind, prefix, start_index, end_index = trigger
        options = self._chat_completion_options(kind, prefix)
        if not options:
            self._hide_chat_completion_menu()
            return
        self._show_chat_completion_menu(kind, options, start_index, end_index)

    def _current_chat_completion_trigger(self):
        if not hasattr(self, "chat_input") or self.chat_input_placeholder_visible:
            return None
        insert = self.chat_input.index(tk.INSERT)
        line_start = self.chat_input.index(f"{insert} linestart")
        before = self.chat_input.get(line_start, insert)
        word_start = max(before.rfind(" "), before.rfind("\t"), before.rfind("\n")) + 1
        word = before[word_start:]
        if len(word) < 1 or word[0] not in {"/", "@", "#"}:
            return None
        if any(character in word for character in "([{,;"):
            return None
        start_index = f"{line_start}+{word_start}c"
        if word[0] == "/":
            kind = "slash"
        elif word[0] == "@":
            kind = "mention"
        else:
            kind = "file_reference"
        return kind, word[1:].lower(), start_index, insert

    def _chat_completion_options(self, kind, prefix):
        if kind == "slash":
            options = []
            for command, data in SLASH_COMMANDS.items():
                if command.startswith(prefix):
                    options.append(
                        {
                            "insert": "/" + command + " ",
                            "label": "/" + command,
                            "detail": data["description"],
                        }
                    )
            return options

        if kind == "file_reference":
            return self._chat_file_reference_options(prefix)

        options = []
        seen = set()
        for snippet in self.snippets_for_context(selected_only=False):
            if snippet.get("card_type") == "card":
                continue
            fallback = str(snippet.get("id") or "snippet")
            slug = snippet_mention_slug(str(snippet.get("description", "")), fallback)
            if prefix and not slug.lower().startswith(prefix):
                continue
            if slug in seen:
                continue
            seen.add(slug)
            description = str(snippet.get("description", "")).strip() or self._relative(snippet.get("source", ""))
            options.append(
                {
                    "insert": "@" + slug + " ",
                    "label": "@" + slug,
                    "detail": description,
                    "snippet": snippet,
                }
            )
        return options[:12]

    def _chat_file_reference_options(self, prefix):
        options = []
        normalized_prefix = (prefix or "").lower()

        if "filetree".startswith(normalized_prefix):
            options.append(
                {
                    "insert": "#filetree ",
                    "label": "#filetree",
                    "detail": "Opened folder tree",
                }
            )

        editor_data = self._active_editor_data() if hasattr(self, "_active_editor_data") else None
        open_editors = list(getattr(self, "open_file_tabs", {}).values())

        if editor_data:
            path = Path(editor_data["path"])
            display = path.name
            file_token = self._chat_visible_file_token(path)
            if not normalized_prefix or "file".startswith(normalized_prefix) or display.lower().startswith(normalized_prefix):
                options.append(
                    {
                        "insert": file_token + " ",
                        "label": file_token,
                        "detail": "Focused file",
                        "file_path": path,
                    }
                )

        for data in open_editors:
            selection = self._chat_selection_reference(data)
            if not selection:
                continue
            path = Path(data["path"])
            display = path.name
            start_line, end_line, _selected = selection
            line_token = self._chat_visible_file_token(path, start_line, end_line)
            if (
                not normalized_prefix
                or "selection".startswith(normalized_prefix)
                or display.lower().startswith(normalized_prefix)
            ):
                options.append(
                    {
                        "insert": line_token + " ",
                        "label": line_token,
                        "detail": "Selected lines" if data is editor_data else "Selected lines in open tab",
                        "file_path": path,
                        "start_line": start_line,
                        "end_line": end_line,
                    },
                )
        return options[:12]

    def _chat_visible_file_token(self, path, start_line=None, end_line=None):
        token = "#file:'{0}'".format(Path(path).name.replace("'", "\\'"))
        if start_line and end_line:
            token += ":{0}-{1}".format(start_line, end_line)
        return token

    def _chat_selection_reference(self, editor_data):
        live_selection = self._chat_active_selection_reference(editor_data)
        if live_selection:
            return live_selection
        start_line = editor_data.get("persistent_selection_start")
        end_line = editor_data.get("persistent_selection_end")
        if not start_line or not end_line:
            return None
        return start_line, end_line, editor_data.get("persistent_selection_text", "")

    def _chat_active_selection_reference(self, editor_data):
        editor = editor_data.get("editor")
        if not editor:
            return None
        try:
            start_index = editor.index(tk.SEL_FIRST)
            end_index = editor.index(tk.SEL_LAST)
            selected = editor.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            return None
        if not selected.strip():
            return None
        start_line = self._line_from_text_index(start_index)
        end_line = self._line_from_text_index(end_index)
        if str(end_index).split(".", 1)[1] == "0" and end_line and end_line > start_line:
            end_line -= 1
        return start_line, end_line, selected

    def _show_chat_completion_menu(self, kind, options, start_index, end_index):
        self.chat_completion_kind = kind
        self.chat_completion_options = options
        self.chat_completion_range = (start_index, end_index)
        if not getattr(self, "chat_completion_popup", None):
            popup = tk.Toplevel(self)
            popup.withdraw()
            popup.overrideredirect(True)
            popup.configure(bg=self.colors["panel2"])
            listbox = tk.Listbox(
                popup,
                height=min(8, len(options)),
                bg=self.colors["panel2"],
                fg=self.colors["text"],
                selectbackground=self.colors["accent"],
                selectforeground="#ffffff",
                relief=tk.FLAT,
                borderwidth=0,
                highlightthickness=1,
                highlightbackground=self.colors["line"],
                font=("Segoe UI", 9),
                activestyle="none",
                width=42,
            )
            listbox.pack(fill=tk.BOTH, expand=True)
            listbox.bind("<ButtonRelease-1>", lambda _event: self._accept_chat_completion())
            self.chat_completion_popup = popup
            self.chat_completion_listbox = listbox
        listbox = self.chat_completion_listbox
        listbox.delete(0, tk.END)
        listbox.configure(height=min(8, len(options)))
        for option in options:
            detail = option.get("detail", "")
            label = option["label"] if not detail else f"{option['label']} - {detail}"
            listbox.insert(tk.END, label)
        listbox.selection_clear(0, tk.END)
        listbox.selection_set(0)
        listbox.activate(0)
        x, y, _width, height = self.chat_input.bbox(tk.INSERT) or (0, 0, 0, 18)
        root_x = self.chat_input.winfo_rootx() + x
        root_y = self.chat_input.winfo_rooty() + y + height + 4
        self.chat_completion_popup.geometry(f"+{root_x}+{root_y}")
        self.chat_completion_popup.deiconify()
        self.chat_completion_popup.lift()

    def _move_chat_completion_selection(self, delta):
        listbox = getattr(self, "chat_completion_listbox", None)
        if not listbox:
            return
        size = listbox.size()
        if not size:
            return
        current = listbox.curselection()
        index = current[0] if current else 0
        index = max(0, min(size - 1, index + delta))
        listbox.selection_clear(0, tk.END)
        listbox.selection_set(index)
        listbox.activate(index)
        listbox.see(index)

    def _accept_chat_completion(self):
        listbox = getattr(self, "chat_completion_listbox", None)
        options = getattr(self, "chat_completion_options", [])
        if not listbox or not options:
            return
        selection = listbox.curselection()
        index = selection[0] if selection else 0
        if index < 0 or index >= len(options):
            return
        start_index, end_index = self.chat_completion_range
        option = options[index]
        insert_text = option["insert"]
        self.chat_input.delete(start_index, end_index)
        self.chat_input.insert(start_index, insert_text)
        if self.chat_completion_kind == "file_reference" and option.get("file_path"):
            registry = getattr(self, "chat_file_reference_registry", None)
            if registry is None:
                registry = {}
                self.chat_file_reference_registry = registry
            registry[insert_text.strip()] = {
                "path": os.fspath(option.get("file_path")),
                "start_line": option.get("start_line"),
                "end_line": option.get("end_line"),
            }
        self._hide_chat_completion_menu()
        self.chat_input.focus_set()
        self.refresh_token_count()

    def _hide_chat_completion_menu(self):
        popup = getattr(self, "chat_completion_popup", None)
        if popup:
            popup.destroy()
        self.chat_completion_popup = None
        self.chat_completion_listbox = None
        self.chat_completion_options = []
        self.chat_completion_range = None

