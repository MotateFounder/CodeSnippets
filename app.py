import tkinter as tk
from tkinter import ttk

from src.app_window import CodeSnippetCollector
from src.features.settings import SettingsMixin
from src.services.llamacpp import DEFAULT_LLAMA_CONTEXT_SIZE
from src.services.sessions import SessionManager, SessionSplash
from src.ui.styles import StyleMixin


STARTUP_COLORS = {
    "bg": "#181a1f",
    "panel": "#14171c",
    "panel2": "#1f232b",
    "line": "#303746",
    "text": "#d8dee9",
    "muted": "#8e9aac",
    "editor": "#111318",
    "accent": "#0ea5c6",
}


class StartupRoot(SettingsMixin, StyleMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.initialize_settings()
        self.colors = self.default_colors()
        self.apply_appearance_settings()
        self.status = tk.Label(self, text="", bg=self.colors["editor"], fg=self.colors["muted"])
        self._configure_styles()


def configure_startup_styles(root):
    style = ttk.Style(root)
    colors = getattr(root, "colors", STARTUP_COLORS)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "TButton",
        background=colors["panel2"],
        foreground=colors["text"],
        bordercolor=colors["line"],
        focusthickness=0,
        padding=(10, 7),
        font=("Segoe UI", 9, "bold"),
    )
    style.map(
        "TButton",
        background=[("active", colors["line"]), ("pressed", colors["panel"])],
        foreground=[("disabled", "#667085")],
    )
    style.configure(
        "Accent.TButton",
        background=colors["accent"],
        foreground="#ffffff",
        bordercolor=colors["accent"],
    )
    style.map("Accent.TButton", background=[("active", colors["accent"])])


def choose_startup_session():
    root = StartupRoot()
    configure_startup_styles(root)
    manager = SessionManager()
    splash = SessionSplash(root, manager, use_root=True)
    splash.show()
    root.mainloop()
    return (
        splash.selected_path,
        splash.selected_session,
        getattr(splash, "launched_repolens_process", None),
        getattr(splash, "llamacpp_launch_requested", True),
        getattr(splash, "llamacpp_model_path", ""),
        getattr(splash, "llamacpp_context_size", DEFAULT_LLAMA_CONTEXT_SIZE),
    )


if __name__ == "__main__":
    session_path, session_data, repolens_process, llama_launch, llama_model, llama_context = choose_startup_session()
    if session_data:
        app = CodeSnippetCollector(show_splash=False)
        app.session_manager = SessionManager()
        app.current_session_path = session_path
        app.current_session_info = session_data.get("session_info", {})
        app.load_session_data(session_data)
        app.apply_llamacpp_launch_selection(llama_launch, llama_model, llama_context)
        app.start_session_autosave()
        app.watch_repolens_process(repolens_process)
        app.status.configure(text=f"Session loaded from {session_path.name}.")
        app.mainloop()
