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


class FileBrowserMixin:
    def choose_folder(self):
        if not self.confirm_discard_unsaved():
            return

        folder = filedialog.askdirectory(title="Select source folder")
        if not folder:
            return

        self.root_folder = Path(folder)
        self.current_file = None
        self.current_file_text = ""
        self.current_file_dirty = False
        self.close_all_editor_tabs(confirm=False)
        self._set_save_file_enabled(False)
        self.refresh_file_browser()
        self.clear_search_results()
        self.search_results.clear()
        self.search_match_positions.clear()
        self.folder_label.configure(text=str(self.root_folder))
        self.refresh_workspace_header()
        self._clear_active_editor()
        self.status.configure(text="Folder loaded. Browse files or search for text.")

    def refresh_workspace_header(self):
        if hasattr(self, "workspace_name_label"):
            info = getattr(self, "current_session_info", {}) or {}
            name = info.get("name") or (Path(self.root_folder).name if getattr(self, "root_folder", None) else "Workspace")
            self.workspace_name_label.configure(text=str(name))
        if hasattr(self, "folder_label"):
            self.folder_label.configure(text=str(getattr(self, "root_folder", "") or "No folder selected"))

    def confirm_discard_unsaved(self):
        dirty_files = [data["path"].name for data in self.open_file_tabs.values() if data["dirty"]]
        if not dirty_files:
            return True
        if len(dirty_files) == 1:
            message = f"{dirty_files[0]} has unsaved changes. Continue without saving them?"
        else:
            message = f"{len(dirty_files)} open files have unsaved changes. Continue without saving them?"
        return messagebox.askyesno(
            "Unsaved file changes",
            message,
        )

    def close_all_editor_tabs(self, confirm=True):
        for editor_data in list(self.open_file_tabs.values()):
            if confirm:
                if not self.close_editor_tab(editor_data):
                    return False
            else:
                if hasattr(self, "editor_tabs"):
                    self.editor_tabs.forget(editor_data["frame"])
                editor_data["frame"].destroy()
        self.open_file_tabs.clear()
        self._clear_active_editor()
        return True

    def refresh_file_browser(self):
        if not self.root_folder:
            return
        expanded_paths = self._expanded_file_tree_paths()
        self.file_items.clear()
        self.file_tree.delete(*self.file_tree.get_children())
        self._insert_tree_node("", self.root_folder)
        self._restore_expanded_file_tree_paths(expanded_paths)
        self.status.configure(text="File browser refreshed.")

    def _expanded_file_tree_paths(self):
        expanded = set()
        if not hasattr(self, "file_tree"):
            return expanded
        for node, path in list(getattr(self, "file_items", {}).items()):
            try:
                if path and path.is_dir() and self.file_tree.item(node, "open"):
                    expanded.add(os.fspath(path.resolve()))
            except (OSError, tk.TclError):
                continue
        return expanded

    def _restore_expanded_file_tree_paths(self, expanded_paths):
        if not expanded_paths or not getattr(self, "root_folder", None):
            return
        try:
            root_key = os.fspath(self.root_folder.resolve())
        except OSError:
            return
        if root_key in expanded_paths:
            self._reveal_file_tree_path(self.root_folder)
        for path_text in sorted(expanded_paths, key=lambda value: len(Path(value).parts)):
            path = Path(path_text)
            if path == self.root_folder:
                continue
            if path.exists():
                self._reveal_file_tree_path(path)

    def create_file_in_selected_folder(self):
        folder = self._selected_file_tree_folder()
        if not folder:
            if self.root_folder:
                folder = self.root_folder
            else:
                self.status.configure(text="Open a folder before creating files.")
                return

        self._create_file_in_folder(folder)

    def _selected_file_tree_folder(self):
        selection = self.file_tree.selection()
        node = selection[0] if selection else self.file_tree.focus()
        path = self.file_items.get(node)
        if not path:
            return None
        return path if path.is_dir() else path.parent

    def _create_file_in_folder(self, folder):
        if not self.root_folder:
            self.status.configure(text="Open a folder before creating files.")
            return

        try:
            folder.resolve().relative_to(self.root_folder.resolve())
        except ValueError:
            messagebox.showerror("Create file failed", "The selected folder is outside the loaded workspace.")
            return

        filename = simpledialog.askstring(
            "New file",
            f"Create file in:\n{folder}\n\nFile name:",
            parent=self,
        )
        if filename is None:
            return

        filename = filename.strip()
        if not filename:
            self.status.configure(text="File creation cancelled: no file name entered.")
            return
        if filename in {".", ".."} or Path(filename).name != filename:
            messagebox.showerror("Invalid file name", "Enter a single file name without folder separators.")
            return

        target = folder / filename
        try:
            target.resolve().relative_to(self.root_folder.resolve())
        except ValueError:
            messagebox.showerror("Create file failed", "The new file must be inside the loaded workspace.")
            return
        if target.exists():
            messagebox.showerror("Create file failed", f"{target.name} already exists.")
            return

        try:
            target.touch()
        except OSError as exc:
            messagebox.showerror("Create file failed", f"Could not create file:\n{exc}")
            return

        self.refresh_file_browser()
        self._reveal_file_tree_path(target)
        self.open_file(target)
        self.status.configure(text=f"Created {target}.")

    def _show_file_tree_context_menu(self, event):
        node = self.file_tree.identify_row(event.y)
        if node:
            self.file_tree.selection_set(node)
            self.file_tree.focus(node)

        path = self.file_items.get(node)
        folder = path if path and path.is_dir() else path.parent if path else None

        menu = tk.Menu(self, tearoff=False)
        if path and path.is_file():
            menu.add_command(label="Open", command=lambda selected=path: self.open_file(selected))
        if folder:
            menu.add_command(label="New File Here", command=lambda selected=folder: self._create_file_in_folder(selected))
        elif self.root_folder:
            menu.add_command(label="New File in Root", command=lambda: self._create_file_in_folder(self.root_folder))
        else:
            menu.add_command(label="New File", state=tk.DISABLED)
        menu.add_separator()
        menu.add_command(label="Refresh", command=self.refresh_file_browser)
        if path:
            menu.add_separator()
            menu.add_command(label="Copy Path", command=lambda selected=path: self._copy_file_tree_path(selected))

        menu.tk_popup(event.x_root, event.y_root)

    def _copy_file_tree_path(self, path):
        self.clipboard_clear()
        self.clipboard_append(os.fspath(path))
        self.status.configure(text=f"Copied path: {path}")

    def open_workspace_folder(self):
        if not getattr(self, "root_folder", None):
            return
        try:
            os.startfile(os.fspath(self.root_folder))
        except Exception as exc:
            messagebox.showerror("Open folder failed", str(exc), parent=self)

    def focus_search_entry(self, _event=None):
        if hasattr(self, "search_entry"):
            self.search_entry.focus_set()
            self.search_entry.selection_range(0, tk.END)
            return "break"
        return None

    def _reveal_file_tree_path(self, target):
        try:
            relative_parts = target.resolve().relative_to(self.root_folder.resolve()).parts
        except (OSError, ValueError):
            return

        nodes = self.file_tree.get_children("")
        if not nodes:
            return

        current_node = nodes[0]
        current_path = self.file_items.get(current_node)
        self.file_tree.item(current_node, open=True)

        for part in relative_parts:
            if not current_path or not current_path.is_dir():
                return
            self._ensure_tree_directory_populated(current_node, current_path)
            next_node = None
            for child in self.file_tree.get_children(current_node):
                child_path = self.file_items.get(child)
                if child_path and child_path.name == part:
                    next_node = child
                    current_path = child_path
                    break
            if not next_node:
                return
            current_node = next_node
            self.file_tree.item(current_node, open=current_path.is_dir())

        self.file_tree.selection_set(current_node)
        self.file_tree.focus(current_node)
        self.file_tree.see(current_node)

    def _ensure_tree_directory_populated(self, node, path):
        children = self.file_tree.get_children(node)
        if len(children) == 1 and self.file_tree.item(children[0], "text") == "loading...":
            self.file_tree.delete(children[0])
            self._populate_directory(node, path)

    def _insert_tree_node(self, parent, path):
        label = path.name if path.name else str(path)
        node = self.file_tree.insert(parent, tk.END, text=label, open=False)
        self.file_items[node] = path
        if path.is_dir() and self.directory_has_displayable_files(path):
            self.file_tree.insert(node, tk.END, text="loading...")
        return node

    def _on_tree_open(self, _event):
        node = self.file_tree.focus()
        path = self.file_items.get(node)
        if not path or not path.is_dir():
            return

        children = self.file_tree.get_children(node)
        if len(children) == 1 and self.file_tree.item(children[0], "text") == "loading...":
            self.file_tree.delete(children[0])
            self._populate_directory(node, path)

    def _populate_directory(self, node, path):
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return

        for entry in entries:
            if entry.name.startswith("."):
                continue
            if not self.is_displayable_tree_entry(entry):
                continue
            self._insert_tree_node(node, entry)

    def is_displayable_tree_entry(self, path):
        if path.is_dir():
            return self.directory_has_displayable_files(path)
        return path.suffix.lower() in TEXT_EXTENSIONS or path.name.lower() in {
            "dockerfile", "makefile", "rakefile", "gemfile", "podfile", "cmakelists.txt",
            ".gitignore", ".gitattributes", ".editorconfig", ".env", ".env.example",
        }

    def directory_has_displayable_files(self, path):
        try:
            for entry in path.iterdir():
                if entry.name.startswith(".") and entry.name not in {".gitignore", ".gitattributes", ".editorconfig"}:
                    continue
                if entry.is_file() and self.is_displayable_tree_entry(entry):
                    return True
                if entry.is_dir() and self.directory_has_displayable_files(entry):
                    return True
        except OSError:
            return False
        return False

    def _on_tree_double_click(self, _event):
        node = self.file_tree.focus()
        path = self.file_items.get(node)
        if path and path.is_file():
            self.open_file(path)

    def _open_selected_result(self, _event):
        selection = self.results_tree.selection()
        if not selection:
            return
        node = selection[0]
        row = self.search_result_rows.get(node)
        if not row:
            return
        if row["type"] == "file":
            self.results_tree.item(node, open=not self.results_tree.item(node, "open"))
        elif row["type"] == "match":
            path = row["path"]
            self.open_file(path)
            self.jump_to_search_match(path, row["index"])
