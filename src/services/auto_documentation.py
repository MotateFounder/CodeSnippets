#!/usr/bin/env python3
"""
Autonomous Python auto-documenter for the current folder tree.

Behavior:
- Recursively scans the current working directory for .py files.
- Excludes __init__.py and auto_documentation.py.
- Uses a local OpenAI-compatible endpoint hardcoded to:
  http://127.0.0.1:5001/v1
- Adds Sphinx-style docstrings to module/class/function/method objects.
- Adds a top-level module summary docstring.
- Renames the previous version to *_OLD_YYYYMMDD_HHMMSS.py
  before writing the updated file.

Run:
    python auto_documentation.py
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests


API_BASE = "http://127.0.0.1:5001/v1"
API_KEY = "sk-local"
SELF_SCRIPT_NAME = "auto_documentation.py"
EXCLUDED_FILES = {"__init__.py", SELF_SCRIPT_NAME}
REQUEST_TIMEOUT = 180


@dataclass
class InsertOp:
    index: int
    text: str


@dataclass
class ReplaceOp:
    start: int
    end: int
    text: str


def line_indent(s: str) -> str:
    return s[: len(s) - len(s.lstrip(" \t"))]


def make_docstring_block(body: str, indent: str) -> str:
    clean = sanitize_ai_text(body).replace('"""', '\\"\\"\\"').strip()
    lines = clean.splitlines() or [""]
    out = [f'{indent}"""']
    out.extend(f"{indent}{line}" if line else indent for line in lines)
    out.append(f'{indent}"""')
    return "\n".join(out) + "\n"


def sanitize_ai_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    text = text.strip()
    if text.startswith('"""') and text.endswith('"""'):
        text = text[3:-3].strip()
    return text


def get_doc_expr(node: ast.AST) -> Optional[ast.Expr]:
    body = getattr(node, "body", None)
    if not body:
        return None
    first = body[0]
    if isinstance(first, ast.Expr):
        value = first.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return first
    return None


def has_docstring(node: ast.AST) -> bool:
    return get_doc_expr(node) is not None


def source_segment(source: str, node: ast.AST) -> str:
    seg = ast.get_source_segment(source, node)
    if seg:
        return seg
    lines = source.splitlines()
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if start is None or end is None:
        return ""
    return "\n".join(lines[start - 1 : end])


def node_to_src(node: Optional[ast.AST]) -> Optional[str]:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return ast.dump(node, include_attributes=False)


def target_names(target: ast.AST) -> List[str]:
    names: List[str] = []

    def walk(t: ast.AST) -> None:
        if isinstance(t, ast.Name):
            names.append(t.id)
        elif isinstance(t, ast.Tuple):
            for e in t.elts:
                walk(e)
        elif isinstance(t, ast.Attribute):
            if isinstance(t.value, ast.Name):
                names.append(f"{t.value.id}.{t.attr}")

    walk(target)
    return names


def module_attributes(module: ast.Module) -> List[dict]:
    items = []
    for stmt in module.body:
        if isinstance(stmt, ast.Assign):
            names = []
            for t in stmt.targets:
                names.extend(target_names(t))
            if names:
                items.append(
                    {
                        "names": names,
                        "value": node_to_src(stmt.value),
                        "lineno": stmt.lineno,
                    }
                )
        elif isinstance(stmt, ast.AnnAssign):
            names = target_names(stmt.target)
            if names:
                items.append(
                    {
                        "names": names,
                        "annotation": node_to_src(stmt.annotation),
                        "value": node_to_src(stmt.value),
                        "lineno": stmt.lineno,
                    }
                )
    return items


