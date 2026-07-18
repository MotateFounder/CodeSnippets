import re


DEFINITION_PATTERNS = (
    re.compile(r"\b(?:inline|constexpr|suspend|func|fun)\s+([A-Za-z_]\w*)\s*\("),
    re.compile(r"(?m)^\s*(?:[A-Za-z_][\w:<>,\[\]*&]*\s+)+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:const\s*)?(?:\{|=>)"),
)

