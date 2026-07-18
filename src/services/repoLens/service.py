import json
import os
import re
import subprocess
from pathlib import Path


class RepoLensError(RuntimeError):
    pass


class RepoLensService:
    DEFAULT_BUDGET_CHARS = 60000
    DEFAULT_LEVEL = 1

    def __init__(self, executable_path=None):
        root = Path(__file__).resolve().parents[3]
        executable = Path(executable_path) if executable_path else (
            root / "src" / "services" / "repoLens" / "repolens.exe"
        )
        self.executable_path = executable.resolve()

    def init(self, repo_path, index_dir):
        return self.run_json(["init", self._absolute(repo_path), "--index-dir", self._absolute(index_dir)])

    def update(self, index_dir, progress=None, lite=False, staged=False):
        args = ["update", "--index-dir", self._absolute(index_dir)]
        if lite:
            args.append("--lite")
        if staged:
            args.append("--staged")
        return self.run_text(
            args,
            progress=progress,
        )

    def updateroot(self, include_file, exclude_file=None, progress=None, lite=False, staged=False):
        args = ["updateroot", "--include-file", self._absolute(include_file)]
        if exclude_file:
            args.extend(["--exclude-file", self._absolute(exclude_file)])
        if lite:
            args.append("--lite")
        if staged:
            args.append("--staged")
        return self.run_text(args, progress=progress)

    def launch_updateroot_terminal(self, include_file, exclude_file=None, lite=True, staged=False):
        args = [
            os.fspath(self.executable_path),
            "updateroot",
            "--include-file",
            self._absolute(include_file),
        ]
        if exclude_file:
            args.extend(["--exclude-file", self._absolute(exclude_file)])
        if lite:
            args.append("--lite")
        if staged:
            args.append("--staged")

        if os.name == "nt":
            command_line = subprocess.list2cmdline(args)
            title = "title RepoLens Lite Index"
            command = "{0} && {1}".format(title, command_line)
            creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            return subprocess.Popen(
                ["cmd.exe", "/c", command],
                cwd=os.fspath(self.executable_path.parent),
                creationflags=creation_flags,
            )

        return subprocess.Popen(
            args,
            cwd=os.fspath(self.executable_path.parent),
        )

    def search(self, index_dir, query, kind="", limit=20, partial=False):
        args = [
            "search",
            "--index-dir",
            self._absolute(index_dir),
            "--query",
            str(query),
            "--limit",
            str(limit),
            "--format",
            "json",
        ]
        if kind:
            args.extend(["--kind", kind])
        if partial:
            args.append("--partial")
        return self.run_json(args)

    def context(
        self,
        index_dir,
        symbols,
        partial=False,
        level=DEFAULT_LEVEL,
        budget_chars=DEFAULT_BUDGET_CHARS,
        include_tree=True,
        include_types=True,
        basic=False,
        situated=False,
        signals_query="",
        grow=False,
        grow_files=None,
    ):
        cleaned = [str(symbol).strip() for symbol in symbols if str(symbol).strip()]
        if not cleaned:
            return {}
        args = [
            "context",
            "--index-dir",
            self._absolute(index_dir),
            "--symbols",
            ",".join(cleaned),
            "--level",
            str(max(0, int(level or 0))),
            "--budget-chars",
            str(max(0, int(budget_chars or 0))),
            "--format",
            "json",
        ]
        if partial:
            args.append("--partial")
        if include_tree:
            args.append("--include-tree")
        if include_types:
            args.append("--include-types")
        if basic:
            args.append("--basic")
        if situated:
            args.append("--situated")
        if signals_query:
            args.extend(["--signals", str(signals_query)])
        cleaned_grow_files = [str(path).strip() for path in (grow_files or []) if str(path).strip()]
        if grow and cleaned_grow_files:
            args.append("--grow")
            args.extend(["--grow-files", ",".join(cleaned_grow_files)])
        return self.run_json(args)

    def _absolute(self, path):
        return os.fspath(Path(path).resolve())

    def run_json(self, args):
        completed = self.run(args)
        text = completed.stdout.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RepoLensError("RepoLens returned invalid JSON: {0}".format(exc)) from exc

    def run_text(self, args, progress=None):
        completed = self.run(args, progress=progress)
        return completed.stdout

    def run(self, args, progress=None):
        if not self.executable_path.exists():
            raise RepoLensError("RepoLens executable not found: {0}".format(self.executable_path))
        command = [os.fspath(self.executable_path)] + list(args)
        if progress:
            return self._run_with_progress(command, progress)
        completed = subprocess.run(
            command,
            cwd=os.fspath(self.executable_path.parent),
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            raise RepoLensError(self._error_message(completed))
        return completed

    def _run_with_progress(self, command, progress):
        process = subprocess.Popen(
            command,
            cwd=os.fspath(self.executable_path.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        stdout_lines = []
        if process.stdout:
            for line in process.stdout:
                stdout_lines.append(line)
                message = line.strip()
                if message:
                    progress(message)
        stderr = process.stderr.read() if process.stderr else ""
        returncode = process.wait()
        completed = subprocess.CompletedProcess(command, returncode, "".join(stdout_lines), stderr)
        if returncode != 0:
            raise RepoLensError(self._error_message(completed))
        return completed

    def _error_message(self, completed):
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        return stderr or stdout or "RepoLens command failed with exit code {0}.".format(completed.returncode)


IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z_0-9]{2,}")
CALL_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z_0-9]{2,})\s*\(")
DECLARATION_PATTERN = re.compile(
    r"\b(?:class|struct|interface|enum|record|delegate|def|function|func|fn|sub|void|async)\s+([A-Za-z_][A-Za-z_0-9]{2,})"
)

IDENTIFIER_STOP_WORDS = {
    "and",
    "args",
    "async",
    "await",
    "bool",
    "break",
    "case",
    "catch",
    "class",
    "const",
    "def",
    "else",
    "enum",
    "false",
    "for",
    "foreach",
    "from",
    "function",
    "get",
    "if",
    "import",
    "int",
    "let",
    "namespace",
    "new",
    "none",
    "null",
    "private",
    "protected",
    "public",
    "return",
    "self",
    "set",
    "static",
    "string",
    "this",
    "true",
    "using",
    "var",
    "void",
    "while",
}


def extract_symbols_from_snippet(snippet, max_symbols=12):
    text = str(snippet.get("text", "") if isinstance(snippet, dict) else snippet or "")
    source = Path(snippet.get("source", "")) if isinstance(snippet, dict) and snippet.get("source") else None
    ordered = []

    def add(value):
        value = str(value or "").strip()
        if not value or value.lower() in IDENTIFIER_STOP_WORDS:
            return
        if value not in ordered:
            ordered.append(value)

    for pattern in (DECLARATION_PATTERN, CALL_PATTERN):
        for match in pattern.finditer(text):
            add(match.group(1))

    for match in IDENTIFIER_PATTERN.finditer(text):
        value = match.group(0)
        if "_" in value or any(character.isupper() for character in value[1:]):
            add(value)

    if source:
        add(source.stem)

    return ordered[:max_symbols]


def format_repolens_context(data):
    if not isinstance(data, dict):
        return ""
    parts = []
    metadata = data.get("metadata") or data.get("repository") or {}
    if metadata:
        repo_root = metadata.get("repo_root", "")
        last_indexed = metadata.get("last_indexed_at", "")
        header = ["<repolens_context>"]
        if repo_root:
            header.append("Repo root: {0}".format(repo_root))
        if last_indexed:
            header.append("Last indexed: {0}".format(last_indexed))
        parts.append("\n".join(header))

    for item in context_items(data):
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip()
        if not code:
            continue
        file_path = item.get("file", "")
        language = language_from_path(file_path)
        line_text = format_line_range(
            item.get("start_line", item.get("line_start")),
            item.get("end_line", item.get("line_end")),
        )
        reason = context_reason(item)
        parts.append(
            "<related_context>\n"
            "Symbol: {0}\n"
            "Kind: {1}\n"
            "File: {2}\n"
            "Lines: {3}\n"
            "Reason: {4}\n"
            "```{5}\n"
            "{6}\n"
            "```\n"
            "</related_context>".format(
                item.get("qualified_name") or item.get("name") or item.get("requested_symbol") or "(unknown)",
                item.get("kind", ""),
                file_path,
                line_text,
                reason,
                language,
                code,
            )
        )

    tree = data.get("reduced_file_tree") or []
    if tree:
        parts.append(
            "<file_tree>\n"
            + "\n".join(str(path) for path in tree)
            + "\n</file_tree>"
        )
    warnings = data.get("warnings") or []
    if warnings:
        parts.append(
            "<repolens_warnings>\n"
            + "\n".join(str(warning) for warning in warnings)
            + "\n</repolens_warnings>"
        )
    if metadata:
        parts.append("</repolens_context>")
    return "\n\n".join(parts)


def context_item_count(data):
    if not isinstance(data, dict):
        return 0
    return len([item for item in context_items(data) if isinstance(item, dict) and item.get("code")])


def context_items(data):
    if not isinstance(data, dict):
        return []
    return data.get("items") or data.get("symbols") or []


def language_from_path(path):
    suffix = Path(str(path)).suffix.lower()
    return {
        ".cs": "csharp",
        ".cpp": "cpp",
        ".cxx": "cpp",
        ".cc": "cpp",
        ".c": "c",
        ".h": "cpp",
        ".hpp": "cpp",
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".php": "php",
        ".rb": "ruby",
        ".sql": "sql",
        ".xaml": "xml",
        ".xml": "xml",
        ".json": "json",
    }.get(suffix, "")


def format_line_range(start_line, end_line):
    if start_line and end_line:
        return "{0}-{1}".format(start_line, end_line)
    if start_line:
        return str(start_line)
    return "unknown"


def context_reason(item):
    relation = item.get("relation_type", "")
    source = item.get("source_qualified_name", "")
    if relation and source:
        return "RepoLens relation {0} from {1}.".format(relation, source)
    if relation:
        return "RepoLens relation {0}.".format(relation)
    return "RepoLens deterministic context for requested symbol."
