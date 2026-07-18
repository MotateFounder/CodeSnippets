import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.services.llamacpp import DEFAULT_LLAMA_CONTEXT_SIZE, list_gguf_models
from src.services.sessions.manager import SessionManager


class SessionSplash:
    def __init__(self, app, manager=None, use_root=False):
        self.app = app
        self.manager = manager or SessionManager()
        self.settings_path = self.manager.app_root / "settings.json"
        self.startup_settings = self._load_startup_settings()
        self.selected_path = None
        self.selected_session = None
        self.launched_repolens_process = None
        self.llamacpp_launch_requested = True
        self.llamacpp_model_path = ""
        self.llamacpp_context_size = DEFAULT_LLAMA_CONTEXT_SIZE
        self.show_archived_var = tk.BooleanVar(value=False)
        self.images = []
        self.window = app if use_root else tk.Toplevel(app)
        self.window.title("CodeSnippets")
        self.window.geometry("980x660")
        self.window.minsize(780, 520)
        self.window.configure(bg=app.colors["bg"])
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.window.bind("<Escape>", lambda _event: self._cancel())
        self._build()
        self.refresh_sessions()

    def show(self):
        self._center_window()
        self.window.update_idletasks()
        self.window.lift()
        try:
            self.window.attributes("-topmost", True)
            self.window.after(500, lambda: self.window.attributes("-topmost", False))
        except tk.TclError:
            pass
        if self.window is not self.app:
            self.window.transient(self.app)
            self.window.grab_set()
        self.window.focus_force()

    def _center_window(self):
        self.window.update_idletasks()
        width = self.window.winfo_width() or 980
        height = self.window.winfo_height() or 660
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = max(0, int((screen_width - width) / 2))
        y = max(0, int((screen_height - height) / 2))
        self.window.geometry(f"{width}x{height}+{x}+{y}")

    def _build(self):
        header = tk.Frame(self.window, bg=self.app.colors["panel2"])
        header.pack(fill=tk.X)
        logo = self._load_image(self.manager.app_root / "src" / "assets" / "images" / "CodeSnippets_logo.jpg", 100)
        if logo:
            self.images.append(logo)
            tk.Label(header, image=logo, bg=self.app.colors["panel2"]).pack(side=tk.LEFT, padx=(24, 18), pady=18)
        else:
            tk.Label(
                header,
                text="CS",
                bg=self.app.colors["accent"],
                fg="#ffffff",
                font=("Segoe UI", 24, "bold"),
                width=4,
                height=2,
            ).pack(side=tk.LEFT, padx=(24, 18), pady=18)

        title_area = tk.Frame(header, bg=self.app.colors["panel2"])
        title_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=18)
        tk.Label(
            title_area,
            text="CodeSnippets",
            bg=self.app.colors["panel2"],
            fg="#f0f3f6",
            font=("Segoe UI", 24, "bold"),
            anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            title_area,
            text="Your coding assistant.",
            bg=self.app.colors["panel2"],
            fg=self.app.colors["text"],
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(fill=tk.X, pady=(2, 0))
        tk.Label(
            title_area,
            text="Choose a workspace session or create a new one.",
            bg=self.app.colors["panel2"],
            fg=self.app.colors["muted"],
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(fill=tk.X, pady=(4, 0))
        ttk.Button(header, text="New Session", style="Accent.TButton", command=self._open_new_session_dialog).pack(
            side=tk.RIGHT, padx=24, pady=18
        )
        ttk.Button(header, text="Settings", command=self._open_settings_from_splash).pack(
            side=tk.RIGHT, padx=(0, 8), pady=18
        )

        self._build_llamacpp_controls()
        tk.Checkbutton(
            self.window,
            text="Show archived sessions",
            variable=self.show_archived_var,
            command=self.refresh_sessions,
            bg=self.app.colors["bg"],
            fg=self.app.colors["text"],
            activebackground=self.app.colors["bg"],
            activeforeground=self.app.colors["text"],
            selectcolor=self.app.colors["editor"],
            borderwidth=0,
        ).pack(anchor="w", padx=22, pady=(8, 0))

        self.empty_label = tk.Label(
            self.window,
            text="No sessions yet. Create one to begin.",
            bg=self.app.colors["bg"],
            fg=self.app.colors["muted"],
            font=("Segoe UI", 12),
        )

        self.canvas = tk.Canvas(self.window, bg=self.app.colors["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.window, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(18, 0), pady=18)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=18, padx=(0, 18))
        self.grid_frame = tk.Frame(self.canvas, bg=self.app.colors["bg"])
        self.canvas_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_grid)

    def _build_llamacpp_controls(self):
        panel = tk.Frame(self.window, bg=self.app.colors["panel"], highlightbackground=self.app.colors["line"], highlightthickness=1)
        panel.pack(fill=tk.X, padx=18, pady=(14, 0))
        tk.Label(
            panel,
            text="Llama.cpp",
            bg=self.app.colors["panel"],
            fg="#f0f3f6",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).pack(side=tk.LEFT, padx=(12, 10), pady=10)

        models = list_gguf_models()
        model_labels = [model.name for model in models]
        self.llamacpp_model_paths = {model.name: model for model in models}
        saved_model = str(self._get_setting("llamacpp.model_path", "") or "")
        saved_label = Path(saved_model).name if saved_model else ""
        default_label = saved_label if saved_label in model_labels else model_labels[0] if model_labels else ""
        self.llamacpp_model_var = tk.StringVar(value=default_label)
        self.llamacpp_model_manual_choice = False
        model_combo = ttk.Combobox(panel, textvariable=self.llamacpp_model_var, values=model_labels, state="readonly" if model_labels else "disabled", width=42)
        model_combo.bind("<<ComboboxSelected>>", lambda _event: setattr(self, "llamacpp_model_manual_choice", True))
        model_combo.pack(side=tk.LEFT, padx=(0, 12), pady=10)

        tk.Label(panel, text="Context", bg=self.app.colors["panel"], fg=self.app.colors["muted"]).pack(side=tk.LEFT, padx=(0, 6), pady=10)
        self.llamacpp_context_var = tk.IntVar(value=int(self._get_setting("llamacpp.ctx_size", DEFAULT_LLAMA_CONTEXT_SIZE) or DEFAULT_LLAMA_CONTEXT_SIZE))
        context_slider = tk.Scale(
            panel,
            from_=1000,
            to=128000,
            resolution=1000,
            orient=tk.HORIZONTAL,
            variable=self.llamacpp_context_var,
            bg=self.app.colors["panel"],
            fg=self.app.colors["text"],
            highlightthickness=0,
            troughcolor=self.app.colors["editor"],
            activebackground=self.app.colors["accent"],
            length=180,
        )
        context_slider.pack(side=tk.LEFT, padx=(0, 12), pady=4)

        self.llamacpp_skip_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            panel,
            text="Launch without Llama.cpp",
            variable=self.llamacpp_skip_var,
            bg=self.app.colors["panel"],
            fg=self.app.colors["text"],
            activebackground=self.app.colors["panel"],
            activeforeground=self.app.colors["text"],
            selectcolor=self.app.colors["editor"],
            borderwidth=0,
        ).pack(side=tk.RIGHT, padx=12, pady=10)

    def _capture_llamacpp_choices(self):
        selected_name = self.llamacpp_model_var.get().strip() if hasattr(self, "llamacpp_model_var") else ""
        model_path = getattr(self, "llamacpp_model_paths", {}).get(selected_name)
        saved_model_path = str(self._get_setting("llamacpp.model_path", "") or "")
        if saved_model_path and not getattr(self, "llamacpp_model_manual_choice", False):
            self.llamacpp_model_path = saved_model_path
        else:
            self.llamacpp_model_path = os.fspath(model_path) if model_path else saved_model_path
        self.llamacpp_context_size = int(self.llamacpp_context_var.get()) if hasattr(self, "llamacpp_context_var") else DEFAULT_LLAMA_CONTEXT_SIZE
        self.llamacpp_launch_requested = not bool(self.llamacpp_skip_var.get()) if hasattr(self, "llamacpp_skip_var") else True
        self._set_setting("llamacpp.model_path", self.llamacpp_model_path)
        self._set_setting("llamacpp.ctx_size", self.llamacpp_context_size)
        self._save_startup_settings()

    def _load_startup_settings(self):
        if hasattr(self.app, "settings"):
            return self.app.settings
        try:
            return json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _get_setting(self, key, default=None):
        if hasattr(self.app, "get_setting"):
            return self.app.get_setting(key, default)
        node = self.startup_settings
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def _set_setting(self, key, value):
        if hasattr(self.app, "set_nested_setting") and hasattr(self.app, "settings"):
            self.app.set_nested_setting(self.app.settings, key, value)
            return
        node = self.startup_settings
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def _save_startup_settings(self):
        if hasattr(self.app, "save_settings_file"):
            try:
                self.app.save_settings_file()
            except Exception:
                pass
            return
        try:
            self.settings_path.write_text(json.dumps(self.startup_settings, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _open_settings_from_splash(self):
        if hasattr(self.app, "open_settings_window"):
            self.app.open_settings_window(parent=self.window, on_close=self._refresh_llamacpp_controls_from_settings)
            return
        messagebox.showerror("Settings unavailable", "The settings window could not be opened.", parent=self.window)

    def _refresh_llamacpp_controls_from_settings(self):
        saved_model = str(self._get_setting("llamacpp.model_path", "") or "")
        saved_label = Path(saved_model).name if saved_model else ""
        self.llamacpp_model_manual_choice = False
        if saved_label and hasattr(self, "llamacpp_model_var") and saved_label in getattr(self, "llamacpp_model_paths", {}):
            self.llamacpp_model_var.set(saved_label)
        if hasattr(self, "llamacpp_context_var"):
            self.llamacpp_context_var.set(int(self._get_setting("llamacpp.ctx_size", DEFAULT_LLAMA_CONTEXT_SIZE) or DEFAULT_LLAMA_CONTEXT_SIZE))

    def refresh_sessions(self):
        for child in self.grid_frame.winfo_children():
            child.destroy()
        sessions = self.manager.list_sessions(include_archived=self.show_archived_var.get())
        self.empty_label.pack_forget()
        if not sessions:
            self.empty_label.pack(expand=True)
            return
        for index, session in enumerate(sessions):
            card = self._session_card(self.grid_frame, session)
            card.grid(row=index // 3, column=index % 3, padx=10, pady=10, sticky="nsew")
        for column in range(3):
            self.grid_frame.grid_columnconfigure(column, weight=1, minsize=240)

    def _session_card(self, parent, session):
        card = tk.Frame(parent, bg=self.app.colors["panel"], highlightbackground=self.app.colors["line"], highlightthickness=1)
        card.configure(width=285, height=235)
        card.grid_propagate(False)
        card.session = session
        card.bind("<Button-1>", lambda _event: self._choose_session(session))

        icon = self._load_image(session.get("icon_path"), 48)
        if icon:
            self.images.append(icon)
            icon_label = tk.Label(card, image=icon, bg=self.app.colors["panel"])
        else:
            initials = "".join(part[:1] for part in session["name"].split()[:2]).upper() or "CS"
            icon_label = tk.Label(
                card,
                text=initials,
                bg="#243447",
                fg="#f0f3f6",
                font=("Segoe UI", 14, "bold"),
                width=5,
                height=2,
            )
        icon_label.pack(anchor="w", padx=14, pady=(14, 6))
        icon_label.bind("<Button-1>", lambda _event: self._choose_session(session))

        self._card_label(card, session["name"], "#f0f3f6", ("Segoe UI", 11, "bold"), 1).pack(
            fill=tk.X, padx=14, pady=(0, 4)
        )
        self._card_label(card, session["description"], self.app.colors["text"], ("Segoe UI", 9), 3).pack(
            fill=tk.X, padx=14
        )
        repo = session.get("repo_path") or "No repository folder set"
        self._card_label(card, repo, self.app.colors["muted"], ("Segoe UI", 8), 2).pack(
            fill=tk.X, padx=14, pady=(8, 0)
        )
        self._card_label(card, "Updated " + session["updated_at"], self.app.colors["muted"], ("Segoe UI", 8), 1).pack(
            fill=tk.X, padx=14, pady=(6, 0)
        )
        actions = tk.Frame(card, bg=self.app.colors["panel"])
        actions.pack(fill=tk.X, padx=12, pady=(6, 0))
        ttk.Button(actions, text="Edit", command=lambda value=session: self._edit_session(value)).pack(side=tk.LEFT)
        archive_text = "Unarchive" if session.get("archived") else "Archive"
        ttk.Button(actions, text=archive_text, command=lambda value=session: self._toggle_archive(value)).pack(side=tk.LEFT, padx=(6, 0))
        return card

    def _card_label(self, parent, text, fg, font, lines):
        label = tk.Label(
            parent,
            text=text,
            bg=self.app.colors["panel"],
            fg=fg,
            font=font,
            anchor="w",
            justify=tk.LEFT,
            wraplength=248,
            height=lines,
        )
        label.bind("<Button-1>", lambda _event: self._choose_session(getattr(parent, "session", None)))
        return label

    def _choose_session(self, session):
        if not session:
            return
        try:
            data = self.manager.load_session(session["path"])
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Session failed", f"Could not open session:\n{exc}", parent=self.window)
            return
        if not self._validate_session_paths(session["path"], data):
            return
        self.selected_path = session["path"]
        self.selected_session = data
        self._capture_llamacpp_choices()
        self.window.destroy()

    def _toggle_archive(self, session):
        try:
            self.manager.set_session_archived(session["path"], not bool(session.get("archived")))
        except Exception as exc:
            messagebox.showerror("Archive failed", str(exc), parent=self.window)
            return
        self.refresh_sessions()

    def _edit_session(self, session):
        try:
            data = self.manager.load_session(session["path"])
        except Exception as exc:
            messagebox.showerror("Edit failed", str(exc), parent=self.window)
            return
        info = data.get("session_info", {})
        dialog = tk.Toplevel(self.window)
        dialog.title("Edit Session")
        dialog.configure(bg=self.app.colors["panel"])
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()
        values = {
            "name": tk.StringVar(value=session.get("name", "")),
            "repo": tk.StringVar(value=session.get("repo_path", "")),
            "icon": tk.StringVar(value=info.get("icon_path", "")),
            "repolens_enabled": tk.BooleanVar(value=bool(info.get("repolens_enabled", True))),
            "lite": tk.BooleanVar(value=True),
        }
        include_paths = self._read_path_list(info.get("include_file"))
        exclude_paths = self._read_path_list(info.get("exclude_file"))

        tk.Label(dialog, text="Name", bg=self.app.colors["panel"], fg=self.app.colors["text"]).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))
        name_entry = ttk.Entry(dialog, textvariable=values["name"], width=48)
        name_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16)

        tk.Label(dialog, text="Repository Folder", bg=self.app.colors["panel"], fg=self.app.colors["text"]).grid(row=2, column=0, sticky="w", padx=16, pady=(12, 4))
        ttk.Entry(dialog, textvariable=values["repo"], width=48).grid(row=3, column=0, sticky="ew", padx=(16, 8))
        ttk.Button(dialog, text="Browse", command=lambda: self._browse_folder(values["repo"])).grid(row=3, column=1, padx=(0, 16))

        tk.Label(dialog, text="Description", bg=self.app.colors["panel"], fg=self.app.colors["text"]).grid(row=4, column=0, sticky="w", padx=16, pady=(12, 4))
        description = tk.Text(dialog, width=48, height=5, bg=self.app.colors["editor"], fg=self.app.colors["text"], insertbackground=self.app.colors["text"], relief=tk.FLAT)
        description.insert("1.0", session.get("description", ""))
        description.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16)

        include_list = self._path_picker(
            dialog,
            "Include in RepoLens index",
            include_paths,
            6,
            repo_variable=values["repo"],
            default_text="Repository folder is included when this list is empty.",
        )
        for value in include_paths:
            include_list.insert(tk.END, value)

        exclude_list = self._path_picker(
            dialog,
            "Exclude from RepoLens index",
            exclude_paths,
            9,
            repo_variable=values["repo"],
            default_text="Optional folders/files to exclude.",
        )
        for value in exclude_paths:
            exclude_list.insert(tk.END, value)

        repolens_check = tk.Checkbutton(
            dialog,
            text="Enable RepoLens for this session",
            variable=values["repolens_enabled"],
            bg=self.app.colors["panel"],
            fg=self.app.colors["text"],
            activebackground=self.app.colors["panel"],
            activeforeground=self.app.colors["text"],
            selectcolor=self.app.colors["editor"],
            anchor="w",
        )
        repolens_check.grid(row=12, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 0))

        lite_check = tk.Checkbutton(
            dialog,
            text="Lite RepoLens index",
            variable=values["lite"],
            bg=self.app.colors["panel"],
            fg=self.app.colors["text"],
            activebackground=self.app.colors["panel"],
            activeforeground=self.app.colors["text"],
            selectcolor=self.app.colors["editor"],
            anchor="w",
        )
        lite_check.grid(row=13, column=0, columnspan=2, sticky="w", padx=16, pady=(6, 0))

        def sync_repolens_controls():
            lite_check.configure(state=tk.NORMAL if values["repolens_enabled"].get() else tk.DISABLED)

        repolens_check.configure(command=sync_repolens_controls)
        sync_repolens_controls()

        tk.Label(dialog, text="Icon", bg=self.app.colors["panel"], fg=self.app.colors["text"]).grid(row=14, column=0, sticky="w", padx=16, pady=(12, 4))
        ttk.Entry(dialog, textvariable=values["icon"], width=48).grid(row=15, column=0, sticky="ew", padx=(16, 8))
        ttk.Button(dialog, text="Browse", command=lambda: self._browse_icon(values["icon"])).grid(row=15, column=1, padx=(0, 16))

        footer = tk.Frame(dialog, bg=self.app.colors["panel"])
        footer.grid(row=16, column=0, columnspan=2, sticky="e", padx=16, pady=16)
        ttk.Button(footer, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)
        save_button = ttk.Button(footer, text="Save", style="Accent.TButton")
        save_button.configure(
            command=lambda: self._save_session_edit(
                dialog,
                session,
                values,
                description,
                include_paths,
                exclude_paths,
                save_button,
            )
        )
        save_button.pack(side=tk.RIGHT, padx=(0, 8))
        status_label = tk.Label(
            dialog,
            text="",
            bg=self.app.colors["panel"],
            fg=self.app.colors["muted"],
            anchor="w",
            justify=tk.LEFT,
            wraplength=390,
        )
        status_label.grid(row=17, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))
        dialog.repolens_status_label = status_label
        name_entry.focus_set()

    def _save_session_edit(self, dialog, session, values, description, include_paths, exclude_paths, save_button=None):
        name = values["name"].get().strip()
        repo_path = values["repo"].get().strip()
        if not name:
            messagebox.showerror("Missing name", "Please enter a session name.", parent=dialog)
            return
        if not repo_path:
            messagebox.showerror("Missing repository", "Please choose a repository folder.", parent=dialog)
            return
        if save_button:
            save_button.configure(state=tk.DISABLED)
        repolens_enabled = bool(values["repolens_enabled"].get())
        lite = bool(values["lite"].get())
        if repolens_enabled:
            self._set_create_status(dialog, "Saving session and launching RepoLens {0} index...".format("lite" if lite else "full"))
        else:
            self._set_create_status(dialog, "Saving session without RepoLens...")
        try:
            updated = self.manager.update_session_details(
                session["path"],
                name,
                repo_path,
                description.get("1.0", tk.END).strip(),
                values["icon"].get().strip(),
                include_paths=include_paths,
                exclude_paths=exclude_paths,
                repolens_enabled=repolens_enabled,
            )
            if repolens_enabled:
                self.manager.launch_session_database_terminal(session["path"], updated, lite=lite)
        except Exception as exc:
            if save_button:
                save_button.configure(state=tk.NORMAL)
            self._set_create_status(dialog, "")
            messagebox.showerror("Save failed", str(exc), parent=dialog)
            return
        dialog.destroy()
        self.refresh_sessions()

    def _read_path_list(self, path):
        if not path:
            return []
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        paths = []
        for line in lines:
            value = line.strip().strip('"')
            if value:
                paths.append(value)
        return paths

    def _validate_session_paths(self, session_path, data):
        repo_path = Path(data.get("root_folder") or data.get("session_info", {}).get("repo_path", ""))
        if repo_path and repo_path.exists():
            return True
        messagebox.showwarning(
            "Workspace missing",
            "The repository folder for this session could not be found. Choose its new location.",
            parent=self.window,
        )
        folder = filedialog.askdirectory(title="Choose repository folder", parent=self.window)
        if not folder:
            return False
        folder_path = Path(folder)
        data["root_folder"] = os.fspath(folder_path)
        session_info = data.setdefault("session_info", {})
        session_info["repo_path"] = os.fspath(folder_path)
        database_dir = Path(session_info.get("database_dir") or self.manager.session_dir_from_path(session_path) / "database")
        session_info["database_dir"] = os.fspath(database_dir)
        session_info["include_file"] = os.fspath(database_dir / "include.txt")
        session_info["exclude_file"] = os.fspath(database_dir / "exclude.txt")
        session_info["repolens_executable"] = os.fspath(database_dir / "repolens.exe")
        self.manager.write_path_list(database_dir / "include.txt", [folder_path])
        self.manager.write_path_list(database_dir / "exclude.txt", [])
        try:
            self.manager.copy_repolens_executable(database_dir / "repolens.exe")
        except Exception:
            pass
        self.manager.save_session(session_path, data)
        if bool(session_info.get("repolens_enabled", True)):
            try:
                self.launched_repolens_process = self.manager.launch_session_database_terminal(session_path, data, lite=True)
            except Exception as exc:
                messagebox.showwarning("RepoLens", "Session path was updated, but RepoLens could not start:\n{0}".format(exc), parent=self.window)
        return True

    def _open_new_session_dialog(self):
        dialog = tk.Toplevel(self.window)
        dialog.title("New Session")
        dialog.configure(bg=self.app.colors["panel"])
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()

        values = {
            "name": tk.StringVar(),
            "repo": tk.StringVar(),
            "icon": tk.StringVar(),
            "repolens_enabled": tk.BooleanVar(value=True),
            "lite": tk.BooleanVar(value=True),
        }
        include_paths = []
        exclude_paths = []
        tk.Label(dialog, text="Name", bg=self.app.colors["panel"], fg=self.app.colors["text"]).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))
        name_entry = ttk.Entry(dialog, textvariable=values["name"], width=48)
        name_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16)

        tk.Label(dialog, text="Repository Folder", bg=self.app.colors["panel"], fg=self.app.colors["text"]).grid(row=2, column=0, sticky="w", padx=16, pady=(12, 4))
        ttk.Entry(dialog, textvariable=values["repo"], width=48).grid(row=3, column=0, sticky="ew", padx=(16, 8))
        ttk.Button(dialog, text="Browse", command=lambda: self._browse_folder(values["repo"])).grid(row=3, column=1, padx=(0, 16))

        tk.Label(dialog, text="Description", bg=self.app.colors["panel"], fg=self.app.colors["text"]).grid(row=4, column=0, sticky="w", padx=16, pady=(12, 4))
        description = tk.Text(dialog, width=48, height=5, bg=self.app.colors["editor"], fg=self.app.colors["text"], insertbackground=self.app.colors["text"], relief=tk.FLAT)
        description.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16)

        include_list = self._path_picker(
            dialog,
            "Include in RepoLens index",
            include_paths,
            6,
            repo_variable=values["repo"],
            default_text="Repository folder is included when this list is empty.",
        )
        exclude_list = self._path_picker(
            dialog,
            "Exclude from RepoLens index",
            exclude_paths,
            9,
            repo_variable=values["repo"],
            default_text="Optional folders/files to exclude.",
        )

        repolens_check = tk.Checkbutton(
            dialog,
            text="Enable RepoLens for this session",
            variable=values["repolens_enabled"],
            bg=self.app.colors["panel"],
            fg=self.app.colors["text"],
            activebackground=self.app.colors["panel"],
            activeforeground=self.app.colors["text"],
            selectcolor=self.app.colors["editor"],
            anchor="w",
        )
        repolens_check.grid(row=12, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 0))

        lite_check = tk.Checkbutton(
            dialog,
            text="Lite RepoLens index",
            variable=values["lite"],
            bg=self.app.colors["panel"],
            fg=self.app.colors["text"],
            activebackground=self.app.colors["panel"],
            activeforeground=self.app.colors["text"],
            selectcolor=self.app.colors["editor"],
            anchor="w",
        )
        lite_check.grid(row=13, column=0, columnspan=2, sticky="w", padx=16, pady=(6, 0))

        def sync_repolens_controls():
            state = tk.NORMAL if values["repolens_enabled"].get() else tk.DISABLED
            lite_check.configure(state=state)

        repolens_check.configure(command=sync_repolens_controls)
        sync_repolens_controls()

        tk.Label(dialog, text="Icon", bg=self.app.colors["panel"], fg=self.app.colors["text"]).grid(row=14, column=0, sticky="w", padx=16, pady=(12, 4))
        ttk.Entry(dialog, textvariable=values["icon"], width=48).grid(row=15, column=0, sticky="ew", padx=(16, 8))
        ttk.Button(dialog, text="Browse", command=lambda: self._browse_icon(values["icon"])).grid(row=15, column=1, padx=(0, 16))

        footer = tk.Frame(dialog, bg=self.app.colors["panel"])
        footer.grid(row=16, column=0, columnspan=2, sticky="e", padx=16, pady=16)
        ttk.Button(footer, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)
        create_button = ttk.Button(
            footer,
            text="Create",
            style="Accent.TButton",
        )
        create_button.configure(
            command=lambda: self._create_session(
                dialog,
                values,
                description,
                include_paths,
                exclude_paths,
                create_button,
            )
        )
        create_button.pack(side=tk.RIGHT, padx=(0, 8))
        status_label = tk.Label(
            dialog,
            text="",
            bg=self.app.colors["panel"],
            fg=self.app.colors["muted"],
            anchor="w",
            justify=tk.LEFT,
            wraplength=390,
        )
        status_label.grid(row=17, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))
        dialog.repolens_status_label = status_label

        name_entry.focus_set()

    def _path_picker(self, dialog, title, paths, row, repo_variable=None, default_text=""):
        tk.Label(dialog, text=title, bg=self.app.colors["panel"], fg=self.app.colors["text"]).grid(
            row=row, column=0, sticky="w", padx=16, pady=(12, 4)
        )
        frame = tk.Frame(dialog, bg=self.app.colors["panel"])
        frame.grid(row=row + 1, column=0, columnspan=2, sticky="ew", padx=16)
        listbox = tk.Listbox(
            frame,
            height=3,
            bg=self.app.colors["editor"],
            fg=self.app.colors["text"],
            selectbackground=self.app.colors["accent"],
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.app.colors["line"],
        )
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        buttons = tk.Frame(frame, bg=self.app.colors["panel"])
        buttons.pack(side=tk.LEFT, padx=(8, 0), fill=tk.Y)
        ttk.Button(buttons, text="Folder", command=lambda: self._add_picker_folder(listbox, paths)).pack(fill=tk.X)
        ttk.Button(buttons, text="Files", command=lambda: self._add_picker_files(listbox, paths)).pack(fill=tk.X, pady=(5, 0))
        ttk.Button(
            buttons,
            text="Repo Items",
            command=lambda: self._add_picker_repo_items(listbox, paths, repo_variable),
        ).pack(fill=tk.X, pady=(5, 0))
        ttk.Button(buttons, text="Remove", command=lambda: self._remove_picker_path(listbox, paths)).pack(fill=tk.X, pady=(5, 0))
        if default_text:
            tk.Label(dialog, text=default_text, bg=self.app.colors["panel"], fg=self.app.colors["muted"], anchor="w").grid(
                row=row + 2, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 0)
            )
        return listbox

    def _add_picker_folder(self, listbox, paths):
        folder = filedialog.askdirectory(title="Choose folder", parent=self.window)
        if folder:
            self._append_picker_path(listbox, paths, folder)

    def _add_picker_files(self, listbox, paths):
        selected_paths = filedialog.askopenfilenames(title="Choose files", parent=self.window)
        for path in selected_paths:
            self._append_picker_path(listbox, paths, path)

    def _add_picker_repo_items(self, listbox, paths, repo_variable):
        repo_path = Path(repo_variable.get().strip()) if repo_variable else None
        if not repo_path or not repo_path.is_dir():
            messagebox.showerror(
                "Repository folder required",
                "Choose the repository folder before selecting repo items.",
                parent=self.window,
            )
            return

        dialog = tk.Toplevel(self.window)
        dialog.title("Choose Repo Items")
        dialog.configure(bg=self.app.colors["panel"])
        dialog.geometry("720x520")
        dialog.minsize(520, 380)
        dialog.transient(self.window)
        dialog.grab_set()

        tk.Label(
            dialog,
            text="Select one or more files/folders",
            bg=self.app.colors["panel"],
            fg=self.app.colors["text"],
            anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(14, 6))

        frame = tk.Frame(dialog, bg=self.app.colors["panel"])
        frame.pack(fill=tk.BOTH, expand=True, padx=14)
        tree = ttk.Treeview(frame, selectmode="extended")
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        tree.paths = {}

        root_node = tree.insert("", tk.END, text=repo_path.name or os.fspath(repo_path), open=True)
        tree.paths[root_node] = repo_path
        self._populate_repo_item_tree(tree, root_node, repo_path)
        tree.bind("<<TreeviewOpen>>", lambda _event: self._on_repo_item_tree_open(tree))

        footer = tk.Frame(dialog, bg=self.app.colors["panel"])
        footer.pack(fill=tk.X, padx=14, pady=14)
        ttk.Button(footer, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)
        ttk.Button(
            footer,
            text="Add Selected",
            style="Accent.TButton",
            command=lambda: self._finish_repo_item_selection(dialog, tree, listbox, paths),
        ).pack(side=tk.RIGHT, padx=(0, 8))

    def _populate_repo_item_tree(self, tree, node, folder):
        try:
            entries = sorted(folder.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower()))
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith(".") and entry.name not in {".gitignore", ".gitattributes", ".editorconfig"}:
                continue
            child = tree.insert(node, tk.END, text=entry.name, open=False)
            tree.paths[child] = entry
            if entry.is_dir():
                tree.insert(child, tk.END, text="loading...", open=False)

    def _on_repo_item_tree_open(self, tree):
        node = tree.focus()
        path = tree.paths.get(node)
        if not path or not path.is_dir():
            return
        children = tree.get_children(node)
        if len(children) == 1 and tree.item(children[0], "text") == "loading...":
            tree.delete(children[0])
            self._populate_repo_item_tree(tree, node, path)

    def _finish_repo_item_selection(self, dialog, tree, listbox, paths):
        for node in tree.selection():
            path = tree.paths.get(node)
            if path:
                self._append_picker_path(listbox, paths, os.fspath(path))
        dialog.destroy()

    def _append_picker_path(self, listbox, paths, path):
        if path in paths:
            return
        paths.append(path)
        listbox.insert(tk.END, path)

    def _remove_picker_path(self, listbox, paths):
        selection = listbox.curselection()
        for index in reversed(selection):
            del paths[index]
            listbox.delete(index)

    def _browse_folder(self, variable):
        folder = filedialog.askdirectory(title="Choose repository folder", parent=self.window)
        if folder:
            variable.set(folder)

    def _browse_icon(self, variable):
        path = filedialog.askopenfilename(
            title="Choose session icon",
            filetypes=[("Images", "*.jpg *.jpeg *.png"), ("All files", "*.*")],
            parent=self.window,
        )
        if path:
            variable.set(path)

    def _create_session(self, dialog, values, description, include_paths=None, exclude_paths=None, create_button=None):
        name = values["name"].get().strip()
        repo_path = values["repo"].get().strip()
        if not name:
            messagebox.showerror("Missing name", "Please enter a session name.", parent=dialog)
            return
        if not repo_path:
            messagebox.showerror("Missing repository", "Please choose a repository folder.", parent=dialog)
            return
        if create_button:
            create_button.configure(state=tk.DISABLED)
        repolens_enabled = bool(values["repolens_enabled"].get())
        lite = bool(values["lite"].get())
        mode = "lite" if lite else "full"
        if repolens_enabled:
            self._set_create_status(dialog, "Creating session and launching RepoLens {0} index...".format(mode))
        else:
            self._set_create_status(dialog, "Creating session without RepoLens...")
        path = None
        session = None
        try:
            path, session = self.manager.create_session(
                name,
                repo_path,
                description.get("1.0", tk.END).strip(),
                values["icon"].get().strip(),
                include_paths=include_paths,
                exclude_paths=exclude_paths,
                repolens_enabled=repolens_enabled,
                initialize_repolens=False,
            )
            if repolens_enabled:
                self.launched_repolens_process = self.manager.launch_session_database_terminal(path, session, lite=lite)
            else:
                self.launched_repolens_process = None
        except Exception as exc:
            self._finish_create_session(dialog, create_button, path, session, str(exc))
            return
        self._finish_create_session(dialog, create_button, path, session, None)

    def _set_create_status(self, dialog, text):
        label = getattr(dialog, "repolens_status_label", None)
        if label:
            label.configure(text=text)

    def _finish_create_session(self, dialog, create_button, path, session, error=None):
        if error and session:
            messagebox.showwarning(
                "RepoLens setup",
                "The session was created, but RepoLens could not finish the database yet:\n{0}".format(error),
                parent=dialog,
            )
        elif error:
            messagebox.showerror("Session failed", "Could not create session:\n{0}".format(error), parent=dialog)
            if create_button:
                create_button.configure(state=tk.NORMAL)
            self._set_create_status(dialog, "")
            return
        self.selected_path = path
        self.selected_session = session
        self._capture_llamacpp_choices()
        dialog.destroy()
        self.window.destroy()

    def _load_image(self, path, max_size):
        if not path:
            return None
        try:
            from PIL import Image, ImageTk

            source = Image.open(os.fspath(path))
            source.thumbnail((max_size, max_size))
            return ImageTk.PhotoImage(source)
        except (ImportError, OSError, tk.TclError):
            pass
        try:
            image = tk.PhotoImage(file=os.fspath(path))
        except tk.TclError:
            return None
        factor = max(1, int(max(image.width() / max_size, image.height() / max_size)))
        if factor > 1:
            image = image.subsample(factor, factor)
        return image

    def _update_scroll_region(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_grid(self, event):
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    def _cancel(self):
        self.selected_path = None
        self.selected_session = None
        self.window.destroy()