def class_attributes(class_node: ast.ClassDef) -> List[dict]:
    items = []
    for stmt in class_node.body:
        if isinstance(stmt, ast.Assign):
            names = []
            for t in stmt.targets:
                names.extend(target_names(t))
            if names:
                items.append(
                    {
                        "names": names,
                        "value": node_to_src(stmt.value),
                        "lineno": stmt.lineno,
                    }
                )
        elif isinstance(stmt, ast.AnnAssign):
            names = target_names(stmt.target)
            if names:
                items.append(
                    {
                        "names": names,
                        "annotation": node_to_src(stmt.annotation),
                        "value": node_to_src(stmt.value),
                        "lineno": stmt.lineno,
                    }
                )
    return items


def instance_attributes(func_node: ast.AST) -> List[dict]:
    items = []
    for stmt in ast.walk(func_node):
        if isinstance(stmt, ast.Assign):
            names = []
            for t in stmt.targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                    names.append(f"self.{t.attr}")
            if names:
                items.append(
                    {
                        "names": names,
                        "value": node_to_src(stmt.value),
                        "lineno": stmt.lineno,
                    }
                )
        elif isinstance(stmt, ast.AnnAssign):
            t = stmt.target
            if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                items.append(
                    {
                        "names": [f"self.{t.attr}"],
                        "annotation": node_to_src(stmt.annotation),
                        "value": node_to_src(stmt.value),
                        "lineno": stmt.lineno,
                    }
                )
    return items


def callable_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict:
    args = []
    posonly = list(node.args.posonlyargs)
    normal = list(node.args.args)
    defaults = list(node.args.defaults)
    merged = posonly + normal
    default_start = len(merged) - len(defaults)

    for i, a in enumerate(merged):
        default = defaults[i - default_start] if i >= default_start else None
        args.append(
            {
                "name": a.arg,
                "annotation": node_to_src(a.annotation),
                "default": node_to_src(default),
                "kind": "positional_only" if a in posonly else "positional_or_keyword",
            }
        )

    if node.args.vararg:
        args.append(
            {
                "name": "*" + node.args.vararg.arg,
                "annotation": node_to_src(node.args.vararg.annotation),
                "default": None,
                "kind": "vararg",
            }
        )

    for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults):
        args.append(
            {
                "name": a.arg,
                "annotation": node_to_src(a.annotation),
                "default": node_to_src(d),
                "kind": "keyword_only",
            }
        )

    if node.args.kwarg:
        args.append(
            {
                "name": "**" + node.args.kwarg.arg,
                "annotation": node_to_src(node.args.kwarg.annotation),
                "default": None,
                "kind": "kwargs",
            }
        )

    decorators = [node_to_src(d) for d in node.decorator_list]
    return {
        "name": node.name,
        "async": isinstance(node, ast.AsyncFunctionDef),
        "returns": node_to_src(node.returns),
        "decorators": decorators,
        "args": args,
    }


