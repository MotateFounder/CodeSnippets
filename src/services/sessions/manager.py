import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from src.services.repoLens.service import RepoLensService


class SessionManager:
    def __init__(self, app_root=None):
        self.app_root = Path(app_root) if app_root else Path(__file__).resolve().parents[3]
        self.sessions_dir = self.app_root / "users" / "sessions"
        self.icons_dir = self.sessions_dir / "icons"

    def ensure_directories(self):
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.icons_dir.mkdir(parents=True, exist_ok=True)

    def list_sessions(self, include_archived=False):
        self.ensure_directories()
        sessions = []
        session_files = [
            path / "session.json"
            for path in self.sessions_dir.iterdir()
            if path.is_dir() and path.name != "icons" and (path / "session.json").exists()
        ]
        for path in sorted(session_files, key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                data = self.load_session(path)
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("session_info", {}).get("archived") and not include_archived:
                continue
            sessions.append(self.session_summary(path, data))
        return sessions

    def load_session(self, path):
        return json.loads(self.session_file_from_path(path).read_text(encoding="utf-8"))

    def session_summary(self, path, data):
        session_dir = self.session_dir_from_path(path)
        session_info = data.get("session_info", {}) if isinstance(data, dict) else {}
        root_folder = data.get("root_folder", "") if isinstance(data, dict) else ""
        chat = data.get("chat", {}) if isinstance(data, dict) else {}
        name = session_info.get("name") or Path(path).stem
        description = session_info.get("description") or self._description_from_data(data)
        repo_path = session_info.get("repo_path") or root_folder
        icon_path = session_info.get("icon_path", "")
        updated_at = session_info.get("updated_at", "")
        if not updated_at:
            updated_at = datetime.fromtimestamp(Path(path).stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        return {
            "path": session_dir,
            "name": str(name),
            "description": str(description),
            "repo_path": str(repo_path),
            "icon_path": str(icon_path),
            "updated_at": str(updated_at),
            "thread_count": len(chat.get("threads", [])) if isinstance(chat, dict) else 0,
            "archived": bool(session_info.get("archived", False)),
        }

    def set_session_archived(self, path, archived=True):
        session = self.load_session(path)
        session_info = session.setdefault("session_info", {})
        session_info["archived"] = bool(archived)
        session_info["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.save_session(path, session)
        return session

    def update_session_details(
        self,
        path,
        name,
        repo_path,
        description="",
        icon_path="",
        include_paths=None,
        exclude_paths=None,
        repolens_enabled=True,
    ):
        session = self.load_session(path)
        session_info = session.setdefault("session_info", {})
        session_info["name"] = str(name or session_info.get("name") or "Untitled Session").strip()
        session_info["description"] = str(description or "").strip()
        session_info["repolens_enabled"] = bool(repolens_enabled)
        if repo_path:
            repo_path = str(Path(repo_path))
            session["root_folder"] = repo_path
            session_info["repo_path"] = repo_path
            database_dir = self.session_dir_from_path(path) / "database"
            session_info["database_dir"] = str(database_dir)
            session_info["include_file"] = str(database_dir / "include.txt")
            session_info["exclude_file"] = str(database_dir / "exclude.txt")
            session_info["repolens_executable"] = str(database_dir / "repolens.exe")
            if repolens_enabled:
                self.write_path_list(database_dir / "include.txt", include_paths or [repo_path])
                self.write_path_list(database_dir / "exclude.txt", exclude_paths or [])
                try:
                    self.copy_repolens_executable(database_dir / "repolens.exe")
                except Exception:
                    pass
        if icon_path:
            session_info["icon_path"] = self._copy_icon(icon_path, self.session_dir_from_path(path).name)
        session_info["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.save_session(path, session)
        return session

    def create_session(
        self,
        name,
        repo_path,
        description="",
        icon_path="",
        include_paths=None,
        exclude_paths=None,
        repolens_enabled=True,
        initialize_repolens=False,
        progress=None,
    ):
        self.ensure_directories()
        clean_name = name.strip() or "Untitled Session"
        repo_path = str(Path(repo_path)) if repo_path else ""
        slug = self._unique_slug(clean_name)
        saved_icon_path = self._copy_icon(icon_path, slug) if icon_path else ""
        session_dir = self.sessions_dir / slug
        database_dir = session_dir / "database"
        database_dir.mkdir(parents=True, exist_ok=True)
        include_file = database_dir / "include.txt"
        exclude_file = database_dir / "exclude.txt"
        repolens_executable = database_dir / "repolens.exe"
        include_paths = include_paths or [repo_path]
        exclude_paths = exclude_paths or []
        if repolens_enabled:
            self.write_path_list(include_file, include_paths)
            self.write_path_list(exclude_file, exclude_paths)
            self.copy_repolens_executable(repolens_executable)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        session = {
            "version": 2,
            "session_info": {
                "name": clean_name,
                "description": description.strip(),
                "repo_path": repo_path,
                "icon_path": saved_icon_path,
                "created_at": now,
                "updated_at": now,
                "session_dir": str(session_dir),
                "database_dir": str(database_dir),
                "include_file": str(include_file),
                "exclude_file": str(exclude_file),
                "repolens_executable": str(repolens_executable),
                "repolens_enabled": bool(repolens_enabled),
            },
            "settings": {},
            "root_folder": repo_path,
            "current_file": "",
            "open_files": [],
            "active_snippet_clipboard": 0,
            "snippet_clipboards": [],
            "snippets": [],
            "chat": {
                "current_thread": 0,
                "threads": [{"title": "Chat 1", "messages": []}],
                "prompt_csv_path": "",
                "prompt_presets": [],
                "selected_prompt_preset": -1,
                "reasoning_enabled": False,
            },
        }
        path = session_dir / "session.json"
        self.save_session(path, session)
        if initialize_repolens:
            self.initialize_session_database(session_dir, session, progress=progress)
        return session_dir, session

    def initialize_session_database(self, session_path, session, progress=None):
        session_dir = self.session_dir_from_path(session_path)
        session_info = session.setdefault("session_info", {})
        database_dir = Path(session_info.get("database_dir") or session_dir / "database")
        include_file = Path(session_info.get("include_file") or database_dir / "include.txt")
        exclude_file = Path(session_info.get("exclude_file") or database_dir / "exclude.txt")
        repolens_executable = Path(session_info.get("repolens_executable") or database_dir / "repolens.exe")
        try:
            RepoLensService(repolens_executable).updateroot(include_file, exclude_file, progress=progress)
            session_info.pop("repolens_init_error", None)
        except Exception as exc:
            session_info["repolens_init_error"] = str(exc)
            self.save_session(session_dir, session)
            raise
        self.save_session(session_dir, session)
        return session

    def launch_session_database_terminal(self, session_path, session, lite=True):
        session_dir = self.session_dir_from_path(session_path)
        session_info = session.setdefault("session_info", {})
        database_dir = Path(session_info.get("database_dir") or session_dir / "database")
        include_file = Path(session_info.get("include_file") or database_dir / "include.txt")
        exclude_file = Path(session_info.get("exclude_file") or database_dir / "exclude.txt")
        repolens_executable = Path(session_info.get("repolens_executable") or database_dir / "repolens.exe")
        process = RepoLensService(repolens_executable).launch_updateroot_terminal(
            include_file,
            exclude_file,
            lite=lite,
        )
        session_info["repolens_init_status"] = "running_lite" if lite else "running_full"
        session_info.pop("repolens_init_error", None)
        self.save_session(session_dir, session)
        return process

    def update_session_metadata(self, session, path=None):
        session_info = session.setdefault("session_info", {})
        if not session_info.get("name") and path:
            path = Path(path)
            session_info["name"] = path.parent.name if path.name == "session.json" else path.name
        if not session_info.get("repo_path"):
            session_info["repo_path"] = session.get("root_folder", "")
        if path:
            session_dir = self.session_dir_from_path(path)
            database_dir = session_dir / "database"
            session_info["session_dir"] = str(session_dir)
            session_info["database_dir"] = str(database_dir)
            session_info["include_file"] = str(database_dir / "include.txt")
            session_info["exclude_file"] = str(database_dir / "exclude.txt")
            session_info["repolens_executable"] = str(database_dir / "repolens.exe")
        session_info["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        return session

    def save_session(self, path, session):
        path = self.session_file_from_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(session, indent=2), encoding="utf-8")

    def session_file_from_path(self, path):
        path = Path(path)
        if path.suffix.lower() == ".json":
            return path
        return path / "session.json"

    def session_dir_from_path(self, path):
        path = Path(path)
        if path.suffix.lower() == ".json":
            return path.parent
        return path

    def database_dir_from_session(self, session, path=None):
        session_info = session.get("session_info", {}) if isinstance(session, dict) else {}
        value = session_info.get("database_dir", "")
        if value:
            return Path(value)
        if path:
            return self.session_dir_from_path(path) / "database"
        return None

    def write_path_list(self, path, values):
        cleaned = []
        for value in values or []:
            text = str(value or "").strip()
            if text:
                cleaned.append('"{}"'.format(text.strip('"')))
        Path(path).write_text("\n".join(cleaned) + ("\n" if cleaned else ""), encoding="utf-8")

    def copy_repolens_executable(self, destination):
        source = RepoLensService().executable_path
        if not source.exists():
            raise FileNotFoundError("RepoLens executable not found: {0}".format(source))
        shutil.copy2(source, destination)

    def _description_from_data(self, data):
        if not isinstance(data, dict):
            return ""
        snippets = data.get("snippets") or []
        clipboards = data.get("snippet_clipboards") or []
        snippet_count = len(snippets)
        if clipboards:
            snippet_count = sum(len(clipboard.get("snippets", [])) for clipboard in clipboards)
        if snippet_count:
            return f"{snippet_count} collected snippet(s)."
        return "CodeSnippets session."

    def _copy_icon(self, icon_path, slug):
        self.ensure_directories()
        source = Path(icon_path)
        if not source.exists() or source.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            return ""
        destination = self.icons_dir / (slug + source.suffix.lower())
        try:
            if source.resolve() == destination.resolve():
                return str(destination)
        except OSError:
            pass
        shutil.copy2(source, destination)
        return str(destination)

    def _unique_slug(self, name):
        base = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip()).strip("._")
        if not base:
            base = "session"
        candidate = base
        index = 2
        while (self.sessions_dir / candidate).exists():
            candidate = f"{base}_{index}"
            index += 1
        return candidate
