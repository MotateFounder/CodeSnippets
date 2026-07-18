import json
import re


MAX_STAGE_CONTEXT_CHARS = 12000
MAX_FINAL_ARTIFACT_CHARS = 14000
MAX_IDENTIFIER_REPORT_ITEMS = 24

IDENTIFIER_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]*\b")
DOTTED_IDENTIFIER_PATTERN = re.compile(
    r"\b[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)+\b"
)
CODE_LIKE_SUFFIXES = (
    "Data",
    "Info",
    "Manager",
    "Mode",
    "Model",
    "Params",
    "Provider",
    "Request",
    "Response",
    "Result",
    "Service",
    "Settings",
    "State",
    "Store",
    "Type",
)
IDENTIFIER_STOP_WORDS = {
    "Add",
    "Analysis",
    "And",
    "Array",
    "Before",
    "Boolean",
    "Class",
    "Code",
    "Context",
    "Dictionary",
    "Do",
    "File",
    "Find",
    "For",
    "From",
    "If",
    "Implementation",
    "In",
    "Json",
    "List",
    "Mode",
    "Must",
    "New",
    "No",
    "Not",
    "Null",
    "Object",
    "Only",
    "Or",
    "parse_status",
    "Required",
    "Return",
    "Rules",
    "Search",
    "Stage",
    "String",
    "Task",
    "The",
    "This",
    "True",
    "False",
    "Use",
    "User",
    "Value",
    "Void",
    "With",
    "bool",
    "class",
    "false",
    "int",
    "new",
    "null",
    "object",
    "return",
    "string",
    "true",
    "var",
    "void",
    "uses",
}


TASK_NORMALIZATION_PROMPT = """You are a task normalizer.

Convert the user request into a structured engineering task.

Output compact JSON with:
- primary_goal
- secondary_goals
- explicit_constraints
- implicit_constraints
- likely_affected_subsystems
- expected_output_type
- risk_level
- ambiguity_level
- backward_compatibility_critical
- task_type

Do not solve the task.
Only normalize it."""

CONTEXT_CLASSIFICATION_PROMPT = """Analyze the task and determine what codebase context is REQUIRED to safely solve it.

Possible context categories:
- calling methods
- called methods
- models/classes
- serialization
- threading
- UI bindings
- persistence
- external services
- configuration
- tests
- interfaces
- inheritance hierarchy
- DTOs
- database
- DSP/audio pipeline
- async flows
- event systems

Return compact JSON with only the categories needed.
Do not solve the task."""

RETRIEVAL_PLANNING_PROMPT = """You are a retrieval planner.

Generate the MINIMUM set of retrieval queries required to safely solve the task.

Prioritize:
- direct implementation dependencies
- persistence boundaries
- compatibility-sensitive code
- shared mutable state
- serialization
- runtime application paths

Avoid broad or generic retrieval.
Return compact JSON as an array of retrieval target strings."""

CONTEXT_SUMMARIZATION_PROMPT = """Summarize the retrieved code into structured implementation facts.

Rules:
- no prose explanations
- no architecture speculation
- no recommendations
- no code generation

Extract:
- responsibilities
- side effects
- persistence behavior
- mutable state
- dependencies
- compatibility assumptions
- threading behavior
- serialization behavior
- runtime flows

Use concise compact JSON."""

MISSING_CONTEXT_PROMPT = """You are a grounding auditor for a coding assistant.

Compare the user request, normalized task, retrieval targets, and retrieved facts.

Return compact JSON with:
- retrieval_sufficient: true or false
- missing_context: array of specific missing files/symbols/callers/types/tests
- unsafe_assumptions: array of assumptions that are not directly grounded
- required_new_types_or_members: array of fields/classes/APIs that would need to be added instead of treated as existing
- followup_retrieval_targets: array of at most 4 very specific additional retrieval targets

Rules:
- Do not solve the task.
- Do not invent code.
- If a field, class, method, dictionary, flag, or API is not visible in retrieved facts/context, mark it as missing or required-new.
- Prefer saying context is insufficient over guessing."""

