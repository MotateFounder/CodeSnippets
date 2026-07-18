import json
from pathlib import Path

from src.services.promptManager.models import normalize_data


DATA_FILE = "prompt_manager.json"


class PromptManagerStorage:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / DATA_FILE

    def load(self):
        if not self.path.exists():
            data = normalize_data({})
            self.save(data)
            return data
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        return normalize_data(data)

    def save(self, data):
        normalized = normalize_data(data)
        self.path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
        return normalized

