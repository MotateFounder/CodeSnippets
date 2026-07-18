import re

from src.services.languages.common_patterns import CALL_EXCLUSIONS, CALL_PATTERN
from src.services.languages.c_patterns import DEFINITION_PATTERNS as C_DEFINITION_PATTERNS
from src.services.languages.cpp_patterns import DEFINITION_PATTERNS as CPP_DEFINITION_PATTERNS
from src.services.languages.csharp_patterns import DEFINITION_PATTERNS as CSHARP_DEFINITION_PATTERNS
from src.services.languages.css_patterns import DEFINITION_PATTERNS as CSS_DEFINITION_PATTERNS
from src.services.languages.generic_patterns import DEFINITION_PATTERNS as GENERIC_DEFINITION_PATTERNS
from src.services.languages.html_patterns import DEFINITION_PATTERNS as HTML_DEFINITION_PATTERNS
from src.services.languages.javascript_patterns import DEFINITION_PATTERNS as JAVASCRIPT_DEFINITION_PATTERNS
from src.services.languages.juce_patterns import DEFINITION_PATTERNS as JUCE_DEFINITION_PATTERNS
from src.services.languages.matlab_patterns import DEFINITION_PATTERNS as MATLAB_DEFINITION_PATTERNS
from src.services.languages.python_patterns import (
    DEFINITION_PATTERNS as PYTHON_DEFINITION_PATTERNS,
    DEFINITION_TYPES as PYTHON_DEFINITION_TYPES,
)
from src.services.languages.typescript_patterns import DEFINITION_PATTERNS as TYPESCRIPT_DEFINITION_PATTERNS


SNIPPET_HEADER_PATTERN = re.compile(r"^=====\s*(.*?)\s*=====\s*$", re.MULTILINE)

DEFINITION_PATTERNS = (
    PYTHON_DEFINITION_PATTERNS
    + JAVASCRIPT_DEFINITION_PATTERNS
    + TYPESCRIPT_DEFINITION_PATTERNS
    + CSHARP_DEFINITION_PATTERNS
    + C_DEFINITION_PATTERNS
    + CPP_DEFINITION_PATTERNS
    + HTML_DEFINITION_PATTERNS
    + CSS_DEFINITION_PATTERNS
    + MATLAB_DEFINITION_PATTERNS
    + JUCE_DEFINITION_PATTERNS
    + GENERIC_DEFINITION_PATTERNS
)
