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
from tkinter import simpledialog

from src.config.constants import MAX_SEARCH_BYTES, TEXT_EXTENSIONS


class ChatThreadsMixin:
    def new_chat_thread(self):
        title = f"Chat {len(self.chat_threads) + 1}"
        self.chat_threads.append(
            {"title": title, "messages": [], "created_at": self.current_timestamp()}
        )
        self.current_chat_index = len(self.chat_threads) - 1
        self.chat_messages = self.chat_threads[self.current_chat_index]["messages"]
        self.refresh_chat_thread_selector()
        self.render_current_chat()
        self.update_chat_input_placeholder("New chat thread started.")
        self.status.configure(text="New chat thread started.")

    def branch_chat_thread(self):
        source_title = self.chat_threads[self.current_chat_index]["title"]
        copied_messages = [dict(message) for message in self.chat_messages]
        title = f"{source_title} branch {self.count_thread_branches(source_title) + 1}"
        self.chat_threads.append(
            {"title": title, "messages": copied_messages, "created_at": self.current_timestamp()}
        )
        self.current_chat_index = len(self.chat_threads) - 1
        self.chat_messages = self.chat_threads[self.current_chat_index]["messages"]
        self.refresh_chat_thread_selector()
        self.render_current_chat()
        self.update_chat_input_placeholder(f"Branched from {source_title}.")
        self.status.configure(text=f"Created branch from {source_title}.")

    def count_thread_branches(self, source_title):
        prefix = f"{source_title} branch "
        return sum(1 for thread in self.chat_threads if thread["title"].startswith(prefix))

    def switch_chat_thread(self, _event=None):
        selected = self.chat_thread_combo.current()
        if selected < 0 or selected >= len(self.chat_threads):
            return
        self.current_chat_index = selected
        self.chat_messages = self.chat_threads[selected]["messages"]
        self.render_current_chat()
        self.update_chat_input_placeholder(f"Switched to {self.chat_threads[selected]['title']}.")
        self.status.configure(text=f"Switched to {self.chat_threads[selected]['title']}.")

    def refresh_chat_thread_selector(self):
        if not hasattr(self, "chat_thread_combo"):
            return
        titles = [thread["title"] for thread in self.chat_threads]
        self.chat_thread_combo.configure(values=titles)
        self.chat_thread_combo.current(self.current_chat_index)
        self.chat_thread_var.set(titles[self.current_chat_index])

    def open_chat_manager(self):
        existing = getattr(self, "chat_manager_window", None)
        try:
            if existing and existing.winfo_exists():
                existing.lift()
                existing.focus_set()
                return
        except tk.TclError:
            pass

        window = tk.Toplevel(self)
        window.title("Chat Manager")
        window.geometry("820x560")
        window.minsize(680, 460)
        window.configure(bg=self.colors["panel"])
        window.transient(self)
        self.chat_manager_window = window

        def on_close():
            self.chat_manager_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", on_close)

        body = tk.Frame(window, bg=self.colors["panel"], padx=14, pady=12)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(2, weight=1)

        header = tk.Frame(body, bg=self.colors["panel"])
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="Chat Manager",
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
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            activestyle="none",
            font=("Segoe UI", 10),
        )
        listbox.grid(row=0, column=0, sticky="nsew")
        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        listbox.configure(yscrollcommand=list_scroll.set)

        detail = tk.Frame(body, bg=self.colors["panel2"], highlightbackground=self.colors["line"], highlightthickness=1)
        detail.grid(row=2, column=1, sticky="nsew", padx=(14, 0))
        detail.columnconfigure(0, weight=1)
        title_var = tk.StringVar()
        category_var = tk.StringVar()
        messages_var = tk.StringVar()
        created_var = tk.StringVar()
        updated_var = tk.StringVar()
        preview_var = tk.StringVar()
        for row, (label, variable) in enumerate(
            [
                ("Title", title_var),
                ("Category", category_var),
                ("Messages", messages_var),
                ("Created", created_var),
                ("Updated", updated_var),
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
                wraplength=260,
                font=("Segoe UI", 10 if row == 0 else 9, "bold" if row == 0 else "normal"),
                padx=10,
                pady=2,
            ).grid(row=row * 2 + 1, column=0, sticky="ew", pady=(0, 4))

        chat_list_rows = []

        def chat_label(thread, index):
            title = thread.get("title", "Chat {0}".format(index + 1))
            messages = len(thread.get("messages", []))
            active = "  *" if index == self.current_chat_index else ""
            return "   {0}{1}    {2} msg".format(title, active, messages)

        def thread_preview(thread):
            for message in reversed(thread.get("messages", [])):
                text = " ".join(str(message.get("content", "")).split())
                if text:
                    return text[:220] + ("..." if len(text) > 220 else "")
            return "No messages yet."

        def refresh():
            previous_index = selected_index(default=None)
            listbox.delete(0, tk.END)
            chat_list_rows.clear()
            needle = search_var.get().strip().lower()
            grouped = {}
            for index, thread in enumerate(self.chat_threads):
                haystack = " ".join(
                    [
                        thread.get("title", ""),
                        thread.get("category", "General"),
                        thread_preview(thread),
                    ]
                ).lower()
                if needle and needle not in haystack:
                    continue
                category = thread.get("category", "General") or "General"
                grouped.setdefault(category, []).append((index, thread))
            for category in sorted(grouped, key=lambda value: value.lower()):
                row_index = listbox.size()
                chat_list_rows.append({"type": "header", "category": category, "thread_index": None})
                listbox.insert(tk.END, category)
                try:
                    listbox.itemconfig(row_index, foreground=self.colors["muted"], background=self.colors["panel2"])
                except tk.TclError:
                    pass
                for index, thread in grouped[category]:
                    row_index = listbox.size()
                    chat_list_rows.append({"type": "chat", "category": category, "thread_index": index})
                    listbox.insert(tk.END, chat_label(thread, index))
            count_label.configure(text="{0} chat{1}".format(len(self.chat_threads), "" if len(self.chat_threads) == 1 else "s"))
            visible_chat_indices = [row["thread_index"] for row in chat_list_rows if row["type"] == "chat"]
            if visible_chat_indices:
                target = previous_index if previous_index in visible_chat_indices else self.current_chat_index
                if target not in visible_chat_indices:
                    target = visible_chat_indices[0]
                visible_index = next(
                    row_index
                    for row_index, row in enumerate(chat_list_rows)
                    if row["type"] == "chat" and row["thread_index"] == target
                )
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(visible_index)
                listbox.activate(visible_index)
                listbox.see(visible_index)
            update_details()

        def selected_index(default=None):
            selection = listbox.curselection()
            if selection and selection[0] < len(chat_list_rows):
                row = chat_list_rows[selection[0]]
                if row["type"] == "chat":
                    return row["thread_index"]
            return self.current_chat_index if default is None else default

        def select_chat_row_at(index):
            if not chat_list_rows:
                return
            index = max(0, min(index, len(chat_list_rows) - 1))
            if chat_list_rows[index]["type"] == "header":
                for candidate in range(index + 1, len(chat_list_rows)):
                    if chat_list_rows[candidate]["type"] == "chat":
                        index = candidate
                        break
                else:
                    for candidate in range(index - 1, -1, -1):
                        if chat_list_rows[candidate]["type"] == "chat":
                            index = candidate
                            break
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(index)
            listbox.activate(index)
            listbox.see(index)
            update_details()

        def update_details(_event=None):
            index = selected_index(default=None)
            if index is None or not (0 <= index < len(self.chat_threads)):
                title_var.set("No chat selected")
                category_var.set("")
                messages_var.set("")
                created_var.set("")
                updated_var.set("")
                preview_var.set("")
                return
            thread = self.chat_threads[index]
            title_var.set(thread.get("title", "Chat {0}".format(index + 1)))
            category_var.set(thread.get("category", "General"))
            messages_var.set(str(len(thread.get("messages", []))))
            created_var.set(self.display_timestamp(thread.get("created_at")) if hasattr(self, "display_timestamp") else thread.get("created_at", ""))
            updated = thread.get("updated_at", "")
            updated_var.set(self.display_timestamp(updated) if updated and hasattr(self, "display_timestamp") else (updated or "Not edited"))
            preview_var.set(thread_preview(thread))

        def open_selected():
            index = selected_index()
            if 0 <= index < len(self.chat_threads):
                self.current_chat_index = index
                self.chat_messages = self.chat_threads[index]["messages"]
                self.refresh_chat_thread_selector()
                self.render_current_chat()
                self.update_chat_input_placeholder(f"Switched to {self.chat_threads[index]['title']}.")
                self.status.configure(text=f"Switched to {self.chat_threads[index]['title']}.")
                on_close()

        def rename_selected():
            index = selected_index()
            title = simpledialog.askstring("Rename chat", "Chat title:", initialvalue=self.chat_threads[index].get("title", ""), parent=window)
            if title:
                self.chat_threads[index]["title"] = title.strip()
                self.chat_threads[index]["updated_at"] = self.current_timestamp()
                refresh()
                self.refresh_chat_thread_selector()
                update_details()

        def categorize_selected():
            index = selected_index()
            category = simpledialog.askstring("Chat category", "Category:", initialvalue=self.chat_threads[index].get("category", "General"), parent=window)
            if category:
                self.chat_threads[index]["category"] = category.strip() or "General"
                self.chat_threads[index]["updated_at"] = self.current_timestamp()
                refresh()
                update_details()

        def delete_selected():
            index = selected_index()
            if len(self.chat_threads) <= 1:
                self.status.configure(text="Keep at least one chat.")
                return
            if not messagebox.askyesno("Delete chat", "Delete this chat?", parent=window):
                return
            del self.chat_threads[index]
            self.current_chat_index = min(self.current_chat_index, len(self.chat_threads) - 1)
            self.chat_messages = self.chat_threads[self.current_chat_index]["messages"]
            refresh()
            self.refresh_chat_thread_selector()
            self.render_current_chat()

        def new_and_refresh():
            self.new_chat_thread()
            search_var.set("")
            refresh()

        def branch_and_refresh():
            self.branch_chat_thread()
            search_var.set("")
            refresh()

        actions = tk.Frame(body, bg=self.colors["panel"])
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(actions, text="Open", style="Accent.TButton", command=open_selected).pack(side=tk.LEFT)
        ttk.Button(actions, text="New", command=new_and_refresh).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(actions, text="Branch", command=branch_and_refresh).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(actions, text="Rename", command=rename_selected).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(actions, text="Category", command=categorize_selected).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(actions, text="Close", command=on_close).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(actions, text="Delete", command=delete_selected).pack(side=tk.RIGHT)

        def show_menu(event):
            index = listbox.nearest(event.y)
            if 0 <= index < listbox.size():
                select_chat_row_at(index)
            menu = tk.Menu(window, tearoff=0)
            menu.add_command(label="Open", command=open_selected)
            menu.add_command(label="Rename", command=rename_selected)
            menu.add_command(label="Set Category", command=categorize_selected)
            menu.add_separator()
            menu.add_command(label="Delete", command=delete_selected)
            menu.tk_popup(event.x_root, event.y_root)
            return "break"

        listbox.bind("<Double-1>", lambda _event: open_selected())
        listbox.bind("<<ListboxSelect>>", update_details)
        listbox.bind("<Button-3>", show_menu)
        search.bind("<KeyRelease>", lambda _event: refresh())
        window.bind("<Escape>", lambda _event: on_close())
        window.bind("<Return>", lambda _event: open_selected())
        refresh()
        search.focus_set()

    def render_current_chat(self):
        for child in self.chat_cards.winfo_children():
            child.destroy()
        self.streaming_card = None
        self.streaming_text = None
        self.streaming_answer = ""
        self._append_conversation_title_card()
        if not self.chat_messages and not self._current_thread_streams():
            self.update_chat_input_placeholder("Empty chat thread. Ctrl+Enter sends the message.")
            return
        for message in self.chat_messages:
            role = message.get("role", "assistant")
            content = message.get("content", "")
            self._append_chat_card("user" if role == "user" else "assistant", content, message=message)
        for request_id in self._current_thread_streams():
            self._start_streaming_assistant_card(request_id=request_id, thread_index=self.current_chat_index)

    def _current_thread_streams(self):
        streams = getattr(self, "chat_streams", {}) or {}
        return [
            request_id
            for request_id, stream in streams.items()
            if stream.get("thread_index") == self.current_chat_index
        ]

    def _append_conversation_title_card(self):
        thread = self.chat_threads[self.current_chat_index]
        self.ensure_created_at(thread)
        outer = tk.Frame(self.chat_cards, bg=self.colors["editor"])
        outer.pack(fill=tk.X, padx=10, pady=(10, 0))
        card = tk.Frame(
            outer,
            bg="#181d24",
            highlightbackground=self.colors["accent"],
            highlightthickness=1,
        )
        card.pack(fill=tk.X)
        header = tk.Frame(card, bg="#181d24")
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text="Conversation title",
            bg="#181d24",
            fg=self.colors["muted"],
            anchor="w",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=5,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.thread_title_timestamp_label = tk.Label(
            header,
            text=self._thread_timestamp_text(thread),
            bg="#181d24",
            fg=self.colors["muted"],
            anchor="e",
            font=("Segoe UI", 8),
            padx=10,
            pady=5,
        )
        self.thread_title_timestamp_label.pack(side=tk.RIGHT)
        self.thread_title_text = tk.Text(
            card,
            height=2,
            bg="#111318",
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            selectbackground=self.colors["select"],
            selectforeground="#ffffff",
            wrap=tk.WORD,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            font=("Segoe UI", 10, "bold"),
            padx=8,
            pady=5,
        )
        self.thread_title_text.insert("1.0", self.chat_threads[self.current_chat_index]["title"])
        self.thread_title_text.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.thread_title_text.bind("<KeyRelease>", self.update_thread_title_from_card)
        self.thread_title_text.bind("<FocusOut>", self.update_thread_title_from_card)

    def _thread_timestamp_text(self, thread):
        created = self.display_timestamp(thread.get("created_at"))
        updated = thread.get("updated_at")
        if updated:
            return f"Created {created} | Edited {self.display_timestamp(updated)}"
        return f"Created {created}"

    def update_thread_title_from_card(self, _event=None):
        if not hasattr(self, "thread_title_text"):
            return
        thread = self.chat_threads[self.current_chat_index]
        old_title = thread.get("title", "")
        title = " ".join(self.thread_title_text.get("1.0", "end-1c").split()).strip()
        if not title:
            title = f"Chat {self.current_chat_index + 1}"
        thread["title"] = title
        if title != old_title:
            thread["updated_at"] = self.current_timestamp()
            if hasattr(self, "thread_title_timestamp_label"):
                self.thread_title_timestamp_label.configure(text=self._thread_timestamp_text(thread))
        self.refresh_chat_thread_selector()


    def update_current_thread_title(self, user_message, thread_index=None):
        thread_index = self.current_chat_index if thread_index is None else thread_index
        thread = self.chat_threads[thread_index]
        if thread["title"].startswith("Chat ") and len(thread["messages"]) <= 2:
            compact = " ".join(user_message.split())
            if compact:
                thread["title"] = compact[:42] + ("..." if len(compact) > 42 else "")
                thread["updated_at"] = self.current_timestamp()
                if (
                    thread_index == self.current_chat_index
                    and hasattr(self, "thread_title_text")
                    and self.thread_title_text.winfo_exists()
                ):
                    self.thread_title_text.delete("1.0", tk.END)
                    self.thread_title_text.insert("1.0", thread["title"])
                if thread_index == self.current_chat_index and hasattr(self, "thread_title_timestamp_label"):
                    self.thread_title_timestamp_label.configure(text=self._thread_timestamp_text(thread))
