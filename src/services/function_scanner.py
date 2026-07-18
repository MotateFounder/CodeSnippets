import keyword
import re

from src.services.languages import definition_patterns_for, detect_language, functions_from_ast
from src.services.languages.common_patterns import (
    CALL_EXCLUSIONS,
    CALL_PATTERN,
)
from src.services.function_patterns import SNIPPET_HEADER_PATTERN


def _iter_snippet_sources(code_snippets):
    if isinstance(code_snippets, str):
        parsed = _parse_saved_snippet_text(code_snippets)
        if parsed:
            yield from parsed
        elif code_snippets.strip():
            yield {"source": "", "text": code_snippets}
        return

    if isinstance(code_snippets, dict):
        text = code_snippets.get("text", "")
        if text and str(text).strip():
            yield {"source": code_snippets.get("source", ""), "text": str(text)}
        return

    for snippet in code_snippets or []:
        if isinstance(snippet, dict):
            text = snippet.get("text", "")
            if text and str(text).strip():
                yield {"source": snippet.get("source", ""), "text": str(text)}
        elif snippet and str(snippet).strip():
            yield {"source": "", "text": str(snippet)}


def _parse_saved_snippet_text(text):
    matches = list(SNIPPET_HEADER_PATTERN.finditer(text))
    snippets = []

    for index, match in enumerate(matches):
        source = match.group(1).strip()
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip("\r\n")
        if source.lower() == "file tree structure":
            continue
        if source and body.strip():
            snippets.append({"source": source, "text": body})

    return snippets


def _functions_from_language_ast(source, code):
    return functions_from_ast(source, code)


def _functions_from_python_ast(source, code):
    return _functions_from_language_ast(source, code)


def _functions_from_text(code, language=None):
    cleaned = _strip_comments_and_strings(code)
    names = []

    for pattern in definition_patterns_for(language):
        names.extend(match.group(1) for match in pattern.finditer(cleaned))

    for match in CALL_PATTERN.finditer(cleaned):
        name = match.group(1)
        base_name = re.split(r"\.|::", name)[-1]
        if base_name in CALL_EXCLUSIONS or keyword.iskeyword(base_name):
            continue
        names.append(name)

    return names


def _strip_comments_and_strings(code):
    cleaned = re.sub(r"//.*?$|/\*.*?\*/|#.*?$", "", code, flags=re.MULTILINE | re.DOTALL)
    cleaned = re.sub(r'"""(?:\\.|.)*?"""|\'\'\'(?:\\.|.)*?\'\'\'', "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"""(["'`])(?:\\.|(?!\1).)*\1""", "", cleaned, flags=re.DOTALL)
    return cleaned