CONSTRAINT_EXTRACTION_PROMPT = """Extract hard engineering constraints from the user request, retrieved code facts, missing-context audit, and retrieval quality report.

Return compact JSON with:
- must_preserve
- must_not_do
- compatibility_constraints
- implementation_constraints
- validation_constraints
- dangerous_assumptions

Rules:
- Only explicit or strongly implied constraints.
- Do not invent architecture.
- Prioritize backward compatibility.
- Include this hard rule if relevant: do not use fields, classes, methods, or APIs unless they exist in retrieved context or are explicitly declared as new."""

ARCHITECTURAL_MINIMIZATION_PROMPT = """You are reviewing a proposed implementation direction for a fragile production codebase.

Goal:
Minimize architectural surface area before the final answer is written.

Rules:
- Prefer extending existing structures over creating new ones.
- Prefer additive compatibility over new abstractions.
- Avoid creating wrappers unless strictly necessary.
- Avoid introducing new persistence models unless existing ones are insufficient.
- Minimize architectural surface area.
- Minimize new types.
- Minimize new serialization paths.
- Minimize runtime branching complexity.
- Assume hidden dependencies exist throughout the codebase.
- Treat identifiers not grounded in retrieved context as requiring follow-up search or explicit new-type proposals.

Return compact JSON with:
- existing_structures_to_extend
- abstractions_to_avoid
- new_types_to_avoid_or_justify
- persistence_changes_to_minimize
- runtime_branching_to_minimize
- safest_minimal_direction
- reasons_to_reject_overengineering

Do not generate code."""

DEFAULT_FINAL_SYNTHESIS_RULES = """- Do not invent fields, classes, methods, properties, dictionaries, flags, files, or APIs.
- If a needed structure does not exist in retrieved context, list it separately under "Required new types/APIs" and do not write code that uses it as if it already exists.
- Identifiers listed as referenced_but_not_grounded are not proven absent, but they are not supported by the current evidence.
- If an identifier is still_not_grounded_after_followup, do not use it as existing code. Put it under "Required new types/APIs" or "Assumptions to verify".
- Do not present pseudo-code as compilable code. If code is illustrative, label it explicitly as illustrative.
- Do not output a patch that references an identifier unless that identifier appears in retrieved context or is declared in the patch.
- If retrieval quality is medium, low, or very_low, state the uncertainty and avoid autonomous patch-style instructions.
- Prefer minimal, compatibility-preserving changes over architectural rewrites.
- Prefer extending existing structures over inventing new abstractions.
- Avoid new wrappers, persistence models, serialization paths, and runtime branches unless the architectural_minimization artifact justifies them.
- Preserve legacy behavior unless the user explicitly asks to break it.
- For C# code, assume C# 7.3 and .NET Framework 4.8 compatibility.
- Keep the final answer focused on the user's request."""


