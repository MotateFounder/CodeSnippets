import csv
import json
import os
import queue
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


DISPLAYABLE_FILE_NAMES = {
    "dockerfile", "makefile", "rakefile", "gemfile", "podfile", "cmakelists.txt",
    ".gitignore", ".gitattributes", ".editorconfig", ".env", ".env.example",
}


def _search_path_key(path):
    try:
        return os.fspath(Path(path).resolve()).lower()
    except OSError:
        return os.fspath(Path(path).absolute()).lower()


def _is_displayable_file_path(path):
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name.lower() in DISPLAYABLE_FILE_NAMES


def _is_searchable_file_for_worker(path):
    try:
        if not path.is_file():
            return False
        if path.name.startswith("."):
            return False
        if not _is_displayable_file_path(path):
            return False
        return path.stat().st_size <= MAX_SEARCH_BYTES
    except OSError:
        return False


def _find_all_matches(text, term_lower):
    lowered = text.lower()
    matches = []
    start = 0
    while True:
        index = lowered.find(term_lower, start)
        if index == -1:
            break
        line = text.count("\n", 0, index) + 1
        matches.append({"index": index, "line": line})
        start = index + max(1, len(term_lower))
    return matches


def _search_preview(text, index, length):
    line_start = text.rfind("\n", 0, index) + 1
    line_end = text.find("\n", index)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end].strip()
    if len(line) > 140:
        relative = index - line_start
        start = max(0, relative - 45)
        end = min(len(line), relative + length + 75)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(line) else ""
        line = prefix + line[start:end].strip() + suffix
    return line.replace("\t", "    ")


def _queue_search_event(result_queue, run_id, event):
    try:
        result_queue.put((run_id, event))
    except Exception:
        pass


def _search_path_text_for_worker(result_queue, run_id, cancel_event, section, path, text, term, term_lower):
    if cancel_event.is_set():
        return
    matches = _find_all_matches(text, term_lower)
    if not matches:
        return
    previews = [
        {"index": match["index"], "line": match["line"], "preview": _search_preview(text, match["index"], len(term))}
        for match in matches
    ]
    _queue_search_event(
        result_queue,
        run_id,
        {
            "type": "result",
            "section": section,
            "path": Path(path),
            "matches": previews,
        },
    )


def _search_path_from_disk_for_worker(result_queue, run_id, cancel_event, section, path, term, term_lower):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    _search_path_text_for_worker(result_queue, run_id, cancel_event, section, path, text, term, term_lower)


def _run_search_worker(result_queue, run_id, cancel_event, term, plan):
    term_lower = term.lower()
    for section, source in plan:
        if cancel_event.is_set():
            break
        if section == "Open files":
            for item in source:
                if cancel_event.is_set():
                    break
                _search_path_text_for_worker(
                    result_queue,
                    run_id,
                    cancel_event,
                    section,
                    item["path"],
                    item.get("text", ""),
                    term,
                    term_lower,
                )
            continue
        if section == "Selected snippet files":
            for path in source:
                if cancel_event.is_set():
                    break
                _search_path_from_disk_for_worker(result_queue, run_id, cancel_event, section, path, term, term_lower)
            continue
        if section == "Workspace files":
            seen = source.get("seen", set())
            try:
                for path in source["root"].rglob("*"):
                    if cancel_event.is_set():
                        break
                    if not _is_searchable_file_for_worker(path):
                        continue
                    key = _search_path_key(path)
                    if key in seen:
                        continue
                    seen.add(key)
                    _search_path_from_disk_for_worker(result_queue, run_id, cancel_event, section, path, term, term_lower)
            except OSError:
                pass
    _queue_search_event(result_queue, run_id, {"type": "done", "cancelled": cancel_event.is_set()})


