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


class ChatResponseMixin:
    def extract_stream_delta(self, parsed):
        choices = parsed.get("choices", [])
        if choices:
            first = choices[0]
            delta = first.get("delta", {})
            if isinstance(delta, dict) and delta.get("content") is not None:
                return str(delta.get("content"))
            message = first.get("message", {})
            if isinstance(message, dict) and message.get("content") is not None:
                return str(message.get("content"))
            if first.get("text") is not None:
                return str(first.get("text"))
        if parsed.get("response") is not None:
            return str(parsed.get("response"))
        return ""

    def extract_chat_answer(self, parsed):
        choices = parsed.get("choices", [])
        if choices:
            first = choices[0]
            message = first.get("message", {})
            if isinstance(message, dict) and message.get("content") is not None:
                return str(message.get("content"))
            if first.get("text") is not None:
                return str(first.get("text"))
        if parsed.get("response") is not None:
            return str(parsed.get("response"))
        return json.dumps(parsed, indent=2)

    def _chat_request_finished(self, user_record, answer, error, thread_index=None, request_id=None):
        thread_index = self.current_chat_index if thread_index is None else thread_index
        if thread_index < 0 or thread_index >= len(self.chat_threads):
            thread_index = self.current_chat_index
        thread = self.chat_threads[thread_index]
        messages = thread.setdefault("messages", [])
        user_message = user_record.get("content", "")
        if error:
            self.ensure_created_at(user_record)
            if user_record not in messages:
                messages.append(user_record)
                user_record = messages[-1]
            self.update_current_thread_title(user_message, thread_index=thread_index)
            self.refresh_chat_thread_selector()
            self._remove_streaming_card(request_id)
            if thread_index == self.current_chat_index:
                self.link_pending_user_card(user_record)
            self.update_chat_input_placeholder(f"Request failed: {error}")
            self.status.configure(text="Chat request failed.")
        else:
            self.ensure_created_at(user_record)
            if user_record not in messages:
                messages.append(user_record)
                user_record = messages[-1]
            assistant_record = {
                "role": "assistant",
                "content": answer,
                "created_at": self.current_timestamp(),
                "request_id": request_id or "",
            }
            messages.append(assistant_record)
            if thread_index == self.current_chat_index:
                self.chat_messages = messages
            self.update_current_thread_title(user_message, thread_index=thread_index)
            self.refresh_chat_thread_selector()
            self._remove_streaming_card(request_id)
            if thread_index == self.current_chat_index:
                self.link_pending_user_card(user_record)
                self._append_chat_card("assistant", answer, message=assistant_record)
            self.update_chat_input_placeholder("Chat response received. Ctrl+Enter sends the next message.")
            self.status.configure(text="Chat response received.")
        self.send_chat_button.configure(state=tk.NORMAL)