def run_thinking_process(user_message, context, call_ai, retrieve_context=None, progress=None, settings=None):
    """Run a compact staged reasoning pipeline and return a final prompt artifact."""
    progress = progress or noop_progress
    settings = settings or {}
    prompts = settings.get("prompts", {})
    reasoning = settings.get("reasoning", {})
    max_stage_context_chars = safe_int_setting(
        reasoning.get("max_stage_context_chars"),
        MAX_STAGE_CONTEXT_CHARS,
    )
    max_final_artifact_chars = safe_int_setting(
        reasoning.get("max_final_artifact_chars"),
        MAX_FINAL_ARTIFACT_CHARS,
    )
    max_retrieval_targets = safe_int_setting(reasoning.get("max_retrieval_targets"), 8)
    max_followup_targets = safe_int_setting(reasoning.get("max_followup_targets"), 4)
    max_identifier_report_items = safe_int_setting(
        reasoning.get("max_identifier_report_items"),
        MAX_IDENTIFIER_REPORT_ITEMS,
    )
    default_steps = {
        "task_normalization",
        "context_classification",
        "retrieval_planning",
        "context_summarization",
        "missing_context",
        "constraint_extraction",
        "architectural_minimization",
        "final_synthesis_rules",
    }
    enabled_steps = set(reasoning.get("enabled_steps") or default_steps)

    def step_enabled(name):
        return name in enabled_steps

    artifact = {
        "task": "",
        "context_needs": "",
        "retrieval_targets": [],
        "retrieved_context": context or "",
        "retrieval_quality": {},
        "context_facts": "",
        "missing_context": "",
        "hard_constraints": "",
        "architectural_minimization": "",
        "custom_reasoning": [],
        "trace": [],
    }

    if step_enabled("task_normalization"):
        progress(1, 9, "Task normalization", "Converting the request into an engineering task.")
        artifact["task_raw"] = call_stage(
            call_ai,
            prompts.get("task_normalization") or TASK_NORMALIZATION_PROMPT,
            build_stage_input(max_stage_context_chars, user_message=user_message),
        )
        artifact["task"] = parse_stage_json(artifact["task_raw"])
        artifact["trace"].append("Task normalized")
    else:
        artifact["trace"].append("Task normalization skipped")

    if step_enabled("context_classification"):
        progress(2, 9, "Context classification", "Deciding what codebase context is required.")
        artifact["context_needs_raw"] = call_stage(
            call_ai,
            prompts.get("context_classification") or CONTEXT_CLASSIFICATION_PROMPT,
            build_stage_input(
                max_stage_context_chars,
                user_message=user_message,
                task=json_dumps_compact(artifact["task"]),
                context_preview=context,
            ),
        )
        artifact["context_needs"] = parse_stage_json(artifact["context_needs_raw"])
        artifact["trace"].append("Context needs classified")
    else:
        artifact["trace"].append("Context classification skipped")

    if step_enabled("retrieval_planning"):
        progress(3, 9, "Retrieval planning", "Asking the model for focused retrieval targets.")
        retrieval_plan = call_stage(
            call_ai,
            prompts.get("retrieval_planning") or RETRIEVAL_PLANNING_PROMPT,
            build_stage_input(
                max_stage_context_chars,
                user_message=user_message,
                task=json_dumps_compact(artifact["task"]),
                context_needs=json_dumps_compact(artifact["context_needs"]),
                context_preview=context,
            ),
        )
        artifact["retrieval_targets"] = parse_retrieval_targets(retrieval_plan, max_retrieval_targets)
        artifact["trace"].append("Retrieval targets planned")
    else:
        artifact["trace"].append("Retrieval planning skipped")

    retrieved_context = context or ""
    if retrieve_context and artifact["retrieval_targets"]:
        progress(4, 9, "Focused retrieval", "Searching local code for the planned targets.")
        retrieval_result = normalize_retrieval_result(retrieve_context(artifact["retrieval_targets"]))
        extra_context = retrieval_result["text"]
        retrieved_context = combine_context(context, extra_context)
        artifact["retrieval_details"] = retrieval_result.get("details", [])
        artifact["trace"].append("Focused retrieval completed")
    else:
        progress(4, 9, "Focused retrieval", "Using currently attached context.")
        artifact["trace"].append("Focused retrieval skipped")

    artifact["retrieved_context"] = limit_text(retrieved_context, max_stage_context_chars)
    artifact["retrieval_quality"] = assess_retrieval_quality(
        artifact["retrieved_context"],
        artifact["retrieval_targets"],
    )

    if step_enabled("context_summarization"):
        progress(5, 9, "Context summarization", "Compressing retrieved code into grounded implementation facts.")
        artifact["context_facts_raw"] = call_stage(
            call_ai,
            prompts.get("context_summarization") or CONTEXT_SUMMARIZATION_PROMPT,
            build_stage_input(
                max_stage_context_chars,
                user_message=user_message,
                task=json_dumps_compact(artifact["task"]),
                context_needs=json_dumps_compact(artifact["context_needs"]),
                retrieval_targets=json.dumps(artifact["retrieval_targets"], indent=2),
                retrieval_quality=json_dumps_compact(artifact["retrieval_quality"]),
                retrieved_context=artifact["retrieved_context"],
            ),
        )
        artifact["context_facts"] = parse_stage_json(artifact["context_facts_raw"])
        artifact["trace"].append("Context summarized")
    else:
        artifact["trace"].append("Context summarization skipped")

    if step_enabled("missing_context"):
        progress(6, 9, "Grounding audit", "Finding missing context, unsafe assumptions, and hard constraints.")
        artifact["missing_context_raw"] = call_stage(
            call_ai,
            prompts.get("missing_context") or MISSING_CONTEXT_PROMPT,
            build_stage_input(
                max_stage_context_chars,
                user_message=user_message,
                task=json_dumps_compact(artifact["task"]),
                retrieval_targets=json.dumps(artifact["retrieval_targets"], indent=2),
                retrieval_quality=json_dumps_compact(artifact["retrieval_quality"]),
                context_facts=json_dumps_compact(artifact["context_facts"]),
            ),
        )
        artifact["missing_context"] = parse_stage_json(artifact["missing_context_raw"])
    else:
        artifact["trace"].append("Grounding audit skipped")

    followup_targets = parse_followup_targets(artifact["missing_context"], max_followup_targets)
    if retrieve_context and followup_targets:
        progress(6, 9, "Grounding audit", "Running one extra focused retrieval pass for missing context.")
        followup_result = normalize_retrieval_result(retrieve_context(followup_targets))
        if followup_result["text"].strip():
            artifact["retrieved_context"] = limit_text(
                combine_context(artifact["retrieved_context"], followup_result["text"]),
                max_stage_context_chars,
            )
            artifact["retrieval_targets"].extend(
                target for target in followup_targets if target not in artifact["retrieval_targets"]
            )
            artifact["retrieval_quality"] = assess_retrieval_quality(
                artifact["retrieved_context"],
                artifact["retrieval_targets"],
            )
            if step_enabled("context_summarization"):
                artifact["context_facts_raw"] = call_stage(
                    call_ai,
                    prompts.get("context_summarization") or CONTEXT_SUMMARIZATION_PROMPT,
                    build_stage_input(
                        max_stage_context_chars,
                        user_message=user_message,
                        task=json_dumps_compact(artifact["task"]),
                        context_needs=json_dumps_compact(artifact["context_needs"]),
                        retrieval_targets=json.dumps(artifact["retrieval_targets"], indent=2),
                        retrieval_quality=json_dumps_compact(artifact["retrieval_quality"]),
                        retrieved_context=artifact["retrieved_context"],
                    ),
                )
                artifact["context_facts"] = parse_stage_json(artifact["context_facts_raw"])
            artifact["trace"].append("One follow-up retrieval pass completed")

    if step_enabled("constraint_extraction"):
        artifact["hard_constraints_raw"] = call_stage(
            call_ai,
            prompts.get("constraint_extraction") or CONSTRAINT_EXTRACTION_PROMPT,
            build_stage_input(
                max_stage_context_chars,
                user_message=user_message,
                task=json_dumps_compact(artifact["task"]),
                context_facts=json_dumps_compact(artifact["context_facts"]),
                missing_context=json_dumps_compact(artifact["missing_context"]),
                retrieval_quality=json_dumps_compact(artifact["retrieval_quality"]),
            ),
        )
        artifact["hard_constraints"] = parse_stage_json(artifact["hard_constraints_raw"])
        artifact["trace"].append("Grounding audit and constraints completed")
    else:
        artifact["trace"].append("Constraint extraction skipped")

    progress(7, 9, "Identifier grounding", "Checking referenced identifiers against retrieved context.")
    artifact["identifier_grounding"] = build_identifier_grounding_report(
        artifact,
        max_items=max_identifier_report_items,
    )
    followup_identifier_targets = artifact["identifier_grounding"].get("followup_searches", [])
    if retrieve_context and followup_identifier_targets:
        progress(7, 9, "Identifier grounding", "Running one targeted search for not-grounded identifiers.")
        identifier_result = normalize_retrieval_result(retrieve_context(followup_identifier_targets))
        if identifier_result["text"].strip():
            artifact["retrieved_context"] = limit_text(
                combine_context(artifact["retrieved_context"], identifier_result["text"]),
                MAX_STAGE_CONTEXT_CHARS,
            )
            artifact["identifier_grounding"] = build_identifier_grounding_report(
                artifact,
                attempted_followup=followup_identifier_targets,
                max_items=max_identifier_report_items,
            )
            artifact["retrieval_quality"] = assess_retrieval_quality(
                artifact["retrieved_context"],
                artifact["retrieval_targets"] + followup_identifier_targets,
            )
        else:
            artifact["identifier_grounding"] = build_identifier_grounding_report(
                artifact,
                attempted_followup=followup_identifier_targets,
                max_items=max_identifier_report_items,
            )
    artifact["trace"].append("Identifier grounding checked")

    if step_enabled("architectural_minimization"):
        progress(8, 9, "Architectural minimization", "Critiquing unnecessary abstractions before final synthesis.")
        artifact["architectural_minimization_raw"] = call_stage(
            call_ai,
            prompts.get("architectural_minimization") or ARCHITECTURAL_MINIMIZATION_PROMPT,
            build_stage_input(
                max_stage_context_chars,
                user_message=user_message,
                task=json_dumps_compact(artifact["task"]),
                context_facts=json_dumps_compact(artifact["context_facts"]),
                hard_constraints=json_dumps_compact(artifact["hard_constraints"]),
                identifier_grounding=json_dumps_compact(artifact["identifier_grounding"]),
                retrieval_quality=json_dumps_compact(artifact["retrieval_quality"]),
            ),
        )
        artifact["architectural_minimization"] = parse_stage_json(artifact["architectural_minimization_raw"])
        artifact["trace"].append("Architectural minimization completed")
    else:
        artifact["trace"].append("Architectural minimization skipped")

    custom_step_keys = [
        key
        for key in prompts
        if str(key).startswith("custom_") and step_enabled(key)
    ]
    for index, key in enumerate(custom_step_keys, start=1):
        progress(8, 9, "Custom reasoning", "Running custom reasoning step {0}.".format(index))
        raw = call_stage(
            call_ai,
            prompts.get(key),
            build_stage_input(
                max_stage_context_chars,
                user_message=user_message,
                task=json_dumps_compact(artifact["task"]),
                context_facts=json_dumps_compact(artifact["context_facts"]),
                missing_context=json_dumps_compact(artifact["missing_context"]),
                hard_constraints=json_dumps_compact(artifact["hard_constraints"]),
                retrieved_context=artifact["retrieved_context"],
            ),
        )
        artifact["custom_reasoning"].append({"key": key, "raw": raw, "parsed": parse_stage_json(raw)})
        artifact["trace"].append("Custom reasoning step {0} completed".format(index))

    progress(9, 9, "Final synthesis", "Preparing the compact final-answer prompt.")
    artifact["final_user_content"] = build_final_synthesis_prompt(
        user_message,
        artifact,
        final_rules=prompts.get("final_synthesis_rules") or DEFAULT_FINAL_SYNTHESIS_RULES,
        max_chars=max_final_artifact_chars,
    )
    return artifact


