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


class PromptPresetsMixin:
    def load_prompt_presets(self):
        path = filedialog.askopenfilename(
            title="Load prompt presets CSV",
            filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            presets = self.read_prompt_presets(Path(path))
        except OSError as exc:
            messagebox.showerror("Prompt load failed", f"Could not load prompt presets:\n{exc}")
            return
        if not presets:
            messagebox.showwarning("No prompts found", "No prompt presets were found in the selected file.")
            return
        self.prompt_csv_path = path
        self.set_nested_setting(self.settings, "prompt_presets.csv_path", path)
        self.prompt_presets = presets
        self.refresh_prompt_preset_dropdown()
        self.status.configure(text=f"Loaded {len(presets)} prompt preset(s).")

    def read_prompt_presets(self, path):
        presets = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=";")
            for row in reader:
                if not row or not any(cell.strip() for cell in row):
                    continue
                prompt = row[0].strip()
                if not prompt or prompt.lower() == "prompt":
                    continue
                tags = row[1].strip() if len(row) > 1 else ""
                explanation = row[2].strip() if len(row) > 2 else ""
                presets.append({"prompt": prompt, "tags": tags, "explanation": explanation})
        return presets

    def refresh_prompt_preset_dropdown(self):
        if not hasattr(self, "prompt_combo"):
            return
        values = []
        for index, preset in enumerate(self.prompt_presets, start=1):
            explanation = preset.get("explanation") or preset.get("prompt", "")
            tags = preset.get("tags", "")
            label = f"{index}. {explanation[:70]}"
            if tags:
                label += f" [{tags}]"
            values.append(label)
        self.prompt_combo.configure(values=values)
        if values:
            if getattr(self, "prompt_controls_visible", False) and not self.prompt_combo.winfo_manager():
                self.prompt_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
            self.prompt_combo.configure(state="readonly")
            self.prompt_combo.current(0)
        else:
            self.prompt_combo.set("")
            self.prompt_combo.configure(state=tk.DISABLED)
            if self.prompt_combo.winfo_manager():
                self.prompt_combo.pack_forget()


    def append_selected_prompt_preset(self, _event=None):
        if not hasattr(self, "prompt_combo"):
            return
        index = self.prompt_combo.current()
        if index < 0 or index >= len(self.prompt_presets):
            return
        prompt = self.prompt_presets[index].get("prompt", "")
        if not prompt:
            return
        self._hide_chat_input_placeholder()
        existing = self.chat_input.get("1.0", "end-1c")
        if existing.strip():
            self.chat_input.insert(tk.END, "\n\n")
        self.chat_input.insert(tk.END, prompt)
        self.chat_input.focus_set()
        self.refresh_token_count()
        self.status.configure(text="Prompt preset appended to the message.")
