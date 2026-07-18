import re

from src.services.languages import cpp_patterns
from src.services.languages.language_utils import context_from_rows, enclosing_brace_block


LANGUAGE = "juce"
EXTENSIONS = {".jucer"}
FILENAMES = {
    "juceconfig.h",
    "appconfig.h",
}
TEST_NAME_PATTERNS = (
    re.compile(r".*(?:test|tests|spec|specs).*\.jucer$", re.IGNORECASE),
)
JUCE_MACRO_PATTERN = re.compile(
    r"\b(?:JUCE_DECLARE_|JUCE_IMPLEMENT_|START_JUCE_APPLICATION|juce_add_|juce_generate_)\w*",
    re.IGNORECASE,
)
JUCE_SOURCE_PATTERN = re.compile(
    r"(?:#\s*include\s+[<\"].*juce|namespace\s+juce\b|\bjuce::|\bJUCE_[A-Z_]+\b|START_JUCE_APPLICATION|juce_add_(?:plugin|gui_app|console_app|module))",
    re.IGNORECASE,
)
DEFINITION_PATTERNS = cpp_patterns.DEFINITION_PATTERNS + (
    re.compile(r"\bSTART_JUCE_APPLICATION\s*\(\s*([A-Za-z_]\w*)\s*\)"),
    re.compile(r"\bjuce_add_(?:plugin|gui_app|console_app|module)\s*\(\s*([A-Za-z_]\w*)", re.IGNORECASE),
)


def extract_import_context(file_text, path, make_context_item, selected_range=None):
    rows = []
    selected_line = selected_range[0] if selected_range else None
    for index, line in enumerate(file_text.splitlines(), start=1):
        stripped = line.strip()
        if cpp_patterns.INCLUDE_PATTERN.match(line):
            rows.append((index, line))
        elif selected_line and index <= selected_line and (stripped.startswith("<") or JUCE_MACRO_PATTERN.search(line)):
            rows.append((index, line))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "JUCE includes, project tags, and JUCE macro context.", 80)


def find_enclosing_symbol_context(file_text, path, selected_range, make_context_item):
    block = enclosing_brace_block(file_text, selected_range, cpp_patterns.FUNCTION_PATTERN)
    if block:
        start_line, end_line, content = block
        return make_context_item("symbol", path, LANGUAGE, start_line, end_line, "Enclosing JUCE/C++ function or method.", content, 90)
    return None


def is_juce_source(file_text):
    return bool(JUCE_SOURCE_PATTERN.search(file_text or ""))