def call_stage(call_ai, system_prompt, user_content):
    return call_ai(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    ).strip()


def build_stage_input(max_chars=MAX_STAGE_CONTEXT_CHARS, **sections):
    parts = []
    for name, value in sections.items():
        if not value:
            continue
        parts.append(f"<{name}>\n{limit_text(str(value), max_chars)}\n</{name}>")
    return "\n\n".join(parts)


def parse_retrieval_targets(text, max_targets=8):
    parsed = parse_jsonish(text)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()][:max_targets]
    if isinstance(parsed, dict):
        values = []
        for value in parsed.values():
            if isinstance(value, list):
                values.extend(str(item).strip() for item in value if str(item).strip())
            elif value:
                values.append(str(value).strip())
        return values[:max_targets]

    targets = []
    for line in text.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip().strip('"')
        if cleaned and len(cleaned) > 3 and cleaned not in targets:
            targets.append(cleaned)
    return targets[:max_targets]


def parse_jsonish(text):
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", stripped, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def parse_stage_json(text):
    parsed = parse_jsonish(text)
    if parsed is None:
        return {"raw": text.strip(), "parse_status": "unstructured"}
    return parsed


def parse_followup_targets(missing_context, max_targets=4):
    if not isinstance(missing_context, dict):
        return []
    targets = missing_context.get("followup_retrieval_targets", [])
    if not isinstance(targets, list):
        return []
    return [str(target).strip() for target in targets if str(target).strip()][:max_targets]


