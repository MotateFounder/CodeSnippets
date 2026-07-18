import re


CALL_PATTERN = re.compile(
    r"(?<![\w$])([A-Za-z_$][\w$]*(?:(?:\.|::)[A-Za-z_$][\w$]*)*)\s*\("
)

CALL_EXCLUSIONS = {
    "if",
    "for",
    "foreach",
    "while",
    "switch",
    "catch",
    "with",
    "return",
    "sizeof",
    "typeof",
    "new",
    "class",
    "struct",
    "enum",
    "namespace",
    "function",
    "def",
    "elif",
    "else",
    "try",
    "except",
    "finally",
    "lambda",
    "import",
    "from",
    "assert",
    "await",
    "yield",
}

