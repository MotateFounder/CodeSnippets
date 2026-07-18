import csv
import json
import os
import re
import shutil
import threading
import tkinter as tk
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.config.constants import MAX_SEARCH_BYTES, TEXT_EXTENSIONS


class SyntaxMixin:
    def _highlight_syntax(self):
        if not self.editor:
            return
        content = self.editor.get("1.0", tk.END)
        for tag in ("keyword", "string", "comment", "number"):
            self.editor.tag_remove(tag, "1.0", tk.END)

        patterns = {
            "comment": r"//[^\n]*|#[^\n]*|/\*[\s\S]*?\*/",
            "string": r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'',
            "number": r"\b\d+(?:\.\d+)?\b",
            "keyword": (
                r"\b(class|struct|enum|namespace|template|typename|using|public|private|"
                r"protected|virtual|override|const|constexpr|static|inline|return|if|else|"
                r"for|while|switch|case|break|continue|try|catch|throw|new|delete|auto|"
                r"void|int|long|short|double|float|bool|char|unsigned|signed|std|string|"
                r"vector|map|set|include|define|function|let|var|import|export|from|async|"
                r"await|this|null|true|false|def|elif|with|as|lambda|None|True|False|self)\b"
            ),
        }

        for tag, pattern in patterns.items():
            for match in re.finditer(pattern, content, flags=re.MULTILINE):
                start = f"1.0+{match.start()}c"
                end = f"1.0+{match.end()}c"
                self.editor.tag_add(tag, start, end)


    def _highlight_code_widget(self, widget):
        content = widget.get("1.0", tk.END)
        patterns = {
            "comment": r"//[^\n]*|#[^\n]*|/\*[\s\S]*?\*/",
            "string": r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'',
            "number": r"\b\d+(?:\.\d+)?\b",
            "keyword": (
                r"\b(class|struct|enum|namespace|template|typename|using|public|private|"
                r"protected|virtual|override|const|constexpr|static|inline|return|if|else|"
                r"for|while|switch|case|break|continue|try|catch|throw|new|delete|auto|"
                r"void|int|long|short|double|float|bool|char|unsigned|signed|std|string|"
                r"vector|map|set|include|define|function|let|var|import|export|from|async|"
                r"await|this|null|true|false|def|elif|with|as|lambda|None|True|False|self)\b"
            ),
        }
        for tag, pattern in patterns.items():
            for match in re.finditer(pattern, content, flags=re.MULTILINE):
                widget.tag_add(tag, f"1.0+{match.start()}c", f"1.0+{match.end()}c")