def normalize_retrieval_result(result):
    if isinstance(result, dict):
        return {
            "text": str(result.get("text", "")),
            "details": result.get("details", []),
        }
    return {"text": str(result or ""), "details": []}


def assess_retrieval_quality(context, targets):
    files = sorted(set(re.findall(r"^File:\s*(.+)$", context or "", flags=re.MULTILINE)))
    target_hits = {}
    lowered = (context or "").lower()
    for target in targets or []:
        words = extract_target_terms(target)
        hits = [word for word in words if word.lower() in lowered]
        target_hits[target] = hits

    missing_targets = [target for target, hits in target_hits.items() if not hits]
    exactish_hit_count = sum(1 for hits in target_hits.values() if hits)
    if files and not missing_targets and exactish_hit_count >= max(1, len(targets or [])):
        confidence = "high"
    elif files and exactish_hit_count:
        confidence = "medium"
    elif files:
        confidence = "low"
    else:
        confidence = "very_low"

    return {
        "confidence": confidence,
        "files_in_context": files[:20],
        "file_count": len(files),
        "retrieval_targets": targets or [],
        "target_hits": target_hits,
        "missing_targets": missing_targets,
        "has_selected_context": "<selected_context>" in (context or ""),
        "has_test_context": "<test_context>" in (context or ""),
        "context_chars": len(context or ""),
    }


