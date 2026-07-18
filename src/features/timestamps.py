from datetime import datetime, timedelta


class TimestampMixin:
    def current_timestamp(self):
        return datetime.now().isoformat(timespec="seconds")

    def current_snippet_id(self):
        return datetime.now().strftime("%Y%m%d%H%M%S")

    def create_snippet_id(self):
        existing_ids = {
            str(snippet.get("id"))
            for snippet in self.all_snippets_for_id_check()
            if snippet.get("id")
        }
        candidate_time = datetime.now().replace(microsecond=0)
        while True:
            candidate = candidate_time.strftime("%Y%m%d%H%M%S")
            if candidate not in existing_ids:
                return candidate
            candidate_time += timedelta(seconds=1)

    def create_clipboard_id(self):
        existing_ids = {
            str(clipboard.get("id"))
            for clipboard in getattr(self, "snippet_clipboards", [])
            if clipboard.get("id")
        }
        candidate_time = datetime.now().replace(microsecond=0)
        while True:
            candidate = candidate_time.strftime("%Y%m%d%H%M%S")
            if candidate not in existing_ids:
                return candidate
            candidate_time += timedelta(seconds=1)

    def ensure_snippet_id(self, snippet):
        if snippet is None:
            return snippet
        existing_ids = {
            str(existing.get("id"))
            for existing in self.all_snippets_for_id_check()
            if existing is not snippet and existing.get("id")
        }
        snippet_id = str(snippet.get("id", "")).strip()
        if not self.is_snippet_id(snippet_id) or snippet_id in existing_ids:
            snippet["id"] = self.create_snippet_id()
        else:
            snippet["id"] = snippet_id
        return snippet

    def is_snippet_id(self, value):
        return bool(value) and len(str(value)) == 14 and str(value).isdigit()

    def all_snippets_for_id_check(self):
        clipboards = getattr(self, "snippet_clipboards", [])
        if clipboards:
            snippets = []
            for clipboard in clipboards:
                snippets.extend(clipboard.get("snippets", []))
            return snippets
        return list(getattr(self, "snippets", []))

    def display_timestamp(self, value):
        if not value:
            return "No timestamp"
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return str(value)
        return parsed.strftime("%Y-%m-%d %H:%M:%S")

    def ensure_created_at(self, record):
        if record is not None and not record.get("created_at"):
            record["created_at"] = self.current_timestamp()
        return record

    def normalize_timestamp(self, value):
        if not value:
            return ""
        text = str(value).strip()
        try:
            return datetime.fromisoformat(text).isoformat(timespec="seconds")
        except ValueError:
            pass
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(text, pattern).isoformat(timespec="seconds")
            except ValueError:
                continue
        return text
