CONTEXT_MODE_CHOICES = ("Lean", "Balanced", "Deep", "Exhaustive")


CONTEXT_MODE_DESCRIPTIONS = {
    "Lean": "Small and sharp. Best for quick questions and small context windows.",
    "Balanced": "Default. Exact snippets plus focused RepoLens context.",
    "Deep": "Follows more related code for fixes, reviews, and refactors.",
    "Exhaustive": "Broadest retrieval for large context windows and investigations.",
}


CONTEXT_MODE_OVERRIDES = {
    "Lean": {
        "repolens.context.basic": True,
        "repolens.context.include_tree": False,
        "repolens.context.include_types": False,
        "repolens.context.budget_chars": 16000,
        "repolens.context.max_symbols": 8,
        "smart_context.max_exact_symbols": 8,
        "smart_context.max_patterns": 4,
        "smart_context.max_pattern_results": 2,
        "smart_context.max_final_symbols": 12,
        "smart_context.max_context_items": 8,
        "smart_context.include_source_ranges": True,
        "smart_context.max_source_range_chars": 8000,
        "smart_context.include_grounding_report": False,
        "smart_context.include_resolution_evidence": False,
        "smart_context.include_reference_inventory": False,
        "smart_context.enable_chain_expansion": False,
        "smart_context.include_tree": False,
        "smart_context.include_types": False,
        "smart_context.include_warnings": False,
    },
    "Balanced": {
        "repolens.context.basic": False,
        "repolens.context.include_tree": False,
        "repolens.context.include_types": True,
        "repolens.context.situated": True,
        "repolens.context.budget_chars": 32000,
        "repolens.context.max_symbols": 12,
        "smart_context.max_exact_symbols": 16,
        "smart_context.max_patterns": 8,
        "smart_context.max_pattern_results": 4,
        "smart_context.max_final_symbols": 24,
        "smart_context.max_context_items": 16,
        "smart_context.include_source_ranges": True,
        "smart_context.max_source_range_chars": 16000,
        "smart_context.include_grounding_report": True,
        "smart_context.include_resolution_evidence": True,
        "smart_context.max_evidence_hits": 16,
        "smart_context.include_reference_inventory": True,
        "smart_context.max_inventory_refs_per_snippet": 32,
        "smart_context.enable_chain_expansion": True,
        "smart_context.max_chain_seed_symbols": 6,
        "smart_context.max_chain_symbols": 8,
        "smart_context.include_tree": False,
        "smart_context.include_types": True,
        "smart_context.include_warnings": False,
    },
    "Deep": {
        "repolens.context.basic": False,
        "repolens.context.include_tree": True,
        "repolens.context.include_types": True,
        "repolens.context.situated": True,
        "repolens.context.budget_chars": 60000,
        "repolens.context.max_symbols": 16,
        "smart_context.max_exact_symbols": 32,
        "smart_context.max_patterns": 12,
        "smart_context.max_pattern_results": 6,
        "smart_context.max_final_symbols": 36,
        "smart_context.max_context_items": 32,
        "smart_context.include_source_ranges": True,
        "smart_context.max_source_range_chars": 24000,
        "smart_context.include_grounding_report": True,
        "smart_context.include_resolution_evidence": True,
        "smart_context.max_evidence_hits": 32,
        "smart_context.include_reference_inventory": True,
        "smart_context.max_inventory_refs_per_snippet": 64,
        "smart_context.enable_chain_expansion": True,
        "smart_context.max_chain_seed_symbols": 10,
        "smart_context.max_chain_symbols": 12,
        "smart_context.include_tree": False,
        "smart_context.include_types": True,
        "smart_context.include_warnings": False,
    },
    "Exhaustive": {
        "repolens.context.basic": False,
        "repolens.context.include_tree": True,
        "repolens.context.include_types": True,
        "repolens.context.situated": True,
        "repolens.context.budget_chars": 100000,
        "repolens.context.max_symbols": 24,
        "smart_context.max_exact_symbols": 48,
        "smart_context.max_patterns": 20,
        "smart_context.max_pattern_results": 10,
        "smart_context.max_final_symbols": 64,
        "smart_context.max_context_items": 50,
        "smart_context.include_source_ranges": True,
        "smart_context.max_source_range_chars": 40000,
        "smart_context.include_grounding_report": True,
        "smart_context.include_resolution_evidence": True,
        "smart_context.max_evidence_hits": 48,
        "smart_context.include_reference_inventory": True,
        "smart_context.max_inventory_refs_per_snippet": 100,
        "smart_context.enable_chain_expansion": True,
        "smart_context.max_chain_seed_symbols": 16,
        "smart_context.max_chain_symbols": 20,
        "smart_context.include_tree": True,
        "smart_context.include_types": True,
        "smart_context.include_warnings": True,
    },
}


def normalized_context_mode(value):
    value = str(value or "Balanced").strip().title()
    return value if value in CONTEXT_MODE_OVERRIDES else "Balanced"


def context_mode_overrides(settings):
    if not nested_setting(settings, "context.use_mode_presets", True):
        return {}
    mode = normalized_context_mode(nested_setting(settings, "context.retrieval_mode", "Balanced"))
    return CONTEXT_MODE_OVERRIDES.get(mode, {})


def nested_setting(settings, key, default=None):
    node = settings or {}
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node
