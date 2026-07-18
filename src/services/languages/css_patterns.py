import re

from src.services.languages.language_utils import context_from_rows, enclosing_brace_block


LANGUAGE = "css"
EXTENSIONS = {".css", ".scss", ".sass", ".less"}
FILENAMES = {
    "postcss.config.js",
    "tailwind.config.js",
    "tailwind.config.cjs",
    "tailwind.config.mjs",
    "stylelint.config.js",
    ".stylelintrc",
    ".stylelintrc.json",
}
TEST_NAME_PATTERNS = ()
IMPORT_PATTERN = re.compile(r"^\s*@(?:import|use|forward)\b.*", re.IGNORECASE | re.MULTILINE)
PROJECT_CONTEXT_PATTERN = re.compile(
    r"^\s*(?:module\.exports|export\s+default|plugins?\s*:|content\s*:|theme\s*:|rules\s*:|extends\s*:)",
    re.IGNORECASE,
)
RULE_PATTERN = re.compile(
    r"(?m)^\s*"
    r"((?:@(?:media|supports|container|layer|keyframes|-webkit-keyframes)\b[^{]+)|(?:[.#]?[A-Za-z_][\w-]*|:[\w-]+|\[[^\]]+\])(?:[^{};]*))\s*\{"
)
DEFINITION_PATTERNS = (
    re.compile(r"^\s*@(?:mixin|function|keyframes|-webkit-keyframes)\s+([A-Za-z_][\w-]*)", re.MULTILINE),
    re.compile(r"^\s*([.#][A-Za-z_][\w-]*)\s*\{", re.MULTILINE),
)


def extract_import_context(file_text, path, make_context_item, selected_range=None):
    if is_project_file(path):
        return extract_project_context(file_text, path, make_context_item)

    rows = []
    for index, line in enumerate(file_text.splitlines(), start=1):
        if IMPORT_PATTERN.match(line):
            rows.append((index, line))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "CSS imports, uses, and forwards.", 80)


def extract_project_context(file_text, path, make_context_item):
    rows = []
    for index, line in enumerate(file_text.splitlines(), start=1):
        if PROJECT_CONTEXT_PATTERN.search(line):
            rows.append((index, line))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "CSS tooling configuration.", 85)


def find_enclosing_symbol_context(file_text, path, selected_range, make_context_item):
    if is_project_file(path):
        return None

    block = enclosing_brace_block(file_text, selected_range, RULE_PATTERN)
    if not block:
        return None
    start_line, end_line, content = block
    return make_context_item("symbol", path, LANGUAGE, start_line, end_line, "Enclosing CSS rule or at-rule.", content, 85)


def is_project_file(path):
    return bool(path and str(path.name).lower() in FILENAMES)
