import tkinter as tk
import threading
import queue

from src.features.chat_api import ChatApiMixin
from src.features.chat_response import ChatResponseMixin
from src.features.chat_cards import ChatCardsMixin
from src.features.chat_input import ChatInputMixin
from src.features.chat_render_stream import ChatRenderStreamMixin
from src.features.chat_threads import ChatThreadsMixin
from src.features.context import ContextMixin
from src.features.editor_actions import EditorActionsMixin
from src.features.editor_tab_state import EditorTabStateMixin
from src.features.editor_tabs import EditorTabsMixin
from src.features.file_browser import FileBrowserMixin
from src.features.markdown_render import MarkdownRenderMixin
from src.features.prompt_presets import PromptPresetsMixin
from src.features.search import SearchMixin
from src.features.session_io import SessionIOMixin
from src.features.session_load import SessionLoadMixin
from src.features.settings import SettingsMixin
from src.features.snippet_cards import SnippetCardsMixin
from src.features.snippet_io import SnippetIOMixin
from src.features.syntax import SyntaxMixin
from src.features.timestamps import TimestampMixin
from src.features.llamacpp_provider_selection import LlamaCppProviderSelectionMixin
from src.services.activityReport import ActivityReportMixin
from src.services.notebook import NotebookMixin
from src.services.promptManager import PromptManagerMixin
from src.services.sessions import SessionManager, SessionSplash
from src.services.llmQueue import LLMRequestQueue
from src.services.llamacpp import DEFAULT_LLAMA_CONTEXT_SIZE
from src.ui.layout_chat import LayoutChatMixin
from src.ui.layout_editor import LayoutEditorMixin
from src.ui.layout_left import LayoutLeftMixin
from src.ui.layout_main import LayoutMainMixin
from src.ui.layout_snippets import LayoutSnippetsMixin
from src.ui.styles import StyleMixin


class CodeSnippetCollector(
    StyleMixin,
    LayoutMainMixin,
    LayoutLeftMixin,
    LayoutEditorMixin,
    LayoutSnippetsMixin,
    LayoutChatMixin,
    FileBrowserMixin,
    EditorTabsMixin,
    EditorTabStateMixin,
    EditorActionsMixin,
    SearchMixin,
    SyntaxMixin,
    SnippetCardsMixin,
    ContextMixin,
    SnippetIOMixin,
    SessionIOMixin,
    SessionLoadMixin,
    ChatThreadsMixin,
    PromptPresetsMixin,
    ChatInputMixin,
    ChatApiMixin,
    ChatResponseMixin,
    ChatRenderStreamMixin,
    ChatCardsMixin,
    MarkdownRenderMixin,
    TimestampMixin,
    LlamaCppProviderSelectionMixin,
    ActivityReportMixin,
    NotebookMixin,
    PromptManagerMixin,
    SettingsMixin,
    tk.Tk,
):
    def __init__(self, show_splash=True):
        super().__init__()
        self.title("Code Snippet Collector")
        self.geometry("1800x900")
        self.minsize(1250, 650)

        self.root_folder = None
        self.current_file = None
        self.current_file_text = ""
        self.current_file_dirty = False
        self.open_file_tabs = {}
        self.syntax_after_id = None
        self.snippets = []
        self.snippet_cards = []
        self.snippet_clipboards = [
            {
                "id": self.create_clipboard_id(),
                "name": "Snippets 1",
                "category": "General",
                "snippets": self.snippets,
            }
        ]
        self.active_snippet_clipboard_index = 0
        self.file_items = {}
        self.search_results = []
        self.search_match_positions = {}
        self.search_result_rows = {}
        self.streaming_card = None
        self.streaming_text = None
        self.streaming_answer = ""
        self.chat_streams = {}
        self.llm_request_counter = 0
        self.pending_user_card = None
        self.chat_threads = [{"title": "Chat 1", "messages": []}]
        self.current_chat_index = 0
        self.chat_messages = self.chat_threads[0]["messages"]
        self.prompt_presets = []
        self.prompt_preset_var = tk.StringVar()
        self.prompt_csv_path = ""
        self.ui_queue = queue.Queue()
        self.llm_queue = LLMRequestQueue(on_state_change=self.on_llm_queue_state_change)
        self.session_manager = SessionManager()
        self.current_session_path = None
        self.current_session_info = {}
        self.autosave_after_id = None
        self.llamacpp_process = None
        self.session_save_lock = threading.Lock()
        self.initialize_settings()
        self.initialize_notebook()
        self.initialize_prompt_manager()

        self.colors = self.default_colors()
        self.apply_appearance_settings()

        self.configure(bg=self.colors["bg"])
        self._configure_styles()
        self._build_ui()
        self.start_context_budget_polling()
        self.protocol("WM_DELETE_WINDOW", self.close_application)
        self.after(50, self.process_ui_queue)
        self.apply_settings_to_controls()
        self._bind_shortcuts()
        if show_splash:
            self._show_startup_splash()

    def _show_startup_splash(self):
        self.withdraw()
        splash = SessionSplash(self, self.session_manager)
        splash.show()
        self.wait_window(splash.window)
        if not splash.selected_session:
            self.destroy()
            return
        self.current_session_path = splash.selected_path
        self.current_session_info = splash.selected_session.get("session_info", {})
        self.load_session_data(splash.selected_session)
        self.apply_llamacpp_launch_selection(
            getattr(splash, "llamacpp_launch_requested", True),
            getattr(splash, "llamacpp_model_path", ""),
            getattr(splash, "llamacpp_context_size", DEFAULT_LLAMA_CONTEXT_SIZE),
        )
        self.start_session_autosave()
        self.watch_repolens_process(getattr(splash, "launched_repolens_process", None))
        if hasattr(self, "status"):
            self.status.configure(text=f"Session loaded from {splash.selected_path.name}.")
        self.deiconify()

    def watch_repolens_process(self, process):
        if not process:
            return

        def worker():
            try:
                process.wait()
            except Exception:
                return
            self.after(0, self.focus_session_window)

        threading.Thread(target=worker, daemon=True).start()

    def focus_session_window(self):
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(500, lambda: self.attributes("-topmost", False))
            if hasattr(self, "status"):
                self.status.configure(text="RepoLens background indexing finished.")
        except tk.TclError:
            pass

    def post_ui(self, callback):
        try:
            self.ui_queue.put(callback)
        except Exception:
            pass

    def on_llm_queue_state_change(self, record):
        def update():
            if not hasattr(self, "status"):
                return
            request_type = "Chat" if record.get("request_type") == "chat" else "LLM task"
            status = record.get("status", "queued")
            if status == "completed":
                return
            if status == "failed":
                self.status.configure(text="{0} failed: {1}".format(request_type, record.get("error", "")))
                return
            self.status.configure(text="{0} {1}.".format(request_type, status))

        self.post_ui(update)

    def process_ui_queue(self):
        try:
            while True:
                callback = self.ui_queue.get_nowait()
                try:
                    callback()
                except tk.TclError:
                    pass
        except queue.Empty:
            pass
        try:
            self.after(50, self.process_ui_queue)
        except tk.TclError:
            pass

