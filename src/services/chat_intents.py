import re


SLASH_COMMANDS = {
    "explain": {
        "label": "Explain",
        "description": "Understand selected code, flow, architecture, or patterns.",
        "base_depth": 1,
    },
    "fix": {
        "label": "Fix",
        "description": "Diagnose and correct bugs, errors, failing tests, or exceptions.",
        "base_depth": 2,
    },
    "change": {
        "label": "Change",
        "description": "Refactor, generate, complete, migrate, integrate, or modify code.",
        "base_depth": 2,
    },
    "review": {
        "label": "Review",
        "description": "Find risks, regressions, security issues, performance problems, or gaps.",
        "base_depth": 2,
    },
    "write": {
        "label": "Write",
        "description": "Create docs, comments, reports, plans, guides, or user-facing text.",
        "base_depth": 1,
    },
    "research": {
        "label": "Research",
        "description": "Trace behavior, dependencies, impact, architecture, or related code.",
        "base_depth": 3,
    },
}


TASK_KEYWORDS = {
    "documentation": {
        "mode": "write",
        "depth": 1,
        "keywords": [
            "api note", "api notes", "comment", "comments", "documentation", "document",
            "docstring", "docstrings", "inline comment", "inline comments", "readme",
            "summary", "summaries", "xml doc", "xml docs",
        ],
    },
    "code_explanation": {
        "mode": "explain",
        "depth": 1,
        "keywords": [
            "architecture", "break down", "describe", "explain", "flow", "how does",
            "how it works", "pattern", "summarize", "understand", "walk me through",
            "what does", "what is",
        ],
    },
    "code_completion": {
        "mode": "change",
        "depth": 2,
        "keywords": [
            "complete", "completion", "continue", "finish", "fill", "implement missing",
            "missing branch", "missing branches", "todo", "todos", "stub", "scaffold",
        ],
    },
    "code_research": {
        "mode": "research",
        "depth": 3,
        "keywords": [
            "compare implementations", "dependency", "dependencies", "find where",
            "investigate", "locate", "research", "trace", "trace symbol", "where is",
            "where used",
        ],
    },
    "refactoring": {
        "mode": "change",
        "depth": 2,
        "keywords": [
            "cleanup", "clean up", "deduplicate", "duplicate", "extract class",
            "extract method", "organize", "reorganize", "refactor", "rename",
            "simplify", "split", "technical debt",
        ],
    },
    "code_generation": {
        "mode": "change",
        "depth": 2,
        "keywords": [
            "adapter", "boilerplate", "build", "class", "config", "create",
            "dto", "generate", "implement", "mapping", "module", "new function",
            "new method", "service",
        ],
    },
    "bug_fixing": {
        "mode": "fix",
        "depth": 2,
        "keywords": [
            "bug", "broken", "defect", "diagnose", "does not work", "incorrect",
            "logic bug", "patch", "regression", "wrong behavior",
        ],
    },
    "error_fixing": {
        "mode": "fix",
        "depth": 2,
        "keywords": [
            "compile error", "crash", "error", "exception", "failing import",
            "runtime error", "stack trace", "traceback", "type error", "warning",
        ],
    },
    "document_creation": {
        "mode": "write",
        "depth": 1,
        "keywords": [
            "changelog", "design doc", "guide", "implementation plan", "migration guide",
            "notes", "release notes", "report", "spec", "write document",
        ],
    },
    "testing": {
        "mode": "review",
        "depth": 2,
        "keywords": [
            "coverage", "failing test", "integration test", "test", "test case",
            "test cases", "unit test", "verify",
        ],
    },
    "debugging_diagnosis": {
        "mode": "fix",
        "depth": 3,
        "keywords": [
            "debug", "debugging", "diagnosis", "log", "logs", "race condition",
            "reproduce", "state", "symptom", "why fails",
        ],
    },
    "code_review": {
        "mode": "review",
        "depth": 2,
        "keywords": [
            "edge case", "maintainability", "missing test", "regression risk",
            "review", "risk", "risks", "smell",
        ],
    },
    "architecture_analysis": {
        "mode": "research",
        "depth": 3,
        "keywords": [
            "architecture analysis", "boundary", "boundaries", "coupling",
            "dependency direction", "layer", "layers", "module boundary",
        ],
    },
    "impact_analysis": {
        "mode": "research",
        "depth": 3,
        "keywords": [
            "affected", "blast radius", "callers", "impact", "impact analysis",
            "side effect", "what else",
        ],
    },
    "migration_upgrade": {
        "mode": "change",
        "depth": 2,
        "keywords": [
            ".net 4.8", "c# 7.3", "framework upgrade", "language version",
            "migration", "port", "upgrade",
        ],
    },
    "performance_optimization": {
        "mode": "review",
        "depth": 2,
        "keywords": [
            "allocation", "bottleneck", "latency", "memory", "optimize",
            "performance", "slow", "speed",
        ],
    },
    "security_review": {
        "mode": "review",
        "depth": 2,
        "keywords": [
            "authorization", "injection", "input validation", "permission",
            "secret", "secrets", "security", "unsafe", "validation",
        ],
    },
    "data_model_schema": {
        "mode": "change",
        "depth": 2,
        "keywords": [
            "config format", "data model", "database", "dto", "migration",
            "schema", "serialization", "sql",
        ],
    },
    "ui_ux_changes": {
        "mode": "change",
        "depth": 2,
        "keywords": [
            "accessibility", "interaction", "layout", "style", "styling",
            "ui", "ux", "visual",
        ],
    },
    "integration_work": {
        "mode": "change",
        "depth": 2,
        "keywords": [
            "api", "connect", "file format", "integration", "service api",
            "third-party", "tool",
        ],
    },
    "build_deployment_tooling": {
        "mode": "change",
        "depth": 2,
        "keywords": [
            "build", "ci", "deploy", "deployment", "dependency setup",
            "installer", "project file", "script", "tooling",
        ],
    },
    "cleanup_maintenance": {
        "mode": "change",
        "depth": 1,
        "keywords": [
            "dead code", "maintenance", "normalize style", "remove unused",
            "tidy", "unused",
        ],
    },
    "translation_wording": {
        "mode": "write",
        "depth": 1,
        "keywords": [
            "copy", "help text", "polish wording", "prompt", "string",
            "translate", "translation", "wording",
        ],
    },
    "planning_task_breakdown": {
        "mode": "research",
        "depth": 1,
        "keywords": [
            "breakdown", "plan", "planning", "roadmap", "steps", "task breakdown",
        ],
    },
    "learning_tutorial": {
        "mode": "explain",
        "depth": 1,
        "keywords": [
            "guide me", "learning", "teach", "tutorial", "walkthrough",
        ],
    },
}


