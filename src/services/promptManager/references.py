import re
from pathlib import Path

from src.services.chat_intents import snippet_mention_slug


REFERENCE_PATTERN = re.compile(r"(?<!\w)@(?:(snippet|file|symbol):)?([^\s@]+)")


class PromptReferenceResolver:
    def __init__(self, snippets=None, root_folder=None, symbol_resolver=None):
        self.snippets = list(snippets or [])
        self.root_folder = Path(root_folder) if root_folder else None
        self.symbol_resolver = symbol_resolver

    def resolve_text(self, text):
        warnings = []

        def replacement(match):
            original = match.group(0)
            kind = (match.group(1) or "snippet").lower()
            value = match.group(2).strip().strip("\"'")
            lookup_value = value.rstrip(".,;:)]}")
            suffix = value[len(lookup_value):]
            resolved = self.resolve(kind, lookup_value)
            if resolved is None:
                warnings.append("Could not resolve {0}.".format(original))
                return original
            return resolved + suffix

        return REFERENCE_PATTERN.sub(replacement, text or ""), warnings

    def resolve(self, kind, value):
        if kind == "snippet":
            return self.resolve_snippet(value)
        if kind == "file":
            return self.resolve_file(value)
        if kind == "symbol":
            return self.resolve_symbol(value)
        return None

    def resolve_snippet(self, value):
        needle = str(value or "").lower()
        for snippet in self.snippets:
            fallback = str(snippet.get("id") or "snippet")
            slug = snippet_mention_slug(str(snippet.get("description", "")), fallback)
            candidates = {
                slug.lower(),
                fallback.lower(),
                str(snippet.get("description", "")).strip().lower(),
            }
            if needle in candidates:
                return str(snippet.get("text", "") or "")
        return None

    def resolve_file(self, value):
        raw = str(value or "").strip()
        if not raw:
            return None
        path = Path(raw)
        if not path.is_absolute() and self.root_folder:
            path = self.root_folder / path
        try:
            if not path.exists() or not path.is_file():
                return None
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def resolve_symbol(self, value):
        if not self.symbol_resolver:
            return None
        try:
            resolved = self.symbol_resolver(value)
        except Exception:
            return None
        return str(resolved or "") or None