def call_local_ai(system_prompt: str, user_prompt: str, model: Optional[str] = None, max_tokens: int = 700) -> str:
    if model is None:
        model = detect_model() or "local-model"

    response = requests.post(
        f"{API_BASE}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
        json={
            "model": model,
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


_MODEL_CACHE: Optional[str] = None


def detect_model() -> Optional[str]:
    global _MODEL_CACHE
    if _MODEL_CACHE:
        return _MODEL_CACHE

    for url in (f"{API_BASE}/models",):
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {API_KEY}"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and "data" in data and data["data"]:
                model_id = data["data"][0].get("id")
                if model_id:
                    _MODEL_CACHE = model_id
                    return _MODEL_CACHE
        except Exception:
            pass

    return None


def build_function_doc(source: str, fn: ast.FunctionDef | ast.AsyncFunctionDef, parent_class: Optional[ast.ClassDef], attrs: List[dict]) -> str:
    system_prompt = (
        "You write concise Python Sphinx docstrings. "
        "Return only the docstring text, without triple quotes and without markdown fences. "
        "Do not invent behavior."
    )
    payload = {
        "container": parent_class.name if parent_class else None,
        "signature": callable_info(fn),
        "attributes": attrs[:25],
        "source": source_segment(source, fn),
    }
    user_prompt = (
        "Generate a Sphinx-style docstring for this callable.\n"
        "Rules:\n"
        "- First line: one-sentence summary.\n"
        "- Then a short paragraph only if useful.\n"
        "- Use :param:, :type:, :return:, :rtype:, and :raises: only when justified.\n"
        "- Skip self and cls in parameter docs unless needed.\n"
        "- Be conservative and technical.\n\n"
        f"{json.dumps(payload, indent=2)}"
    )
    return sanitize_ai_text(call_local_ai(system_prompt, user_prompt, max_tokens=700))


def build_class_doc(source: str, cls: ast.ClassDef) -> str:
    system_prompt = (
        "You write concise Python Sphinx class docstrings. "
        "Return only the docstring text, without triple quotes and without markdown fences. "
        "Do not invent behavior."
    )
    payload = {
        "class_name": cls.name,
        "bases": [node_to_src(b) for b in cls.bases],
        "attributes": class_attributes(cls),
        "methods": [n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))],
        "source": source_segment(source, cls),
    }
    user_prompt = (
        "Generate a Sphinx-style class docstring.\n"
        "- First line: concise summary.\n"
        "- Add one short paragraph if useful.\n"
        "- Mention responsibilities and notable attributes.\n\n"
        f"{json.dumps(payload, indent=2)}"
    )
    return sanitize_ai_text(call_local_ai(system_prompt, user_prompt, max_tokens=500))


def build_module_doc(source: str, file_path: Path, tree: ast.Module) -> str:
    funcs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]

    system_prompt = (
        "You write concise Python module docstrings in Sphinx-friendly style. "
        "Return only the docstring text, without triple quotes and without markdown fences."
    )
    payload = {
        "file": str(file_path),
        "functions": [callable_info(f) for f in funcs[:40]],
        "classes": [c.name for c in classes[:40]],
        "module_attributes": module_attributes(tree)[:40],
        "source_head": "\n".join(source.splitlines()[:250]),
    }
    user_prompt = (
        "Generate a module docstring for this Python file.\n"
        "- First line: what the file is for.\n"
        "- Then one short paragraph.\n"
        "- Add 'Main contents:' and a short bullet list when useful.\n"
        "- Keep it compact and technical.\n\n"
        f"{json.dumps(payload, indent=2)}"
    )
    return sanitize_ai_text(call_local_ai(system_prompt, user_prompt, max_tokens=700))


def insertion_index_after_header(lines: List[str], node: ast.AST) -> int:
    i = node.lineno - 1
    while i < len(lines):
        if lines[i].rstrip().endswith(":"):
            return i + 1
        i += 1
    return node.lineno


def body_indent_for_node(lines: List[str], node: ast.AST) -> str:
    body = getattr(node, "body", None)
    if body:
        first_stmt = body[0]
        first_line_idx = first_stmt.lineno - 1
        if 0 <= first_line_idx < len(lines):
            raw = lines[first_line_idx]
            indent = line_indent(raw)
            if indent:
                return indent

    base_line = lines[node.lineno - 1]
    return line_indent(base_line) + ("    " if "\t" not in line_indent(base_line) else "\t")


def insert_docstring(lines: List[str], node: ast.AST, body: str) -> InsertOp:
    idx = insertion_index_after_header(lines, node)
    indent = body_indent_for_node(lines, node)
    return InsertOp(idx, make_docstring_block(body, indent))


def replace_docstring(node: ast.AST, body: str, lines: List[str]) -> Optional[ReplaceOp]:
    expr = get_doc_expr(node)
    if not expr:
        return None
    indent = body_indent_for_node(lines, node)
    return ReplaceOp(expr.lineno - 1, expr.end_lineno - 1, make_docstring_block(body, indent).rstrip("\n"))