SLASH_PATTERN = re.compile(r"^\s*/([A-Za-z_][A-Za-z_0-9-]*)\b")
MENTION_PATTERN = re.compile(r"(?<!\w)@([A-Za-z0-9_.-]+)")


def parse_slash_command(text):
    match = SLASH_PATTERN.search(text or "")
    if not match:
        return None
    value = match.group(1).lower().strip()
    return value if value in SLASH_COMMANDS else None


def strip_slash_command(text):
    return SLASH_PATTERN.sub("", text or "", count=1).lstrip()


def infer_chat_intent(text):
    lowered = (text or "").lower()
    scores = {}
    matched = []
    for group_name, group in TASK_KEYWORDS.items():
        hits = [keyword for keyword in group["keywords"] if keyword in lowered]
        if not hits:
            continue
        mode = group["mode"]
        score = len(hits) * max(1, int(group.get("depth", 1)))
        scores[mode] = scores.get(mode, 0) + score
        matched.append({"group": group_name, "mode": mode, "hits": hits, "depth": group.get("depth", 1)})

    if not scores:
        mode = "explain"
        depth = 1
    else:
        mode = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]
        depth = max([item["depth"] for item in matched if item["mode"] == mode] or [1])

    return {
        "mode": mode,
        "label": SLASH_COMMANDS[mode]["label"],
        "depth": min(3, max(0, int(depth))),
        "source": "heuristic",
        "scores": scores,
        "matched": matched,
    }


def chat_intent_for_message(text):
    command = parse_slash_command(text)
    if command:
        profile = dict(SLASH_COMMANDS[command])
        return {
            "mode": command,
            "label": profile["label"],
            "depth": int(profile["base_depth"]),
            "source": "slash",
            "scores": {},
            "matched": [],
        }
    return infer_chat_intent(text)


def snippet_mention_slug(description, fallback):
    source = description.strip() if description and description.strip() else fallback
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(source)).strip("._")
    return slug or fallback


def find_mention_tokens(text):
    return [match.group(1) for match in MENTION_PATTERN.finditer(text or "")]
