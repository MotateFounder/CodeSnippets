import re

from src.services.languages.language_utils import context_from_rows, enclosing_brace_block


LANGUAGE = "javascript"
EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs"}
FILENAMES = {
    "package.json",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "bun.lock",
    "jsconfig.json",
    ".babelrc",
    ".eslintrc",
    ".eslintrc.json",
    ".eslintrc.js",
    ".prettierrc",
    "babel.config.js",
    "eslint.config.js",
    "vite.config.js",
    "webpack.config.js",
    "rollup.config.js",
}
TEST_NAME_PATTERNS = (
    re.compile(r".*\.(?:test|spec)\.jsx?$", re.IGNORECASE),
)
IMPORT_PATTERN = re.compile(
    r"^\s*(?:import\b.*(?:from\s+)?[\"'][^\"']+[\"'];?|export\b.*from\s+[\"'][^\"']+[\"'];?|const\s+\w+\s*=\s*require\s*\([\"'][^\"']+[\"']\)\s*;?)",
    re.MULTILINE,
)
PROJECT_CONTEXT_PATTERN = re.compile(
    r"^\s*(?:\"(?:scripts|dependencies|devDependencies|peerDependencies|optionalDependencies|workspaces|main|module|exports|imports|type|browser|engines)\"\s*:|"
    r"import\b|export\b|module\.exports|plugins?\s*:|presets?\s*:|rules\s*:)",
    re.IGNORECASE,
)
CLASS_PATTERN = re.compile(r"(?m)^\s*(?:export\s+default\s+|export\s+)?class\s+([A-Za-z_$][\w$]*)\b[^{]*\{")
FUNCTION_PATTERN = re.compile(
    r"(?m)^\s*(?:export\s+default\s+|export\s+|async\s+)*"
    r"(?:function\s*\*?\s+([A-Za-z_$][\w$]*)|"
    r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)|"
    r"([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*)\s*\{"
)
DEFINITION_PATTERNS = (
    re.compile(r"\b(?:export\s+default\s+|export\s+)?(?:async\s+)?function\s*\*?\s+([A-Za-z_$][\w$]*)\s*\("),
    re.compile(r"\b(?:function\s*)?\*\s*([A-Za-z_$][\w$]*)\s*\("),
    re.compile(r"\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)"),
    re.compile(r"\b([A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)"),
    CLASS_PATTERN,
)


def extract_import_context(file_text, path, make_context_item, selected_range=None):
    if is_project_file(path):
        return extract_project_context(file_text, path, make_context_item)

    rows = []
    for index, line in enumerate(file_text.splitlines(), start=1):
        if IMPORT_PATTERN.match(line):
            rows.append((index, line))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "JavaScript imports, exports, and require calls.", 80)


def extract_project_context(file_text, path, make_context_item):
    rows = []
    for index, line in enumerate(file_text.splitlines(), start=1):
        if PROJECT_CONTEXT_PATTERN.search(line):
            rows.append((index, line))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "JavaScript package, dependency, and tooling configuration.", 85)


def find_enclosing_symbol_context(file_text, path, selected_range, make_context_item):
    if is_project_file(path):
        return None

    for pattern, reason, kind in (
        (FUNCTION_PATTERN, "Enclosing JavaScript function or method.", "symbol"),
        (CLASS_PATTERN, "Enclosing JavaScript class.", "class"),
    ):
        block = enclosing_brace_block(file_text, selected_range, pattern)
        if block:
            start_line, end_line, content = block
            return make_context_item(kind, path, LANGUAGE, start_line, end_line, reason, content, 90)
    return None


def is_project_file(path):
    return bool(path and str(path.name).lower() in FILENAMES)