def build_identifier_grounding_report(artifact, attempted_followup=None, max_items=MAX_IDENTIFIER_REPORT_ITEMS):
    attempted_followup = attempted_followup or []
    retrieved_context = artifact.get("retrieved_context", "")
    known_identifiers = extract_known_identifiers(retrieved_context)
    known_dotted = extract_dotted_identifiers(retrieved_context)
    referenced_identifiers = extract_referenced_identifiers(artifact)
    referenced_dotted = extract_referenced_dotted_identifiers(artifact)

    grounded = sorted(identifier for identifier in referenced_identifiers if identifier in known_identifiers)
    not_grounded = sorted(
        identifier
        for identifier in referenced_identifiers
        if identifier not in known_identifiers and is_code_like_identifier(identifier)
    )
    grounded_dotted = sorted(chain for chain in referenced_dotted if chain in known_dotted)
    not_grounded_dotted = sorted(chain for chain in referenced_dotted if chain not in known_dotted)

    followup_searches = build_identifier_followup_searches(not_grounded, not_grounded_dotted)
    still_not_grounded = []
    if attempted_followup:
        attempted_terms = " ".join(attempted_followup).lower()
        still_not_grounded = [
            identifier
            for identifier in not_grounded + not_grounded_dotted
            if identifier.lower() in attempted_terms
        ]

    return {
        "grounded_in_retrieved_context": (grounded_dotted + grounded)[:max_items],
        "referenced_but_not_grounded": (not_grounded_dotted + not_grounded)[:max_items],
        "followup_searches": followup_searches[:max_items],
        "followup_searches_attempted": attempted_followup[:max_items],
        "still_not_grounded_after_followup": still_not_grounded[:max_items],
        "final_answer_rules": [
            "Identifiers referenced_but_not_grounded are not proven absent; they are only absent from retrieved context.",
            "Before using a not-grounded identifier as existing code, say it requires follow-up search.",
            "If follow-up search was attempted and it is still not grounded, place it under Required new types/APIs or Assumptions to verify.",
            "Do not write patch-like code that assumes a not-grounded identifier already exists.",
        ],
    }


