import copy
import json
import re
from pathlib import Path

from src.services.repoLens.service import (
    RepoLensService,
    context_item_count,
    context_items,
    extract_symbols_from_snippet,
    format_repolens_context,
)


PLANNER_SYSTEM_PROMPT = (
    "You are a context retrieval planner for a local coding assistant. "
    "The final model is a local LLM, so request the bare minimum useful context. "
    "Do not solve the task. Return JSON only."
)

PLANNER_USER_TEMPLATE = """Create a minimal retrieval plan for this coding task.

Return only valid JSON with this exact shape:
{{
  "task": "explain|fix|change|review|write|research|unknown",
  "confidence": 0.0,
  "strong_symbols": [],
  "search_patterns": [],
  "file_hints": [],
  "needed_context": [],
  "ignore_terms": [],
  "recommended_depth": 1
}}

Rules:
- Prefer specific project symbols, methods, classes, properties, functions, files, and naming families.
- Include patterns only when they are specific enough to find siblings or related implementations.
- Put generic framework/UI/language terms in ignore_terms.
- If the task needs context outside the snippet, describe it in needed_context and search_patterns.
- Do not include broad words unless paired with a stronger project-specific pattern.
- If the task asks to follow an existing example, include symbols and file hints for that example.
- If bindings/configuration/UI references are involved, include owning model/controller/viewmodel symbols, initialization sites, backing control/state types, and register/parameter/config names when inferable.
- If the task separates shared state into independent variants, include patterns for existing independent variants and shared/linking code that may need guarding.
- Use file_hints for likely source files that should be resolved by the retrieval engine.

Task intent: {intent}
User request:
{user_message}

Selected snippets:
{snippet_block}
"""


WEAK_TERMS = {
    "abstract",
    "active",
    "add",
    "align",
    "alignment",
    "args",
    "array",
    "background",
    "base",
    "body",
    "bool",
    "boolean",
    "border",
    "borderbrush",
    "bottom",
    "button",
    "callback",
    "cancel",
    "case",
    "catch",
    "center",
    "check",
    "class",
    "click",
    "color",
    "column",
    "columndefinition",
    "columndefinitions",
    "command",
    "config",
    "const",
    "content",
    "context",
    "control",
    "count",
    "data",
    "default",
    "double",
    "doubleupdown",
    "dynamicresource",
    "else",
    "enabled",
    "end",
    "event",
    "exponentialdoubleupdown",
    "exttoolkit",
    "false",
    "float",
    "foreground",
    "format",
    "formatstring",
    "get",
    "grid",
    "groupbox",
    "handler",
    "header",
    "height",
    "horizontal",
    "horizontalalignment",
    "id",
    "index",
    "input",
    "int",
    "item",
    "label",
    "left",
    "length",
    "list",
    "margin",
    "max",
    "maximum",
    "message",
    "min",
    "minimum",
    "model",
    "name",
    "new",
    "none",
    "null",
    "object",
    "option",
    "output",
    "padding",
    "param",
    "private",
    "protected",
    "public",
    "readonly",
    "return",
    "review",
    "right",
    "row",
    "rowdefinition",
    "rowdefinitions",
    "selected",
    "self",
    "set",
    "size",
    "source",
    "start",
    "state",
    "static",
    "string",
    "style",
    "system",
    "text",
    "this",
    "top",
    "true",
    "type",
    "value",
    "var",
    "vertical",
    "verticalalignment",
    "void",
    "volume",
    "width",
    "isenabled",
    "toolkit",
    "orientation",
    "largechange",
    "smallchange",
    "mode",
    "twoway",
    "rendertransformorigin",
}

LIBRARY_PATH_PARTS = {
    ".git",
    ".hg",
    ".svn",
    "bin",
    "build",
    "debug",
    "dist",
    "lib",
    "libs",
    "node_modules",
    "obj",
    "packages",
    "release",
    "thirdparty",
    "third_party",
    "vendor",
}

IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z_0-9]{2,}")
MEMBER_PATH_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)+)\b")
BINDING_LIKE_PATTERN = re.compile(r"\b(?:Binding|bind|bind:|v-model)\s+([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)", re.IGNORECASE)
ASSIGNMENT_LIKE_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?)\s*(?:=|:)\s*([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?)")
CHANNEL_MARKERS = ("Left", "Right", "_Left", "_Right", "FrontLR", "Front", "Rear", "Hi", "Lo")
EXAMPLE_WORDS = ("example", "pattern", "working", "already", "reference", "template")
TARGET_WORDS = ("target", "change", "fix", "review", "drc", "eq", "bass", "control")
STRONG_COMPOUND_TERMS = {
    "controlset",
}


class SmartContextRetriever:
    def __init__(self, settings=None, repolens_service=None):
        self.settings = settings or {}
        self.service = repolens_service or RepoLensService()

    def retrieve(
        self,
        index_dir,
        snippets,
        user_message="",
        intent=None,
        planner_call=None,
        progress=None,
        emit_step=None,
    ):
        progress = progress or (lambda _message: None)
        emit_step = emit_step or (lambda _title, _text, _selected=False: None)
        snippets = snippets or []
        intent = intent or {}

        progress("Smart context - planning deterministic signals...")
        deterministic = self.deterministic_plan(snippets, user_message, intent)
        emit_step("Smart context: deterministic plan", self.format_plan(deterministic), False)

        source_ranges = self.source_range_context(snippets)
        if source_ranges:
            emit_step("Smart context: source ranges", source_ranges, False)
        inventory = self.reference_inventory(snippets)
        if inventory:
            emit_step("Smart context: reference inventory", inventory, False)

        merged = self.merge_plans(deterministic, {}, intent)
        emit_step("Smart context: merged plan", self.format_plan(merged), False)

        progress("Smart context - validating symbols and patterns with RepoLens...")
        resolved = self.resolve_plan(index_dir, merged, snippets)
        emit_step("Smart context: RepoLens resolution", self.format_resolution(resolved), False)

        if self.setting_bool("smart_context.enable_chain_expansion", True):
            progress("Smart context - walking retrieval chains...")
            chains = self.expand_retrieval_chains(index_dir, resolved, merged, snippets)
            if chains.get("symbols"):
                for symbol in chains["symbols"]:
                    self.add_symbol(resolved.setdefault("symbols", []), symbol)
            resolved["chains"] = chains
            emit_step("Smart context: retrieval chains", self.format_chains(chains), False)

        if self.setting_bool("smart_context.update_before_retrieval", False):
            progress("Smart context - updating RepoLens index...")
            self.service.update(
                index_dir,
                lite=self.setting_bool("smart_context.update_lite", True),
                progress=lambda message: progress("RepoLens update - {0}".format(message)),
            )

        symbols = resolved.get("symbols", [])
        if not symbols:
            return {
                "text": "",
                "parts": [],
                "item_count": 0,
                "symbols": [],
                "plan": merged,
                "resolved": resolved,
                "depth": self.recommended_depth(merged, intent),
            }

        depth = self.recommended_depth(merged, intent)
        progress("Smart context - retrieving final context at depth {0}...".format(depth))
        result = self.context_for_symbols(index_dir, symbols, depth, partial=False)
        if context_item_count(result) == 0 and self.setting_bool("repolens.context.partial_fallback", True):
            result = self.context_for_symbols(index_dir, symbols[: self.setting_int("smart_context.max_exact_symbols", 16)], depth, partial=True)

        pruned = self.prune_context(result, merged, snippets)
        grounding = self.grounding_report(merged, resolved, pruned, snippets)
        text_parts = []
        if grounding:
            text_parts.append(grounding)
        if self.setting_bool("smart_context.include_resolution_evidence", True):
            evidence = self.format_resolution_evidence(resolved)
            if evidence:
                text_parts.append(evidence)
        if inventory and self.setting_bool("smart_context.include_reference_inventory", True):
            text_parts.append(inventory)
        if source_ranges and self.setting_bool("smart_context.include_source_ranges", True):
            text_parts.append(source_ranges)
        repolens_text = format_repolens_context(pruned).strip()
        if repolens_text:
            text_parts.append(repolens_text)
        text = "\n\n".join(part for part in text_parts if part.strip())
        summary = self.format_final_summary(merged, resolved, pruned, depth)
        emit_step("Smart context: final package", summary + ("\n\n" + text if text else ""), True)

        return {
            "text": text,
            "parts": [text] if text else [],
            "item_count": context_item_count(pruned),
            "symbols": symbols,
            "plan": merged,
            "resolved": resolved,
            "depth": depth,
            "summary": summary,
        }

    def context_for_symbols(self, index_dir, symbols, depth, partial=False):
        batch_size = max(1, self.setting_int("smart_context.context_batch_size", 6))
        merged = {}
        for start in range(0, len(symbols), batch_size):
            batch = symbols[start:start + batch_size]
            if not batch:
                continue
            result = self.service.context(
                index_dir,
                batch,
                partial=partial,
                include_tree=self.setting_bool("smart_context.include_tree", False),
                include_types=self.setting_bool("smart_context.include_types", True),
                level=depth,
                budget_chars=self.setting_int("repolens.context.budget_chars", 60000),
                basic=self.setting_bool("repolens.context.basic", False),
                situated=self.setting_bool("repolens.context.situated", False),
                signals_query=self.setting_string("repolens.context.signals_query", ""),
                grow=self.setting_bool("repolens.context.grow_enabled", False),
                grow_files=self.setting_string("repolens.context.grow_files", "").split(","),
            )
            merged = merge_context_results(merged, result)
        return merged

    def deterministic_plan(self, snippets, user_message, intent):
        strong = []
        weak = []
        patterns = []
        file_hints = []
        needed = []

        def add_unique(target, value):
            value = clean_symbol(value)
            if value and value not in target:
                target.append(value)

        max_exact = self.setting_int("smart_context.max_exact_symbols", 16)
        per_snippet_quota = max(6, max_exact // max(1, len(snippets)))
        deferred_strong = []
        prompt_hints = self.prompt_hints(user_message)

        for symbol in prompt_hints.get("strong_symbols", []):
            add_unique(strong, symbol)
        for hint in prompt_hints.get("file_hints", []):
            add_unique(file_hints, hint)
        for item in prompt_hints.get("needed_context", []):
            add_unique(needed, item)
        for pattern in prompt_hints.get("search_patterns", []):
            add_unique(patterns, pattern)

        comparison = self.comparative_pattern_plan(snippets, user_message)
        for symbol in comparison.get("strong_symbols", []):
            add_unique(strong, symbol)
        for pattern in comparison.get("search_patterns", []):
            add_unique(patterns, pattern)
        for item in comparison.get("needed_context", []):
            add_unique(needed, item)

        for snippet in snippets:
            local_strong = []
            local_weak = []
            local_patterns = []

            def add_local(value):
                value = clean_symbol(value)
                if not value:
                    return
                if self.is_weak_symbol(value):
                    add_unique(local_weak, value)
                else:
                    add_unique(local_strong, value)

            source = snippet.get("source", "")
            if source:
                file_hints.append(str(source))
            text = str(snippet.get("text", ""))
            for symbol in self.member_path_symbols(text):
                add_local(symbol)
            for symbol in self.assignment_symbols(text):
                add_local(symbol)
            for pattern in self.patterns_from_text(text):
                add_unique(local_patterns, pattern)
            for pattern in self.channel_patterns_from_text(text):
                add_unique(local_patterns, pattern)
            for symbol in extract_symbols_from_snippet(
                snippet,
                max_symbols=max_exact * 2,
            ):
                add_local(symbol)

            local_strong = sorted(
                local_strong,
                key=lambda value: symbol_priority(value),
                reverse=True,
            )
            for symbol in local_strong[:per_snippet_quota]:
                add_unique(strong, symbol)
            deferred_strong.extend(local_strong[per_snippet_quota:])
            for symbol in local_weak:
                add_unique(weak, symbol)
            for pattern in local_patterns:
                add_unique(patterns, pattern)

        for symbol in deferred_strong:
            add_unique(strong, symbol)

        for symbol in extract_symbols_from_snippet({"text": user_message}, max_symbols=8):
            if self.is_weak_symbol(symbol):
                add_unique(weak, symbol)
            else:
                add_unique(strong, symbol)
        for pattern in self.patterns_from_text(user_message):
            add_unique(patterns, pattern)

        if patterns:
            needed.append("Related symbols that share specific naming patterns with the selected snippets.")
        if file_hints:
            needed.append("Owning files and nearby symbols for the selected snippets.")

        return {
            "task": intent.get("mode", "unknown"),
            "confidence": 0.65 if strong else 0.35,
            "strong_symbols": strong,
            "search_patterns": patterns[: self.setting_int("smart_context.max_patterns", 12)],
            "file_hints": file_hints,
            "needed_context": needed,
            "ignore_terms": weak,
            "recommended_depth": intent.get("depth", 1),
            "source": "deterministic",
            "comparison": comparison,
        }

    def llm_plan(self, snippets, user_message, intent, planner_call):
        return {}
        snippet_block = self.snippet_block(snippets)
        prompt = self.setting_string("smart_context.planner_prompt", PLANNER_USER_TEMPLATE).format(
            intent=intent.get("label", intent.get("mode", "unknown")),
            user_message=user_message,
            snippet_block=snippet_block,
        )
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        text = str(planner_call(messages) or "")
        return normalize_plan(parse_json_object(text))

    def merge_plans(self, deterministic, planner, intent):
        merged = {
            "task": planner.get("task") or deterministic.get("task") or intent.get("mode", "unknown"),
            "confidence": max(float_or_zero(deterministic.get("confidence")), float_or_zero(planner.get("confidence"))),
            "strong_symbols": [],
            "search_patterns": [],
            "file_hints": [],
            "needed_context": [],
            "ignore_terms": [],
            "recommended_depth": planner.get("recommended_depth") or deterministic.get("recommended_depth") or intent.get("depth", 1),
            "warnings": [],
        }
        for key in ("strong_symbols", "search_patterns"):
            for plan in (planner, deterministic):
                for value in listify(plan.get(key)):
                    self.add_plan_value(merged[key], value)
        for key in ("file_hints", "needed_context", "ignore_terms"):
            for plan in (deterministic, planner):
                for value in listify(plan.get(key)):
                    self.add_plan_value(merged[key], value)
        for warning in listify(planner.get("warnings")):
            self.add_plan_value(merged["warnings"], warning)

        ignore = {str(value).lower() for value in merged["ignore_terms"]}
        merged["strong_symbols"] = [
            value for value in merged["strong_symbols"]
            if value.lower() not in ignore and not self.is_weak_symbol(value)
        ][: self.setting_int("smart_context.max_exact_symbols", 16)]
        merged["search_patterns"] = [
            value for value in merged["search_patterns"]
            if not self.is_weak_pattern(value)
        ][: self.setting_int("smart_context.max_patterns", 12)]
        return merged

    def resolve_plan(self, index_dir, plan, snippets):
        max_results = self.setting_int("smart_context.max_pattern_results", 5)
        source_paths = [str(snippet.get("source", "")).replace("\\", "/") for snippet in snippets if snippet.get("source")]
        symbols = []
        exact_hits = []
        pattern_hits = []
        file_hits = []

        for symbol in plan.get("strong_symbols", []):
            hits = self.search_results(index_dir, symbol, partial=False, limit=3)
            ranked = self.rank_hits(hits, symbol, source_paths, exact=True)[:3]
            if ranked:
                exact_hits.extend(ranked)
                self.add_symbol(symbols, symbol)
                for hit in ranked:
                    self.add_symbol(symbols, hit.get("qualified_name") or hit.get("name"))

        for pattern in plan.get("search_patterns", []):
            hits = self.search_results(index_dir, pattern, partial=True, limit=max_results * 3)
            ranked = self.rank_hits(hits, pattern, source_paths, exact=False)
            for hit in ranked[:max_results]:
                name = hit.get("qualified_name") or hit.get("name")
                self.add_symbol(symbols, name)
                pattern_hits.append(hit)

        for hint in plan.get("file_hints", []):
            query = file_hint_query(hint)
            if not query or self.is_weak_pattern(query):
                continue
            hits = self.search_results(index_dir, query, partial=True, limit=max_results * 2, kind="file")
            if not hits:
                hits = self.search_results(index_dir, query, partial=True, limit=max_results * 2)
            ranked = self.rank_hits(hits, query, source_paths, exact=False)
            for hit in ranked[:max_results]:
                name = hit.get("qualified_name") or hit.get("name") or Path(str(hit.get("file") or hit.get("path") or query)).stem
                self.add_symbol(symbols, name)
                file_hits.append(hit)

        return {
            "symbols": symbols[: self.setting_int("smart_context.max_final_symbols", 24)],
            "exact_hits": exact_hits,
            "pattern_hits": pattern_hits,
            "file_hits": file_hits,
        }

    def expand_retrieval_chains(self, index_dir, resolved, plan, snippets):
        seed_symbols = resolved.get("symbols", [])[: self.setting_int("smart_context.max_chain_seed_symbols", 10)]
        if not seed_symbols:
            return {"symbols": [], "steps": [], "missing": []}
        chain_context = self.context_for_symbols(index_dir, seed_symbols, depth=0, partial=False)
        symbols = []
        steps = []
        missing = []
        source_paths = [str(snippet.get("source", "")).replace("\\", "/") for snippet in snippets if snippet.get("source")]
        for item in context_items(chain_context):
            if not isinstance(item, dict):
                continue
            code = str(item.get("code", ""))
            owner = item.get("qualified_name") or item.get("name") or item.get("requested_symbol") or ""
            candidates = []
            candidates.extend(self.member_path_symbols(code))
            candidates.extend(self.assignment_symbols(code))
            candidates.extend(type_like_symbols(code))
            kept = []
            for candidate in unique(candidates):
                if self.is_weak_symbol(candidate):
                    continue
                hits = self.search_results(index_dir, candidate, partial=False, limit=3)
                ranked = self.rank_hits(hits, candidate, source_paths, exact=True)
                if ranked:
                    self.add_symbol(symbols, candidate)
                    kept.append(candidate)
                else:
                    missing.append(candidate)
            if kept:
                steps.append({"from": owner, "symbols": kept[:8]})
        return {
            "symbols": symbols[: self.setting_int("smart_context.max_chain_symbols", 12)],
            "steps": steps[: self.setting_int("smart_context.max_chain_steps", 12)],
            "missing": unique(missing)[:20],
        }

    def search_results(self, index_dir, query, partial=False, limit=20, kind=""):
        if self.is_weak_pattern(query):
            return []
        try:
            data = self.service.search(index_dir, query, kind=kind, limit=limit, partial=partial)
        except Exception:
            return []
        return flatten_search_results(data)

    def rank_hits(self, hits, query, source_paths, exact=False):
        ranked = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            name = str(hit.get("name") or hit.get("qualified_name") or "")
            qualified = str(hit.get("qualified_name") or name)
            file_path = str(hit.get("file") or hit.get("path") or "").replace("\\", "/")
            if self.is_weak_symbol(name) or self.is_library_path(file_path):
                continue
            score = 20 if exact else 10
            if query.lower() == name.lower() or query.lower() == qualified.lower():
                score += 20
            if query.lower() in qualified.lower():
                score += 8
            if any(file_path and self.same_folder(file_path, source) for source in source_paths):
                score += 10
            if any(file_path and source and file_path == source for source in source_paths):
                score += 8
            kind = str(hit.get("kind", "")).lower()
            if kind in {"class", "struct", "interface", "enum", "method", "function", "property", "field", "xaml_element"}:
                score += 4
            ranked.append(dict(hit, _score=score))
        return sorted(ranked, key=lambda item: item.get("_score", 0), reverse=True)

    def prune_context(self, data, plan, snippets):
        if not isinstance(data, dict):
            return {}
        pruned = copy.deepcopy(data)
        ignore = {str(value).lower() for value in plan.get("ignore_terms", [])}
        source_paths = [str(snippet.get("source", "")).replace("\\", "/") for snippet in snippets if snippet.get("source")]
        items = []
        seen = set()
        for item in context_items(pruned):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("qualified_name") or item.get("requested_symbol") or "")
            leaf = name.rsplit(".", 1)[-1]
            file_path = str(item.get("file", "")).replace("\\", "/")
            source_leaf = str(item.get("source_qualified_name", "")).rsplit(".", 1)[-1]
            if leaf.lower() in ignore or self.is_weak_symbol(leaf):
                continue
            if source_leaf and self.is_weak_symbol(source_leaf):
                continue
            if self.is_library_path(file_path):
                continue
            key = (item.get("qualified_name") or name, file_path, item.get("start_line") or item.get("line_start"))
            if key in seen:
                continue
            seen.add(key)
            scored = dict(item)
            scored["_smart_score"] = self.context_item_score(item, source_paths, plan.get("strong_symbols", []))
            items.append(scored)

        items = sorted(items, key=lambda item: item.get("_smart_score", 0), reverse=True)
        max_items = self.setting_int("smart_context.max_context_items", 32)
        for item in items:
            item.pop("_smart_score", None)
        pruned["items"] = items[:max_items]
        pruned.pop("symbols", None)
        if not self.setting_bool("smart_context.include_tree", False):
            pruned.pop("reduced_file_tree", None)
        if not self.setting_bool("smart_context.include_warnings", False):
            pruned.pop("warnings", None)
        return pruned

    def context_item_score(self, item, source_paths, strong_symbols):
        score = 0
        file_path = str(item.get("file", "")).replace("\\", "/")
        name = str(item.get("qualified_name") or item.get("name") or "")
        source = str(item.get("source_qualified_name") or "")
        for symbol in strong_symbols:
            symbol = str(symbol)
            if symbol and (symbol.lower() in name.lower()):
                score += 30
            elif symbol and (symbol.lower() in source.lower()):
                score += 12
        if any(file_path and file_path == source for source in source_paths):
            score += 20
        elif any(file_path and self.same_folder(file_path, source) for source in source_paths):
            score += 12
        relation = str(item.get("relation_type", ""))
        if relation:
            score += 4
        kind = str(item.get("kind", "")).lower()
        if kind in {"class", "struct", "interface", "enum", "method", "function", "property", "field", "xaml_element"}:
            score += 4
        code = str(item.get("code", ""))
        if len(code) > 2000:
            score -= 3
        return score

    def member_path_symbols(self, text):
        symbols = []
        for pattern in (MEMBER_PATH_PATTERN, BINDING_LIKE_PATTERN):
            for match in pattern.finditer(text or ""):
                path = match.group(1)
                parts = [part for part in path.split(".") if part]
                for value in (path, parts[0] if parts else "", parts[-1] if parts else ""):
                    if value and value not in symbols:
                        symbols.append(value)
        return symbols

    def assignment_symbols(self, text):
        symbols = []
        for match in ASSIGNMENT_LIKE_PATTERN.finditer(text or ""):
            for value in match.groups():
                if value and value not in symbols:
                    symbols.append(value)
        return symbols

    def patterns_from_text(self, text):
        patterns = []
        for match in IDENTIFIER_PATTERN.finditer(text or ""):
            value = match.group(0)
            if self.is_weak_symbol(value):
                continue
            for pattern in patterns_from_identifier(value):
                if not self.is_weak_pattern(pattern) and pattern not in patterns:
                    patterns.append(pattern)
        return patterns[: self.setting_int("smart_context.max_patterns", 12)]

    def channel_patterns_from_text(self, text):
        patterns = []
        for match in IDENTIFIER_PATTERN.finditer(text or ""):
            value = match.group(0)
            if self.is_weak_symbol(value):
                continue
            for marker in CHANNEL_MARKERS:
                if marker in value and len(value.replace(marker, "")) >= 4:
                    patterns.append(value.replace(marker, "").strip("_"))
        return unique([pattern for pattern in patterns if not self.is_weak_pattern(pattern)])

    def comparative_pattern_plan(self, snippets, user_message):
        examples = []
        targets = []
        for snippet in snippets:
            text = "{0}\n{1}".format(snippet.get("description", ""), snippet.get("text", ""))
            lowered = text.lower()
            if any(word in lowered for word in EXAMPLE_WORDS):
                examples.append(snippet)
            else:
                targets.append(snippet)
        if not examples and len(snippets) > 1 and any(word in user_message.lower() for word in ("like", "same as", "following", "example", "pattern")):
            examples = [snippet for snippet in snippets if has_balanced_counterparts(snippet.get("text", ""))]
            targets = [snippet for snippet in snippets if snippet not in examples]
        if not examples:
            return {}

        example_symbols = []
        target_symbols = []
        for snippet in examples:
            example_symbols.extend(self.member_path_symbols(snippet.get("text", "")))
            example_symbols.extend(extract_symbols_from_snippet(snippet, max_symbols=12))
        for snippet in targets:
            target_symbols.extend(self.member_path_symbols(snippet.get("text", "")))
            target_symbols.extend(extract_symbols_from_snippet(snippet, max_symbols=12))

        example_families = counterpart_families(example_symbols)
        target_families = counterpart_families(target_symbols)
        needed = []
        patterns = []
        for family in example_families:
            patterns.append(family)
            needed.append("Compare target code against example family '{0}'.".format(family))
        for family in target_families:
            patterns.append(family)
            needed.append("Check whether target family '{0}' has independent counterparts and backend support.".format(family))
        return {
            "strong_symbols": unique(example_symbols + target_symbols)[: self.setting_int("smart_context.max_exact_symbols", 16)],
            "search_patterns": unique(patterns)[: self.setting_int("smart_context.max_patterns", 12)],
            "needed_context": unique(needed),
            "examples": [str(snippet.get("description") or snippet.get("source") or "") for snippet in examples],
            "targets": [str(snippet.get("description") or snippet.get("source") or "") for snippet in targets],
        }

    def prompt_hints(self, text):
        text = str(text or "")
        strong = []
        file_hints = []
        patterns = []
        needed = []

        for match in re.finditer(r"[\w .:/\\-]+\.(?:cs|xaml|py|js|ts|tsx|jsx|cpp|c|h|hpp|java|go|rs|php|rb|sql|json|xml|html|css)\b", text, re.IGNORECASE):
            file_hints.append(match.group(0).strip(" ,'\"`"))

        for match in re.finditer(r"\b[A-Z][A-Za-z_0-9]{3,}\b", text):
            value = match.group(0)
            if not self.is_weak_symbol(value):
                strong.append(value)

        for match in re.finditer(r"\b([A-Z][A-Za-z0-9]{1,}(?:\s+[A-Z][A-Za-z0-9]{1,}){1,3})\b", text):
            compact = "".join(match.group(1).split())
            if not self.is_weak_symbol(compact):
                strong.append(compact)
                patterns.append(compact)

        for match in re.finditer(r"\b[A-Za-z_][A-Za-z_0-9]*(?:Left|Right|FrontLR|Front|Rear|Hi|Lo)[A-Za-z_0-9]*\b", text):
            value = match.group(0)
            if not self.is_weak_symbol(value):
                strong.append(value)
                for pattern in patterns_from_identifier(value):
                    patterns.append(pattern)

        lowered = text.lower()
        if any(word in lowered for word in ("example", "pattern", "same as", "like", "mirror", "follow")):
            needed.append("Find and compare an existing working example pattern from selected snippets or named files.")
        if any(word in lowered for word in ("left", "right", "independent", "separate", "split", "channel")):
            needed.append("Check left/right variants, shared state, backing control support, and linking/copy behavior.")
            patterns.extend(["Left", "Right", "FrontLR"])
        if any(word in lowered for word in ("binding", "bindings", "viewmodel", "model", "controller", "initialization", "constructor")):
            needed.append("Resolve bindings to owning model/controller/viewmodel declarations and initialization sites.")
        if any(word in lowered for word in ("backend", "register", "parameter", "param", "control", "hardware", "api")):
            needed.append("Resolve backing control, parameter/register definitions, and lower-layer support.")
            patterns.extend(["Param", "Control", "Register"])

        return {
            "strong_symbols": unique(strong),
            "file_hints": unique(file_hints),
            "search_patterns": unique([pattern for pattern in patterns if not self.is_weak_pattern(pattern)]),
            "needed_context": unique(needed),
        }

    def source_range_context(self, snippets):
        if not self.setting_bool("smart_context.include_source_ranges", True):
            return ""
        parts = []
        padding = self.setting_int("smart_context.source_range_padding_lines", 4)
        max_chars = self.setting_int("smart_context.max_source_range_chars", 24000)
        per_snippet_chars = max(1000, max_chars // max(1, len(snippets)))
        used_chars = 0
        for snippet in snippets:
            source = snippet.get("source")
            text = self.read_source_range(source, snippet.get("start_line"), snippet.get("end_line"), padding)
            if not text:
                text = str(snippet.get("text", "")).strip()
            if not text:
                continue
            if len(text) > per_snippet_chars:
                text = text[:per_snippet_chars] + "\n... source range truncated for balance ..."
            if used_chars + len(text) > max_chars:
                remaining = max_chars - used_chars
                if remaining <= 0:
                    break
                text = text[:remaining]
            used_chars += len(text)
            parts.append(
                "<source_range>\n"
                "Description: {0}\n"
                "File: {1}\n"
                "Lines: {2}-{3}\n"
                "```{4}\n{5}\n```\n"
                "</source_range>".format(
                    snippet.get("description", ""),
                    source or "",
                    snippet.get("start_line") or "?",
                    snippet.get("end_line") or "?",
                    language_hint(source),
                    text,
                )
            )
        return "<selected_source_ranges>\n{0}\n</selected_source_ranges>".format("\n\n".join(parts)) if parts else ""

    def reference_inventory(self, snippets):
        if not self.setting_bool("smart_context.include_reference_inventory", True):
            return ""
        blocks = []
        max_refs = self.setting_int("smart_context.max_inventory_refs_per_snippet", 80)
        for snippet in snippets:
            text = str(snippet.get("text", ""))
            refs = []
            refs.extend(self.member_path_symbols(text))
            refs.extend(self.assignment_symbols(text))
            refs.extend(extract_symbols_from_snippet(snippet, max_symbols=max_refs))
            refs = [
                value for value in unique(refs)
                if not self.is_weak_symbol(value)
            ][:max_refs]
            if not refs:
                continue
            blocks.append(
                "<reference_inventory_item>\n"
                "Description: {0}\n"
                "File: {1}\n"
                "Lines: {2}-{3}\n"
                "References:\n{4}\n"
                "</reference_inventory_item>".format(
                    snippet.get("description", ""),
                    snippet.get("source", ""),
                    snippet.get("start_line") or "?",
                    snippet.get("end_line") or "?",
                    format_list(refs),
                )
            )
        return "<smart_context_reference_inventory>\n{0}\n</smart_context_reference_inventory>".format("\n\n".join(blocks)) if blocks else ""

    def read_source_range(self, source, start_line, end_line, padding):
        if not source or not start_line or not end_line:
            return ""
        try:
            path = Path(source)
            if not path.exists() or not path.is_file():
                return ""
            start = max(1, int(start_line) - padding)
            end = int(end_line) + padding
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            selected = lines[start - 1:end]
            return "\n".join("{0}: {1}".format(start + index, line) for index, line in enumerate(selected))
        except (OSError, ValueError, TypeError):
            return ""

    def grounding_report(self, plan, resolved, data, snippets):
        if not self.setting_bool("smart_context.include_grounding_report", True):
            return ""
        found_names = {
            str(item.get("name") or item.get("qualified_name") or "").lower()
            for item in context_items(data)
            if isinstance(item, dict)
        }
        found_text = "\n".join(
            str(item.get("qualified_name") or item.get("name") or "")
            for item in context_items(data)
            if isinstance(item, dict)
        ).lower()
        grounded = []
        likely = []
        missing = []
        for symbol in plan.get("strong_symbols", []):
            lower = symbol.lower()
            leaf = lower.rsplit(".", 1)[-1]
            if lower in found_text or leaf in found_names:
                grounded.append(symbol)
            else:
                hits = [hit for hit in resolved.get("exact_hits", []) if lower in str(hit.get("qualified_name") or hit.get("name") or "").lower()]
                if hits:
                    likely.append(symbol)
                else:
                    missing.append(symbol)
        comparison = plan.get("comparison") or {}
        lines = [
            "<smart_context_grounding>",
            "Grounded symbols:",
            format_list(grounded[:20]),
            "",
            "Likely relevant but not present in final context:",
            format_list(likely[:20]),
            "",
            "Missing or unconfirmed symbols:",
            format_list(missing[:20]),
        ]
        if comparison:
            lines.extend(
                [
                    "",
                    "Example snippets:",
                    format_list(comparison.get("examples", [])),
                    "",
                    "Target snippets:",
                    format_list(comparison.get("targets", [])),
                    "",
                    "Comparison notes:",
                    format_list(comparison.get("needed_context", [])),
                ]
            )
        if resolved.get("chains", {}).get("missing"):
            lines.extend(["", "Unconfirmed chain symbols:", format_list(resolved["chains"]["missing"][:20])])
        lines.append("</smart_context_grounding>")
        return "\n".join(lines)

    def is_weak_symbol(self, value):
        value = clean_symbol(value)
        if not value:
            return True
        lower = value.lower().strip("_")
        if lower in STRONG_COMPOUND_TERMS:
            return False
        if lower in WEAK_TERMS:
            return True
        if "." in value:
            return all(self.is_weak_symbol(part) for part in value.split("."))
        if len(value) < self.setting_int("smart_context.min_symbol_length", 3):
            return True
        pieces = split_identifier(value)
        if pieces and all(piece.lower() in WEAK_TERMS for piece in pieces):
            return True
        return False

    def is_weak_pattern(self, value):
        value = clean_symbol(value)
        if not value:
            return True
        if self.is_weak_symbol(value):
            return True
        if len(value.strip("_")) < self.setting_int("smart_context.min_pattern_length", 5):
            return True
        return False

    def is_library_path(self, file_path):
        if not self.setting_bool("smart_context.exclude_library_paths", True):
            return False
        parts = {part.lower() for part in str(file_path).replace("\\", "/").split("/") if part}
        return bool(parts & LIBRARY_PATH_PARTS)

    def same_folder(self, left, right):
        if not left or not right:
            return False
        return str(Path(left).parent).replace("\\", "/").lower() == str(Path(right).parent).replace("\\", "/").lower()

    def add_symbol(self, symbols, symbol):
        symbol = clean_symbol(symbol)
        if symbol and symbol not in symbols and not self.is_weak_symbol(symbol):
            symbols.append(symbol)

    def add_plan_value(self, target, value):
        value = clean_symbol(value)
        if value and value not in target:
            target.append(value)

    def recommended_depth(self, plan, intent):
        depth = int_or_default(plan.get("recommended_depth"), intent.get("depth", 1))
        min_depth = self.setting_int("smart_context.min_depth", 1)
        max_depth = self.setting_int("smart_context.max_depth", 3)
        return max(min_depth, min(max_depth, depth))

    def snippet_block(self, snippets):
        blocks = []
        for index, snippet in enumerate(snippets, start=1):
            blocks.append(
                "Snippet {0}\nSource: {1}\nLines: {2}-{3}\nDescription: {4}\n```text\n{5}\n```".format(
                    index,
                    snippet.get("source", ""),
                    snippet.get("start_line") or "?",
                    snippet.get("end_line") or "?",
                    snippet.get("description", ""),
                    str(snippet.get("text", ""))[: self.setting_int("smart_context.planner_max_snippet_chars", 6000)],
                )
            )
        return "\n\n".join(blocks)

    def format_plan(self, plan):
        lines = [
            "Task: {0}".format(plan.get("task", "unknown")),
            "Confidence: {0}".format(plan.get("confidence", "")),
            "Depth: {0}".format(plan.get("recommended_depth", "")),
            "",
            "Strong symbols:",
            format_list(plan.get("strong_symbols", [])),
            "",
            "Search patterns:",
            format_list(plan.get("search_patterns", [])),
            "",
            "Files / file hints:",
            format_list(plan.get("file_hints", [])),
            "",
            "Needed context:",
            format_list(plan.get("needed_context", [])),
            "",
            "Ignored terms:",
            format_list(plan.get("ignore_terms", [])),
        ]
        if plan.get("warnings"):
            lines.extend(["", "Warnings:", format_list(plan.get("warnings", []))])
        if plan.get("comparison"):
            lines.extend(["", "Comparative pattern analysis:", format_list(plan["comparison"].get("needed_context", []))])
        return "\n".join(lines)

    def format_resolution(self, resolved):
        lines = [
            "Final RepoLens symbols:",
            format_list(resolved.get("symbols", [])),
            "",
            "Exact hits:",
            format_hit_list(resolved.get("exact_hits", [])),
            "",
            "Pattern hits:",
            format_hit_list(resolved.get("pattern_hits", [])),
            "",
            "File hint hits:",
            format_hit_list(resolved.get("file_hits", [])),
        ]
        if resolved.get("chains"):
            lines.extend(["", "Retrieval chain symbols:", format_list(resolved["chains"].get("symbols", []))])
        return "\n".join(lines)

    def format_resolution_evidence(self, resolved):
        blocks = []
        for title, key in (
            ("Exact symbol evidence", "exact_hits"),
            ("Pattern evidence", "pattern_hits"),
            ("File hint evidence", "file_hits"),
        ):
            hits = resolved.get(key, [])
            if not hits:
                continue
            lines = ["<smart_context_evidence section=\"{0}\">".format(title)]
            for hit in hits[: self.setting_int("smart_context.max_evidence_hits", 40)]:
                lines.append(format_hit_evidence(hit))
            lines.append("</smart_context_evidence>")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def format_chains(self, chains):
        lines = ["Expanded symbols:", format_list(chains.get("symbols", [])), "", "Chain steps:"]
        if chains.get("steps"):
            for step in chains.get("steps", []):
                lines.append("- {0} -> {1}".format(step.get("from", "(unknown)"), ", ".join(step.get("symbols", []))))
        else:
            lines.append("- (none)")
        lines.extend(["", "Unconfirmed symbols:", format_list(chains.get("missing", []))])
        return "\n".join(lines)

    def format_final_summary(self, plan, resolved, data, depth):
        return "\n".join(
            [
                "Smart context final package",
                "Task: {0}".format(plan.get("task", "unknown")),
                "Depth: {0}".format(depth),
                "Context items: {0}".format(context_item_count(data)),
                "Symbols: {0}".format(", ".join(resolved.get("symbols", [])[:20]) or "(none)"),
            ]
        )

    def setting_bool(self, key, default=False):
        return bool(self.settings.get(key, default))

    def setting_int(self, key, default=0):
        return int_or_default(self.settings.get(key), default)

    def setting_string(self, key, default=""):
        value = self.settings.get(key, default)
        return str(value if value is not None else default)


def patterns_from_identifier(value):
    value = clean_symbol(value)
    if not value:
        return []
    patterns = []
    if re.search(r"\d", value):
        stripped = re.sub(r"\d+", "", value).strip("_")
        prefix = re.split(r"\d+", value, 1)[0].strip("_")
        for candidate in (prefix, stripped):
            if candidate and candidate != value:
                patterns.append(candidate)

    pieces = split_identifier(value)
    if len(pieces) >= 3:
        patterns.append("".join(pieces[:-1]))
        patterns.append("".join(pieces[1:]))
    if len(pieces) >= 2:
        patterns.append("".join(pieces[:2]))
    return unique(patterns)


def split_identifier(value):
    value = value.replace("_", " ")
    raw = []
    for token in value.split():
        raw.extend(re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+", token))
    return [part for part in raw if not part.isdigit()]


def type_like_symbols(text):
    symbols = []
    patterns = [
        r"\bnew\s+([A-Za-z_][A-Za-z_0-9]*)",
        r"\b(?:class|struct|interface|enum|record|delegate)\s+([A-Za-z_][A-Za-z_0-9]*)",
        r"\b(?:public|private|protected|internal)?\s*(?:readonly\s+)?([A-Z][A-Za-z_0-9]{2,})\s+[A-Za-z_][A-Za-z_0-9]*\s*(?:[;={]|$)",
        r"\b([A-Z][A-Za-z_0-9]{2,})<[^>]+>\s+[A-Za-z_][A-Za-z_0-9]*",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text or ""):
            symbols.append(match.group(1))
    return unique(symbols)


def counterpart_families(symbols):
    families = []
    for symbol in symbols:
        value = clean_symbol(symbol)
        if not value:
            continue
        leaf = value.rsplit(".", 1)[-1]
        normalized = leaf
        for marker in ("_Left", "_Right", "Left", "Right", "FrontLR", "Front", "Rear"):
            normalized = normalized.replace(marker, "")
        normalized = re.sub(r"\d+", "", normalized).strip("_")
        if len(normalized) >= 5:
            families.append(normalized)
    return unique(families)


def has_balanced_counterparts(text):
    symbols = re.findall(IDENTIFIER_PATTERN, text or "")
    joined = " ".join(symbols)
    return (
        ("Left" in joined or "_Left" in joined)
        and ("Right" in joined or "_Right" in joined)
    )


def language_hint(source):
    suffix = Path(str(source or "")).suffix.lower()
    return {
        ".cs": "csharp",
        ".xaml": "xml",
        ".xml": "xml",
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".jsx": "jsx",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".c": "c",
        ".h": "cpp",
        ".hpp": "cpp",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".php": "php",
        ".rb": "ruby",
        ".sql": "sql",
        ".html": "html",
        ".css": "css",
        ".json": "json",
    }.get(suffix, "")


def file_hint_query(value):
    value = clean_symbol(value)
    if not value:
        return ""
    value = value.replace("\\", "/")
    if "/" in value or "." in Path(value).name:
        stem = Path(value).stem
        return stem or value
    return value


def symbol_priority(value):
    value = clean_symbol(value)
    lower = value.lower()
    score = 0
    for marker in ("left", "right", "frontlr", "front", "rear"):
        if marker in lower:
            score += 12
    for marker in (
        "gain",
        "limiter",
        "freq",
        "frequency",
        "level",
        "gate",
        "ratio",
        "rat",
        "threshold",
        "thr",
        "attack",
        "release",
        "att",
        "rel",
        "eq",
        "drc",
        "vb",
        "volume",
        "ramp",
    ):
        if marker in lower:
            score += 8
    if "." in value:
        score += 4
    if "_" in value:
        score += 3
    if re.search(r"\d", value):
        score += 2
    score += min(6, max(0, len(value) - 8) // 4)
    return score


def parse_json_object(text):
    text = str(text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    return {}


def normalize_plan(value):
    if not isinstance(value, dict):
        return {}
    plan = dict(value)
    for key in ("strong_symbols", "search_patterns", "file_hints", "needed_context", "ignore_terms"):
        plan[key] = [clean_symbol(item) for item in listify(plan.get(key)) if clean_symbol(item)]
    return plan


def flatten_search_results(data):
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("results", "items", "symbols", "matches"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def merge_context_results(left, right):
    if not isinstance(left, dict) or not left:
        left = {}
    if not isinstance(right, dict):
        return left
    merged = copy.deepcopy(left)
    if not merged.get("metadata") and right.get("metadata"):
        merged["metadata"] = copy.deepcopy(right.get("metadata"))
    if not merged.get("repository") and right.get("repository"):
        merged["repository"] = copy.deepcopy(right.get("repository"))

    existing = set()
    items = []
    for data in (merged, right):
        for item in context_items(data):
            if not isinstance(item, dict):
                continue
            key = (
                item.get("qualified_name") or item.get("name") or item.get("requested_symbol"),
                item.get("file"),
                item.get("start_line") or item.get("line_start"),
            )
            if key in existing:
                continue
            existing.add(key)
            items.append(copy.deepcopy(item))
    merged["items"] = items

    warnings = []
    for data in (left, right):
        for warning in data.get("warnings", []) if isinstance(data, dict) else []:
            if warning not in warnings:
                warnings.append(warning)
    if warnings:
        merged["warnings"] = warnings
    return merged


def clean_symbol(value):
    value = str(value or "").strip()
    value = value.strip("`'\" ")
    return value


def listify(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def unique(values):
    output = []
    for value in values:
        value = clean_symbol(value)
        if value and value not in output:
            output.append(value)
    return output


def int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def float_or_zero(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_list(values):
    values = [str(value) for value in values if str(value).strip()]
    return "\n".join("- {0}".format(value) for value in values) if values else "- (none)"


def format_hit_list(values):
    lines = []
    for item in values[:20]:
        name = item.get("qualified_name") or item.get("name") or "(unknown)"
        file_path = item.get("file") or item.get("path") or ""
        kind = item.get("kind") or ""
        lines.append("- {0} [{1}] {2}".format(name, kind, file_path))
    return "\n".join(lines) if lines else "- (none)"


def format_hit_evidence(hit):
    name = hit.get("qualified_name") or hit.get("name") or "(unknown)"
    file_path = hit.get("file") or hit.get("path") or ""
    kind = hit.get("kind") or ""
    signature = hit.get("signature") or hit.get("declaration") or ""
    line = hit.get("line") or hit.get("line_start") or hit.get("start_line") or ""
    pieces = [
        "- Symbol: {0}".format(name),
        "  Kind: {0}".format(kind or "unknown"),
        "  File: {0}".format(file_path or "unknown"),
    ]
    if line:
        pieces.append("  Line: {0}".format(line))
    if signature:
        pieces.append("  Signature: {0}".format(signature))
    return "\n".join(pieces)
