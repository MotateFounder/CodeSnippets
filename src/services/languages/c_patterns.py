import re

from src.services.languages.language_utils import context_from_rows, enclosing_brace_block


LANGUAGE = "c"
EXTENSIONS = {".c", ".i", ".mk", ".mak", ".make"}
FILENAMES = {
    "makefile",
    "gnumakefile",
    "bsdmakefile",
    "nmakefile",
    "configure",
    "configure.ac",
    "configure.in",
    "makefile.am",
    "makefile.in",
}
TEST_NAME_PATTERNS = (
    re.compile(r".*(?:test|tests|spec|specs).*\.c$", re.IGNORECASE),
)
BUILD_EXTENSIONS = {".mk", ".mak", ".make"}
BUILD_FILENAMES = FILENAMES
INCLUDE_PATTERN = re.compile(r"^\s*#\s*include\s+[<\"].*[>\"]", re.MULTILINE)
DEFINE_PATTERN = re.compile(r"^\s*#\s*(?:define|ifdef|ifndef|if|elif|endif)\b.*", re.MULTILINE)
MAKE_CONTEXT_PATTERN = re.compile(
    r"^\s*(?:[A-Za-z_][\w.-]*\s*(?::|[+:?]?=)|include\s+|"
    r"(?:CC|CFLAGS|CPPFLAGS|LDFLAGS|LDLIBS|AR|AS|OBJS|SRCS|TARGET)\b|"
    r"AC_(?:INIT|CONFIG|PROG|CHECK)|AM_INIT_AUTOMAKE)",
    re.IGNORECASE,
)
FUNCTION_PATTERN = re.compile(
    r"(?m)^\s*"
    r"(?:static\s+|extern\s+|inline\s+|const\s+|volatile\s+|unsigned\s+|signed\s+|struct\s+\w+\s+|enum\s+\w+\s+)*"
    r"(?:[A-Za-z_]\w*[\w\s\*]*\s+)+"
    r"([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{"
)
DEFINITION_PATTERNS = (
    FUNCTION_PATTERN,
    re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE),
)


def extract_import_context(file_text, path, make_context_item, selected_range=None):
    if is_build_file(path):
        return extract_build_context(file_text, path, make_context_item)

    rows = []
    selected_line = selected_range[0] if selected_range else None
    for index, line in enumerate(file_text.splitlines(), start=1):
        if INCLUDE_PATTERN.match(line) or (selected_line and index <= selected_line and DEFINE_PATTERN.match(line)):
            rows.append((index, line))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "C includes and nearby preprocessor context.", 80)


def extract_build_context(file_text, path, make_context_item):
    rows = []
    for index, line in enumerate(file_text.splitlines(), start=1):
        if MAKE_CONTEXT_PATTERN.match(line):
            rows.append((index, line))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "C/C build targets, variables, and configure checks.", 85)


def find_enclosing_symbol_context(file_text, path, selected_range, make_context_item):
    if is_build_file(path):
        return None

    block = enclosing_brace_block(file_text, selected_range, FUNCTION_PATTERN)
    if not block:
        return None
    start_line, end_line, content = block
    return make_context_item("symbol", path, LANGUAGE, start_line, end_line, "Enclosing C function for the selected code.", content, 90)


def is_build_file(path):
    if not path:
        return False
    name = str(path.name).lower()
    return path.suffix.lower() in BUILD_EXTENSIONS or name in BUILD_FILENAMES
