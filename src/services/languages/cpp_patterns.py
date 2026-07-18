import re

from src.services.languages.language_utils import context_from_rows, enclosing_brace_block


LANGUAGE = "cpp"
EXTENSIONS = {
    ".cpp",
    ".cc",
    ".cxx",
    ".c++",
    ".hpp",
    ".hh",
    ".hxx",
    ".h++",
    ".ipp",
    ".inl",
    ".h",
    ".ixx",
    ".cppm",
    ".mpp",
    ".cu",
    ".cuh",
    ".mm",
    ".vcxproj",
    ".filters",
    ".cmake",
    ".ninja",
}
FILENAMES = {
    "cmakelists.txt",
    "cmakepresets.json",
    "ctesttestfile.cmake",
    "conanfile.txt",
    "conanfile.py",
    "vcpkg.json",
    "meson.build",
    "meson_options.txt",
    "build.ninja",
    "premake5.lua",
    "xmake.lua",
}
FILENAME_PATTERNS = (
    re.compile(r".*\.vcxproj(?:\.filters|\.user)?$", re.IGNORECASE),
)
TEST_NAME_PATTERNS = (
    re.compile(r".*(?:test|tests|spec|specs).*\.c(?:pp|c|xx|\+\+)$", re.IGNORECASE),
    re.compile(r".*(?:test|tests|spec|specs).*\.h(?:pp|h|xx|\+\+)$", re.IGNORECASE),
)
BUILD_EXTENSIONS = {".vcxproj", ".filters", ".cmake", ".ninja"}
BUILD_FILENAMES = FILENAMES
INCLUDE_PATTERN = re.compile(r"^\s*#\s*include\s+[<\"].*[>\"]", re.MULTILINE)
BUILD_CONTEXT_PATTERN = re.compile(
    r"^\s*(?:project\s*\(|add_(?:executable|library|subdirectory)\s*\(|target_(?:link_libraries|include_directories|sources|compile_definitions|compile_options)\s*\(|"
    r"find_(?:package|library|path|file)\s*\(|set\s*\(|option\s*\(|include\s*\(|"
    r"\[?ClCompile\b|\[?ClInclude\b|<Project\b|<ItemGroup\b|<PropertyGroup\b|<Import\b|<PackageReference\b|"
    r"(?:executable|library|project|dependency)\s*\(|(?:requires|generators|options|default_options)\s*=)",
    re.IGNORECASE,
)
NAMESPACE_PATTERN = re.compile(r"^\s*namespace\s+(?:[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*|\{)", re.MULTILINE)
TYPE_PATTERN = re.compile(
    r"^\s*(?:template\s*<[^;{}]+>\s*)?"
    r"(?:class|struct|enum\s+class|enum|union)\s+([A-Za-z_]\w*)",
    re.MULTILINE,
)
FUNCTION_PATTERN = re.compile(
    r"(?m)^\s*"
    r"(?:template\s*<[^;{}]+>\s*)?"
    r"(?:constexpr\s+|consteval\s+|constinit\s+|static\s+|extern\s+|inline\s+|virtual\s+|explicit\s+|friend\s+)*"
    r"(?:[\w:<>~,\[\]\*&]+\s+)+"
    r"([A-Za-z_~]\w*(?:::[A-Za-z_~]\w*)?|operator\s*[^\s(]+)\s*"
    r"\([^;{}]*\)\s*(?:const\s*)?(?:noexcept\s*)?(?:override\s*)?(?:final\s*)?(?:->\s*[\w:<>~,\[\]\*&\s]+)?\s*\{"
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
        if INCLUDE_PATTERN.match(line):
            rows.append((index, line))
        elif selected_line and index <= selected_line and (NAMESPACE_PATTERN.match(line) or TYPE_PATTERN.match(line)):
            rows.append((index, line.strip()))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "C++ includes and nearby namespace/type headers.", 80)


def extract_build_context(file_text, path, make_context_item):
    rows = []
    for index, line in enumerate(file_text.splitlines(), start=1):
        if BUILD_CONTEXT_PATTERN.search(line):
            rows.append((index, line))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "C/C++ project targets, dependencies, sources, and build settings.", 85)


def find_enclosing_symbol_context(file_text, path, selected_range, make_context_item):
    if is_build_file(path):
        return None

    block = enclosing_brace_block(file_text, selected_range, FUNCTION_PATTERN)
    if block:
        start_line, end_line, content = block
        return make_context_item("symbol", path, LANGUAGE, start_line, end_line, "Enclosing C++ function or method for the selected code.", content, 90)

    block = enclosing_brace_block(file_text, selected_range, TYPE_PATTERN)
    if not block:
        return None
    start_line, end_line, content = block
    return make_context_item("class", path, LANGUAGE, start_line, end_line, "Enclosing C++ type for the selected code.", content, 85)


def is_build_file(path):
    if not path:
        return False
    name = str(path.name).lower()
    suffixes = tuple(suffix.lower() for suffix in path.suffixes)
    return path.suffix.lower() in BUILD_EXTENSIONS or name in BUILD_FILENAMES or suffixes[-2:] == (".vcxproj", ".filters")


def detect_from_content(path, file_text):
    if not path:
        return None
    text = file_text or ""
    if path.suffix.lower() in {".props", ".targets", ".xml"} and re.search(r"<(?:ClCompile|ClInclude|VCTargetsPath|PlatformToolset)\b", text, re.IGNORECASE):
        return LANGUAGE
    return None
