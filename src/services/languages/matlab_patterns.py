import re

from src.services.languages.language_utils import context_from_rows


LANGUAGE = "matlab"
EXTENSIONS = {".m", ".mlx", ".prj", ".mlapp", ".mlappinstall"}
FILENAMES = {
    "startup.m",
    "finish.m",
    "pathdef.m",
}
TEST_NAME_PATTERNS = (
    re.compile(r".*(?:test|tests).*\.m$", re.IGNORECASE),
)
PROJECT_EXTENSIONS = {".prj", ".mlappinstall"}
IMPORT_PATTERN = re.compile(r"^\s*(?:import\s+[\w.*]+|addpath\s*\(|run\s*\()", re.IGNORECASE)
PROJECT_CONTEXT_PATTERN = re.compile(
    r"<\s*(?:param|configuration|fileset|file|dependency|matlab|toolbox|namespace|name|description|version)\b|"
    r"^\s*(?:addpath|import|requires|matlabRelease|products)\b",
    re.IGNORECASE,
)
FUNCTION_PATTERN = re.compile(
    r"^\s*function\s+(?:\[[^\]]+\]\s*=\s*|[A-Za-z_]\w*\s*=\s*)?([A-Za-z_]\w*)\s*(?:\(|$)",
    re.IGNORECASE | re.MULTILINE,
)
CLASS_PATTERN = re.compile(r"^\s*classdef\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)", re.IGNORECASE | re.MULTILINE)
SECTION_PATTERN = re.compile(r"^\s*%%\s*(.+)$", re.MULTILINE)
DEFINITION_PATTERNS = (
    FUNCTION_PATTERN,
    CLASS_PATTERN,
)


def extract_import_context(file_text, path, make_context_item, selected_range=None):
    if is_project_file(path):
        return extract_project_context(file_text, path, make_context_item)

    rows = []
    for index, line in enumerate(file_text.splitlines(), start=1):
        if IMPORT_PATTERN.match(line):
            rows.append((index, line))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "MATLAB imports, paths, and run dependencies.", 80)


def extract_project_context(file_text, path, make_context_item):
    rows = []
    for index, line in enumerate(file_text.splitlines(), start=1):
        if PROJECT_CONTEXT_PATTERN.search(line):
            rows.append((index, line))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "MATLAB project metadata, files, and dependencies.", 85)


def find_enclosing_symbol_context(file_text, path, selected_range, make_context_item):
    if is_project_file(path):
        return None

    selected_start, selected_end = selected_range
    lines = file_text.splitlines()
    starts = []
    for pattern, kind in ((FUNCTION_PATTERN, "symbol"), (CLASS_PATTERN, "class"), (SECTION_PATTERN, "symbol")):
        for match in pattern.finditer(file_text):
            start_line = file_text.count("\n", 0, match.start()) + 1
            starts.append({"line": start_line, "kind": kind})
    starts.sort(key=lambda item: item["line"])

    best = None
    for index, item in enumerate(starts):
        next_line = starts[index + 1]["line"] if index + 1 < len(starts) else len(lines) + 1
        if item["line"] <= selected_start and (selected_end or selected_start) < next_line:
            best = {"start_line": item["line"], "end_line": next_line - 1, "kind": item["kind"]}

    if not best:
        return None
    content = "\n".join(lines[best["start_line"] - 1 : best["end_line"]])
    return make_context_item(best["kind"], path, LANGUAGE, best["start_line"], best["end_line"], "Enclosing MATLAB function, class, or section.", content, 85)


def is_project_file(path):
    return bool(path and path.suffix.lower() in PROJECT_EXTENSIONS)
