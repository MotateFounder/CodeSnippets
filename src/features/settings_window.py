import copy
import tkinter as tk
from tkinter import ttk


class SettingsWindowDialog:
    def __init__(self, parent, settings_owner, on_close=None):
        self.parent = parent
        self.owner = settings_owner
        self.on_close = on_close
        self.window = None
        self.settings_widgets = {}
        self.action_widgets = {}
        self.refresh_settings_window_current_category = None
        self._settings_refresh_pending = False
        self._build()

    @classmethod
    def open(cls, parent, settings_owner, on_close=None):
        existing = getattr(settings_owner, "settings_window", None)
        try:
            if existing and existing.winfo_exists():
                existing.lift()
                existing.focus_set()
                return existing
        except tk.TclError:
            pass
        dialog = cls(parent, settings_owner, on_close=on_close)
        return dialog.window

    @property
    def colors(self):
        return self.owner.colors

    def _set_status(self, text):
        status = getattr(self.owner, "status", None)
        if status is not None:
            try:
                status.configure(text=text)
            except tk.TclError:
                pass

    def _build(self):
        definitions_error = ""
        try:
            rebuilt_definitions = self.owner.build_settings_definitions()
            if rebuilt_definitions:
                self.owner.settings_definitions = rebuilt_definitions
                if hasattr(self.owner, "default_settings_from_definitions") and hasattr(self.owner, "merge_nested_settings"):
                    defaults = self.owner.default_settings_from_definitions(rebuilt_definitions)
                    self.owner.settings = self.owner.merge_nested_settings(defaults, getattr(self.owner, "settings", {}))
                if hasattr(self.owner, "load_settings_profiles"):
                    self.owner.load_settings_profiles()
        except Exception as exc:
            definitions_error = str(exc)

        window = tk.Toplevel(self.parent)
        self.window = window
        self.owner.settings_window = window
        window.title("Settings")
        window.geometry("1100x760")
        window.minsize(850, 560)
        window.configure(bg=self.colors["bg"])
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.bind("<Destroy>", self._on_destroy, add="+")

        body = tk.Frame(window, bg=self.colors["bg"])
        body.pack(fill=tk.BOTH, expand=True)

        nav_frame = tk.Frame(body, bg=self.colors["panel2"], width=220)
        nav_frame.pack(side=tk.LEFT, fill=tk.Y)
        nav_frame.pack_propagate(False)

        canvas = tk.Canvas(nav_frame, bg=self.colors["panel2"], borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(nav_frame, orient=tk.VERTICAL, command=canvas.yview)
        nav_holder = tk.Frame(canvas, bg=self.colors["panel2"])
        nav_holder.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        nav_window = canvas.create_window((0, 0), window=nav_holder, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(nav_window, width=event.width))
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        content_shell = tk.Frame(body, bg=self.colors["panel"])
        content_shell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content_header = tk.Frame(content_shell, bg=self.colors["panel"])
        content_header.pack(fill=tk.X)
        content_title = tk.Label(
            content_header,
            text="",
            bg=self.colors["panel"],
            fg="#f4f7fb",
            anchor="w",
            font=("Segoe UI", 13, "bold"),
            padx=16,
            pady=0,
        )
        content_title.pack(fill=tk.X, pady=(12, 2))
        content_description = tk.Label(
            content_header,
            text="",
            bg=self.colors["panel"],
            fg=self.colors["muted"],
            anchor="w",
            justify=tk.LEFT,
            wraplength=780,
            font=("Segoe UI", 9),
            padx=16,
            pady=0,
        )
        content_description.pack(fill=tk.X, pady=(0, 12))
        content_canvas = tk.Canvas(content_shell, bg=self.colors["panel"], borderwidth=0, highlightthickness=0)
        content_scroll = ttk.Scrollbar(content_shell, orient=tk.VERTICAL, command=content_canvas.yview)
        content_frame = tk.Frame(content_canvas, bg=self.colors["panel"])
        content_frame.bind("<Configure>", lambda _event: content_canvas.configure(scrollregion=content_canvas.bbox("all")))
        content_window = content_canvas.create_window((0, 0), window=content_frame, anchor="nw")
        content_canvas.configure(yscrollcommand=content_scroll.set)
        content_canvas.bind("<Configure>", lambda event: content_canvas.itemconfigure(content_window, width=event.width))
        content_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        selected_category = {"key": None, "category": None}
        nav_buttons = {}
        categories = list(getattr(self.owner, "settings_definitions", []) or [])

        def advanced_mode_enabled():
            return bool(self.owner.get_setting("settings.advanced_mode", False))

        def visible_categories():
            advanced = advanced_mode_enabled()
            return [
                category
                for category in categories
                if advanced or not category.get("advanced_only")
            ]

        def render_category(category):
            self.collect_settings_from_window_controls()
            selected_category["key"] = category["key"]
            selected_category["category"] = category
            content_title.configure(text=category["title"])
            content_description.configure(text=category.get("description", ""))
            for key, button in nav_buttons.items():
                is_selected = key == category["key"]
                button.configure(
                    bg=self.colors["accent"] if is_selected else "#2b3240",
                    fg="#ffffff" if is_selected else self.colors["text"],
                )
            for child in content_frame.winfo_children():
                child.destroy()
            self.settings_widgets = {}
            self.action_widgets = {}
            try:
                self.render_settings_category(content_frame, category)
                self.refresh_action_buttons()
            except Exception as exc:
                tk.Label(
                    content_frame,
                    text="This settings page could not be rendered.",
                    bg=self.colors["panel"],
                    fg="#f4f7fb",
                    anchor="w",
                    font=("Segoe UI", 11, "bold"),
                    padx=16,
                    pady=0,
                ).pack(fill=tk.X, pady=(8, 2))
                tk.Label(
                    content_frame,
                    text=str(exc),
                    bg=self.colors["panel"],
                    fg=self.colors["muted"],
                    anchor="w",
                    justify=tk.LEFT,
                    wraplength=760,
                    font=("Segoe UI", 9),
                    padx=16,
                    pady=0,
                ).pack(fill=tk.X, pady=(0, 8))

        self.refresh_settings_window_current_category = lambda: (
            render_category(selected_category["category"]) if selected_category["category"] else None
        )

        def render_nav():
            for child in nav_holder.winfo_children():
                child.destroy()
            nav_buttons.clear()
            current_categories = visible_categories()
            if not current_categories:
                tk.Label(
                    nav_holder,
                    text="No settings loaded",
                    bg=self.colors["panel2"],
                    fg="#f4f7fb",
                    anchor="w",
                    justify=tk.LEFT,
                    wraplength=180,
                    font=("Segoe UI", 9, "bold"),
                    padx=12,
                    pady=10,
                ).pack(fill=tk.X, padx=10, pady=(10, 0))
                return

            for category in current_categories:
                button = tk.Button(
                    nav_holder,
                    text=category["title"],
                    command=lambda value=category: render_category(value),
                    bg="#2b3240",
                    fg=self.colors["text"],
                    activebackground=self.colors["accent"],
                    activeforeground="#ffffff",
                    relief=tk.FLAT,
                    borderwidth=0,
                    cursor="hand2",
                    anchor="w",
                    font=("Segoe UI", 9, "bold"),
                    padx=12,
                    pady=10,
                )
                button.pack(fill=tk.X, padx=10, pady=(10, 0))
                nav_buttons[category["key"]] = button

        footer = tk.Frame(window, bg=self.colors["panel2"])
        footer.pack(fill=tk.X)
        advanced_mode_var = tk.BooleanVar(value=advanced_mode_enabled())

        def toggle_advanced_mode():
            self.collect_settings_from_window_controls()
            self.owner.set_nested_setting(self.owner.settings, "settings.advanced_mode", bool(advanced_mode_var.get()))
            render_nav()
            current = selected_category.get("category")
            current_categories = visible_categories()
            current_keys = {category["key"] for category in current_categories}
            if current and current.get("key") in current_keys:
                render_category(current)
            elif current_categories:
                render_category(current_categories[0])
            else:
                selected_category["key"] = None
                selected_category["category"] = None
                content_title.configure(text="Settings unavailable")
                content_description.configure(text=definitions_error or "The settings definitions list is empty.")
                for child in content_frame.winfo_children():
                    child.destroy()

        tk.Checkbutton(
            footer,
            text="Advanced mode",
            variable=advanced_mode_var,
            command=toggle_advanced_mode,
            bg=self.colors["panel2"],
            fg=self.colors["text"],
            activebackground=self.colors["panel2"],
            activeforeground=self.colors["text"],
            selectcolor=self.colors["editor"],
            borderwidth=0,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, padx=12, pady=10)
        tk.Button(
            footer,
            text="Cancel",
            command=window.destroy,
            bg="#2b3240",
            fg=self.colors["text"],
            activebackground="#354052",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=7,
        ).pack(side=tk.RIGHT, padx=(0, 12), pady=10)
        ttk.Button(footer, text="Apply", style="Accent.TButton", command=self.apply_settings_from_window).pack(
            side=tk.RIGHT, padx=(0, 8), pady=10
        )
        ttk.Button(footer, text="Save", command=lambda: self.save_settings_window(window)).pack(
            side=tk.RIGHT, padx=(0, 8), pady=10
        )

        render_nav()
        current_categories = visible_categories()
        if current_categories:
            render_category(current_categories[0])
        else:
            content_title.configure(text="Settings unavailable")
            content_description.configure(
                text=definitions_error or "The settings definitions list is empty. Restart the app after updating the source files."
            )

    def _on_destroy(self, event):
        if event.widget is not self.window:
            return
        if getattr(self.owner, "settings_window", None) is self.window:
            self.owner.settings_window = None
        if callable(self.on_close):
            self.on_close()

    def render_settings_category(self, parent, category):
        advanced = bool(self.owner.get_setting("settings.advanced_mode", False))
        for section in category.get("sections", []):
            if section.get("advanced") and not advanced:
                continue
            section_frame = tk.Frame(parent, bg=self.colors["panel"])
            section_frame.pack(fill=tk.X, padx=16, pady=(0, 18))
            tk.Label(
                section_frame,
                text=section["title"],
                bg=self.colors["panel"],
                fg="#f4f7fb",
                anchor="w",
                font=("Segoe UI", 11, "bold"),
            ).pack(fill=tk.X, pady=(0, 8))

            for subsection in section.get("subsections", []):
                if subsection.get("advanced") and not advanced:
                    continue
                subsection_frame = tk.Frame(
                    section_frame,
                    bg=self.colors["panel2"],
                    highlightbackground="#343c4c",
                    highlightthickness=1,
                )
                subsection_frame.pack(fill=tk.X, pady=(0, 10))
                tk.Label(
                    subsection_frame,
                    text=subsection["title"],
                    bg=self.colors["panel2"],
                    fg=self.colors["text"],
                    anchor="w",
                    font=("Segoe UI", 10, "bold"),
                    padx=10,
                    pady=7,
                ).pack(fill=tk.X)
                for field in subsection.get("fields", []):
                    self.render_setting_field(subsection_frame, field)

    def render_setting_field(self, parent, field):
        row = tk.Frame(parent, bg=self.colors["panel2"])
        row.pack(fill=tk.X, padx=10, pady=(0, 9))
        label_text = field["label"] if field.get("used", True) else f"{field['label']} (reserved)"
        tk.Label(
            row,
            text=label_text,
            bg=self.colors["panel2"],
            fg="#f4f7fb",
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        ).pack(fill=tk.X)
        if field.get("description"):
            tk.Label(
                row,
                text=field["description"],
                bg=self.colors["panel2"],
                fg=self.colors["muted"],
                anchor="w",
                justify=tk.LEFT,
                wraplength=720,
                font=("Segoe UI", 8),
            ).pack(fill=tk.X, pady=(1, 4))

        if field["type"] == "action":
            button = ttk.Button(
                row,
                text=field.get("button_text", field["label"]),
                command=lambda value=field: self.run_setting_action(value),
            )
            button.pack(anchor="w", pady=(2, 0))
            self.action_widgets[field.get("action", field["key"])] = (field, button)
            self.refresh_action_buttons()
            return

        value = self.owner.get_setting(field["key"], field.get("default"))
        if field["type"] == "bool":
            variable = tk.BooleanVar(value=bool(value))
            widget = tk.Checkbutton(
                row,
                variable=variable,
                bg=self.colors["panel2"],
                fg=self.colors["text"],
                activebackground=self.colors["panel2"],
                activeforeground=self.colors["text"],
                selectcolor=self.colors["editor"],
                borderwidth=0,
                anchor="w",
            )
            widget.pack(fill=tk.X)
            self.settings_widgets[field["key"]] = (field, variable)
            variable.trace_add("write", lambda *_args: self.refresh_action_buttons())
            return

        if field["type"] == "multiline":
            widget = tk.Text(
                row,
                height=int(field.get("height", 5)),
                bg=self.colors["editor"],
                fg=self.colors["text"],
                insertbackground=self.colors["text"],
                selectbackground=self.colors["select"],
                selectforeground="#ffffff",
                wrap=tk.WORD,
                borderwidth=0,
                highlightthickness=1,
                highlightbackground=self.colors["line"],
                font=("Consolas", 9),
                padx=8,
                pady=6,
            )
            widget.insert("1.0", "" if value is None else str(value))
            widget.pack(fill=tk.X)
            self.settings_widgets[field["key"]] = (field, widget)
            widget.bind("<<Modified>>", self.on_multiline_setting_modified)
            return

        if field["type"] == "choice":
            variable = tk.StringVar(value="" if value is None else str(value))
            widget = ttk.Combobox(
                row,
                textvariable=variable,
                values=[str(choice) for choice in field.get("choices", [])],
                state="readonly",
            )
            widget.pack(fill=tk.X, ipady=3)
            self.settings_widgets[field["key"]] = (field, variable)
            variable.trace_add("write", lambda *_args: self.refresh_action_buttons())
            return

        variable = tk.StringVar(value="" if value is None else str(value))
        widget = tk.Entry(
            row,
            textvariable=variable,
            bg=self.colors["editor"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            selectbackground=self.colors["select"],
            selectforeground="#ffffff",
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            font=("Consolas", 9),
        )
        widget.pack(fill=tk.X, ipady=5)
        self.settings_widgets[field["key"]] = (field, variable)
        variable.trace_add("write", lambda *_args: self.refresh_action_buttons())

    def on_multiline_setting_modified(self, event):
        widget = event.widget
        try:
            if widget.edit_modified():
                widget.edit_modified(False)
        except tk.TclError:
            pass
        self.refresh_action_buttons()

    def run_setting_action(self, field):
        self.collect_settings_from_window_controls()
        action = field.get("action", "")
        if action == "reload_llamacpp_model" and hasattr(self.owner, "reload_llamacpp_model_from_settings"):
            self.owner.reload_llamacpp_model_from_settings()
            self.refresh_action_buttons()

    def refresh_action_buttons(self):
        for action, (_field, button) in list(getattr(self, "action_widgets", {}).items()):
            enabled = True
            if action == "reload_llamacpp_model" and hasattr(self.owner, "llamacpp_settings_have_changed"):
                current = self.preview_settings_from_window()
                enabled = self.owner.llamacpp_settings_have_changed(current)
            try:
                button.configure(state=tk.NORMAL if enabled else tk.DISABLED)
            except tk.TclError:
                pass

    def preview_settings_from_window(self):
        settings = copy.deepcopy(getattr(self.owner, "settings", {}))
        for key, item in list(self.settings_widgets.items()):
            field, control = item
            if not self.setting_control_exists(field, control):
                continue
            value = self.value_from_setting_control(field, control)
            self.owner.set_nested_setting(settings, key, value)
        return settings

    def apply_settings_from_window(self):
        self.collect_settings_from_window_controls()
        self.owner.apply_settings_to_controls()
        self.owner.save_settings_profiles()
        refresh = self.refresh_settings_window_current_category
        if callable(refresh):
            refresh()
        self._set_status("Settings applied.")

    def on_advanced_visibility_changed(self, key, variable):
        self.owner.set_nested_setting(self.owner.settings, key, bool(variable.get()))
        if self._settings_refresh_pending:
            return
        self._settings_refresh_pending = True
        self.parent.after_idle(self.refresh_settings_window_after_toggle)

    def refresh_settings_window_after_toggle(self):
        self._settings_refresh_pending = False
        refresh = self.refresh_settings_window_current_category
        if callable(refresh):
            refresh()

    def collect_settings_from_window_controls(self):
        for key, item in list(self.settings_widgets.items()):
            field, control = item
            if not self.setting_control_exists(field, control):
                continue
            value = self.value_from_setting_control(field, control)
            self.owner.set_nested_setting(self.owner.settings, key, value)

    def setting_control_exists(self, field, control):
        try:
            if field["type"] in {"bool", "string", "int", "float", "choice"}:
                return True
            return bool(control.winfo_exists())
        except tk.TclError:
            return False

    def save_settings_window(self, window):
        self.apply_settings_from_window()
        if self.owner.save_settings_file():
            window.destroy()
            self._set_status(f"Settings saved to {self.owner.settings_path.name}.")

    def value_from_setting_control(self, field, control):
        if field["type"] == "multiline":
            return control.get("1.0", "end-1c")
        value = control.get()
        if field["type"] == "bool":
            return bool(value)
        if field["type"] == "int":
            try:
                return int(value)
            except (TypeError, ValueError):
                return int(field.get("default", 0))
        if field["type"] == "float":
            try:
                return float(value)
            except (TypeError, ValueError):
                return float(field.get("default", 0.0))
        return str(value)


class SettingsWindowMixin:
    def open_settings_window(self, parent=None, on_close=None):
        return SettingsWindowDialog.open(parent or self, self, on_close=on_close)