def extract_known_identifiers(text):
    return {
        match.group(0)
        for match in IDENTIFIER_PATTERN.finditer(text or "")
        if is_code_like_identifier(match.group(0), allow_common=True)
    }


def extract_dotted_identifiers(text):
    return set(DOTTED_IDENTIFIER_PATTERN.findall(text or ""))


def extract_referenced_identifiers(artifact):
    text = "\n".join(
        [
            json_dumps_compact(artifact.get("context_facts", "")),
            json_dumps_compact(artifact.get("missing_context", "")),
            json_dumps_compact(artifact.get("hard_constraints", "")),
            "\n".join(artifact.get("retrieval_targets", [])),
        ]
    )
    dotted_roots = {
        chain.split(".", 1)[0]
        for chain in DOTTED_IDENTIFIER_PATTERN.findall(text)
        if chain.split(".", 1)[0][:1].islower()
    }
    return {
        match.group(0)
        for match in IDENTIFIER_PATTERN.finditer(text)
        if is_code_like_identifier(match.group(0)) and match.group(0) not in dotted_roots
    }


def extract_referenced_dotted_identifiers(artifact):
    text = "\n".join(
        [
            json_dumps_compact(artifact.get("context_facts", "")),
            json_dumps_compact(artifact.get("missing_context", "")),
            json_dumps_compact(artifact.get("hard_constraints", "")),
            "\n".join(artifact.get("retrieval_targets", [])),
        ]
    )
    return set(DOTTED_IDENTIFIER_PATTERN.findall(text))


def is_code_like_identifier(identifier, allow_common=False):
    if not identifier or identifier in IDENTIFIER_STOP_WORDS:
        return False
    if not allow_common and identifier.lower() in {word.lower() for word in IDENTIFIER_STOP_WORDS}:
        return False
    if "_" in identifier:
        return True
    if identifier.endswith(CODE_LIKE_SUFFIXES):
        return True
    if re.match(r"^[A-Z][A-Za-z0-9]*$", identifier):
        return True
    if re.match(r"^[a-z]+[A-Z][A-Za-z0-9]*$", identifier):
        return True
    return allow_common and len(identifier) >= 4


def build_identifier_followup_searches(not_grounded, not_grounded_dotted):
    searches = []
    for chain in not_grounded_dotted:
        searches.append(f"Find {chain}")
        leaf = chain.rsplit(".", 1)[-1]
        if leaf != chain:
            searches.append(f"Find {leaf}")
    for identifier in not_grounded:
        searches.append(f"Find {identifier}")

    deduped = []
    seen = set()
    for search in searches:
        key = search.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(search)
    return deduped


def extract_target_terms(target):
    terms = re.findall(r"[A-Za-z_][A-Za-z_0-9]{3,}", str(target or ""))
    stop = {"find", "load", "save", "path", "code", "class", "method", "caller", "callers", "definition"}
    return [term for term in terms if term.lower() not in stop][:6]


