import tkinter as tk
from tkinter import ttk

from src.ui.appearance_themes import APPEARANCE_THEMES
from src.ui.widget_hints import WidgetHintsMixin


class StyleMixin(WidgetHintsMixin):
    def default_colors(self):
        return dict(APPEARANCE_THEMES["Night Watercolor"])

    def apply_appearance_settings(self):
        if not hasattr(self, "settings"):
            self.colors = self.default_colors()
            return
        theme = str(self.get_setting("appearance.theme", "Night Watercolor") or "Night Watercolor")
        colors = dict(APPEARANCE_THEMES.get(theme, APPEARANCE_THEMES["Night Watercolor"]))
        for key in (
            "bg", "panel", "panel2", "line", "text", "muted", "editor", "accent",
            "select", "highlight", "highlight_text", "comment", "keyword", "string", "number",
        ):
            value = str(self.get_setting("appearance.colors.{0}".format(key), "") or "").strip()
            if value:
                colors[key] = value
        self.colors = colors
        try:
            self.configure(bg=self.colors["bg"])
            self.option_add("*Font", self.ui_font("base"))
            self.option_add("*Text.Font", self.code_font("code"))
            self.option_add("*Entry.Font", self.ui_font("base"))
            self.option_add("*Listbox.Font", self.ui_font("base"))
        except tk.TclError:
            pass
        if hasattr(self, "status"):
            self.refresh_appearance_on_widgets()
        if hasattr(self, "_configure_styles"):
            self._configure_styles()

    def appearance_font_size(self, key, fallback):
        try:
            return max(7, int(self.get_setting("appearance.text.{0}".format(key), fallback) or fallback))
        except (TypeError, ValueError):
            return fallback

    def ui_font(self, size_key="base", weight="normal", family="Segoe UI"):
        size = self.appearance_font_size(size_key, {"small": 8, "base": 9, "title": 10, "code": 9}.get(size_key, 9))
        if weight and weight != "normal":
            return (family, size, weight)
        return (family, size)

    def code_font(self, size_key="code", weight="normal"):
        return self.ui_font(size_key, weight=weight, family="Consolas")

    def refresh_appearance_on_widgets(self):
        self._refresh_widget_appearance(self)

    def _refresh_widget_appearance(self, widget):
        try:
            if isinstance(widget, (tk.Frame, tk.Canvas)):
                current = str(widget.cget("bg"))
                if current:
                    widget.configure(bg=self.closest_palette_color(current, fallback=self.colors["panel"]))
            elif isinstance(widget, tk.Label):
                widget.configure(
                    bg=self.closest_palette_color(str(widget.cget("bg")), fallback=self.colors["panel"]),
                    fg=self.closest_palette_color(str(widget.cget("fg")), fallback=self.colors["text"]),
                )
            elif isinstance(widget, (tk.Entry, tk.Text, tk.Listbox)):
                widget.configure(
                    bg=self.closest_palette_color(str(widget.cget("bg")), fallback=self.colors["editor"]),
                    fg=self.closest_palette_color(str(widget.cget("fg")), fallback=self.colors["text"]),
                    insertbackground=self.colors["text"],
                    selectbackground=self.colors["select"],
                    selectforeground="#ffffff",
                )
                if isinstance(widget, (tk.Entry, tk.Text)):
                    try:
                        widget.configure(highlightbackground=self.colors["line"], highlightcolor=self.colors["accent"])
                    except tk.TclError:
                        pass
            elif isinstance(widget, tk.Checkbutton):
                widget.configure(
                    bg=self.closest_palette_color(str(widget.cget("bg")), fallback=self.colors["panel2"]),
                    fg=self.colors["text"],
                    activebackground=self.closest_palette_color(str(widget.cget("activebackground")), fallback=self.colors["panel2"]),
                    activeforeground=self.colors["text"],
                    selectcolor=self.colors["editor"],
                )
            elif isinstance(widget, tk.Button):
                widget.configure(
                    bg=self.colors["panel2"],
                    fg=self.colors["text"],
                    activebackground=self.colors["accent"],
                    activeforeground="#ffffff",
                )
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._refresh_widget_appearance(child)

    def closest_palette_color(self, color, fallback):
        current = str(color or "").lower()
        for key, value in self.colors.items():
            if current == str(value).lower():
                return self.colors.get(key, fallback)
        legacy = {
            "#181a1f": "bg",
            "#14171c": "panel",
            "#1f232b": "panel2",
            "#303746": "line",
            "#d8dee9": "text",
            "#8e9aac": "muted",
            "#111318": "editor",
            "#0ea5c6": "accent",
            "#146db4": "select",
            "#ffd166": "highlight",
            "#6a9955": "comment",
            "#58a6ff": "keyword",
            "#ce9178": "string",
            "#b5cea8": "number",
            "#f0f3f6": "text",
            "#f4f7fb": "text",
            "#2b3240": "panel2",
            "#354052": "line",
            "#343c4c": "line",
        }
        key = legacy.get(current)
        return self.colors.get(key, fallback) if key else fallback

    def _configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=self.colors["bg"])
        style.configure("Panel.TFrame", background=self.colors["panel"])
        style.configure("Header.TFrame", background=self.colors["panel2"])
        style.configure(".", font=self.ui_font("base"))
        style.configure(
            "Middle.TNotebook",
            background=self.colors["bg"],
            borderwidth=0,
            tabmargins=(6, 6, 6, 0),
        )
        style.configure(
            "Middle.TNotebook.Tab",
            background="#2b3240",
            foreground=self.colors["text"],
            padding=(14, 7),
            font=self.ui_font("base", "bold"),
        )
        style.map(
            "Middle.TNotebook.Tab",
            background=[("selected", self.colors["panel2"]), ("active", "#354052")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "TButton",
            background="#2b3240",
            foreground=self.colors["text"],
            bordercolor="#465166",
            focusthickness=0,
            padding=(10, 7),
            font=self.ui_font("base", "bold"),
        )
        style.map(
            "TButton",
            background=[("active", "#354052"), ("pressed", "#202632")],
            foreground=[("disabled", "#667085")],
        )
        style.configure(
            "Accent.TButton",
            background=self.colors["accent"],
            foreground="#ffffff",
            bordercolor="#65d6ea",
        )
        style.map("Accent.TButton", background=[("active", "#12b8dc")])
        style.configure(
            "Treeview",
            background=self.colors["editor"],
            foreground=self.colors["text"],
            fieldbackground=self.colors["editor"],
            bordercolor=self.colors["line"],
            rowheight=max(22, self.appearance_font_size("base", 9) + 15),
            font=self.ui_font("base"),
        )
        style.map(
            "Treeview",
            background=[("selected", self.colors["accent"])],
            foreground=[("selected", "#ffffff")],
        )
