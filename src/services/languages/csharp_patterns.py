import re

from src.services.languages.language_utils import context_from_rows, enclosing_brace_block


LANGUAGE = "csharp"
EXTENSIONS = {
    ".cs",
    ".csx",
    ".csproj",
    ".sln",
    ".slnx",
    ".props",
    ".targets",
    ".ruleset",
    ".resx",
    ".xaml",
    ".razor",
}
FILENAMES = {
    "app.config",
    "web.config",
    "packages.config",
    "directory.build.props",
    "directory.build.targets",
    "directory.packages.props",
    "global.json",
    "nuget.config",
}
TEST_NAME_PATTERNS = (
    re.compile(r".*\.tests\.cs$", re.IGNORECASE),
    re.compile(r".*test\.cs$", re.IGNORECASE),
)
PROJECT_EXTENSIONS = {".csproj", ".sln", ".slnx", ".props", ".targets", ".ruleset", ".resx", ".xaml"}
PROJECT_FILENAMES = {
    "app.config",
    "web.config",
    "packages.config",
    "directory.build.props",
    "directory.build.targets",
    "directory.packages.props",
    "global.json",
    "nuget.config",
}
PROJECT_CONTEXT_PATTERN = re.compile(
    r"<\s*(?:Project|Sdk|PropertyGroup|ItemGroup|TargetFrameworks?|OutputType|RootNamespace|AssemblyName|"
    r"PackageReference|ProjectReference|Reference|Import|Compile|None|Content|EmbeddedResource|Analyzer|"
    r"LangVersion|Nullable|UseWPF|UseWindowsForms|RuntimeIdentifier|RuntimeIdentifiers|PackageVersion|"
    r"package|add|bindingRedirect)\b|^\s*(?:Project\(|GlobalSection|EndProject|MinimumVisualStudioVersion|VisualStudioVersion)\b",
    re.IGNORECASE,
)
TYPE_PATTERN = re.compile(
    r"(?m)^\s*(?:\[.*?\]\s*)*(?:public|private|protected|internal|static|abstract|sealed|partial|\s)*"
    r"\b(?:class|interface|struct|enum)\s+([A-Za-z_]\w*)"
)
METHOD_PATTERN = re.compile(
    r"(?m)^\s*(?:\[.*?\]\s*)*"
    r"(?:(?:public|private|protected|internal|static|virtual|override|abstract|async|sealed|partial|extern|new)\s+)*"
    r"(?:(?:[A-Za-z_][\w<>,\[\].?]*\s+)+|)"
    r"([A-Za-z_]\w*|operator\s*[^\s(]+)\s*\([^;{}]*\)\s*(?:where\s+[^{]+)?\{"
)
DEFINITION_PATTERNS = (
    re.compile(r"\b(?:public|private|protected|internal|static|sealed|override|virtual|async|partial|extern|new)\s+(?:[A-Za-z_][\w<>,\[\].?]*\s+)*([A-Za-z_]\w*)\s*\("),
    re.compile(r"(?m)^\s*(?:[A-Za-z_][\w:<>,\[\]*&]*\s+)+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:\{|=>)"),
    TYPE_PATTERN,
)


def extract_import_context(file_text, path, make_context_item, selected_range=None):
    if is_project_file(path):
        return extract_project_context(file_text, path, make_context_item)

    lines = file_text.splitlines()
    selected_line = selected_range[0] if selected_range else None
    collected = []
    headers = []

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("using ") and stripped.endswith(";"):
            collected.append((index, line))
        elif stripped.startswith("namespace ") and (not selected_line or index <= selected_line):
            headers.append((index, line))
        elif TYPE_PATTERN.search(line) and (not selected_line or index <= selected_line):
            headers.append((index, line.strip()))

    rows = collected + headers[-3:]
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "Using directives and nearby namespace/type headers for the selected C# code.", 80)


def extract_project_context(file_text, path, make_context_item):
    rows = []
    for index, line in enumerate(file_text.splitlines(), start=1):
        if PROJECT_CONTEXT_PATTERN.search(line):
            rows.append((index, line))
    return context_from_rows(rows, path, LANGUAGE, make_context_item, "C#/.NET project references, packages, and build properties.", 85)


def find_enclosing_symbol_context(file_text, path, selected_range, make_context_item):
    if is_project_file(path):
        return None

    block = enclosing_brace_block(file_text, selected_range, METHOD_PATTERN)
    if block:
        start_line, end_line, content = block
        return make_context_item("symbol", path, LANGUAGE, start_line, end_line, "Enclosing C# method for the selected code.", content, 90)

    block = enclosing_brace_block(file_text, selected_range, TYPE_PATTERN)
    if not block:
        return None
    start_line, end_line, content = block
    return make_context_item("class", path, LANGUAGE, start_line, end_line, "Enclosing C# type for the selected code.", content, 85)


def is_project_file(path):
    if not path:
        return False
    name = str(path.name).lower()
    return path.suffix.lower() in PROJECT_EXTENSIONS or name in PROJECT_FILENAMES


def detect_from_content(path, file_text):
    if not path:
        return None
    name = str(path.name).lower()
    suffix = path.suffix.lower()
    if suffix in {".props", ".targets", ".config", ".json", ".xml"} or name in PROJECT_FILENAMES:
        text = file_text or ""
        if re.search(r"<PackageReference\b|<TargetFrameworks?\b|<ProjectReference\b|<packages\b|nuget|Microsoft\.NET\.Sdk", text, re.IGNORECASE):
            return LANGUAGE
    return None
