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


class ChatRenderStreamMixin:
    def next_llm_request_id(self, prefix="llm"):
        value = int(getattr(self, "llm_request_counter", 0) or 0) + 1
        self.llm_request_counter = value
        return "{0}_{1}".format(prefix, value)

    def _start_streaming_assistant_card(self, request_id=None, thread_index=None):
        request_id = request_id or self.next_llm_request_id("chat")
        thread_index = self.current_chat_index if thread_index is None else thread_index
        existing_answer = self.chat_streams.get(request_id, {}).get("answer", "")
        outer = tk.Frame(self.chat_cards, bg=self.colors["editor"])
        outer.pack(fill=tk.X, padx=10, pady=(10, 0))

        card = tk.Frame(
            outer,
            bg="#1f232b",
            highlightbackground="#343c4c",
            highlightthickness=1,
        )
        card.pack(fill=tk.X, anchor="w")

        header = tk.Frame(card, bg="#1f232b")
        header.pack(fill=tk.X)

        body_holder = tk.Frame(card, bg="#1f232b")
        body_holder.pack(fill=tk.X)
        body_holder.visible = True

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
            text="Assistant",
            bg="#1f232b",
            fg="#f4f7fb",
            anchor="w",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=6,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(
            header,
            text=self.display_timestamp(self.current_timestamp()),
            bg="#1f232b",
            fg=self.colors["muted"],
            anchor="e",
            font=("Segoe UI", 8),
            padx=6,
            pady=6,
        ).pack(side=tk.LEFT)

        self._make_card_copy_button(
            header,
            lambda key=request_id: self.chat_streams.get(key, {}).get("answer", ""),
            "Streaming response copied to the system clipboard.",
            "#1f232b",
        ).pack(side=tk.RIGHT, padx=(0, 6), pady=5)

        body = tk.Text(
            body_holder,
            height=2,
            bg="#1f232b",
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
        body.insert("1.0", existing_answer or "Streaming response...")
        body.configure(state=tk.DISABLED)
        body.pack(fill=tk.X, padx=0, pady=(0, 8))
        if hasattr(self, "register_chat_text_widget"):
            self.register_chat_text_widget(body)

        def toggle():
            if getattr(body_holder, "visible", True):
                body_holder.pack_forget()
                body_holder.visible = False
                collapse_button.configure(text="+")
            else:
                body_holder.pack(fill=tk.X)
                body_holder.visible = True
                collapse_button.configure(text="-")
                self.after_idle(self.resize_chat_text_widgets)
            self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))

        collapse_button.configure(command=toggle)

        self.chat_streams[request_id] = {
            "thread_index": thread_index,
            "card": outer,
            "text": body,
            "answer": existing_answer,
        }
        self.streaming_card = outer
        self.streaming_text = body
        self.streaming_answer = ""
        self.after(20, self._scroll_chat_to_bottom)
        return request_id

    def _start_reasoning_card(self):
        outer = tk.Frame(self.chat_cards, bg=self.colors["editor"])
        outer.pack(fill=tk.X, padx=10, pady=(10, 0))

        card = tk.Frame(
            outer,
            bg="#1b202a",
            highlightbackground="#465166",
            highlightthickness=1,
        )
        card.pack(fill=tk.X, anchor="w")

        header = tk.Frame(card, bg="#1b202a")
        header.pack(fill=tk.X)

        body_holder = tk.Frame(card, bg="#1b202a")
        body_holder.pack(fill=tk.X)
        body_holder.visible = True

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
            text="Reasoning",
            bg="#1b202a",
            fg="#f4f7fb",
            anchor="w",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=6,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(
            header,
            text=self.display_timestamp(self.current_timestamp()),
            bg="#1b202a",
            fg=self.colors["muted"],
            anchor="e",
            font=("Segoe UI", 8),
            padx=6,
            pady=6,
        ).pack(side=tk.LEFT)

        self._make_card_copy_button(
            header,
            lambda: "\n".join(getattr(self, "reasoning_lines", [])),
            "Reasoning trace copied to the system clipboard.",
            "#1b202a",
        ).pack(side=tk.RIGHT, padx=(0, 6), pady=5)

        body = tk.Text(
            body_holder,
            height=2,
            bg="#1b202a",
            fg=self.colors["text"],
            selectbackground=self.colors["select"],
            selectforeground="#ffffff",
            wrap=tk.WORD,
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 9),
            padx=10,
            pady=4,
        )
        body.insert("1.0", "Starting reasoning process...")
        body.configure(state=tk.DISABLED)
        body.pack(fill=tk.X, padx=0, pady=(0, 8))
        if hasattr(self, "register_chat_text_widget"):
            self.register_chat_text_widget(body)

        def toggle():
            if getattr(body_holder, "visible", True):
                body_holder.pack_forget()
                body_holder.visible = False
                collapse_button.configure(text="+")
            else:
                body_holder.pack(fill=tk.X)
                body_holder.visible = True
                collapse_button.configure(text="-")
                self.after_idle(self.resize_chat_text_widgets)
            self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))

        collapse_button.configure(command=toggle)

        self.reasoning_card = outer
        self.reasoning_text = body
        self.reasoning_lines = []
        self.after(20, self._scroll_chat_to_bottom)

    def _update_reasoning_card(self, text):
        if not getattr(self, "reasoning_text", None) or not self.reasoning_text.winfo_exists():
            return
        self.reasoning_lines.append(text)
        max_lines = int(self.get_setting("reasoning.visible_trace_lines", 8) or 8)
        visible_lines = self.reasoning_lines[-max_lines:]
        self.reasoning_text.configure(state=tk.NORMAL)
        self.reasoning_text.delete("1.0", tk.END)
        self.reasoning_text.insert("1.0", "\n".join(visible_lines))
        if hasattr(self, "fit_chat_text_widget"):
            self.fit_chat_text_widget(self.reasoning_text)
        self.reasoning_text.configure(state=tk.DISABLED)
        self._scroll_chat_to_bottom()

    def _append_stream_chunk(self, chunk, request_id=None):
        request_id = request_id or self._latest_stream_request_id()
        stream = self.chat_streams.get(request_id)
        if not stream:
            return
        stream["answer"] = stream.get("answer", "") + chunk
        text_widget = stream.get("text")
        if not text_widget or not text_widget.winfo_exists():
            return
        if stream.get("thread_index") != self.current_chat_index:
            return
        if stream["answer"] == chunk:
            text_widget.configure(state=tk.NORMAL)
            text_widget.delete("1.0", tk.END)
        else:
            text_widget.configure(state=tk.NORMAL)

        text_widget.insert(tk.END, chunk)
        if hasattr(self, "fit_chat_text_widget"):
            self.fit_chat_text_widget(text_widget)
        text_widget.configure(state=tk.DISABLED)
        self.streaming_answer = stream["answer"]
        self._scroll_chat_to_bottom()

    def _remove_streaming_card(self, request_id=None):
        request_id = request_id or self._latest_stream_request_id()
        stream = self.chat_streams.pop(request_id, None)
        if stream and stream.get("card") and stream["card"].winfo_exists():
            stream["card"].destroy()
        if not self.chat_streams:
            self.streaming_card = None
            self.streaming_text = None
            self.streaming_answer = ""
        elif request_id is None:
            self._sync_legacy_stream_state()

    def _clear_reasoning_card_state(self):
        self.reasoning_card = None
        self.reasoning_text = None
        self.reasoning_lines = []

    def _latest_stream_request_id(self):
        if not getattr(self, "chat_streams", None):
            return None
        return next(reversed(self.chat_streams))

    def _sync_legacy_stream_state(self):
        request_id = self._latest_stream_request_id()
        stream = self.chat_streams.get(request_id, {}) if request_id else {}
        self.streaming_card = stream.get("card")
        self.streaming_text = stream.get("text")
        self.streaming_answer = stream.get("answer", "")
