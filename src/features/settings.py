import copy
import json
from pathlib import Path
from tkinter import messagebox

from src.features.settings_definitions import SettingsDefinitionsMixin
from src.features.settings_window import SettingsWindowMixin
from src.services.llamacpp import (
    DEFAULT_LLAMA_CONTEXT_SIZE,
    LLAMA_MODELS_DIR,
    LLAMA_UI_DIR,
    default_model_path,
    llama_server_executable,
    normalized_llamacpp_path,
)
from src.services.settings_profiles import load_profiles_into_settings, save_settings_to_profiles


class SettingsMixin(SettingsDefinitionsMixin, SettingsWindowMixin):
    def initialize_settings(self):
        self.settings_definitions = self.build_settings_definitions()
        self.settings = self.default_settings_from_definitions(self.settings_definitions)
        self.set_nested_setting(self.settings, "settings.advanced_mode", False)
        self.settings_path = Path(__file__).resolve().parents[2] / "settings.json"
        self.settings_load_error = ""
        self.settings_window = None
        self.settings_widgets = {}
        self.load_settings_file()
        self.load_settings_profiles()
        self.prune_removed_settings()
        safe_startup_migrated = self.apply_llamacpp_safe_startup_defaults()
        self.normalize_llamacpp_settings()
        if safe_startup_migrated:
            self.save_settings_file_silently()
        self.save_settings_profiles()

    def default_settings_from_definitions(self, definitions):
        settings = {}
        for field in self.iter_setting_fields(definitions):
            self.set_nested_setting(settings, field["key"], copy.deepcopy(field.get("default")))
        return settings

    def iter_setting_fields(self, definitions=None):
        for category in definitions or self.settings_definitions:
            for section in category.get("sections", []):
                for subsection in section.get("subsections", []):
                    for field in subsection.get("fields", []):
                        if field.get("type") == "action":
                            continue
                        yield field

    def merge_settings(self, incoming):
        if not isinstance(incoming, dict):
            return
        self.settings = self.merge_nested_settings(copy.deepcopy(self.settings), incoming)
        self.normalize_llamacpp_settings(apply_controls=False)
        self.apply_settings_to_controls()

    def load_settings_file(self):
        if not self.settings_path.exists():
            return
        try:
            loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.settings_load_error = str(exc)
            return
        self.merge_settings(loaded)

    def save_settings_file(self):
        try:
            self.settings_path.write_text(
                json.dumps(self.settings, indent=2),
                encoding="utf-8",
            )
            save_settings_to_profiles(self.settings, self.settings_definitions)
        except OSError as exc:
            messagebox.showerror("Settings save failed", f"Could not save settings:\n{exc}")
            return False
        return True

    def save_settings_file_silently(self):
        try:
            self.settings_path.write_text(
                json.dumps(self.settings, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            self.settings_load_error = str(exc)
            return False
        return True

    def load_settings_profiles(self):
        self.settings = load_profiles_into_settings(self.settings, self.settings_definitions)

    def save_settings_profiles(self):
        try:
            save_settings_to_profiles(self.settings, self.settings_definitions)
        except OSError as exc:
            self.settings_load_error = str(exc)

    def merge_nested_settings(self, base, incoming):
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key] = self.merge_nested_settings(base[key], value)
            else:
                base[key] = value
        return base

    def normalize_llamacpp_settings(self, apply_controls=True):
        local_base_url = str(self.get_setting("api.default_base_url", "") or "").strip().rstrip("/")
        if local_base_url in {"http://127.0.0.1:5001", "http://localhost:5001"}:
            self.set_nested_setting(self.settings, "api.default_base_url", "http://localhost:8080")
        self.set_nested_setting(
            self.settings,
            "llamacpp.executable_path",
            str(normalized_llamacpp_path(self.get_setting("llamacpp.executable_path", ""), llama_server_executable())),
        )
        self.set_nested_setting(
            self.settings,
            "llamacpp.ui_path",
            str(normalized_llamacpp_path(self.get_setting("llamacpp.ui_path", ""), LLAMA_UI_DIR)),
        )
        self.set_nested_setting(
            self.settings,
            "llamacpp.models_dir",
            str(normalized_llamacpp_path(self.get_setting("llamacpp.models_dir", ""), LLAMA_MODELS_DIR)),
        )
        self.set_nested_setting(
            self.settings,
            "llamacpp.model_path",
            str(
                normalized_llamacpp_path(
                    self.get_setting("llamacpp.model_path", ""),
                    default_model_path(),
                    filename_match=True,
                )
            ),
        )
        if not self.get_setting("llamacpp.ctx_size", 0):
            self.set_nested_setting(self.settings, "llamacpp.ctx_size", DEFAULT_LLAMA_CONTEXT_SIZE)
        if apply_controls:
            self.apply_settings_to_controls()

    def migrate_legacy_chat_api_url(self, value):
        raw = str(value or "").strip()
        if not raw:
            return
        if raw.lower() == "openrouter":
            self.set_nested_setting(self.settings, "api.use_local_api", False)
        else:
            self.set_nested_setting(self.settings, "api.use_local_api", True)
            self.set_nested_setting(self.settings, "api.default_base_url", raw)
        self.apply_settings_to_controls()

    def get_setting(self, key, default=None):
        node = self.settings
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set_nested_setting(self, settings, key, value):
        node = settings
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def remove_nested_setting(self, settings, key):
        node = settings
        parts = key.split(".")
        for part in parts[:-1]:
            if not isinstance(node, dict) or part not in node:
                return
            node = node[part]
        if isinstance(node, dict):
            node.pop(parts[-1], None)

    def prune_removed_settings(self):
        removed_keys = [
            "appearance.show_advanced_color_settings",
            "model_provider.show_advanced_provider_settings",
            "chat.show_advanced_generation_settings",
            "context.show_advanced_retrieval_settings",
            "reasoning.show_advanced_prompt_settings",
            "generation.top_p",
            "generation.frequency_penalty",
            "generation.presence_penalty",
            "api.stream_responses",
            "prompt_presets.auto_load",
            "prompt_presets.append_separator",
            "kokoro",
        ]
        for key in removed_keys:
            self.remove_nested_setting(self.settings, key)

    def apply_llamacpp_safe_startup_defaults(self):
        if int(self.get_setting("settings.safe_llamacpp_startup_defaults_version", 0) or 0) >= 2:
            return False
        safe_values = {
            "llamacpp.ctx_size": DEFAULT_LLAMA_CONTEXT_SIZE,
            "llamacpp.n_gpu_layers": "0",
            "llamacpp.parallel": 1,
            "llamacpp.flash_attn": "off",
            "llamacpp.fit": "off",
            "llamacpp.n_cpu_moe": 0,
            "llamacpp.reasoning": "",
            "llamacpp.cache_type_k": "",
            "llamacpp.cache_type_v": "",
            "llamacpp.cache_type_k_draft": "",
            "llamacpp.cache_type_v_draft": "",
            "llamacpp.spec_type": "",
            "llamacpp.spec_draft_n_max": 0,
            "llamacpp.temperature": "",
            "llamacpp.top_p": "",
            "llamacpp.top_k": 0,
            "llamacpp.min_p": "",
            "llamacpp.presence_penalty": "",
            "llamacpp.repeat_penalty": "",
            "llamacpp.verbosity": 0,
            "llamacpp.cache_idle_slots": False,
            "llamacpp.kv_unified": False,
        }
        for key, value in safe_values.items():
            self.set_nested_setting(self.settings, key, value)
        smallest_model = default_model_path()
        if smallest_model:
            self.set_nested_setting(self.settings, "llamacpp.model_path", str(smallest_model))
        self.remove_nested_setting(self.settings, "settings.safe_llamacpp_startup_defaults_applied")
        self.set_nested_setting(self.settings, "settings.safe_llamacpp_startup_defaults_version", 2)
        return True

    def apply_settings_to_controls(self):
        if hasattr(self, "apply_appearance_settings"):
            self.apply_appearance_settings()
        if hasattr(self, "refresh_notebook_view") and hasattr(self, "notebook_list_frame"):
            self.refresh_notebook_view()
        if hasattr(self, "reasoning_enabled_var"):
            self.reasoning_enabled_var.set(bool(self.get_setting("reasoning.enabled_by_default", False)))
        prompt_csv_path = self.get_setting("prompt_presets.csv_path", "")
        self.prompt_csv_path = prompt_csv_path
        if hasattr(self, "request_context_recalculation"):
            self.request_context_recalculation("Settings changed")

    def chat_settings(self):
        return self.settings