def json_dumps_compact(value):
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def combine_context(original_context, extra_context):
    parts = []
    if original_context and original_context.strip():
        parts.append(original_context.strip())
    if extra_context and extra_context.strip():
        parts.append("<focused_retrieval>\n" + extra_context.strip() + "\n</focused_retrieval>")
    return "\n\n".join(parts)


def build_final_synthesis_prompt(user_message, artifact, final_rules=None, max_chars=MAX_FINAL_ARTIFACT_CHARS):
    final_rules = final_rules or DEFAULT_FINAL_SYNTHESIS_RULES
    content = f"""Use the staged reasoning artifacts below to answer the user.

Hard rules:
{final_rules}

<user_request>
{user_message}
</user_request>

<normalized_task>
{json_dumps_compact(artifact.get("task", ""))}
</normalized_task>

<context_needs>
{json_dumps_compact(artifact.get("context_needs", ""))}
</context_needs>

<retrieval_targets>
{json.dumps(artifact.get("retrieval_targets", []), indent=2)}
</retrieval_targets>

<retrieval_quality>
{json_dumps_compact(artifact.get("retrieval_quality", {}))}
</retrieval_quality>

<context_facts>
{json_dumps_compact(artifact.get("context_facts", ""))}
</context_facts>

<missing_context_and_unsafe_assumptions>
{json_dumps_compact(artifact.get("missing_context", ""))}
</missing_context_and_unsafe_assumptions>

<hard_constraints>
{json_dumps_compact(artifact.get("hard_constraints", ""))}
</hard_constraints>

<identifier_grounding>
{json_dumps_compact(artifact.get("identifier_grounding", {}))}
</identifier_grounding>

<architectural_minimization>
{json_dumps_compact(artifact.get("architectural_minimization", {}))}
</architectural_minimization>

<custom_reasoning>
{json_dumps_compact(artifact.get("custom_reasoning", []))}
</custom_reasoning>

<retrieved_context>
{artifact.get("retrieved_context", "")}
</retrieved_context>
"""
    return limit_text(content, max_chars)


def safe_int_setting(value, default):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def format_reasoning_trace(artifact):
    lines = ["Reasoning trace"]
    for item in artifact.get("trace", []):
        lines.append(f"- {item}")
    targets = artifact.get("retrieval_targets", [])
    if targets:
        lines.append("")
        lines.append("Retrieval targets:")
        lines.extend(f"- {target}" for target in targets[:6])
    quality = artifact.get("retrieval_quality", {})
    if quality:
        lines.append("")
        lines.append(f"Retrieval confidence: {quality.get('confidence', 'unknown')}")
        lines.append(f"Files in context: {quality.get('file_count', 0)}")
    missing = artifact.get("missing_context", {})
    if isinstance(missing, dict) and missing.get("missing_context"):
        lines.append("")
        lines.append("Missing context flagged:")
        for item in missing.get("missing_context", [])[:4]:
            lines.append(f"- {item}")
    grounding = artifact.get("identifier_grounding", {})
    if grounding:
        not_grounded = grounding.get("referenced_but_not_grounded", [])
        lines.append("")
        lines.append(f"Identifier grounding: {len(not_grounded)} not grounded in retrieved context")
        for item in not_grounded[:4]:
            lines.append(f"- {item}")
    minimization = artifact.get("architectural_minimization", {})
    if minimization:
        lines.append("")
        lines.append("Architectural minimization completed")
    return "\n".join(lines)


def limit_text(text, max_chars):
    if not text or len(text) <= max_chars:
        return text or ""
    head = max_chars // 2
    tail = max_chars - head - 80
    return text[:head].rstrip() + "\n\n[...middle omitted to preserve context budget...]\n\n" + text[-tail:].lstrip()


def noop_progress(_step, _total, _title, _detail):
    return None