class SearchMixin:
    def search_folder(self):
        if not self.root_folder:
            self.status.configure(text="Open a folder before searching.")
            return

        self.cancel_active_search()
        term = self.search_var.get()
        self.clear_search_results()
        self.search_results.clear()
        self.search_match_positions.clear()
        self._highlight_search()

        if not term:
            self.status.configure(text="Enter text to search for.")
            return

        self.search_run_id = int(getattr(self, "search_run_id", 0) or 0) + 1
        run_id = self.search_run_id
        cancel_event = threading.Event()
        self.search_cancel_event = cancel_event
        self.search_active_term = term
        self.search_section_nodes = {}
        self.search_seen_paths = set()
        self.search_file_count = 0
        self.search_match_count = 0
        self.search_result_queue = queue.Queue()
        plan = self.search_plan()
        self.status.configure(text="Searching for '{0}'...".format(term))
        thread = threading.Thread(
            target=_run_search_worker,
            args=(self.search_result_queue, run_id, cancel_event, term, plan),
            daemon=True,
        )
        self.search_thread = thread
        thread.start()
        self.schedule_search_result_poll(run_id)

    def cancel_active_search(self, invalidate=True):
        cancel_event = getattr(self, "search_cancel_event", None)
        if cancel_event:
            cancel_event.set()
        self.search_cancel_event = None
        poll_after_id = getattr(self, "search_poll_after_id", None)
        if poll_after_id:
            try:
                self.after_cancel(poll_after_id)
            except tk.TclError:
                pass
            self.search_poll_after_id = None
        if invalidate:
            self.search_run_id = int(getattr(self, "search_run_id", 0) or 0) + 1

    def stop_search_worker(self, timeout=0.2):
        self.cancel_active_search()
        thread = getattr(self, "search_thread", None)
        if thread and thread.is_alive() and thread is not threading.current_thread():
            try:
                thread.join(timeout=timeout)
            except RuntimeError:
                pass

    def on_search_query_changed(self, _event=None):
        active_term = getattr(self, "search_active_term", "")
        if active_term and self.search_var.get() != active_term:
            self.cancel_active_search()
            self.search_active_term = ""
            if hasattr(self, "status"):
                self.status.configure(text="Search cancelled. Press Enter or Search to run the new query.")

    def search_plan(self):
        seen = set()
        sections = []

        open_items = []
        for data in getattr(self, "open_file_tabs", {}).values():
            path = data.get("path")
            if not path or not self._is_searchable_file(path):
                continue
            key = self.search_path_key(path)
            if key in seen:
                continue
            seen.add(key)
            text = ""
            editor = data.get("editor")
            try:
                if editor and editor.winfo_exists():
                    text = editor.get("1.0", "end-1c")
            except tk.TclError:
                text = ""
            open_items.append({"path": path, "text": text})
        sections.append(("Open files", open_items))

        snippet_paths = []
        for snippet in self.selected_search_snippets():
            path = snippet.get("source")
            if not path:
                continue
            path = Path(path)
            if not self._is_searchable_file(path):
                continue
            key = self.search_path_key(path)
            if key in seen:
                continue
            seen.add(key)
            snippet_paths.append(path)
        sections.append(("Selected snippet files", snippet_paths))

        sections.append(("Workspace files", {"root": self.root_folder, "seen": set(seen)}))
        return sections

    def selected_search_snippets(self):
        snippets = []
        for clipboard in getattr(self, "snippet_clipboards", []) or []:
            for snippet in clipboard.get("snippets", []):
                if snippet.get("selected") and not snippet.get("generated_context") and snippet.get("card_type") != "card":
                    snippets.append(snippet)
        if snippets:
            return snippets
        return [
            snippet
            for snippet in getattr(self, "snippets", []) or []
            if snippet.get("selected") and not snippet.get("generated_context") and snippet.get("card_type") != "card"
        ]

    def search_path_key(self, path):
        return _search_path_key(path)

    def queue_search_event(self, run_id, event):
        result_queue = getattr(self, "search_result_queue", None)
        if not result_queue:
            return
        try:
            result_queue.put((run_id, event))
        except Exception:
            pass

    def schedule_search_result_poll(self, run_id):
        try:
            self.search_poll_after_id = self.after(40, lambda value=run_id: self.poll_search_results(value))
        except tk.TclError:
            pass

    def poll_search_results(self, run_id):
        if run_id != getattr(self, "search_run_id", None):
            return
        result_queue = getattr(self, "search_result_queue", None)
        if not result_queue:
            return
        finished = False
        try:
            for _ in range(50):
                event_run_id, event = result_queue.get_nowait()
                if event_run_id != run_id:
                    continue
                if event.get("type") == "result":
                    self.append_search_result(run_id, event["section"], event["path"], event["matches"])
                elif event.get("type") == "done":
                    finished = True
                    self.search_poll_after_id = None
                    self.finish_search_run(run_id, cancelled=bool(event.get("cancelled")))
                    break
        except queue.Empty:
            pass
        if not finished and run_id == getattr(self, "search_run_id", None):
            self.schedule_search_result_poll(run_id)

    def append_search_result(self, run_id, section, path, matches):
        if run_id != getattr(self, "search_run_id", None):
            return
        key = self.search_path_key(path)
        if key in getattr(self, "search_seen_paths", set()):
            return
        self.search_seen_paths.add(key)
        header = self.search_section_nodes.get(section)
        if not header or not self.results_tree.exists(header):
            header = self.results_tree.insert("", tk.END, text=section, open=True)
            self.search_result_rows[header] = {"type": "separator"}
            self.search_section_nodes[section] = header

        self.search_file_count += 1
        self.search_match_count += len(matches)
        self.search_results.append(path)
        self.search_match_positions[path] = matches[0]["index"]
        file_node = self.results_tree.insert(header, tk.END, text=f"{self._relative(path)} ({len(matches)})", open=True)
        self.search_result_rows[file_node] = {"type": "file", "path": path}
        for match in matches:
            child = self.results_tree.insert(
                file_node,
                tk.END,
                text=f"Line {match['line']}: {match['preview']}",
            )
            self.search_result_rows[child] = {
                "type": "match",
                "path": path,
                "index": match["index"],
                "line": match["line"],
            }
        self.status.configure(
            text="Searching... found {0} match{1} in {2} file{3}.".format(
                self.search_match_count,
                "" if self.search_match_count == 1 else "es",
                self.search_file_count,
                "" if self.search_file_count == 1 else "s",
            )
        )

    def finish_search_run(self, run_id, cancelled=False):
        if run_id != getattr(self, "search_run_id", None):
            return
        if getattr(self, "search_cancel_event", None):
            self.search_cancel_event = None
        if cancelled:
            self.status.configure(text="Search cancelled.")
            return
        file_suffix = "" if self.search_file_count == 1 else "s"
        match_suffix = "" if self.search_match_count == 1 else "es"
        self.status.configure(text=f"Found {self.search_match_count} match{match_suffix} in {self.search_file_count} file{file_suffix}.")

    def clear_search_results(self):
        self.cancel_active_search()
        if hasattr(self, "results_tree"):
            self.results_tree.delete(*self.results_tree.get_children())
        self.search_result_rows.clear()
        self.search_section_nodes = {}
        self.search_seen_paths = set()

    def find_all_matches(self, text, term_lower):
        return _find_all_matches(text, term_lower)

    def search_preview(self, text, index, length):
        return _search_preview(text, index, length)

    def _is_searchable_file(self, path):
        if not path.is_file():
            return False
        if path.name.startswith("."):
            return False
        if not self.is_displayable_tree_entry(path):
            return False
        try:
            return path.stat().st_size <= MAX_SEARCH_BYTES
        except OSError:
            return False

    def _is_searchable_file_for_worker(self, path):
        return _is_searchable_file_for_worker(path)

    def _is_displayable_file_path(self, path):
        return _is_displayable_file_path(path)

    def _highlight_search(self):
        if not self.editor:
            return
        self.editor.tag_remove("search", "1.0", tk.END)
        term = self.search_var.get()
        if not term:
            return

        start = "1.0"
        while True:
            index = self.editor.search(term, start, stopindex=tk.END, nocase=True)
            if not index:
                break
            end = f"{index}+{len(term)}c"
            self.editor.tag_add("search", index, end)
            start = end

    def jump_to_search_match(self, path, match_index=None):
        if match_index is None:
            match_index = self.search_match_positions.get(path)
        term = self.search_var.get()
        if match_index is None or not term or not self.editor:
            return

        start = f"1.0+{match_index}c"
        end = f"{start}+{len(term)}c"
        self.editor.mark_set(tk.INSERT, start)
        self.editor.tag_remove(tk.SEL, "1.0", tk.END)
        self.editor.tag_add(tk.SEL, start, end)
        self.editor.see(start)
        self.editor.focus_set()
        self.status.configure(text=f"Opened first match in {self._relative(path)}.")
