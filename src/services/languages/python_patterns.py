import ast
import re


LANGUAGE = "python"
EXTENSIONS = {".py", ".pyi"}
TEST_NAME_PATTERNS = (
    re.compile(r"^test_.*\.py$", re.IGNORECASE),
    re.compile(r".*_test\.py$", re.IGNORECASE),
)
DEFINITION_TYPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
)
DEFINITION_PATTERNS = (
    re.compile(r"\b(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\("),
)


def extract_import_context(file_text, path, make_context_item, selected_range=None):
    lines = file_text.splitlines()
    collected = []
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            collected.append((index, line))
        elif collected and stripped and not line.startswith((" ", "\t")):
            break
    if not collected:
        return None
    start = collected[0][0]
    end = collected[-1][0]
    content = "\n".join(line for _, line in collected)
    return make_context_item("import_block", path, LANGUAGE, start, end, "Imports used by the selected file.", content, 80)


def find_enclosing_symbol_context(file_text, path, selected_range, make_context_item):
    try:
        tree = ast.parse(file_text)
    except SyntaxError:
        return None

    selected_start, selected_end = selected_range
    best_node = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None)
        if start and end and start <= selected_start and selected_end <= end:
            if not best_node or (end - start) < (best_node.end_lineno - best_node.lineno):
                best_node = node

    if not best_node:
        return None

    lines = file_text.splitlines()
    content = "\n".join(lines[best_node.lineno - 1 : best_node.end_lineno])
    kind = "class" if isinstance(best_node, ast.ClassDef) else "symbol"
    return make_context_item(
        kind,
        path,
        LANGUAGE,
        best_node.lineno,
        best_node.end_lineno,
        f"Enclosing Python {best_node.__class__.__name__} for the selected code.",
        content,
        90,
    )


def functions_from_ast(source, code):
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    nodes = sorted(
        ast.walk(tree),
        key=lambda node: (getattr(node, "lineno", -1), getattr(node, "col_offset", -1)),
    )
    names = []
    for node in nodes:
        if isinstance(node, DEFINITION_TYPES):
            names.append(node.name)
        elif isinstance(node, ast.Call):
            name = call_name(node.func)
            if name:
                names.append(name)

    return names


def call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))
    return ""

