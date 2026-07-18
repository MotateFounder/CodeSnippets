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
from src.services.context_budget import ContextBudgeter
from src.services.context_modes import CONTEXT_MODE_DESCRIPTIONS, normalized_context_mode


class ContextMixin:
    CONTEXT_BUDGET_IMPORTANCES = {
        "has_sources": "high",
        "has_enough_context": "high",
        "is_focused": "mid",
        "fits_window": "mid",
        "retrieved_context": "mid",
        "low_duplication": "mid",
        "has_evidence": "low",
        "task_clarity": "mid",
    }

    def context_budgeter(self):
        if not hasattr(self, "_context_budgeter"):
            self._context_budgeter = ContextBudgeter()
        return self._context_budgeter

    def on_context_mode_changed(self, _event=None):
        mode = normalized_context_mode(self.context_mode_var.get() if hasattr(self, "context_mode_var") else "Balanced")
        self.set_nested_setting(self.settings, "context.retrieval_mode", mode)
        if hasattr(self, "context_mode_var"):
            self.context_mode_var.set(mode)
        self.context_retrieval_preview_signature = ""
        self.request_context_recalculation("Context mode changed")
        if hasattr(self, "status"):
            self.status.configure(text="Context mode set to {0}.".format(mode))

    def start_context_budget_polling(self):
        self.context_budget_after_id = None
        self.context_budget_state = {
            "stage": "Draft",
            "context_text": "",
            "user_message": "",
            "report": None,
        }
        self.context_retrieval_preview_text = ""
        self.context_retrieval_preview_signature = ""
        self.context_retrieval_preview_running = False
        self.context_task_quality = None
        self.context_task_quality_reason = ""
        self.context_task_quality_signature = ""
        self.context_task_quality_running = False
        self.context_recalculation_after_id = None
        self.refresh_context_budget_state(stage="Draft")

    def bind_context_recalculation_events(self):
        if getattr(self, "_context_recalculation_events_bound", False):
            return
        self._context_recalculation_events_bound = True
        try:
            self.bind_all("<KeyRelease>", lambda _event: self.request_context_recalculation("Input changed"), add="+")
            self.bind_all("<ButtonRelease-1>", lambda _event: self.request_context_recalculation("Selection changed"), add="+")
        except tk.TclError:
            pass

    def request_context_recalculation(self, stage="Context changed"):
        if not hasattr(self, "context_quality"):
            return

    def recalculate_context_quality(self, stage="Context changed"):
        self.context_recalculation_after_id = None
        self.refresh_context_budget_state(stage=stage)
        self.maybe_start_context_preview_retrieval()
        self.maybe_start_task_quality_preview()

    def refresh_context_budget_state(self, context_text=None, user_message=None, stage="Draft"):
        if not hasattr(self, "context_quality"):
            return None
        if context_text is None:
            context_text = self.assemble_context_preview_text(include_retrieval_preview=True)
        if user_message is None:
            user_message = self.chat_input_text().strip() if hasattr(self, "chat_input") else ""
        settings = getattr(self, "settings", {})
        if self.context_task_quality is not None:
            settings = self.copy_settings_with_task_quality(settings, self.context_task_quality)
        report = self.context_budgeter().evaluate(
            context_text=context_text,
            user_message=user_message,
            settings=settings,
            stage=stage,
        )
        self.context_budget_state = {
            "stage": stage,
            "context_text": context_text,
            "user_message": user_message,
            "report": report,
        }
        self.apply_context_budget_report(report)
        self.refresh_token_count_from_report(report)
        self.refresh_context_inspector(report)
        return report

    def apply_context_budget_report(self, report):
        if not report or not hasattr(self, "context_quality"):
            return
        self.context_quality.reset()
        self.context_quality.set_many(
            report.get("quality", {}),
            importances=self.CONTEXT_BUDGET_IMPORTANCES,
        )
        self.context_quality.set_tooltip("")

    def publish_context_budget_snapshot(self, context_text, user_message="", stage="Context update"):
        return self.refresh_context_budget_state(
            context_text=context_text,
            user_message=user_message,
            stage=stage,
        )

    def optimize_context_for_send(self, context_text, user_message="", stage="Final assembly"):
        optimized_text, report = self.context_budgeter().optimize_text(
            context_text,
            settings=getattr(self, "settings", {}),
        )
        final_report = self.context_budgeter().evaluate(
            context_text=optimized_text,
            user_message=user_message,
            settings=getattr(self, "settings", {}),
            stage=stage,
        )
        self.context_budget_state = {
            "stage": stage,
            "context_text": optimized_text,
            "user_message": user_message,
            "report": final_report,
            "pre_optimization_report": report,
        }
        self.post_ui(lambda value=final_report: self.apply_context_budget_report(value))
        self.post_ui(lambda value=final_report: self.refresh_context_inspector(value))
        return optimized_text, final_report

    def maybe_add_context_audit_card(self, report):
        if not report or not bool(self.get_setting("context.create_audit_card", True)):
            return None
        if not report.get("audit_text", "").strip():
            return None
        if hasattr(self, "add_smart_context_step_card"):
            return self.add_smart_context_step_card(
                "Context budget audit",
                report.get("audit_text", ""),
                selected=False,
            )
        return None

    def copy_settings_with_task_quality(self, settings, task_quality):
        data = dict(settings or {})
        context_settings = dict(data.get("context", {}) or {})
        context_settings["preview_task_quality"] = task_quality
        data["context"] = context_settings
        return data

    def assemble_context_preview_text(self, include_retrieval_preview=True):
        parts = []
        raw_message = self.chat_input_text().strip() if hasattr(self, "chat_input") else ""
        file_references = self.chat_file_references(raw_message) if hasattr(self, "chat_file_references") else []
        mention_context = self.formatted_mentioned_snippets(raw_message) if hasattr(self, "formatted_mentioned_snippets") else ""
        context = self.formatted_snippets(selected_only=True)
        file_context = self.formatted_chat_file_reference_context(file_references) if hasattr(self, "formatted_chat_file_reference_context") else ""
        display_message = self.shortened_chat_file_reference_message(raw_message, file_references) if hasattr(self, "shortened_chat_file_reference_message") else raw_message
        prompt_message = self.chat_prompt_message_with_file_references(display_message, file_references) if hasattr(self, "chat_prompt_message_with_file_references") else display_message

        for part in (mention_context, context, file_context):
            if str(part or "").strip():
                parts.append(part)
        if include_retrieval_preview and str(getattr(self, "context_retrieval_preview_text", "") or "").strip():
            parts.append("===== Preview Retrieved Context =====\n" + self.context_retrieval_preview_text.strip())
        if prompt_message.strip():
            parts.append("===== Current User Message =====\n{0}".format(prompt_message.strip()))
        return "\n\n".join(parts)

    def refresh_token_count_from_report(self, report):
        if not hasattr(self, "token_count_label") or not report:
            return
        self.token_count_label.configure(
            text="~{0:,}/{1:,} tokens".format(
                int(report.get("total_tokens", 0) or 0),
                int(report.get("available_prompt_tokens", 0) or 0),
            )
        )

    def refresh_context_inspector(self, report):
        if not hasattr(self, "context_inspector_text") or not report:
            return
        lines = [
            "Context Inspector",
            "Stage: {0}".format(report.get("stage", "Draft")),
            "Mode: {0} - {1}".format(
                self.current_context_mode(),
                CONTEXT_MODE_DESCRIPTIONS.get(self.current_context_mode(), ""),
            ),
            "Estimated prompt: ~{0:,}/{1:,} tokens".format(
                int(report.get("total_tokens", 0) or 0),
                int(report.get("available_prompt_tokens", 0) or 0),
            ),
            "Sections: {0}; duplicates removed: {1}".format(
                report.get("optimized_section_count", 0),
                report.get("duplicate_sections_removed", 0),
            ),
        ]
        if getattr(self, "context_task_quality_reason", ""):
            lines.append("Task clarity note: {0}".format(self.context_task_quality_reason))
        lines.extend(["", "Retrieval status:"])
        for line in self.context_retrieval_status_lines(report):
            lines.append("- " + line)
        lines.extend(["", "Quality checks:"])
        labels = self.context_budgeter().quality_labels()
        for key, value in (report.get("quality") or {}).items():
            lines.append(
                "- {0}: {1:.2f}".format(
                    labels.get(key, key.replace("_", " ").title()),
                    float(value),
                )
            )
        lines.append("")
        lines.append("Context parts:")
        for item in report.get("sections", [])[:30]:
            lines.append(
                "- ~{0:,} tokens | {1} | {2}".format(
                    int(item.get("tokens", 0) or 0),
                    item.get("kind", "context"),
                    item.get("title", "Context"),
                )
            )
        if len(report.get("sections", [])) > 30:
            lines.append("- ... {0} more section(s)".format(len(report.get("sections", [])) - 30))
        text = "\n".join(lines)
        if hasattr(self, "context_inspector_timestamp_label"):
            self.context_inspector_timestamp_label.configure(
                text="Updated {0}".format(self.display_timestamp(self.current_timestamp()))
            )
        self.context_inspector_text.configure(state=tk.NORMAL)
        self.context_inspector_text.delete("1.0", tk.END)
        self.context_inspector_text.insert("1.0", text)
        line_count = max(8, min(48, text.count("\n") + 2))
        self.context_inspector_text.configure(height=line_count)
        self.context_inspector_text.configure(state=tk.DISABLED)

    def current_context_mode(self):
        return normalized_context_mode(self.get_setting("context.retrieval_mode", "Balanced"))

    def context_retrieval_status_lines(self, report):
        raw_message = self.chat_input_text().strip() if hasattr(self, "chat_input") else ""
        file_refs = self.chat_file_references(raw_message) if hasattr(self, "chat_file_references") else []
        selected = self.snippets_for_context(selected_only=True)
        mentioned = self.mentioned_snippets(raw_message) if hasattr(self, "mentioned_snippets") else []
        lines = [
            "{0} checked snippet(s) will be attached.".format(len(selected)),
            "{0} @snippet mention(s) resolved.".format(len(mentioned)),
            "{0} #file reference(s) resolved.".format(len([ref for ref in file_refs if not ref.get("error")])),
        ]
        if getattr(self, "context_retrieval_preview_running", False):
            lines.append("RepoLens preview is running.")
        elif getattr(self, "context_retrieval_preview_text", "").strip():
            lines.append("RepoLens preview context is included in the estimate.")
        else:
            lines.append("RepoLens preview has no extra context yet.")
        if getattr(self, "context_task_quality_running", False):
            lines.append("Task clarity check is running.")
        elif self.context_task_quality is not None:
            lines.append("Task clarity score is included.")
        if report.get("duplicate_sections_removed", 0):
            lines.append("{0} duplicate context section(s) removed.".format(report.get("duplicate_sections_removed", 0)))
        return lines

    def maybe_start_context_preview_retrieval(self):
        if not bool(self.get_setting("context.preview_retrieval_enabled", True)):
            return
        if getattr(self, "context_retrieval_preview_running", False):
            return
        if not hasattr(self, "repolens_enabled_for_current_session") or not self.repolens_enabled_for_current_session():
            return
        raw_message = self.chat_input_text().strip() if hasattr(self, "chat_input") else ""
        if not raw_message and not self.snippets_for_context(selected_only=True):
            self.context_retrieval_preview_text = ""
            self.context_retrieval_preview_signature = ""
            return
        local_context = self.assemble_context_preview_text(include_retrieval_preview=False)
        signature = self.context_budgeter().section_hash(local_context + "\n" + raw_message)
        if signature == getattr(self, "context_retrieval_preview_signature", ""):
            return
        self.context_retrieval_preview_signature = signature
        self.context_retrieval_preview_running = True

        def worker():
            text = ""
            try:
                file_references = self.chat_file_references(raw_message) if hasattr(self, "chat_file_references") else []
                anchors = self.repolens_chat_snapshots(raw_message, file_references=file_references) if hasattr(self, "repolens_chat_snapshots") else []
                if anchors:
                    intent = self.chat_preview_intent(raw_message)
                    if bool(self.get_setting("smart_context.enabled", True)) and hasattr(self, "retrieve_smart_context"):
                        result = self.retrieve_smart_context(
                            anchors,
                            user_message=raw_message,
                            endpoint=None,
                            intent=intent,
                            progress=lambda _message: None,
                            create_cards=False,
                        )
                    else:
                        result = self.retrieve_repolens_context_for_snippets(
                            anchors,
                            user_message=raw_message,
                            depth=self.repolens_depth_for_intent(intent, fallback=1),
                            update_before=False,
                            progress=lambda _message: None,
                        )
                    text = str((result or {}).get("text", "")).strip()
            except Exception as exc:
                text = "Preview retrieval unavailable: {0}".format(exc)

            def finish():
                self.context_retrieval_preview_text = text
                self.context_retrieval_preview_running = False
                self.refresh_context_budget_state(stage="Preview retrieval")

            self.post_ui(finish)

        threading.Thread(target=worker, daemon=True).start()

    def chat_preview_intent(self, raw_message):
        try:
            from src.services.chat_intents import chat_intent_for_message

            return chat_intent_for_message(raw_message)
        except Exception:
            return {"mode": "explain", "label": "Explain", "depth": 1, "source": "preview"}

    def maybe_start_task_quality_preview(self):
        if not bool(self.get_setting("context.preview_task_quality_enabled", False)):
            return
        if getattr(self, "context_task_quality_running", False):
            return
        raw_message = self.chat_input_text().strip() if hasattr(self, "chat_input") else ""
        min_chars = int(self.get_setting("context.preview_task_quality_min_chars", 20) or 20)
        if len(raw_message) < min_chars:
            self.context_task_quality = None
            self.context_task_quality_reason = ""
            self.context_task_quality_signature = ""
            return
        signature = self.context_budgeter().section_hash(raw_message)
        if signature == getattr(self, "context_task_quality_signature", ""):
            return
        self.context_task_quality_signature = signature
        self.context_task_quality_running = True

        def worker():
            score = None
            reason = ""
            try:
                endpoint = self.normalized_chat_endpoint() if hasattr(self, "normalized_chat_endpoint") else ""
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "Score the user's coding task clarity. Return compact JSON only: "
                            "{\"score\":0.0,\"reason\":\"short actionable note\"}. "
                            "Score 1 means clear goal, constraints, and expected output; 0 means unusable."
                        ),
                    },
                    {"role": "user", "content": raw_message[:1200]},
                ]
                answer = self._call_chat_once(endpoint, messages) if hasattr(self, "_call_chat_once") else ""
                data = self.parse_task_quality_response(answer)
                score = data.get("score")
                reason = str(data.get("reason", "")).strip()[:160]
            except Exception:
                score = None
                reason = ""

            def finish():
                self.context_task_quality = score
                self.context_task_quality_reason = reason
                self.context_task_quality_running = False
                self.refresh_context_budget_state(stage="Task clarity scored")

            self.post_ui(finish)

        threading.Thread(target=worker, daemon=True).start()

    def parse_task_quality_response(self, text):
        raw = str(text or "").strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                return {}
        return {}

    def formatted_snippets(self, selected_only=False):
        parts = []
        include_tree = True
        if selected_only:
            include_tree = bool(
                hasattr(self, "include_context_tree_var") and self.include_context_tree_var.get()
            )
        tree = self.file_tree_structure(selected_only=selected_only) if include_tree else ""
        if tree:
            parts.append(
                "===== File Tree Structure =====\n"
                f"Timestamp: {self.display_timestamp(self.current_timestamp())}\n\n"
                f"{tree}"
            )
        for snippet in self.snippets_for_context(selected_only=selected_only):
            self.ensure_created_at(snippet)
            snippet_text = snippet["text"].strip()
            if not snippet_text:
                continue
            timestamp_lines = [f"Timestamp: {self.display_timestamp(snippet.get('created_at'))}"]
            if snippet.get("updated_at"):
                timestamp_lines.append(f"Edited: {self.display_timestamp(snippet.get('updated_at'))}")
            timestamp_text = "\n".join(timestamp_lines)
            title = "Card" if snippet.get("card_type") == "card" else self._relative(snippet["source"])
            parts.append(
                f"===== {title} =====\n"
                f"{timestamp_text}\n\n"
                f"{snippet_text}"
            )
        return "\n\n".join(parts)

    def exclude_repolens_generated_context_enabled(self):
        return bool(
            hasattr(self, "exclude_repolens_generated_context_var")
            and self.exclude_repolens_generated_context_var.get()
        )

    def snippets_for_context(self, selected_only=False):
        if not selected_only:
            return list(self.snippets)
        snippets = [snippet for snippet in self.snippets if snippet.get("selected", False)]
        if self.exclude_repolens_generated_context_enabled():
            snippets = [snippet for snippet in snippets if not snippet.get("generated_context", False)]
        return snippets

    def file_tree_structure(self, selected_only=False):
        paths = sorted(
            {
                self._relative(snippet["source"])
                for snippet in self.snippets_for_context(selected_only)
                if snippet.get("card_type") != "card"
            }
        )
        if not paths:
            return ""

        tree = {}
        for path in paths:
            normalized = path.replace("\\", "/")
            parts = [part for part in normalized.split("/") if part and part != "."]
            node = tree
            for part in parts:
                node = node.setdefault(part, {})

        lines = [self.root_folder.name if self.root_folder else "."]
        self._append_tree_lines(tree, lines, "")
        return "\n".join(lines)

    def _append_tree_lines(self, node, lines, prefix):
        items = sorted(node.items(), key=lambda item: (not bool(item[1]), item[0].lower()))
        for index, (name, children) in enumerate(items):
            is_last = index == len(items) - 1
            connector = "`-- " if is_last else "|-- "
            lines.append(f"{prefix}{connector}{name}")
            if children:
                child_prefix = "    " if is_last else "|   "
                self._append_tree_lines(children, lines, prefix + child_prefix)

    def refresh_context_tree(self):
        if not hasattr(self, "context_tree_text"):
            return
        tree = self.file_tree_structure() or "(no snippet references yet)"
        if hasattr(self, "context_tree_timestamp_label"):
            self.context_tree_timestamp_label.configure(
                text=f"Updated {self.display_timestamp(self.current_timestamp())}"
            )
        self.context_tree_text.configure(state=tk.NORMAL)
        self.context_tree_text.delete("1.0", tk.END)
        self.context_tree_text.insert("1.0", tree)
        self.context_tree_text.configure(state=tk.DISABLED)

    def estimate_llama_tokens(self, text):
        if not text:
            return 0

        token_count = 1
        token_pattern = re.compile(
            r"[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?|==|!=|<=|>=|->|=>|::|&&|\|\||"
            r"\+\+|--|[^\sA-Za-z_0-9]",
            re.UNICODE,
        )

        for match in token_pattern.finditer(text):
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

    def refresh_token_count(self):
        if not hasattr(self, "token_count_label"):
            return
        self.refresh_context_tree()
        if hasattr(self, "context_quality"):
            self.refresh_context_budget_state(stage="Draft")
            return
        count = self.estimate_llama_tokens(self.current_token_count_text())
        self.token_count_label.configure(text=f"~{count:,} tokens")

    def current_token_count_text(self):
        return self.assemble_context_preview_text(include_retrieval_preview=True)


    def _relative(self, path):
        path = Path(path)
        if self.root_folder:
            try:
                return os.fspath(path.relative_to(self.root_folder))
            except ValueError:
                pass
        return os.fspath(path)
