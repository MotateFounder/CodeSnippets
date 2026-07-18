import hashlib
import math
import re


SECTION_SPLIT_PATTERN = re.compile(
    r"(?=^===== |\n===== |\n<related_context>|\n<smart_context_|\n<repolens_|\n<file_tree>)",
    re.MULTILINE,
)

TOKEN_PATTERN = re.compile(
    r"[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?|==|!=|<=|>=|->|=>|::|&&|\|\||"
    r"\+\+|--|[^\sA-Za-z_0-9]",
    re.UNICODE,
)


class ContextBudgeter:
    """Scores and lightly optimizes assembled context without forcing a fixed window."""

    DEFAULT_CONTEXT_WINDOW = 40000
    DEFAULT_RESERVE_OUTPUT_TOKENS = 1600

    def evaluate(self, context_text="", user_message="", settings=None, stage="Draft"):
        settings = settings or {}
        context_text = str(context_text or "")
        user_message = str(user_message or "")
        sections = self.sections_from_text(context_text)
        deduped_sections, duplicate_count = self.deduplicate_sections(sections)
        optimized_text = self.join_sections(deduped_sections)

        prompt_tokens = self.estimate_tokens(user_message)
        context_tokens = self.estimate_tokens(context_text)
        optimized_context_tokens = self.estimate_tokens(optimized_text)
        section_reports = self.section_reports(deduped_sections)
        total_tokens = prompt_tokens + optimized_context_tokens
        context_window = self.context_window(settings)
        reserve_output_tokens = self.reserve_output_tokens(settings)
        available_for_prompt = max(1, context_window - reserve_output_tokens)
        usage_ratio = total_tokens / float(available_for_prompt)

        task_quality = self.setting_value(settings, "context.preview_task_quality", None)
        quality = self.quality_scores(
            sections=deduped_sections,
            duplicate_count=duplicate_count,
            usage_ratio=usage_ratio,
            warning_ratio=self.setting_int(settings, "context.warning_threshold_percent", 85) / 100.0,
            user_message=user_message,
            context_text=optimized_text,
        )
        if task_quality is not None:
            try:
                quality["task_clarity"] = self.clamp(task_quality)
            except (TypeError, ValueError):
                pass

        report = {
            "stage": stage or "Draft",
            "context_window": context_window,
            "reserve_output_tokens": reserve_output_tokens,
            "available_prompt_tokens": available_for_prompt,
            "prompt_tokens": prompt_tokens,
            "context_tokens": context_tokens,
            "optimized_context_tokens": optimized_context_tokens,
            "total_tokens": total_tokens,
            "usage_ratio": usage_ratio,
            "section_count": len(sections),
            "optimized_section_count": len(deduped_sections),
            "sections": section_reports,
            "duplicate_sections_removed": duplicate_count,
            "optimized_text": optimized_text,
            "quality": quality,
        }
        report["summary"] = self.summary(report)
        report["tooltip"] = self.tooltip(report)
        report["audit_text"] = self.audit_text(report)
        return report

    def optimize_text(self, context_text, settings=None):
        settings = settings or {}
        report = self.evaluate(context_text=context_text, settings=settings, stage="Final assembly")
        if not self.setting_bool(settings, "context.optimization_enabled", True):
            return context_text, report
        text = context_text
        if self.setting_bool(settings, "context.remove_duplicate_sections", True):
            text = report["optimized_text"]
        max_chars = self.setting_int(settings, "context.max_attached_chars", 0)
        if max_chars > 0 and self.setting_bool(settings, "context.allow_auto_compaction", False):
            text = text[:max_chars]
            if len(text) == max_chars:
                text += "\n\n[Context compacted at configured character budget.]"
        return text, report

    def sections_from_text(self, text):
        text = str(text or "").strip()
        if not text:
            return []
        raw_sections = SECTION_SPLIT_PATTERN.split(text)
        sections = []
        for raw in raw_sections:
            value = raw.strip()
            if value:
                sections.append(value)
        return sections or [text]

    def deduplicate_sections(self, sections):
        seen = set()
        output = []
        duplicates = 0
        for section in sections:
            key = self.section_hash(section)
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            output.append(section)
        return output, duplicates

    def join_sections(self, sections):
        return "\n\n".join(section.strip() for section in sections if str(section).strip())

    def section_reports(self, sections):
        reports = []
        for index, section in enumerate(sections, start=1):
            reports.append(
                {
                    "index": index,
                    "title": self.section_title(section, index),
                    "kind": self.section_kind(section),
                    "tokens": self.estimate_tokens(section),
                }
            )
        return reports

    def section_title(self, section, index):
        text = str(section or "").strip()
        first_line = text.splitlines()[0].strip() if text else ""
        first_line = first_line.strip("<>").strip()
        if first_line.startswith("====="):
            first_line = first_line.strip("= ").strip()
        if not first_line:
            first_line = "Context section {0}".format(index)
        return first_line[:90]

    def section_kind(self, section):
        lower = str(section or "").lower()
        if "current user message" in lower:
            return "user message"
        if "mentioned snippet" in lower:
            return "mentioned snippet"
        if "referenced file" in lower:
            return "file reference"
        if "file tree" in lower:
            return "file tree"
        if "smart context" in lower:
            return "smart context"
        if "repolens" in lower or "related_context" in lower:
            return "RepoLens"
        return "snippet/card"

    def section_hash(self, text):
        normalized = re.sub(r"\s+", " ", str(text or "").strip()).lower()
        return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()

    def estimate_tokens(self, text):
        text = str(text or "")
        if not text:
            return 0
        token_count = 1
        for match in TOKEN_PATTERN.finditer(text):
            piece = match.group(0)
            byte_length = len(piece.encode("utf-8"))
            if re.match(r"^[A-Za-z_][A-Za-z_0-9]*$", piece):
                token_count += max(1, (len(piece) + 3) // 4)
            elif re.match(r"^\d+(?:\.\d+)?$", piece):
                token_count += max(1, (len(piece) + 2) // 3)
            elif byte_length != len(piece):
                token_count += max(1, (byte_length + 1) // 2)
            else:
                token_count += 1
        token_count += text.count("\n")
        token_count += len(re.findall(r"\s{2,}", text)) // 2
        return token_count

    def quality_scores(self, sections, duplicate_count, usage_ratio, warning_ratio, user_message, context_text):
        section_count = len(sections)
        grounded = 0
        exact = 0
        broad = 0
        repolens = 0
        source_range = 0
        evidence = 0
        for section in sections:
            lower = section.lower()
            has_file = "file:" in lower or "source:" in lower
            has_lines = "lines:" in lower or "referenced lines" in lower or re.search(r"\b\d+:\s", section)
            has_symbol = "symbol:" in lower or "qualified_name" in lower
            if has_file or has_lines or has_symbol:
                grounded += 1
            if has_lines or "<smart_context_source_range" in lower:
                exact += 1
            if "===== referenced file:" in lower:
                broad += 1
            if "repolens" in lower or "<related_context>" in lower:
                repolens += 1
            if "<smart_context_source_range" in lower:
                source_range += 1
            if "evidence" in lower or "resolution" in lower:
                evidence += 1

        has_sources = self.ratio(grounded, section_count, empty=0.35 if user_message.strip() else 0.0)
        is_focused = self.clamp((exact + repolens + source_range + 1.0) / max(1.0, section_count + broad))
        has_enough_context = self.clamp((math.log(section_count + 1, 8) if section_count else 0.0) + (0.15 if repolens else 0.0))
        fits_window = self.budget_score(usage_ratio, warning_ratio)
        retrieved_context = 0.85 if repolens else 0.35
        low_duplication = self.clamp(1.0 - self.ratio(duplicate_count + broad, max(1, section_count + duplicate_count)))
        if not context_text.strip() and user_message.strip():
            has_enough_context = min(has_enough_context, 0.25)
            has_sources = min(has_sources, 0.25)
        return {
            "has_sources": has_sources,
            "has_enough_context": has_enough_context,
            "is_focused": is_focused,
            "fits_window": fits_window,
            "retrieved_context": retrieved_context,
            "low_duplication": low_duplication,
            "has_evidence": self.clamp((evidence + source_range) / max(1.0, section_count)),
        }

    def budget_score(self, usage_ratio, warning_ratio=0.85):
        warning_ratio = self.clamp(warning_ratio)
        comfortable_ratio = max(0.10, warning_ratio * 0.75)
        if usage_ratio <= comfortable_ratio:
            return 1.0
        if usage_ratio <= warning_ratio:
            return 0.82
        if usage_ratio <= 1.0:
            return 0.62
        if usage_ratio <= 1.25:
            return 0.38
        return 0.18

    def summary(self, report):
        percent = int(round(report.get("usage_ratio", 0.0) * 100))
        duplicate_count = report.get("duplicate_sections_removed", 0)
        pieces = [
            "{0}: ~{1:,}/{2:,} prompt tokens ({3}%)".format(
                report.get("stage", "Context"),
                report.get("total_tokens", 0),
                report.get("available_prompt_tokens", 0),
                percent,
            )
        ]
        if duplicate_count:
            pieces.append("{0} duplicate section(s) removed".format(duplicate_count))
        return "; ".join(pieces)

    def tooltip(self, report):
        labels = self.quality_labels()
        lines = [
            "Context budget: ~{0:,}/{1:,} prompt tokens".format(
                report.get("total_tokens", 0),
                report.get("available_prompt_tokens", 0),
            ),
            "Window: {0:,}, reserved output: {1:,}".format(
                report.get("context_window", 0),
                report.get("reserve_output_tokens", 0),
            ),
            "Sections: {0} ({1} duplicate removed)".format(
                report.get("optimized_section_count", 0),
                report.get("duplicate_sections_removed", 0),
            ),
            "",
            "Quality signals:",
        ]
        for name, value in (report.get("quality") or {}).items():
            label = labels.get(name, name.replace("_", " ").title())
            lines.append("- {0}: {1:.2f}".format(label, float(value)))
        return "\n".join(lines)

    def quality_labels(self):
        return {
            "has_sources": "Files and line references",
            "has_enough_context": "Enough relevant context",
            "is_focused": "Focused, not broad",
            "fits_window": "Fits selected context window",
            "retrieved_context": "RepoLens context included",
            "low_duplication": "Low duplication",
            "has_evidence": "Resolution evidence",
            "task_clarity": "Task clarity",
        }

    def audit_text(self, report):
        values = dict(report)
        values["tooltip_text"] = report.get("tooltip", "")
        return (
            "Context budget audit\n"
            "Stage: {stage}\n"
            "Context window: {context_window:,}\n"
            "Reserved output tokens: {reserve_output_tokens:,}\n"
            "Available prompt tokens: {available_prompt_tokens:,}\n"
            "Estimated user/prompt tokens: {prompt_tokens:,}\n"
            "Estimated context tokens: {optimized_context_tokens:,}\n"
            "Estimated total prompt tokens: {total_tokens:,}\n"
            "Usage ratio: {usage_ratio:.2%}\n"
            "Sections included: {optimized_section_count}\n"
            "Duplicate sections removed: {duplicate_sections_removed}\n\n"
            "{tooltip_text}"
        ).format(**values)

    def context_window(self, settings):
        local = self.setting_bool(settings, "api.use_local_api", True)
        if local:
            return max(1, self.setting_int(settings, "llamacpp.ctx_size", self.DEFAULT_CONTEXT_WINDOW))
        return max(1, self.setting_int(settings, "openrouter.context_window", self.DEFAULT_CONTEXT_WINDOW))

    def reserve_output_tokens(self, settings):
        max_tokens = self.setting_int(settings, "generation.max_tokens", 0)
        if max_tokens > 0:
            return max_tokens
        return max(0, self.setting_int(settings, "context.reserve_output_tokens", self.DEFAULT_RESERVE_OUTPUT_TOKENS))

    def setting_bool(self, settings, key, default=False):
        return bool(self.setting_value(settings, key, default))

    def setting_int(self, settings, key, default=0):
        try:
            return int(self.setting_value(settings, key, default))
        except (TypeError, ValueError):
            return int(default)

    def setting_value(self, settings, key, default=None):
        node = settings or {}
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def ratio(self, numerator, denominator, empty=0.0):
        if denominator <= 0:
            return empty
        return self.clamp(float(numerator) / float(denominator))

    def clamp(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        return max(0.0, min(1.0, value))
