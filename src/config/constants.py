"""
Defines configuration constants for file type identification and search limits.

This module centralizes constants used throughout the application for defining recognized code and text file extensions, alongside system limits for operations like file searching.

Main contents:
* :attr:`CODE_TEXT_EXTENSIONS`: A dictionary mapping various source code file extensions.
* :attr:`TEXT_EXTENSIONS`: Alias for `CODE_TEXT_EXTENSIONS`.
* :attr:`MAX_SEARCH_BYTES`: The maximum byte size allowed for search operations.
"""

CODE_TEXT_EXTENSIONS = {
    ".adb", ".ads", ".ahk", ".applescript", ".asm", ".asp", ".aspx", ".astro",
    ".awk", ".bat", ".blade.php", ".c", ".c++", ".cbl", ".cc", ".cfg", ".clj", ".cljs",
    ".cmake", ".cmd", ".coffee", ".conf", ".cpp", ".cppm", ".cs", ".cshtml", ".csproj", ".csx", ".css",
    ".csv", ".cts", ".cu", ".cuh", ".dart", ".diff", ".dockerfile", ".dtd", ".edn",
    ".elm", ".erl", ".ex", ".exs", ".f", ".f03", ".f08", ".f90", ".filters", ".fish",
    ".fs", ".fsi", ".fsx", ".g4", ".gd", ".glsl", ".go", ".graphql", ".groovy",
    ".h", ".h++", ".haml", ".handlebars", ".hbs", ".hh", ".hpp", ".hrl", ".hs", ".htm",
    ".html", ".hxx", ".i", ".inc", ".ini", ".inl", ".ino", ".ipp", ".ixx", ".java", ".jl", ".js", ".json",
    ".json5", ".jsx", ".jsp", ".kt", ".kts", ".less", ".lhs", ".lisp", ".ll",
    ".lua", ".m", ".mak", ".make", ".markdown", ".md", ".mdx", ".mjs", ".mk", ".mlapp", ".mlappinstall", ".mlx", ".mm",
    ".mpp", ".mts", ".mustache", ".nim", ".ninja", ".nix", ".pas", ".patch", ".perl", ".php", ".pl",
    ".plist", ".pm", ".prj", ".props", ".ps1", ".psm1", ".pug", ".py", ".pyi", ".r", ".razor", ".rb",
    ".resx", ".rs", ".rst", ".ruleset", ".sass", ".scala", ".scss", ".sh", ".sln", ".slnx", ".sql",
    ".svelte", ".swift", ".targets", ".tcl", ".tex", ".toml", ".ts", ".tsx", ".twig", ".txt",
    ".vb", ".vbs", ".vcxproj", ".vh", ".vhd", ".vhdl", ".vue", ".xaml", ".xhtml", ".xml",
    ".xsd", ".xsl", ".xslt", ".yaml", ".yml", ".zig",
}

TEXT_EXTENSIONS = CODE_TEXT_EXTENSIONS

MAX_SEARCH_BYTES = 2 * 1024 * 1024
