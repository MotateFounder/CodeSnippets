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


class ChatCardsMixin:
    def register_chat_text_widget(self, widget):
        widgets = getattr(self, "chat_auto_resize_widgets", [])
        widgets.append(widget)
        self.chat_auto_resize_widgets = widgets
        widget.bind("<Configure>", lambda _event, value=widget: self.after_idle(lambda: self.fit_chat_text_widget(value)), add="+")
        self.after_idle(lambda value=widget: self.fit_chat_text_widget(value))

    def fit_chat_text_widget(self, widget, minimum=1):
        try:
            if not widget.winfo_exists():
                return
            widget.update_idletasks()
            count = widget.count("1.0", "end-1c", "displaylines")
            display_lines = int(count[0]) if count else 1
            widget.configure(height=max(minimum, display_lines + 1))
        except (tk.TclError, TypeError, ValueError):
            pass

    def resize_chat_text_widgets(self):
        alive = []
        for widget in getattr(self, "chat_auto_resize_widgets", []):
            try:
                if widget.winfo_exists():
                    self.fit_chat_text_widget(widget)
                    alive.append(widget)
            except tk.TclError:
                pass
        self.chat_auto_resize_widgets = alive

    def _append_chat_card(self, role, text, message=None, persist_on_delete=True):
        self.ensure_created_at(message)
        is_user = role == "user"
        outer = tk.Frame(
            self.chat_cards,
            bg=self.colors["editor"],
        )
        outer.pack(fill=tk.X, padx=10, pady=(10, 0))

        card_bg = self.colors.get("panel2", "#20303a") if is_user else self.colors.get("panel", "#1f232b")
        border = self.colors["accent"] if is_user else self.colors.get("line", "#343c4c")

        card = tk.Frame(
            outer,
            bg=card_bg,
            highlightbackground=border,
            highlightthickness=1,
        )
        card.pack(fill=tk.X, anchor="e" if is_user else "w")

        label = "User" if is_user else "CodeSnippets"
        header = tk.Frame(card, bg=card_bg)
        header.pack(fill=tk.X)

        collapse_button = tk.Button(
            header,
            text="-",
            bg="#2b3240",
            fg="#f4f7fb",
            activebackground=self.colors["accent"],
            activeforeground="#ffffff",
            relief=tk.FLAT,
            borderwidth=0,
            width=3,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        )
        collapse_button.pack(side=tk.LEFT, padx=(6, 0), pady=5)

        tk.Label(
            header,
            text=label,
            bg=card_bg,
            fg="#f4f7fb",
            anchor="w",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=6,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(
            header,
            text=self.display_timestamp(message.get("created_at") if message else self.current_timestamp()),
            bg=card_bg,
            fg=self.colors["muted"],
            anchor="e",
            font=("Segoe UI", 8),
            padx=6,
            pady=6,
        ).pack(side=tk.LEFT)

        self._make_card_copy_button(
            header,
            lambda value=text: value,
            "Message copied to the system clipboard.",
            card_bg,
        ).pack(side=tk.RIGHT, padx=(0, 6), pady=5)

        tk.Button(
            header,
            text="X",
            command=lambda: self.delete_chat_card(outer, message, persist_on_delete),
            bg="#2b3240",
            fg="#f4f7fb",
            activebackground="#b42318",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            borderwidth=0,
            width=3,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.RIGHT, padx=(0, 6), pady=5)

        content_frame = tk.Frame(card, bg=card_bg)
        content_frame.pack(fill=tk.X)
        content_frame.visible = True
        if role == "assistant":
            self._render_assistant_content(content_frame, text, card_bg)
        else:
            self._render_plain_message(content_frame, text, card_bg)

        def toggle(_event=None):
            if getattr(content_frame, "visible", True):
                content_frame.pack_forget()
                content_frame.visible = False
                collapse_button.configure(text="+")
            else:
                content_frame.pack(fill=tk.X)
                content_frame.visible = True
                collapse_button.configure(text="-")
                self.after_idle(self.resize_chat_text_widgets)
            self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))

        collapse_button.configure(command=toggle)

        self.after(20, self._scroll_chat_to_bottom)
        if message is not None and not persist_on_delete:
            self.pending_user_card = {"card": outer, "message": message}
        return outer

    def link_pending_user_card(self, message):
        if not self.pending_user_card:
            return
        self.pending_user_card["message"].clear()
        self.pending_user_card["message"].update(message)
        self.pending_user_card = None

    def delete_chat_card(self, card, message, persist_on_delete=True):
        if message in self.chat_messages:
            self.chat_messages.remove(message)
            self.refresh_chat_thread_selector()
        elif self.pending_user_card and self.pending_user_card.get("card") == card:
            self.pending_user_card = None
        if card.winfo_exists():
            card.destroy()
        self.status.configure(text="Chat card removed.")


    def copy_text_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.configure(text="Code block copied to the system clipboard.")

    def _copy_value_to_clipboard(self, value_getter, status_text):
        value = value_getter() if callable(value_getter) else value_getter
        self.clipboard_clear()
        self.clipboard_append(value or "")
        self.status.configure(text=status_text)

    def _make_card_copy_button(self, parent, value_getter, status_text, bg):
        return tk.Button(
            parent,
            text="Copy",
            command=lambda: self._copy_value_to_clipboard(value_getter, status_text),
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

    def _scroll_chat_to_bottom(self):
        self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))
        self.chat_canvas.yview_moveto(1.0)
