import json
from pathlib import Path


DATA_FILE = "notes_app.json"


class NotebookStorage:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / DATA_FILE
        self.legacy_notebooks_dir = self.data_dir / "notebooks"

    def load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            return self.normalize_data(data)

        migrated = self.load_legacy_notebooks()
        if migrated["notebooks"]:
            self.save(migrated)
            return migrated

        data = {
            "version": 1,
            "selectedNotebookId": "",
            "selectedPageId": "",
            "notebooks": [],
        }
        self.save(data)
        return data

    def save(self, data):
        normalized = self.normalize_data(data)
        self.path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
        return normalized

    def normalize_data(self, data):
        if not isinstance(data, dict):
            data = {}
        notebooks = []
        seen_notebooks = set()
        for raw in data.get("notebooks", []):
            notebook = self.normalize_notebook(raw)
            if notebook["id"] in seen_notebooks:
                notebook["id"] = ""
                notebook = self.normalize_notebook(notebook)
            seen_notebooks.add(notebook["id"])
            notebooks.append(notebook)
        selected_notebook_id = str(data.get("selectedNotebookId", "") or "")
        selected_page_id = str(data.get("selectedPageId", "") or "")
        if notebooks and selected_notebook_id not in [item["id"] for item in notebooks]:
            selected_notebook_id = notebooks[0]["id"]
        selected_notebook = next((item for item in notebooks if item["id"] == selected_notebook_id), None)
        if selected_notebook and selected_notebook["pages"]:
            if selected_page_id not in [item["id"] for item in selected_notebook["pages"]]:
                selected_page_id = selected_notebook["pages"][0]["id"]
        else:
            selected_page_id = ""
        return {
            "version": 1,
            "selectedNotebookId": selected_notebook_id,
            "selectedPageId": selected_page_id,
            "notebooks": notebooks,
        }

    def normalize_notebook(self, notebook):
        from src.services.notebook.operations import new_id, timestamp

        if not isinstance(notebook, dict):
            notebook = {}
        pages = []
        seen_pages = set()
        for raw in notebook.get("pages", []):
            page = self.normalize_page(raw)
            if page["id"] in seen_pages:
                page["id"] = new_id()
            seen_pages.add(page["id"])
            pages.append(page)
        return {
            "id": str(notebook.get("id", "") or "").strip() or new_id(),
            "name": str(notebook.get("name", "") or "Untitled Notebook").strip() or "Untitled Notebook",
            "color": str(notebook.get("color", "") or "#7c83ff").strip() or "#7c83ff",
            "createdAt": str(notebook.get("createdAt", "") or timestamp()),
            "updatedAt": str(notebook.get("updatedAt", "") or timestamp()),
            "pages": pages,
        }

    def normalize_page(self, page):
        from src.services.notebook.operations import new_id, timestamp

        if not isinstance(page, dict):
            page = {}
        created = str(page.get("createdAt", "") or timestamp())
        return {
            "id": str(page.get("id", "") or "").strip() or new_id(),
            "title": str(page.get("title", "") or "Untitled Page").strip() or "Untitled Page",
            "content": str(page.get("content", page.get("body", "")) or ""),
            "tags": self.normalize_tags(page.get("tags", [])),
            "spans": self.normalize_spans(page.get("spans", [])),
            "createdAt": created,
            "updatedAt": str(page.get("updatedAt", "") or created),
        }

    def normalize_tags(self, tags):
        if isinstance(tags, str):
            tags = [tags]
        values = []
        for tag in tags or []:
            clean = str(tag).strip().lstrip("#")
            if clean and clean not in values:
                values.append(clean)
        return values[:8]

    def normalize_spans(self, spans):
        normalized = []
        for span in spans or []:
            if not isinstance(span, dict):
                continue
            tag = str(span.get("tag", "")).strip()
            if tag not in {"bold", "italic"}:
                continue
            try:
                start = int(span.get("start", 0))
                end = int(span.get("end", 0))
            except (TypeError, ValueError):
                continue
            if end > start >= 0:
                normalized.append({"tag": tag, "start": start, "end": end})
        return normalized

    def load_legacy_notebooks(self):
        notebooks = []
        if not self.legacy_notebooks_dir.exists():
            return {"version": 1, "selectedNotebookId": "", "selectedPageId": "", "notebooks": notebooks}

        for path in sorted(self.legacy_notebooks_dir.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            name = str(payload.get("name", path.stem)).strip() or path.stem
            category = path.parent.name if path.parent != self.legacy_notebooks_dir else ""
            display_name = "{0} - {1}".format(category, name) if category else name
            pages = []
            for note in payload.get("notes", []):
                page = {
                    "id": str(note.get("id", "") or ""),
                    "title": str(note.get("title", "") or "Untitled Page"),
                    "content": str(note.get("body", "") or ""),
                    "tags": self.normalize_tags(note.get("tags", [])),
                    "spans": [],
                    "createdAt": str(note.get("createdAt", "") or ""),
                    "updatedAt": str(note.get("updatedAt", "") or ""),
                }
                pages.append(self.normalize_page(page))
            notebooks.append(self.normalize_notebook({"name": display_name, "pages": pages}))

        data = {"version": 1, "selectedNotebookId": "", "selectedPageId": "", "notebooks": notebooks}
        return self.normalize_data(data)
