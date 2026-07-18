import ast
import pprint
from pathlib import Path


PROFILE_DIR = Path(__file__).resolve().parents[1] / "config" / "toolsandprofiles"

PROFILE_SPECS = [
    ("appearance", "appearanceprofile.py", ("appearance.",), ()),
    ("llamacpp", "llamaprofile.py", ("llamacpp.",), ()),
    ("api", "apiprofile.py", ("api.",), ()),
    ("openrouter", "openrouterprofile.py", ("openrouter.",), ()),
    ("chat", "chatprofile.py", ("generation.", "chat.", "context.wrapper_prompt"), ()),
    ("context", "contextprofile.py", ("context.", "repolens.", "smart_context."), ("context.wrapper_prompt",)),
    ("reasoning", "reasoningprofile.py", ("reasoning.", "prompts.", "prompt_presets."), ()),
]


def setting_get(settings, key, default=None):
    node = settings
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def setting_set(settings, key, value):
    node = settings
    parts = key.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def all_setting_keys(definitions):
    keys = []
    for category in definitions or []:
        for section in category.get("sections", []):
            for subsection in section.get("subsections", []):
                for field in subsection.get("fields", []):
                    if field.get("type") == "action":
                        continue
                    key = field.get("key")
                    if key:
                        keys.append(key)
    return keys


def keys_for_prefixes(setting_keys, prefixes, excludes=()):
    return [
        key
        for key in setting_keys
        if key not in excludes and any(key.startswith(prefix) for prefix in prefixes)
    ]


def read_profile(path):
    if not path.exists():
        return {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PROFILE":
                    try:
                        value = ast.literal_eval(node.value)
                    except (ValueError, SyntaxError):
                        return {}
                    return value if isinstance(value, dict) else {}
    return {}


def write_profile(path, name, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "name": name,
        "format": 1,
        "description": "Flat settings mirror. Edit values, then restart the app or reopen Settings.",
        "settings": values,
    }
    text = "# Auto-generated CodeSnippets profile. Keep PROFILE as a Python literal.\n"
    text += "PROFILE = "
    text += pprint.pformat(profile, width=120, sort_dicts=True)
    text += "\n"
    path.write_text(text, encoding="utf-8")


def load_profiles_into_settings(settings, definitions):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    all_keys = set(all_setting_keys(definitions))
    for _name, filename, prefixes, excludes in PROFILE_SPECS:
        setting_keys = keys_for_prefixes(all_keys, prefixes, excludes)
        profile = read_profile(PROFILE_DIR / filename)
        values = profile.get("settings", {})
        if not isinstance(values, dict):
            continue
        allowed = set(setting_keys)
        for key, value in values.items():
            if key in allowed:
                setting_set(settings, key, value)
    return settings


def save_settings_to_profiles(settings, definitions):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    all_keys = all_setting_keys(definitions)
    for name, filename, prefixes, excludes in PROFILE_SPECS:
        setting_keys = keys_for_prefixes(all_keys, prefixes, excludes)
        values = {}
        for key in setting_keys:
            values[key] = setting_get(settings, key)
        write_profile(PROFILE_DIR / filename, name, values)
