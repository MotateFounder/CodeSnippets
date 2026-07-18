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
from tkinter import filedialog, messagebox, simpledialog, ttk

from src.config.constants import MAX_SEARCH_BYTES, TEXT_EXTENSIONS
from src.services.repoLens.service import (
    RepoLensService,
    context_item_count,
    extract_symbols_from_snippet,
    format_repolens_context,
)
from src.services.smart_context import SmartContextRetriever
from src.services.context_modes import context_mode_overrides


class SnippetCardsMixin:
    def add_blank_card(self):
        snippet = {
            "id": self.create_snippet_id(),
            "description": "",
            "source": Path("Card"),
            "text": "",
            "selected": False,
            "start_line": None,
            "end_line": None,
            "reason": "User-created clipboard card.",
            "card_type": "card",
            "created_at": self.current_timestamp(),
        }
        self.snippets.append(snippet)
        self._render_snippet(snippet)
        if snippet.get("body_widget"):
            snippet["body_widget"].focus_set()
        self.refresh_token_count()
        self.status.configure(text="New card added to the temporary clipboard.")

    def add_snippet_clipboard(self):
        clipboard = self.create_snippet_clipboard()
        self.snippet_clipboards.append(clipboard)
        self.active_snippet_clipboard_index = len(self.snippet_clipboards) - 1
        self.snippets = clipboard["snippets"]
        self.render_active_snippet_clipboard()
        self.refresh_snippet_clipboard_selector()
        self.refresh_token_count()
        self.status.configure(text=f"Created {clipboard['name']}.")

    def create_snippet_clipboard(self, name=None, category=None):
        number = len(getattr(self, "snippet_clipboards", [])) + 1
        return {
            "id": self.create_clipboard_id(),
            "name": name or f"Snippets {number}",
            "category": category or self.default_snippet_clipboard_category(),
            "snippets": [],
        }

    def switch_snippet_clipboard(self, _event=None):
        if not hasattr(self, "snippet_clipboard_combo"):
            return
        selected = self.snippet_clipboard_combo.current()
        if selected < 0 or selected >= len(self.snippet_clipboards):
            return
        self.active_snippet_clipboard_index = selected
        self.snippets = self.snippet_clipboards[selected]["snippets"]
        self.render_active_snippet_clipboard()
        self.refresh_token_count()
        self.status.configure(text=f"Switched to {self.snippet_clipboards[selected]['name']}.")

    def refresh_snippet_clipboard_selector(self):
        if not hasattr(self, "snippet_clipboards"):
            return
        for clipboard in self.snippet_clipboards:
            clipboard.setdefault("category", self.default_snippet_clipboard_category())
        if not hasattr(self, "snippet_clipboard_combo"):
            self.refresh_snippet_clipboard_status()
            return
        values = [
            self.snippet_clipboard_label(clipboard, index)
            for index, clipboard in enumerate(self.snippet_clipboards)
        ]
        self.snippet_clipboard_combo.configure(
            values=values,
            state="readonly" if len(values) > 1 else "disabled",
        )
        active = min(self.active_snippet_clipboard_index, max(0, len(values) - 1))
        self.active_snippet_clipboard_index = active
        if values:
            self.snippet_clipboard_combo.current(active)
            self.snippet_clipboard_var.set(values[active])
        self.refresh_snippet_clipboard_status()

    def snippet_clipboard_label(self, clipboard, index):
        return "{0} / {1} - {2}".format(
            clipboard.get("category") or self.default_snippet_clipboard_category(),
            clipboard.get("name") or "Snippets " + str(index + 1),
            clipboard.get("id", ""),
        )

    def refresh_snippet_clipboard_status(self):
        if not hasattr(self, "snippet_clipboard_status_var"):
            return
        clipboard = self.current_snippet_clipboard()
        if not clipboard:
            self.snippet_clipboard_status_var.set("No snippets set")
            return
        self.snippet_clipboard_status_var.set(
            "{0} / {1}".format(
                clipboard.get("category") or self.default_snippet_clipboard_category(),
                clipboard.get("name") or "Untitled snippets",
            )
        )

    def current_snippet_clipboard(self):
        clipboards = getattr(self, "snippet_clipboards", [])
        index = getattr(self, "active_snippet_clipboard_index", 0)
        if 0 <= index < len(clipboards):
            return clipboards[index]
        return None

    def default_snippet_clipboard_category(self):
        return "General"

    def safe_snippet_clipboard_category(self, category):
        raw = str(category or self.default_snippet_clipboard_category()).strip().replace("\\", "/")
        parts = []
        for part in raw.split("/"):
            clean = "".join(char if char.isalnum() or char in "._- " else "_" for char in part).strip(" ._")
            if clean:
                parts.append(clean)
        return "/".join(parts) if parts else self.default_snippet_clipboard_category()

    def snippet_clipboard_categories(self):
        categories = {self.default_snippet_clipboard_category()}
        for clipboard in getattr(self, "snippet_clipboards", []):
            categories.add(clipboard.get("category") or self.default_snippet_clipboard_category())
        return ["All"] + sorted(categories)

    def snippet_clipboards_for_category(self, category):
        selected_category = category or self.default_snippet_clipboard_category()
        if selected_category == "All":
            return list(enumerate(getattr(self, "snippet_clipboards", [])))
        return [
            (index, clipboard)
            for index, clipboard in enumerate(getattr(self, "snippet_clipboards", []))
            if (clipboard.get("category") or self.default_snippet_clipboard_category()) == selected_category
        ]

    def open_snippet_clipboard_manager(self):
        existing = getattr(self, "snippet_manager_window", None)
        try:
            if existing and existing.winfo_exists():
                existing.lift()
                existing.focus_set()
                return
        except tk.TclError:
            pass

        window = tk.Toplevel(self)
        window.title("Snippets Manager")
        window.geometry("900x600")
        window.minsize(720, 480)
        window.configure(bg=self.colors["panel"])
        window.transient(self)
        self.snippet_manager_window = window

        def on_close():
            self.snippet_manager_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", on_close)

        body = tk.Frame(window, bg=self.colors["panel"], padx=16, pady=14)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(2, weight=1)

        header = tk.Frame(body, bg=self.colors["panel"])
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="Snippets Manager",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI", 14, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        count_label = tk.Label(
            header,
            text="",
            bg=self.colors["panel"],
            fg=self.colors["muted"],
            font=("Segoe UI", 9),
            anchor="e",
        )
        count_label.grid(row=0, column=1, sticky="e")

        search_var = tk.StringVar()
        search = tk.Entry(
            body,
            textvariable=search_var,
            bg=self.colors["editor"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            highlightcolor=self.colors["accent"],
            font=("Segoe UI", 10),
        )
        search.grid(row=1, column=0, sticky="ew", pady=(0, 8), ipady=5)
        tk.Label(
            body,
            text="Details",
            bg=self.colors["panel"],
            fg=self.colors["muted"],
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).grid(row=1, column=1, sticky="ew", padx=(14, 0), pady=(0, 8))

        list_frame = tk.Frame(body, bg=self.colors["panel"])
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        listbox = tk.Listbox(
            list_frame,
            bg=self.colors["editor"],
            fg=self.colors["text"],
            selectbackground=self.colors["accent"],
            selectforeground=self.readable_text_on(self.colors["accent"]) if hasattr(self, "readable_text_on") else "#ffffff",
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            font=("Segoe UI", 10),
            activestyle="none",
        )
        listbox.grid(row=0, column=0, sticky="nsew")
        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        listbox.configure(yscrollcommand=list_scroll.set)

        detail = tk.Frame(body, bg=self.colors["panel2"], highlightbackground=self.colors["line"], highlightthickness=1)
        detail.grid(row=2, column=1, sticky="nsew", padx=(14, 0))
        detail.columnconfigure(0, weight=1)
        name_var = tk.StringVar()
        category_detail_var = tk.StringVar()
        snippet_count_var = tk.StringVar()
        source_count_var = tk.StringVar()
        selected_count_var = tk.StringVar()
        updated_var = tk.StringVar()
        preview_var = tk.StringVar()

        for row, (label, variable) in enumerate(
            [
                ("Name", name_var),
                ("Category", category_detail_var),
                ("Snippets", snippet_count_var),
                ("Sources", source_count_var),
                ("Selected", selected_count_var),
                ("Latest Activity", updated_var),
                ("Preview", preview_var),
            ]
        ):
            tk.Label(
                detail,
                text=label,
                bg=self.colors["panel2"],
                fg=self.colors["muted"],
                anchor="w",
                font=("Segoe UI", 8, "bold"),
                padx=10,
                pady=1,
            ).grid(row=row * 2, column=0, sticky="ew")
            tk.Label(
                detail,
                textvariable=variable,
                bg=self.colors["panel2"],
                fg=self.colors["text"],
                anchor="nw",
                justify=tk.LEFT,
                wraplength=280,
                font=("Segoe UI", 10 if row == 0 else 9, "bold" if row == 0 else "normal"),
                padx=10,
                pady=2,
            ).grid(row=row * 2 + 1, column=0, sticky="ew", pady=(0, 4))

        clipboard_rows = []

        def clipboard_category(clipboard):
            return clipboard.get("category") or self.default_snippet_clipboard_category()

        def snippet_source(snippet):
            source = snippet.get("source", "")
            try:
                return self._relative(source)
            except Exception:
                return str(source or "Card")

        def snippet_preview(clipboard):
            snippets = clipboard.get("snippets", [])
            for snippet in snippets:
                description = str(snippet.get("description", "")).strip()
                if description:
                    return description[:220] + ("..." if len(description) > 220 else "")
            for snippet in snippets:
                text = " ".join(str(snippet.get("text", "")).split())
                if text:
                    return text[:220] + ("..." if len(text) > 220 else "")
            return "No snippets yet."

        def clipboard_latest_activity(clipboard):
            values = [
                str(snippet.get("updated_at") or snippet.get("created_at") or "").strip()
                for snippet in clipboard.get("snippets", [])
                if str(snippet.get("updated_at") or snippet.get("created_at") or "").strip()
            ]
            if not values:
                return "No snippet timestamps"
            latest = max(values)
            return self.display_timestamp(latest) if hasattr(self, "display_timestamp") else latest

        def clipboard_label(clipboard, index):
            name = clipboard.get("name") or "Snippets {0}".format(index + 1)
            count = len(clipboard.get("snippets", []))
            selected = sum(1 for snippet in clipboard.get("snippets", []) if snippet.get("selected"))
            active = "  *" if index == self.active_snippet_clipboard_index else ""
            return "   {0}{1}    {2} snippet{3}  {4} selected".format(
                name,
                active,
                count,
                "" if count == 1 else "s",
                selected,
            )

        def clipboard_matches(clipboard, needle):
            if not needle:
                return True
            parts = [
                clipboard.get("name", ""),
                clipboard_category(clipboard),
                snippet_preview(clipboard),
            ]
            for snippet in clipboard.get("snippets", []):
                parts.extend(
                    [
                        str(snippet.get("description", "")),
                        str(snippet.get("text", "")),
                        snippet_source(snippet),
                    ]
                )
            return needle in " ".join(parts).lower()

        def refresh_clipboards(_event=None):
            previous_index = selected_clipboard_index(default=None)
            listbox.delete(0, tk.END)
            clipboard_rows.clear()
            needle = search_var.get().strip().lower()
            grouped = {}
            for index, clipboard in enumerate(getattr(self, "snippet_clipboards", [])):
                if not clipboard_matches(clipboard, needle):
                    continue
                grouped.setdefault(clipboard_category(clipboard), []).append((index, clipboard))
            for category in sorted(grouped, key=lambda value: value.lower()):
                row_index = listbox.size()
                clipboard_rows.append({"type": "header", "category": category, "clipboard_index": None})
                listbox.insert(tk.END, category)
                try:
                    listbox.itemconfig(row_index, foreground=self.colors["muted"], background=self.colors["panel2"])
                except tk.TclError:
                    pass
                for index, clipboard in grouped[category]:
                    clipboard_rows.append({"type": "clipboard", "category": category, "clipboard_index": index})
                    listbox.insert(tk.END, clipboard_label(clipboard, index))
            count_label.configure(
                text="{0} set{1}, {2} snippet{3}".format(
                    len(getattr(self, "snippet_clipboards", [])),
                    "" if len(getattr(self, "snippet_clipboards", [])) == 1 else "s",
                    sum(len(clipboard.get("snippets", [])) for clipboard in getattr(self, "snippet_clipboards", [])),
                    "" if sum(len(clipboard.get("snippets", [])) for clipboard in getattr(self, "snippet_clipboards", [])) == 1 else "s",
                )
            )
            visible_clipboards = [row["clipboard_index"] for row in clipboard_rows if row["type"] == "clipboard"]
            if visible_clipboards:
                target = previous_index if previous_index in visible_clipboards else self.active_snippet_clipboard_index
                if target not in visible_clipboards:
                    target = visible_clipboards[0]
                row_index = next(
                    row
                    for row, value in enumerate(clipboard_rows)
                    if value["type"] == "clipboard" and value["clipboard_index"] == target
                )
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(row_index)
                listbox.activate(row_index)
                listbox.see(row_index)
            update_details()

        def selected_clipboard_index(default=None):
            selection = listbox.curselection()
            if selection and selection[0] < len(clipboard_rows):
                row = clipboard_rows[selection[0]]
                if row["type"] == "clipboard":
                    return row["clipboard_index"]
            return self.active_snippet_clipboard_index if default is None else default

        def select_clipboard_row_at(index):
            if not clipboard_rows:
                return
            index = max(0, min(index, len(clipboard_rows) - 1))
            if clipboard_rows[index]["type"] == "header":
                for candidate in range(index + 1, len(clipboard_rows)):
                    if clipboard_rows[candidate]["type"] == "clipboard":
                        index = candidate
                        break
                else:
                    for candidate in range(index - 1, -1, -1):
                        if clipboard_rows[candidate]["type"] == "clipboard":
                            index = candidate
                            break
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(index)
            listbox.activate(index)
            listbox.see(index)
            update_details()

        def update_details(_event=None):
            index = selected_clipboard_index(default=None)
            if index is None or not (0 <= index < len(getattr(self, "snippet_clipboards", []))):
                name_var.set("No snippets set selected")
                category_detail_var.set("")
                snippet_count_var.set("")
                source_count_var.set("")
                selected_count_var.set("")
                updated_var.set("")
                preview_var.set("")
                return
            clipboard = self.snippet_clipboards[index]
            snippets = clipboard.get("snippets", [])
            sources = {snippet_source(snippet) for snippet in snippets}
            name_var.set(clipboard.get("name") or "Snippets {0}".format(index + 1))
            category_detail_var.set(clipboard_category(clipboard))
            snippet_count_var.set(str(len(snippets)))
            source_count_var.set(str(len(sources)))
            selected_count_var.set(str(sum(1 for snippet in snippets if snippet.get("selected"))))
            updated_var.set(clipboard_latest_activity(clipboard))
            preview_var.set(snippet_preview(clipboard))

        def switch_selected(close_window=False):
            index = selected_clipboard_index()
            if index is None:
                return
            self.switch_to_snippet_clipboard_index(index)
            refresh_clipboards()
            if close_window:
                on_close()

        def open_selected():
            switch_selected(close_window=True)

        def create_new():
            self.open_new_snippet_clipboard_window(
                parent_window=window,
                after_create=lambda _category: (search_var.set(""), refresh_clipboards()),
            )

        def rename_selected():
            index = selected_clipboard_index()
            if index is None:
                self.status.configure(text="Select a snippets set to rename.")
                return
            clipboard = self.snippet_clipboards[index]
            name = simpledialog.askstring(
                "Rename snippets set",
                "Snippets set name:",
                initialvalue=clipboard.get("name", "Untitled snippets"),
                parent=window,
            )
            if not name:
                return
            clipboard["name"] = name.strip() or "Untitled snippets"
            self.refresh_snippet_clipboard_selector()
            refresh_clipboards()

        def categorize_selected():
            index = selected_clipboard_index()
            if index is None:
                self.status.configure(text="Select a snippets set to categorize.")
                return
            clipboard = self.snippet_clipboards[index]
            category = simpledialog.askstring(
                "Set snippets category",
                "Category:",
                initialvalue=clipboard_category(clipboard),
                parent=window,
            )
            if category is None:
                return
            clipboard["category"] = self.safe_snippet_clipboard_category(category)
            self.refresh_snippet_clipboard_selector()
            refresh_clipboards()

        def delete_selected():
            index = selected_clipboard_index(default=None)
            if index is None:
                self.status.configure(text="Select a snippets set to delete.")
                return
            clipboard = self.snippet_clipboards[index]
            if len(self.snippet_clipboards) <= 1:
                messagebox.showinfo("Delete snippets", "At least one snippets set must remain.")
                return
            name = clipboard.get("name") or "Untitled snippets"
            if not messagebox.askyesno("Delete snippets", "Delete snippets set \"{0}\"?".format(name), parent=window):
                return
            del self.snippet_clipboards[index]
            self.active_snippet_clipboard_index = min(self.active_snippet_clipboard_index, len(self.snippet_clipboards) - 1)
            self.snippets = self.snippet_clipboards[self.active_snippet_clipboard_index]["snippets"]
            self.render_active_snippet_clipboard()
            self.refresh_snippet_clipboard_selector()
            self.refresh_token_count()
            refresh_clipboards()
            self.status.configure(text="Deleted snippets set {0}.".format(name))

        def show_menu(event):
            row = listbox.nearest(event.y)
            if 0 <= row < listbox.size():
                select_clipboard_row_at(row)
            menu = tk.Menu(window, tearoff=0)
            menu.add_command(label="Open", command=open_selected)
            menu.add_command(label="Switch Here", command=lambda: switch_selected(close_window=False))
            menu.add_command(label="Rename", command=rename_selected)
            menu.add_command(label="Set Category", command=categorize_selected)
            menu.add_separator()
            menu.add_command(label="Delete", command=delete_selected)
            menu.tk_popup(event.x_root, event.y_root)
            return "break"

        listbox.bind("<Double-Button-1>", lambda _event: switch_selected(close_window=False))
        listbox.bind("<<ListboxSelect>>", update_details)
        listbox.bind("<Button-3>", show_menu)
        search.bind("<KeyRelease>", refresh_clipboards)
        window.bind("<Escape>", lambda _event: on_close())
        window.bind("<Return>", lambda _event: open_selected())
        refresh_clipboards()

        footer = tk.Frame(body, bg=self.colors["panel"])
        footer.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        #ttk.Button(footer, text="Open", style="Accent.TButton", command=open_selected).pack(side=tk.LEFT)
        ttk.Button(footer, text="Switch Snippet", command=lambda: switch_selected(close_window=False)).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(footer, text="New Snippets", command=create_new).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(footer, text="Rename Snippet", command=rename_selected).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(footer, text="New Category", command=categorize_selected).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(footer, text="Close", command=on_close).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(footer, text="Delete Snippet", command=delete_selected).pack(side=tk.RIGHT)
        search.focus_set()

    def open_new_snippet_clipboard_window(self, parent_window=None, after_create=None):
        window = tk.Toplevel(self)
        window.title("New snippets set")
        window.geometry("520x300")
        window.minsize(460, 260)
        window.configure(bg=self.colors["panel"])
        window.transient(parent_window or self)
        window.grab_set()

        body = tk.Frame(window, bg=self.colors["panel"], padx=16, pady=14)
        body.pack(fill=tk.BOTH, expand=True)
        tk.Label(body, text="Name", bg=self.colors["panel"], fg=self.colors["muted"], font=("Segoe UI", 8, "bold")).pack(fill=tk.X)
        name_var = tk.StringVar(value="Snippets {0}".format(len(getattr(self, "snippet_clipboards", [])) + 1))
        tk.Entry(body, textvariable=name_var, bg=self.colors["editor"], fg=self.colors["text"], insertbackground=self.colors["text"], relief=tk.FLAT, highlightthickness=1, highlightbackground=self.colors["line"], highlightcolor=self.colors["accent"], font=("Segoe UI", 9)).pack(fill=tk.X, pady=(4, 12), ipady=5)

        tk.Label(body, text="Category", bg=self.colors["panel"], fg=self.colors["muted"], font=("Segoe UI", 8, "bold")).pack(fill=tk.X)
        category_values = self.snippet_clipboard_categories()
        category_var = tk.StringVar(value=category_values[0] if category_values else self.default_snippet_clipboard_category())
        ttk.Combobox(body, textvariable=category_var, values=category_values, state="readonly").pack(fill=tk.X, pady=(4, 12))

        tk.Label(body, text="New category", bg=self.colors["panel"], fg=self.colors["muted"], font=("Segoe UI", 8, "bold")).pack(fill=tk.X)
        new_category_var = tk.StringVar()
        tk.Entry(body, textvariable=new_category_var, bg=self.colors["editor"], fg=self.colors["text"], insertbackground=self.colors["text"], relief=tk.FLAT, highlightthickness=1, highlightbackground=self.colors["line"], highlightcolor=self.colors["accent"], font=("Segoe UI", 9)).pack(fill=tk.X, pady=(4, 12), ipady=5)

        def create():
            name = name_var.get().strip() or "Untitled snippets"
            category = self.safe_snippet_clipboard_category(new_category_var.get().strip() or category_var.get())
            clipboard = self.create_snippet_clipboard(name=name, category=category)
            self.snippet_clipboards.append(clipboard)
            self.switch_to_snippet_clipboard_index(len(self.snippet_clipboards) - 1)
            window.destroy()
            if after_create:
                after_create(category)
            self.status.configure(text="Created snippets set {0}.".format(name))

        footer = tk.Frame(window, bg=self.colors["panel2"])
        footer.pack(fill=tk.X)
        ttk.Button(footer, text="Cancel", command=window.destroy).pack(side=tk.RIGHT, padx=(0, 12), pady=10)
        ttk.Button(footer, text="Create", command=create).pack(side=tk.RIGHT, padx=(0, 8), pady=10)

    def switch_to_snippet_clipboard_index(self, index):
        if index < 0 or index >= len(getattr(self, "snippet_clipboards", [])):
            return
        self.active_snippet_clipboard_index = index
        self.snippets = self.snippet_clipboards[index]["snippets"]
        self.render_active_snippet_clipboard()
        self.refresh_snippet_clipboard_selector()
        self.refresh_token_count()
        self.status.configure(text="Switched to {0}.".format(self.snippet_clipboards[index].get("name", "snippets")))

    def render_active_snippet_clipboard(self):
        self.snippet_cards.clear()
        for child in self.snippet_holder.winfo_children():
            child.destroy()
        self.refresh_context_cards_visibility_toggle()
        for snippet in self.snippets:
            if self.should_render_snippet_card(snippet):
                self._render_snippet(snippet)

    def add_selection(self):
        editor_data = self._active_editor_data()
        if not editor_data:
            self.status.configure(text="Open a file before adding a snippet.")
            return

        try:
            start_index = editor_data["editor"].index(tk.SEL_FIRST)
            end_index = editor_data["editor"].index(tk.SEL_LAST)
            selected = editor_data["editor"].get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            self.status.configure(text="Select code in the editor first.")
            return

        if not selected.strip():
            self.status.configure(text="Select code in the editor first.")
            return

        snippet = {
            "id": self.create_snippet_id(),
            "description": "",
            "source": editor_data["path"],
            "text": selected,
            "selected": False,
            "start_line": self._line_from_text_index(start_index),
            "end_line": self._line_from_text_index(end_index),
            "reason": "User-selected primary context.",
            "created_at": self.current_timestamp(),
        }
        self.snippets.append(snippet)
        self._render_snippet(snippet)
        self.refresh_token_count()
        self.status.configure(text="Snippet added to the temporary clipboard.")

    def retrieve_context_for_selected_snippets(self):
        anchors = [
            self._context_retrieval_snapshot(snippet)
            for snippet in self.snippets_for_context(selected_only=True)
            if not snippet.get("generated_context") and snippet.get("card_type") != "card"
        ]
        if not anchors:
            self.status.configure(text="Select at least one non-generated snippet before retrieving context.")
            return

        user_message = self.chat_input_text().strip() if hasattr(self, "chat_input") else ""
        root_folder = self.root_folder
        self._set_retrieve_context_running(True)
        self.status.configure(text=f"0/{len(anchors)} - Preparing context retrieval...")

        thread = threading.Thread(
            target=self._retrieve_context_worker,
            args=(anchors, user_message, root_folder),
            daemon=True,
        )
        thread.start()

    def _retrieve_context_worker(self, anchors, user_message, root_folder):
        try:
            depth = int(self.get_setting("repolens.clipboard.depth", 2) or 2)
            result = self.retrieve_repolens_context_for_snippets(
                anchors,
                user_message=user_message,
                depth=depth,
                update_before=bool(self.get_setting("repolens.clipboard.update_before_retrieval", False)),
                update_lite=bool(self.get_setting("repolens.clipboard.update_lite", True)),
                progress=lambda message: self._report_context_retrieval_status(message),
            )
        except Exception as exc:
            self.post_ui(lambda error=str(exc): self._finish_context_retrieval([], 0, len(anchors), error))
            return

        self.post_ui(
            lambda: self._finish_context_retrieval(
                result.get("parts", []),
                result.get("item_count", 0),
                len(anchors),
                None,
            ),
        )

    def retrieve_repolens_context_for_snippets(
        self,
        anchors,
        user_message="",
        depth=1,
        update_before=False,
        update_lite=True,
        progress=None,
        retrieval_options=None,
    ):
        progress = progress or (lambda _message: None)
        retrieval_options = retrieval_options or {}
        context_parts = []
        total_items = 0
        symbols_used = []
        index_dir = self._repolens_index_dir()
        service = RepoLensService()
        if update_before:
            progress("RepoLens update - updating database...")
            service.update(
                index_dir,
                lite=update_lite,
                progress=lambda message: progress("RepoLens update - {0}".format(message)),
            )

        total_snippets = len(anchors)
        for snippet_index, snippet in enumerate(anchors, start=1):
            symbols = self._symbols_for_repolens_snippet(snippet, user_message=user_message)
            if not symbols:
                progress(
                    "Snippet {0}/{1} - no symbols found for RepoLens.".format(snippet_index, total_snippets)
                )
                continue
            symbols_used.extend(symbol for symbol in symbols if symbol not in symbols_used)
            progress(
                "Snippet {0}/{1} - retrieving RepoLens context for {2}.".format(
                    snippet_index,
                    total_snippets,
                    ", ".join(symbols[:4]),
                )
            )
            result = service.context(
                index_dir,
                symbols,
                partial=False,
                include_tree=bool(retrieval_options.get("compact_structure", self.get_setting("repolens.context.include_tree", True))),
                include_types=bool(retrieval_options.get("resolve_symbols", self.get_setting("repolens.context.include_types", True))),
                level=max(0, int(depth or 0)),
                budget_chars=int(self.get_setting("repolens.context.budget_chars", 60000) or 60000),
                basic=bool(retrieval_options.get("exact_symbol", self.get_setting("repolens.context.basic", False))),
                situated=bool(retrieval_options.get("situated", self.get_setting("repolens.context.situated", False))),
                signals_query=str(self.get_setting("repolens.context.signals_query", "") or "") if retrieval_options.get("signals", False) else "",
                grow=bool(retrieval_options.get("impact", self.get_setting("repolens.context.grow_enabled", False))),
                grow_files=str(self.get_setting("repolens.context.grow_files", "") or "").split(","),
            )
            if context_item_count(result) == 0 and bool(self.get_setting("repolens.context.partial_fallback", True)):
                result = service.context(
                    index_dir,
                    symbols[: max(1, min(6, len(symbols)))],
                    partial=True,
                    include_tree=bool(retrieval_options.get("compact_structure", self.get_setting("repolens.context.include_tree", True))),
                    include_types=bool(retrieval_options.get("resolve_symbols", self.get_setting("repolens.context.include_types", True))),
                    level=max(0, int(depth or 0)),
                    budget_chars=int(self.get_setting("repolens.context.budget_chars", 60000) or 60000),
                    basic=bool(retrieval_options.get("exact_symbol", self.get_setting("repolens.context.basic", False))),
                    situated=bool(retrieval_options.get("situated", self.get_setting("repolens.context.situated", False))),
                    signals_query=str(self.get_setting("repolens.context.signals_query", "") or "") if retrieval_options.get("signals", False) else "",
                    grow=bool(retrieval_options.get("impact", self.get_setting("repolens.context.grow_enabled", False))),
                    grow_files=str(self.get_setting("repolens.context.grow_files", "") or "").split(","),
                )
            text = format_repolens_context(result).strip()
            if text:
                context_parts.append(text)
                total_items += context_item_count(result)

        return {
            "parts": context_parts,
            "text": "\n\n".join(context_parts),
            "item_count": total_items,
            "symbols": symbols_used,
            "depth": max(0, int(depth or 0)),
        }

    def _repolens_index_dir(self):
        session_info = getattr(self, "current_session_info", {}) or {}
        database_dir = session_info.get("database_dir", "")
        if database_dir:
            return Path(database_dir)
        if getattr(self, "current_session_path", None) and hasattr(self, "session_manager"):
            return self.session_manager.session_dir_from_path(self.current_session_path) / "database"
        raise ValueError("This session does not have a RepoLens database folder.")

    def _symbols_for_repolens_snippet(self, snippet, user_message=None):
        max_symbols = int(self.get_setting("repolens.context.max_symbols", 12) or 12)
        forced_symbols = [
            str(symbol).strip()
            for symbol in snippet.get("repolens_symbols", [])
            if str(symbol).strip()
        ]
        if forced_symbols:
            return forced_symbols[:max_symbols]
        symbols = extract_symbols_from_snippet(snippet, max_symbols=max_symbols)
        if user_message is None:
            user_message = self.chat_input_text().strip() if hasattr(self, "chat_input") else ""
        if user_message:
            symbols.extend(
                symbol
                for symbol in extract_symbols_from_snippet({"text": user_message}, max_symbols=max_symbols)
                if symbol not in symbols
            )
        return symbols[:max_symbols]

    def retrieve_smart_context(
        self,
        anchors,
        user_message="",
        endpoint=None,
        intent=None,
        progress=None,
        create_cards=True,
    ):
        retriever = SmartContextRetriever(settings=self.flattened_settings())

        def emit_step(title, text, selected=False):
            if not create_cards or not bool(self.get_setting("smart_context.create_step_cards", True)):
                return
            if selected and not bool(self.get_setting("smart_context.create_final_card", True)):
                return
            self.post_ui(
                lambda step_title=title, step_text=text, step_selected=selected: self.add_smart_context_step_card(
                    step_title,
                    step_text,
                    selected=step_selected,
                )
            )

        return retriever.retrieve(
            self._repolens_index_dir(),
            anchors,
            user_message=user_message,
            intent=intent,
            planner_call=None,
            progress=progress,
            emit_step=emit_step,
        )

    def flattened_settings(self):
        flat = {}

        def visit(prefix, value):
            if isinstance(value, dict):
                for key, child in value.items():
                    visit("{0}.{1}".format(prefix, key) if prefix else str(key), child)
            else:
                flat[prefix] = value

        visit("", getattr(self, "settings", {}) or {})
        for key, value in context_mode_overrides(getattr(self, "settings", {})).items():
            flat[key] = value
        return flat

    def add_smart_context_step_card(self, title, text, selected=False):
        if not str(text or "").strip():
            return None
        generated = {
            "id": self.create_snippet_id(),
            "description": title,
            "source": Path("Smart Context"),
            "text": str(text).strip(),
            "selected": bool(selected),
            "generated_context": True,
            "reason": "Generated smart context retrieval step.",
            "created_at": self.current_timestamp(),
        }
        self.snippets.append(generated)
        self.refresh_context_cards_visibility_toggle()
        if self.should_render_snippet_card(generated):
            self._render_snippet(generated)
        self.refresh_token_count()
        return generated

    def repolens_depth_for_intent(self, intent, fallback=1):
        mode = (intent or {}).get("mode", "")
        if mode:
            return int(self.get_setting("repolens.depth.{0}".format(mode), (intent or {}).get("depth", fallback)) or fallback)
        return int((intent or {}).get("depth", fallback) or fallback)

    def add_repolens_context_card(self, context_text, source_request="", depth=1, symbols=None, selected=True):
        if not context_text.strip():
            return None
        header = [
            "RepoLens request:",
            source_request.strip() or "(no chat command)",
            "",
            "Depth: {0}".format(depth),
        ]
        if symbols:
            header.append("Symbols: {0}".format(", ".join(symbols[:20])))
        body = "\n".join(header) + "\n\n" + context_text.strip()
        generated = {
            "id": self.create_snippet_id(),
            "description": "RepoLens context",
            "source": Path("RepoLens Context"),
            "text": body,
            "selected": selected,
            "generated_context": True,
            "reason": "Generated RepoLens context.",
            "created_at": self.current_timestamp(),
        }
        self.snippets.append(generated)
        self.refresh_context_cards_visibility_toggle()
        if self.should_render_snippet_card(generated):
            self._render_snippet(generated)
        self.refresh_token_count()
        return generated

    def _report_context_retrieval_status(self, message):
        self.post_ui(lambda value=message: self.status.configure(text=value))

    def _report_context_retrieval_progress(self, snippet_index, total_snippets, step, total, message):
        text = f"Snippet {snippet_index}/{total_snippets}, step {step}/{total} - {message}"
        self.post_ui(lambda value=text: self.status.configure(text=value))

    def _finish_context_retrieval(self, context_parts, total_items, anchor_count, error=None):
        self._set_retrieve_context_running(False)
        if error:
            self.status.configure(text=f"Context retrieval failed: {error}")
            return
        if not context_parts:
            self.status.configure(text="No extra context could be retrieved for the selected snippets.")
            return

        generated = {
            "id": self.create_snippet_id(),
            "description": "Retrieved context",
            "source": Path("Retrieved Context"),
            "text": "\n\n".join(context_parts),
            "selected": True,
            "generated_context": True,
            "reason": "Generated context retrieved from selected snippets.",
            "created_at": self.current_timestamp(),
        }
        self.snippets.append(generated)
        self.refresh_context_cards_visibility_toggle()
        if self.should_render_snippet_card(generated):
            self._render_snippet(generated)
        self.refresh_token_count()
        self.status.configure(text=f"Retrieved {total_items} context item(s) from {anchor_count} selected snippet(s).")

    def _set_retrieve_context_running(self, running):
        if hasattr(self, "retrieve_context_button"):
            self.retrieve_context_button.configure(state=tk.DISABLED if running else tk.NORMAL)

    def _context_retrieval_snapshot(self, snippet):
        return {
            "source": snippet.get("source"),
            "text": snippet.get("text", ""),
            "description": snippet.get("description", ""),
            "start_line": snippet.get("start_line"),
            "end_line": snippet.get("end_line"),
            "reason": snippet.get("reason", ""),
        }

    def _line_from_text_index(self, index):
        try:
            return int(str(index).split(".", 1)[0])
        except (TypeError, ValueError):
            return None

    def has_context_cards_in_clipboard(self):
        return any(snippet.get("generated_context", False) for snippet in getattr(self, "snippets", []))

    def should_show_context_cards(self):
        return bool(
            hasattr(self, "show_context_cards_var")
            and self.show_context_cards_var.get()
        )

    def should_render_snippet_card(self, snippet):
        return not snippet.get("generated_context", False) or self.should_show_context_cards()

    def refresh_context_cards_visibility_toggle(self):
        if not hasattr(self, "show_context_cards_check"):
            return
        if not self.has_context_cards_in_clipboard():
            self.show_context_cards_var.set(False)
        self.show_context_cards_check.pack_forget()

    def snippet_can_open_source(self, snippet):
        if snippet.get("generated_context") or snippet.get("card_type") == "card":
            return False
        source = snippet.get("source")
        if not source:
            return False
        try:
            return Path(source).exists()
        except (TypeError, OSError):
            return False

    def bind_snippet_source_navigation(self, widget, snippet):
        if self.snippet_can_open_source(snippet):
            widget.bind("<Double-Button-1>", lambda event, value=snippet: self.open_snippet_source(value))
            try:
                widget.configure(cursor="hand2")
            except tk.TclError:
                pass

    def open_snippet_source(self, snippet):
        if not self.snippet_can_open_source(snippet):
            return "break"
        path = Path(snippet.get("source"))
        self.open_file(path)
        if hasattr(self, "_reveal_file_tree_path") and getattr(self, "root_folder", None):
            self._reveal_file_tree_path(path)
        if hasattr(self, "middle_tabs") and hasattr(self, "open_file_tab_frame"):
            self.middle_tabs.select(self.open_file_tab_frame)

        editor_data = getattr(self, "open_file_tabs", {}).get(path)
        if editor_data and hasattr(self, "editor_tabs"):
            self.editor_tabs.select(editor_data["frame"])
            try:
                self.editor_tabs.focus_set()
            except tk.TclError:
                pass
        editor = editor_data.get("editor") if editor_data else None
        if editor is None:
            self.status.configure(text="Opened {0}.".format(path.name))
            return "break"

        start_line = self.safe_snippet_line(snippet.get("start_line"), fallback=1)
        end_line = self.safe_snippet_line(snippet.get("end_line"), fallback=start_line)
        if end_line < start_line:
            end_line = start_line
        start = "{0}.0".format(start_line)
        end = "{0}.end".format(end_line)
        editor.tag_configure("snippet_jump", background=self.colors["highlight"], foreground=self.colors["highlight_text"])
        editor.tag_remove("snippet_jump", "1.0", tk.END)
        editor.tag_add("snippet_jump", start, end)
        editor.mark_set(tk.INSERT, start)
        editor.see(start)
        editor.focus_set()
        self.status.configure(text="Opened {0} at line {1}.".format(path.name, start_line))
        return "break"

    def safe_snippet_line(self, value, fallback=1):
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return fallback

    def _render_snippet(self, snippet):
        self.ensure_created_at(snippet)
        self.ensure_snippet_id(snippet)
        card = tk.Frame(
            self.snippet_holder,
            bg=self.colors["panel2"],
            highlightbackground="#343c4c",
            highlightthickness=1,
        )
        card.snippet_id = snippet["id"]
        card.snippet_description = snippet.get("description", "")
        card.pack(fill=tk.X, padx=0, pady=(0, 10))
        self.bind_snippet_source_navigation(card, snippet)

        header = tk.Frame(card, bg=self.colors["panel2"])
        header.pack(fill=tk.X)
        self.bind_snippet_source_navigation(header, snippet)

        selected_var = tk.BooleanVar(value=snippet.get("selected", False))
        snippet["selected_var"] = selected_var
        selector = tk.Checkbutton(
            header,
            variable=selected_var,
            command=lambda: self.update_snippet_selected(snippet),
            bg=self.colors["panel2"],
            fg=self.colors["text"],
            activebackground=self.colors["panel2"],
            selectcolor=self.colors["editor"],
            borderwidth=0,
        )
        selector.pack(side=tk.LEFT, padx=(6, 0))

        source = tk.Label(
            header,
            text=self.snippet_display_source(snippet),
            bg=self.colors["panel2"],
            fg="#f4f7fb",
            anchor="w",
            font=("Segoe UI", 9, "bold"),
            padx=9,
            pady=6,
        )
        source.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.bind_snippet_source_navigation(source, snippet)

        snippet_id = tk.Label(
            header,
            text=f"ID {snippet.get('id', '')}",
            bg=self.colors["panel2"],
            fg=self.colors["muted"],
            anchor="e",
            font=("Segoe UI", 8),
            padx=6,
            pady=6,
        )
        snippet_id.pack(side=tk.LEFT)
        self.bind_snippet_source_navigation(snippet_id, snippet)

        timestamp = tk.Label(
            header,
            text=self._snippet_timestamp_text(snippet),
            bg=self.colors["panel2"],
            fg=self.colors["muted"],
            anchor="e",
            font=("Segoe UI", 8),
            padx=6,
            pady=6,
        )
        timestamp.pack(side=tk.LEFT)
        self.bind_snippet_source_navigation(timestamp, snippet)
        snippet["timestamp_label"] = timestamp

        copy_button = tk.Button(
            header,
            text="Copy",
            command=lambda value=snippet: self.copy_snippet_to_clipboard(value),
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
        )
        copy_button.pack(side=tk.RIGHT, padx=(0, 6), pady=5)

        remove_button = tk.Button(
            header,
            text="X",
            command=lambda: self.remove_snippet(snippet, card),
            bg="#2b3240",
            fg="#f4f7fb",
            activebackground="#b42318",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            borderwidth=0,
            width=3,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        )
        remove_button.pack(side=tk.RIGHT, padx=(0, 6), pady=5)

        description_row = tk.Frame(card, bg=self.colors["panel2"])
        description_row.pack(fill=tk.X, padx=9, pady=(0, 7))

        description_label = tk.Label(
            description_row,
            text="Description",
            bg=self.colors["panel2"],
            fg=self.colors["muted"],
            anchor="w",
            font=("Segoe UI", 8, "bold"),
            padx=0,
            pady=2,
        )
        description_label.pack(side=tk.LEFT, padx=(0, 8))
        self.bind_snippet_source_navigation(description_label, snippet)

        description_var = tk.StringVar(value=snippet.get("description", ""))
        snippet["description_var"] = description_var
        description_entry = tk.Entry(
            description_row,
            textvariable=description_var,
            bg=self.colors["editor"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            highlightcolor=self.colors["accent"],
            font=("Segoe UI", 9),
        )
        description_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        description_entry.bind(
            "<KeyRelease>",
            lambda _event: self.update_snippet_description(snippet, card, description_var),
        )
        description_entry.bind(
            "<FocusOut>",
            lambda _event: self.update_snippet_description(snippet, card, description_var),
        )

        lines = max(3, min(12, snippet["text"].count("\n") + 2))
        body = tk.Text(
            card,
            height=lines,
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
        body.insert("1.0", snippet["text"])
        body.pack(fill=tk.X, padx=9, pady=(0, 9))
        self.bind_snippet_source_navigation(body, snippet)
        body.bind("<KeyRelease>", lambda _event: self.update_snippet_text(snippet, body))
        body.bind("<FocusOut>", lambda _event: self.update_snippet_text(snippet, body))
        snippet["body_widget"] = body
        snippet["content_widgets"] = [body]
        if snippet.get("collapsed", False):
            body.pack_forget()
        for widget in (header, source):
            widget.bind("<Button-1>", lambda event, value=snippet: self.toggle_snippet_collapsed(value))
        self.snippet_cards.append((snippet, card))

    def toggle_snippet_collapsed(self, snippet):
        snippet["collapsed"] = not bool(snippet.get("collapsed", False))
        for widget in snippet.get("content_widgets", []):
            try:
                if snippet["collapsed"]:
                    widget.pack_forget()
                else:
                    widget.pack(fill=tk.X, padx=9, pady=(0, 9))
            except tk.TclError:
                pass
        if hasattr(self, "status"):
            self.status.configure(text="Snippet {0}.".format("collapsed" if snippet["collapsed"] else "expanded"))

    def snippet_display_source(self, snippet):
        if snippet.get("card_type") == "card":
            return "Card"
        return self._relative(snippet["source"])

    def _snippet_timestamp_text(self, snippet):
        created = self.display_timestamp(snippet.get("created_at"))
        updated = snippet.get("updated_at")
        if updated:
            return f"Created {created} | Edited {self.display_timestamp(updated)}"
        return f"Created {created}"

    def copy_snippet_to_clipboard(self, snippet):
        self.clipboard_clear()
        self.clipboard_append(snippet.get("text", ""))
        self.status.configure(text="Snippet copied to the system clipboard.")

    def update_snippet_text(self, snippet, body):
        current_text = body.get("1.0", "end-1c")
        if current_text == snippet.get("text", ""):
            return
        snippet["text"] = current_text
        snippet["updated_at"] = self.current_timestamp()
        if snippet.get("timestamp_label"):
            snippet["timestamp_label"].configure(text=self._snippet_timestamp_text(snippet))
        self.refresh_token_count()

    def update_snippet_description(self, snippet, card, description_var):
        description = description_var.get()
        if description == snippet.get("description", ""):
            return
        snippet["description"] = description
        card.snippet_description = description

    def update_snippet_selected(self, snippet):
        snippet["selected"] = bool(snippet.get("selected_var").get())
        self.refresh_token_count()

    def set_all_snippets_selected(self, selected):
        for snippet in self.snippets:
            snippet["selected"] = selected
            if "selected_var" in snippet:
                snippet["selected_var"].set(selected)
        self.refresh_token_count()
        self.status.configure(text="Updated chat context snippet selection.")

    def remove_snippet(self, snippet, card):
        if snippet in self.snippets:
            self.snippets.remove(snippet)
        self.snippet_cards = [
            (stored_snippet, stored_card)
            for stored_snippet, stored_card in self.snippet_cards
            if stored_card != card
        ]
        card.destroy()
        self.refresh_context_cards_visibility_toggle()
        self.refresh_token_count()
        self.status.configure(text="Snippet removed from the temporary clipboard.")