def module_doc_op(tree: ast.Module, lines: List[str], body: str) -> tuple[Optional[ReplaceOp], Optional[InsertOp]]:
    expr = get_doc_expr(tree)
    if expr:
        return ReplaceOp(expr.lineno - 1, expr.end_lineno - 1, make_docstring_block(body, "" ).rstrip("\n")), None

    insert_at = 0
    if lines and lines[0].startswith("#!"):
        insert_at = 1
    if insert_at < len(lines) and re.match(r"#.*coding[:=]\s*[-\w.]+", lines[insert_at]):
        insert_at += 1

    return None, InsertOp(insert_at, make_docstring_block(body, "") + "\n")


def apply_changes(lines: List[str], inserts: List[InsertOp], replaces: List[ReplaceOp]) -> str:
    insert_map: dict[int, List[str]] = {}
    for op in inserts:
        insert_map.setdefault(op.index, []).append(op.text)

    replacement_starts = {op.start: op for op in replaces}
    skip = set()
    for op in replaces:
        for i in range(op.start, op.end + 1):
            skip.add(i)

    out: List[str] = []
    for i in range(len(lines) + 1):
        if i in insert_map:
            out.extend(insert_map[i])

        if i == len(lines):
            break

        if i in replacement_starts:
            out.append(replacement_starts[i].text + "\n")
            continue

        if i in skip:
            continue

        out.append(lines[i] + "\n")

    return "".join(out)


def process_python_file(file_path: Path) -> None:
    original = file_path.read_text(encoding="utf-8")
    lines = original.splitlines()
    tree = ast.parse(original)

    inserts: List[InsertOp] = []
    replaces: List[ReplaceOp] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if not has_docstring(node):
                class_doc = build_class_doc(original, node)
                inserts.append(insert_docstring(lines, node, class_doc))

            cls_attrs = class_attributes(node)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not has_docstring(item):
                    attrs = cls_attrs + instance_attributes(item)
                    fn_doc = build_function_doc(original, item, node, attrs)
                    inserts.append(insert_docstring(lines, item, fn_doc))

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not has_docstring(node):
                fn_doc = build_function_doc(original, node, None, module_attributes(tree))
                inserts.append(insert_docstring(lines, node, fn_doc))

    module_doc = build_module_doc(original, file_path, tree)
    rep, ins = module_doc_op(tree, lines, module_doc)
    if rep:
        replaces.append(rep)
    if ins:
        inserts.append(ins)

    updated = apply_changes(lines, inserts, replaces)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = file_path.with_name(f"{file_path.stem}_OLD_{timestamp}{file_path.suffix}")
    shutil.move(str(file_path), str(backup_path))
    file_path.write_text(updated, encoding="utf-8")


def discover_python_files(root: Path) -> List[Path]:
    files = []
    for path in root.rglob("*.py"):
        if path.name in EXCLUDED_FILES:
            continue
        files.append(path)
    return sorted(files)


def main() -> int:
    root = Path.cwd()
    files = discover_python_files(root)

    if not files:
        print("No Python files found.")
        return 0

    print(f"Using API base: {API_BASE}")
    print(f"Scanning: {root}")
    print(f"Found {len(files)} Python file(s).")

    failures = []

    for file_path in files:
        try:
            print(f"[PROCESS] {file_path}")
            process_python_file(file_path)
            print(f"[OK]      {file_path}")
        except SyntaxError as exc:
            failures.append((file_path, f"SyntaxError: {exc}"))
            print(f"[FAIL]    {file_path} -> SyntaxError: {exc}")
        except requests.HTTPError as exc:
            failures.append((file_path, f"HTTPError: {exc}"))
            print(f"[FAIL]    {file_path} -> HTTPError: {exc}")
        except Exception as exc:
            failures.append((file_path, f"{type(exc).__name__}: {exc}"))
            print(f"[FAIL]    {file_path} -> {type(exc).__name__}: {exc}")

    print()
    print(f"Processed: {len(files) - len(failures)}/{len(files)}")

    if failures:
        print("Failures:")
        for file_path, msg in failures:
            print(f" - {file_path}: {msg}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())