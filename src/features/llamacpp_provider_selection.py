import tkinter as tk

from src.services.llamacpp import (
    DEFAULT_LLAMA_CONTEXT_SIZE,
    build_llama_server_command,
    launch_llama_server,
    llama_base_url,
    open_llama_browser,
)


class LlamaCppProviderSelectionMixin:
    def apply_llamacpp_launch_selection(self, launch_requested=True, model_path="", context_size=DEFAULT_LLAMA_CONTEXT_SIZE):
        if not launch_requested:
            self.set_nested_setting(self.settings, "api.use_local_api", False)
            self.set_nested_setting(self.settings, "llamacpp.auto_launch", False)
            self.apply_settings_to_controls()
            self.save_settings_file()
            if hasattr(self, "status"):
                self.status.configure(text="Session loaded with OpenRouter provider.")
            return

        self.set_nested_setting(self.settings, "api.use_local_api", True)
        self.set_nested_setting(self.settings, "llamacpp.auto_launch", True)
        if model_path:
            self.set_nested_setting(self.settings, "llamacpp.model_path", model_path)
        if context_size:
            self.set_nested_setting(self.settings, "llamacpp.ctx_size", int(context_size))
        host = self.get_setting("llamacpp.host", "0.0.0.0")
        port = int(self.get_setting("llamacpp.port", 8080) or 8080)
        self.set_nested_setting(self.settings, "api.default_base_url", llama_base_url(host=host, port=port))
        self.apply_settings_to_controls()
        self.save_settings_file()
        try:
            self.llamacpp_process = launch_llama_server(
                settings=self.get_setting("llamacpp", {}),
                model_path=model_path or self.get_setting("llamacpp.model_path", ""),
                context_size=context_size or self.get_setting("llamacpp.ctx_size", DEFAULT_LLAMA_CONTEXT_SIZE),
            )
            self.remember_llamacpp_loaded_settings()
        except Exception as exc:
            if hasattr(self, "status"):
                self.status.configure(text="Llama.cpp launch skipped: {0}".format(exc))
            return
        if hasattr(self, "status"):
            self.status.configure(text="Llama.cpp server launched on {0}.".format(self.get_setting("api.default_base_url", "http://localhost:8080")))

    def open_llamacpp_web_ui(self):
        open_llama_browser(
            host=self.get_setting("llamacpp.host", "0.0.0.0"),
            port=int(self.get_setting("llamacpp.port", 8080) or 8080),
        )

    def llamacpp_settings_signature(self, settings=None):
        source = settings or getattr(self, "settings", {})
        llamacpp_settings = source.get("llamacpp", {}) if isinstance(source, dict) else {}
        try:
            command = build_llama_server_command(
                settings=llamacpp_settings,
                model_path=llamacpp_settings.get("model_path", ""),
                context_size=llamacpp_settings.get("ctx_size", DEFAULT_LLAMA_CONTEXT_SIZE),
            )
        except Exception:
            command = []
        api = source.get("api", {}) if isinstance(source, dict) else {}
        return (
            tuple(str(part) for part in command),
            str(api.get("use_local_api", True)),
            str(api.get("default_base_url", "")),
        )

    def remember_llamacpp_loaded_settings(self):
        self.llamacpp_loaded_signature = self.llamacpp_settings_signature()

    def llamacpp_settings_have_changed(self, settings=None):
        loaded = getattr(self, "llamacpp_loaded_signature", None)
        if loaded is None:
            loaded = self.llamacpp_settings_signature()
            self.llamacpp_loaded_signature = loaded
        return self.llamacpp_settings_signature(settings=settings) != loaded

    def reload_llamacpp_model_from_settings(self):
        host = self.get_setting("llamacpp.host", "0.0.0.0")
        port = int(self.get_setting("llamacpp.port", 8080) or 8080)
        self.set_nested_setting(self.settings, "api.use_local_api", True)
        self.set_nested_setting(self.settings, "api.default_base_url", llama_base_url(host=host, port=port))
        self.apply_settings_to_controls()
        self.save_settings_file()
        self.stop_llamacpp_process()
        try:
            self.llamacpp_process = launch_llama_server(
                settings=self.get_setting("llamacpp", {}),
                model_path=self.get_setting("llamacpp.model_path", ""),
                context_size=self.get_setting("llamacpp.ctx_size", DEFAULT_LLAMA_CONTEXT_SIZE),
            )
            self.remember_llamacpp_loaded_settings()
        except Exception as exc:
            if hasattr(self, "status"):
                self.status.configure(text="Llama.cpp reload failed: {0}".format(exc))
            return False
        if hasattr(self, "status"):
            self.status.configure(
                text="Llama.cpp model reloaded on {0}.".format(self.get_setting("api.default_base_url", "http://localhost:8080"))
            )
        return True

    def stop_llamacpp_process(self, timeout_seconds=5):
        process = getattr(self, "llamacpp_process", None)
        if not process:
            return
        try:
            if process.poll() is not None:
                self.llamacpp_process = None
                return
            process.terminate()
            try:
                process.wait(timeout=timeout_seconds)
            except Exception:
                if process.poll() is None:
                    process.kill()
                    try:
                        process.wait(timeout=2)
                    except Exception:
                        pass
        except Exception:
            pass
        self.llamacpp_process = None

    def close_application(self):
        try:
            if hasattr(self, "stop_search_worker"):
                self.stop_search_worker()
        except Exception:
            pass
        try:
            self.stop_session_autosave()
        except Exception:
            pass
        try:
            if hasattr(self, "save_prompt_manager_now"):
                self.save_prompt_manager_now()
        except Exception:
            pass
        try:
            if hasattr(self, "save_notebook_now"):
                self.save_notebook_now()
        except Exception:
            pass
        try:
            if hasattr(self, "llm_queue"):
                self.llm_queue.close()
        except Exception:
            pass
        self.stop_llamacpp_process()
        try:
            self.destroy()
        except tk.TclError:
            pass

