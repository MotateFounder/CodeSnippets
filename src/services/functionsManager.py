from src.services.function_scanner import (
    detect_language,
    _functions_from_language_ast,
    _functions_from_text,
    _iter_snippet_sources,
)


def processCodeSnippets(code_snippets):
    return {
        "functions": list_functions_in_snippets(code_snippets),
    }


def list_functions_in_snippets(code_snippets):
    """Return function definitions and calls found in Code Snippet Collector snippets.

    The input may be saved snippet text, in-memory snippet dictionaries,
    or a raw code string.
    """
    functions = []
    seen = set()

    for snippet in _iter_snippet_sources(code_snippets):
        source = snippet["source"]
        code = snippet["text"]
        language = detect_language(source, code)
        for name in _functions_from_language_ast(source, code) or _functions_from_text(code, language):
            if name not in seen:
                seen.add(name)
                functions.append(name)

    return functions
