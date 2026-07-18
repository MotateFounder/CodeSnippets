from src.features.settings_categories.appearance_settings import appearance_settings
from src.features.settings_categories.chat_settings import chat_settings
from src.features.settings_categories.context_settings import context_settings
from src.features.settings_categories.model_provider_settings import model_provider_settings
from src.features.settings_categories.prompts_reasoning_settings import prompts_reasoning_settings


class SettingsDefinitionsMixin:
    def build_settings_definitions(self):
        return [
            appearance_settings(self.appearance_color_field),
            model_provider_settings(),
            chat_settings(),
            context_settings(),
            prompts_reasoning_settings(),
        ]

    def appearance_color_field(self, key, label):
        return {
            "key": "appearance.colors.{0}".format(key),
            "label": label,
            "type": "string",
            "default": "",
            "description": "Optional hex color override. Leave blank to use the selected theme.",
            "used": True,
        }

