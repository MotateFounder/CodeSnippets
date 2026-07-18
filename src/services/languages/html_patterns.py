import re

from src.services.languages.language_utils import find_matching_tag, offset_to_line, compute_line_start_offsets


LANGUAGE = "html"
EXTENSIONS = {".html", ".htm", ".xhtml", ".cshtml", ".razor", ".astro", ".svelte", ".vue", ".jsp", ".aspx"}
FILENAMES = {
    "index.html",
}
TEST_NAME_PATTERNS = ()
IMPORT_PATTERN = re.compile(
    r"^\s*<(?:script|link)\b[^>]*(?:src|href)\s*=\s*[\"'][^\"']+[\"'][^>]*>",
    re.IGNORECASE | re.MULTILINE,
)
TAG_PATTERN = re.compile(r"<\s*([A-Za-z][\w:-]*)\b[^>]*>")
ID_CLASS_PATTERN = re.compile(r"\b(?:id|class)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
DEFINITION_PATTERNS = (
    re.compile(r"<\s*(template|slot|section|article|main|form|script)\b", re.IGNORECASE),
)


def extract_import_context(file_text, path, make_context_item, selected_range=None):
    rows = []
    for index, line in enumerate(file_text.splitlines(), start=1):
        if IMPORT_PATTERN.match(line):
            rows.append((index, line))
    if not rows:
        return None
    start = rows[0][0]
    end = rows[-1][0]
    content = "\n".join(line for _, line in rows)
    return make_context_item("import_block", path, LANGUAGE, start, end, "HTML linked scripts and stylesheets.", content, 80)


def find_enclosing_symbol_context(file_text, path, selected_range, make_context_item):
    selected_start, selected_end = selected_range
    line_starts = compute_line_start_offsets(file_text)
    selected_offset = line_starts[max(0, selected_start - 1)] if selected_start else 0
    best = None

    for match in TAG_PATTERN.finditer(file_text):
        tag_name = match.group(1).lower()
        if tag_name in {"br", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}:
            continue
        close_offset = find_matching_tag(file_text, tag_name, match.start())
        if close_offset == -1 or not (match.start() <= selected_offset <= close_offset):
            continue
        start_line = offset_to_line(line_starts, match.start())
        end_line = offset_to_line(line_starts, close_offset)
        if selected_end and end_line < selected_end:
            continue
        if not best or (end_line - start_line) < (best["end_line"] - best["start_line"]):
            best = {"start_line": start_line, "end_line": end_line, "tag": tag_name}

    if not best:
        return None
    lines = file_text.splitlines()
    content = "\n".join(lines[best["start_line"] - 1 : best["end_line"]])
    return make_context_item("symbol", path, LANGUAGE, best["start_line"], best["end_line"], f"Enclosing HTML <{best['tag']}> element.", content, 85)
