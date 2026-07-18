import re


def compute_line_start_offsets(text):
    offsets = [0]
    for match in re.finditer(r"\n", text):
        offsets.append(match.end())
    return offsets


def offset_to_line(line_starts, offset):
    line = 1
    for index, line_start in enumerate(line_starts, start=1):
        if line_start > offset:
            break
        line = index
    return line


def find_matching_brace(text, open_offset):
    if open_offset < 0 or open_offset >= len(text) or text[open_offset] != "{":
        return -1
    depth = 0
    in_string = None
    escaped = False
    in_line_comment = False
    in_block_comment = False
    in_template = False

    for index in range(open_offset, len(text)):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
            continue
        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
            continue
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
            continue
        if in_template:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "`":
                in_template = False
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            continue
        if char in ("'", '"'):
            in_string = char
            continue
        if char == "`":
            in_template = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def find_matching_tag(text, tag_name, start_offset):
    if not tag_name:
        return -1
    pattern = re.compile(r"</?\s*" + re.escape(tag_name) + r"\b[^>]*>", re.IGNORECASE)
    depth = 0
    for match in pattern.finditer(text, start_offset):
        token = match.group(0)
        if token.startswith("</"):
            depth -= 1
            if depth <= 0:
                return match.end()
        elif token.endswith("/>"):
            continue
        else:
            depth += 1
    return -1


def enclosing_brace_block(file_text, selected_range, pattern):
    selected_start, selected_end = selected_range
    lines = file_text.splitlines()
    line_starts = compute_line_start_offsets(file_text)
    selected_offset = line_starts[max(0, selected_start - 1)] if selected_start else 0
    best = None

    for match in pattern.finditer(file_text):
        open_brace = file_text.find("{", match.end() - 1)
        close_brace = find_matching_brace(file_text, open_brace)
        if close_brace == -1 or not (match.start() <= selected_offset <= close_brace):
            continue
        start_line = offset_to_line(line_starts, match.start())
        end_line = offset_to_line(line_starts, close_brace)
        if selected_end and end_line < selected_end:
            continue
        if not best or (end_line - start_line) < (best["end_line"] - best["start_line"]):
            best = {"start_line": start_line, "end_line": end_line}

    if not best:
        return None
    content = "\n".join(lines[best["start_line"] - 1 : best["end_line"]])
    return best["start_line"], best["end_line"], content


def context_from_rows(rows, path, language, make_context_item, reason, score=80):
    if not rows:
        return None
    rows = sorted(rows, key=lambda row: row[0])
    start = rows[0][0]
    end = rows[-1][0]
    content = "\n".join(line for _, line in rows)
    return make_context_item("import_block", path, language, start, end, reason, content, score)

