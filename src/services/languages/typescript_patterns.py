import re

from src.services.languages import javascript_patterns
from src.services.languages.language_utils import context_from_rows, enclosing_brace_block


LANGUAGE = "typescript"
EXTENSIONS = {".ts", ".tsx", ".mts", ".cts"}
FILENAMES = {
    "tsconfig.json",
    "tsconfig.base.json",
    "tsconfig.build.json",
    "tsconfig.app.json",
    "tsconfig.spec.json",
    "tsconfig.node.json",
    "tsconfig.lib.json",
    "tsconfig.eslint.json",
    "typedoc.json",
    "api-extractor.json",
}
FILENAME_PATTERNS = (
    re.compile(r"tsconfig\..*\.json$", re.IGNORECASE),
    re.compile(r".*\.d\.ts$", re.IGNORECASE),
)
TEST_NAME_PATTERNS = (
    re.compile(r".*\.(?:test|spec)\.tsx?$", re.IGNORECASE),
)
IMPORT_PATTERN = javascript_patterns.IMPORT_PATTERN
PROJECT_CONTEXT_PATTERN = re.compile(
    r"^\s*\"(?:compilerOptions|references|extends|files|include|exclude|paths|baseUrl|types|typeRoots|lib|target|module|moduleResolution|jsx|declaration|composite)\"\s*:",
    re.IGNORECASE,
)
CLASS_PATTERN = javascript_patterns.CLASS_PATTERN
FUNCTION_PATTERN = re.compile(
    r"(?m)^\s*(?:export\s+|default\s+|declare\s+|async\s+)*"
    r"(?:function\s+([A-Za-z_$][\w$]*)|"
    r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*:\s*[^=]+=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>|"
    r"([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*:\s*[^={;]+)\s*\{"
)
INTERFACE_PATTERN = re.compile(r"(?m)^\s*(?:export\s+)?(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)\b[^{=]*(?:\{|=)")
DEFINITION_PATTERNS = (
    re.compile(r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("),
    re.compile(r"\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)"),
    re.compile(r"\b(?:export\s+)?(?:class|interface|type|enum)\s+([A-Za-z_$][\w$]*)\b"),
    re.compile(r"\b([A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)"),
)


def extract_import_context(file_text, path, make_context_item, selected_range=None):
    if is_project_file(path):
        return extract_project_context(file_text, path, make_context_item)

    rows = []
    for index, line in enumerate(file_text.splitlines(), start=1):
        if IMPORT_PATTERN.match(line):
            rows.append((index, line))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "TypeScript imports and exports.", 80)


def extract_project_context(file_text, path, make_context_item):
    rows = []
    for index, line in enumerate(file_text.splitlines(), start=1):
        if PROJECT_CONTEXT_PATTERN.search(line):
            rows.append((index, line))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "TypeScript compiler options, references, and path mappings.", 85)


def find_enclosing_symbol_context(file_text, path, selected_range, make_context_item):
    if is_project_file(path):
        return None

    for pattern, reason, kind in (
        (FUNCTION_PATTERN, "Enclosing TypeScript function or method.", "symbol"),
        (CLASS_PATTERN, "Enclosing TypeScript class.", "class"),
        (INTERFACE_PATTERN, "Enclosing TypeScript type/interface/enum.", "class"),
    ):
        block = enclosing_brace_block(file_text, selected_range, pattern)
        if block:
            start_line, end_line, content = block
            return make_context_item(kind, path, LANGUAGE, start_line, end_line, reason, content, 90)
    return None


def is_project_file(path):
    if not path:
        return False
    name = str(path.name).lower()
    return name in FILENAMES or any(pattern.match(name) for pattern in FILENAME_PATTERNS)
