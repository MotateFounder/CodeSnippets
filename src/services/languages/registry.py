from pathlib import Path

from src.services.languages import (
    c_patterns,
    cpp_patterns,
    csharp_patterns,
    css_patterns,
    generic_patterns,
    html_patterns,
    javascript_patterns,
    juce_patterns,
    matlab_patterns,
    python_patterns,
    typescript_patterns,
)


LANGUAGE_MODULES = {
    python_patterns.LANGUAGE: python_patterns,
    csharp_patterns.LANGUAGE: csharp_patterns,
    javascript_patterns.LANGUAGE: javascript_patterns,
    typescript_patterns.LANGUAGE: typescript_patterns,
    c_patterns.LANGUAGE: c_patterns,
    cpp_patterns.LANGUAGE: cpp_patterns,
    html_patterns.LANGUAGE: html_patterns,
    css_patterns.LANGUAGE: css_patterns,
    matlab_patterns.LANGUAGE: matlab_patterns,
    juce_patterns.LANGUAGE: juce_patterns,
}

EXTENSION_TO_LANGUAGE = {}
for module in LANGUAGE_MODULES.values():
    for extension in module.EXTENSIONS:
        EXTENSION_TO_LANGUAGE[extension] = module.LANGUAGE

FILENAME_TO_LANGUAGE = {}
for module in LANGUAGE_MODULES.values():
    for filename in getattr(module, "FILENAMES", ()):
        FILENAME_TO_LANGUAGE[filename.lower()] = module.LANGUAGE

LANGUAGE_ALIASES = {
    "c++": cpp_patterns,
    "objective-c++": cpp_patterns,
    "objective-c": c_patterns,
    "scss": css_patterns,
    "sass": css_patterns,
    "less": css_patterns,
}


def language_for_extension(extension):
    return EXTENSION_TO_LANGUAGE.get((extension or "").lower(), "text")


def language_for_filename(name):
    name = (name or "").lower()
    if name in FILENAME_TO_LANGUAGE:
        return FILENAME_TO_LANGUAGE[name]
    for module in LANGUAGE_MODULES.values():
        for pattern in getattr(module, "FILENAME_PATTERNS", ()):
            if pattern.match(name):
                return module.LANGUAGE
    return "text"


def language_for_name(name):
    return LANGUAGE_MODULES.get(name) or LANGUAGE_ALIASES.get(name)


def detect_language(path, file_text=None):
    if not path:
        return "text"
    path = Path(path)
    language = language_for_filename(path.name)
    if language == "text":
        language = language_for_extension(path.suffix)
    for module in LANGUAGE_MODULES.values():
        detector = getattr(module, "detect_from_content", None)
        if detector:
            detected = detector(path, file_text)
            if detected:
                language = detected
                break
    if language in {"cpp", "c"} and juce_patterns.is_juce_source(file_text):
        return juce_patterns.LANGUAGE
    return language


def is_source_file(path):
    return detect_language(path) != "text"


def is_known_language_file(path):
    return detect_language(path) != "text"


def extract_import_context(file_text, path, language, make_context_item, selected_range=None):
    module = language_for_name(language)
    extractor = getattr(module, "extract_import_context", None)
    if not extractor:
        return None
    return extractor(file_text, path, make_context_item, selected_range)


def find_enclosing_symbol_context(file_text, path, language, selected_range, make_context_item):
    module = language_for_name(language)
    finder = getattr(module, "find_enclosing_symbol_context", None)
    if not finder:
        return None
    return finder(file_text, path, selected_range, make_context_item)


def functions_from_ast(source, code):
    module = language_for_name(detect_language(source, code) if source else "python")
    parser = getattr(module, "functions_from_ast", None)
    if not parser:
        return []
    return parser(source, code)


def definition_patterns_for(language):
    module = language_for_name(language)
    patterns = getattr(module, "DEFINITION_PATTERNS", None)
    if patterns:
        return patterns
    return fallback_definition_patterns()


def fallback_definition_patterns():
    return (
        python_patterns.DEFINITION_PATTERNS
        + javascript_patterns.DEFINITION_PATTERNS
        + typescript_patterns.DEFINITION_PATTERNS
        + csharp_patterns.DEFINITION_PATTERNS
        + c_patterns.DEFINITION_PATTERNS
        + cpp_patterns.DEFINITION_PATTERNS
        + html_patterns.DEFINITION_PATTERNS
        + css_patterns.DEFINITION_PATTERNS
        + matlab_patterns.DEFINITION_PATTERNS
        + juce_patterns.DEFINITION_PATTERNS
        + generic_patterns.DEFINITION_PATTERNS
    )


def test_name_patterns():
    patterns = []
    for module in LANGUAGE_MODULES.values():
        patterns.extend(getattr(module, "TEST_NAME_PATTERNS", ()))
    return tuple(patterns)
