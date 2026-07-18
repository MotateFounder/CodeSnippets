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
from src.services.openRouterAPI import (
    openrouter_error_message,
    stream_openrouter_chat,
)
from src.services.repoLens.service import (
    RepoLensService,
    context_item_count,
    extract_symbols_from_snippet,
    format_repolens_context,
)
from src.services.chat_intents import (
    chat_intent_for_message,
    find_mention_tokens,
    snippet_mention_slug,
    strip_slash_command,
)
from src.services import thinkingProcess
from src.services.thinkingProcess import format_reasoning_trace, run_thinking_process
from src.ui.heat_bar import HeatBar


class ChatApiMixin:
    def send_chat_message(self):
        set_context_enabled = self.set_context_enabled()
        raw_message = self.chat_input_text().strip()
        if set_context_enabled:
            file_references = self.chat_file_references(raw_message)
            display_message = self.shortened_chat_file_reference_message(raw_message, file_references)
            message = strip_slash_command(display_message).strip()
            prompt_message = self.chat_prompt_message_with_file_references(message, file_references)
        else:
            file_references = []
            display_message = raw_message
            message = raw_message
            prompt_message = raw_message
        if not message:
            self.update_chat_input_placeholder("Write a chat message before sending.")
            self.status.configure(text="Write a chat message before sending.")
            return

        intent = chat_intent_for_message(raw_message)
        context = ""
        if set_context_enabled:
            mention_context = self.formatted_mentioned_snippets(raw_message)
            context = self.formatted_snippets_for_set_context(selected_only=True, include_cards=False)
            if mention_context:
                context = "\n\n".join(part for part in [mention_context, context] if part.strip())
            file_context = self.formatted_chat_file_reference_context(file_references)
            if file_context:
                context = "\n\n".join(part for part in [context, file_context] if part.strip())
            if not bool(self.get_setting("context.include_selected_snippets", True)):
                context = "\n\n".join(part for part in [mention_context, file_context] if part.strip())
            self.refresh_context_budget_state(
                context_text=context,
                user_message=prompt_message,
                stage="Before retrieval",
            )
        has_context = bool(context.strip())
        reasoning_enabled = bool(
            set_context_enabled
            and hasattr(self, "reasoning_enabled_var")
            and self.reasoning_enabled_var.get()
        )
        snippet_snapshots = []
        repolens_snapshots = []
        if set_context_enabled:
            snippet_snapshots = [
                self._context_retrieval_snapshot(snippet)
                for snippet in self.snippets_for_context(selected_only=True)
                if not snippet.get("generated_context") and snippet.get("card_type") != "card"
            ]
            snippet_snapshots.extend(self.chat_file_reference_retrieval_snapshots(file_references))
            repolens_snapshots = self.repolens_chat_snapshots(raw_message, file_references=file_references)
            dialog_result = self.open_set_context_dialog(
                raw_message=raw_message,
                prompt_message=prompt_message,
                display_message=display_message,
                context=context,
                snippet_snapshots=snippet_snapshots,
                repolens_snapshots=repolens_snapshots,
                intent=intent,
            )
            if not dialog_result:
                self.status.configure(text="Send cancelled.")
                return
            if dialog_result.get("action") == "copy":
                self.clipboard_clear()
                self.clipboard_append(dialog_result.get("prompt", ""))
                self.status.configure(text="Context prompt copied to clipboard.")
                return
            prompt_message = dialog_result.get("task_text", prompt_message)
            display_message = prompt_message
            message = strip_slash_command(display_message).strip()
            raw_message = prompt_message
            context = dialog_result.get("context", context)
            reasoning_enabled = bool(dialog_result.get("reasoning_enabled", False))
            snippet_snapshots = dialog_result.get("snippet_snapshots", snippet_snapshots)
            repolens_snapshots = dialog_result.get("repolens_snapshots", repolens_snapshots)
            context_options = dialog_result.get("options", {})
            reasoning_prompts = dialog_result.get("reasoning_prompts", {})
        else:
            context_options = None
            reasoning_prompts = {}

        try:
            api_target = self.normalized_chat_endpoint()
        except ValueError as exc:
            self.update_chat_input_placeholder(str(exc))
            self.status.configure(text=str(exc))
            return
        root_folder = self.root_folder
        thread_index = self.current_chat_index
        history_messages = self.sanitized_chat_messages(self.chat_threads[thread_index]["messages"])
        request_id = self.next_llm_request_id("chat")

        self.chat_input.delete("1.0", tk.END)
        visible_user_message = {
            "role": "user",
            "content": display_message,
            "prompt_content": prompt_message,
            "created_at": self.current_timestamp(),
            "intent": intent,
            "request_id": request_id,
        }
        self.chat_threads[thread_index]["messages"].append(visible_user_message)
        self.chat_messages = self.chat_threads[self.current_chat_index]["messages"]
        self._append_chat_card("user", display_message, message=visible_user_message)
        self.update_current_thread_title(user_message=display_message, thread_index=thread_index)
        self.refresh_chat_thread_selector()
        if has_context:
            selected_count = len(self.snippets_for_context(selected_only=True))
            self.update_chat_input_placeholder(
                f"Sending as {intent['label']} with {selected_count} selected snippet(s) attached..."
            )
        else:
            self.update_chat_input_placeholder(f"Sending as {intent['label']} without snippet context...")
        if reasoning_enabled:
            self._start_reasoning_card()
        self._start_streaming_assistant_card(request_id=request_id, thread_index=thread_index)
        self.send_chat_button.configure(state=tk.NORMAL)
        if api_target == "openrouter":
            self.status.configure(text="Sending message to OpenRouter...")
        else:
            self.status.configure(text="Sending message to local LLM API...")

        self.llm_queue.submit(
            query=display_message,
            target_id=request_id,
            request_type="chat",
            model_key=api_target,
            restartable=False,
            worker=lambda request: self._send_chat_request(
                api_target,
                visible_user_message,
                context,
                reasoning_enabled,
                snippet_snapshots,
                root_folder,
                intent,
                prompt_message,
                repolens_snapshots,
                thread_index,
                request_id,
                history_messages,
                set_context_enabled,
                context_options if set_context_enabled else None,
                reasoning_prompts if reasoning_enabled else None,
                queue_request=request,
            ),
        )

    def set_context_enabled(self):
        return bool(
            not hasattr(self, "set_context_enabled_var")
            or self.set_context_enabled_var.get()
        )

    def open_set_context_dialog(
        self,
        raw_message="",
        prompt_message="",
        display_message="",
        context="",
        snippet_snapshots=None,
        repolens_snapshots=None,
        intent=None,
    ):
        dialog = tk.Toplevel(self)
        dialog.title("Set context")
        dialog.transient(self)
        dialog.resizable(True, True)
        dialog.configure(bg=self.colors["bg"])
        result = {"value": None}
        snippet_snapshots = list(snippet_snapshots or [])
        repolens_snapshots = list(repolens_snapshots or [])
        symbol_vars = self.default_set_context_symbol_vars(repolens_snapshots, raw_message)
        enable_reasoning_var = tk.BooleanVar(value=bool(self.get_setting("reasoning.enabled_by_default", False)))
        reasoning_var = tk.BooleanVar(value=False)
        metadata_vars = {
            "reduced_file_tree": tk.BooleanVar(value=True),
            "chat_history": tk.BooleanVar(value=True),
            "reasoning_artifacts": tk.BooleanVar(value=False),
        }
        option_vars = self.default_repolens_option_vars(intent)
        depth_var = tk.IntVar(value=self.repolens_depth_for_intent(intent, fallback=1))
        manual_card_vars = self.default_manual_card_vars()
        retrieved_state = {"key": None, "text": "", "error": "", "files": [], "file_vars": {}}
        reasoning_steps = self.default_reasoning_steps()
        improve_state = {
            "mode": "original",
            "cached_original": None,
            "cached_improved": None,
            "in_progress": False,
        }

        header = ttk.Frame(dialog, padding=(16, 14, 16, 8))
        header.pack(fill=tk.X)
        header_text = ttk.Frame(header)
        header_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(header_text, text="Set Context", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(header_text, text="Review and refine the context before sending").pack(anchor="w")
        header_metrics = ttk.Frame(header)
        header_metrics.pack(side=tk.RIGHT, padx=(16, 0))
        header_token_label = ttk.Label(header_metrics, text="")
        header_token_label.pack(anchor="e", pady=(0, 4))
        header_heat_bar = HeatBar(header_metrics, length=260, value=0.0)
        header_heat_bar.pack(anchor="e")

        shell = ttk.Frame(dialog, padding=(16, 0, 16, 0))
        shell.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(
            shell,
            bg=self.colors["panel"],
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
        )
        scroll = ttk.Scrollbar(shell, orient=tk.VERTICAL, command=canvas.yview)
        content = ttk.Frame(canvas, padding=12)
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._set_context_section_label(content, "1", "Task")
        task_row = ttk.Frame(content)
        task_row.pack(fill=tk.X, pady=(2, 12))
        task_text = tk.Text(
            task_row,
            height=4,
            wrap=tk.WORD,
            font=("Segoe UI", 10),
            bg=self.colors["editor"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            selectbackground=self.colors["select"],
            selectforeground="#ffffff",
            highlightbackground=self.colors["line"],
        )
        task_text.insert("1.0", raw_message)
        task_text.edit_modified(False)
        task_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        improve_button = ttk.Button(task_row, text="Improve prompt")
        improve_button.pack(side=tk.RIGHT, padx=(8, 0), anchor="n")

        def current_task_text():
            return task_text.get("1.0", "end-1c")

        def replace_task_text(value):
            task_text.delete("1.0", tk.END)
            task_text.insert("1.0", value)

        def refresh_improve_button_label():
            if improve_state["in_progress"]:
                return
            current = current_task_text()
            if improve_state["mode"] == "improved":
                improve_button.configure(text="Get the old prompt")
            elif (
                improve_state.get("cached_original") == current
                and improve_state.get("cached_improved") is not None
            ):
                improve_button.configure(text="Get the new prompt")
            else:
                improve_button.configure(text="Improve prompt")

        def on_task_text_changed(_event=None):
            if task_text.edit_modified():
                task_text.edit_modified(False)
                if improve_state["mode"] == "improved":
                    improve_state["mode"] = "original"
                refresh_improve_button_label()

        task_text.bind("<<Modified>>", on_task_text_changed)

        def finish_improvement(original, improved=None, error=None):
            improve_state["in_progress"] = False
            try:
                dialog.lift()
                dialog.focus_force()
            except tk.TclError:
                pass
            if error or not str(improved or "").strip():
                improve_button.configure(text="Improve prompt", state=tk.NORMAL)
                messagebox.showerror("Prompt improvement failed", str(error or "The LLM returned an empty improved prompt."))
                return
            improve_state["cached_original"] = original
            improve_state["cached_improved"] = str(improved)
            improve_state["mode"] = "improved"
            replace_task_text(str(improved))
            task_text.edit_modified(False)
            improve_button.configure(state=tk.NORMAL)
            refresh_improve_button_label()

        def request_improved_prompt(original):
            try:
                endpoint = self.normalized_chat_endpoint()
                self.focus_llamacpp_terminal_window()
                improved = self._call_chat_once(
                    endpoint,
                    [
                        {
                            "role": "user",
                            "content": self.prompt_improvement_template(original),
                        }
                    ],
                )
                self.post_ui(lambda value=improved: finish_improvement(original, improved=value))
            except Exception as exc:
                self.post_ui(lambda error=str(exc): finish_improvement(original, error=error))

        def toggle_prompt_improvement():
            if improve_state["in_progress"]:
                return
            if improve_state["mode"] == "improved":
                cached_original = improve_state.get("cached_original")
                if cached_original is not None:
                    replace_task_text(cached_original)
                improve_state["mode"] = "original"
                task_text.edit_modified(False)
                refresh_improve_button_label()
                return
            original = current_task_text()
            if (
                improve_state.get("cached_original") == original
                and improve_state.get("cached_improved") is not None
            ):
                replace_task_text(improve_state["cached_improved"])
                improve_state["mode"] = "improved"
                task_text.edit_modified(False)
                refresh_improve_button_label()
                return
            improve_state["in_progress"] = True
            improve_button.configure(state=tk.DISABLED)
            threading.Thread(target=lambda value=original: request_improved_prompt(value), daemon=True).start()

        improve_button.configure(command=toggle_prompt_improvement)

        self._set_context_section_label(content, "2", "Reasoning")
        enable_reasoning_check = tk.Checkbutton(
            content,
            text="Enable reasoning",
            variable=enable_reasoning_var,
            bg=self.colors["panel"],
            fg=self.colors["text"],
            activebackground=self.colors["panel"],
            selectcolor=self.colors["editor"],
            borderwidth=0,
            anchor="w",
        )
        enable_reasoning_check.pack(fill=tk.X)
        reasoning_check = tk.Checkbutton(
            content,
            text="Include reasoning steps (See below when enabled)",
            variable=reasoning_var,
            bg=self.colors["panel"],
            fg=self.colors["text"],
            activebackground=self.colors["panel"],
            selectcolor=self.colors["editor"],
            borderwidth=0,
            anchor="w",
        )
        reasoning_check.pack(fill=tk.X, pady=(2, 0))
        reasoning_cards = ttk.Frame(content)
        reasoning_cards.pack_forget()

        def render_reasoning_cards():
            for child in reasoning_cards.winfo_children():
                child.destroy()
            ttk.Label(
                reasoning_cards,
                text="Reasoning steps",
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w", pady=(0, 6))
            for index, step in enumerate(reasoning_steps, start=1):
                card = tk.Frame(
                    reasoning_cards,
                    bg=self.colors["panel2"],
                    highlightbackground=self.colors["line"],
                    highlightthickness=1,
                )
                card.pack(fill=tk.X, pady=(0, 8))
                header_row = tk.Frame(card, bg=self.colors["panel2"])
                header_row.pack(fill=tk.X, padx=8, pady=(6, 4))
                tk.Label(
                    header_row,
                    text="{0}. {1}".format(index, step.get("title", "Reasoning step")),
                    bg=self.colors["panel2"],
                    fg=self.colors["text"],
                    font=("Segoe UI", 9, "bold"),
                    anchor="w",
                ).pack(side=tk.LEFT, fill=tk.X, expand=True)

                def remove_step(value=step):
                    if value in reasoning_steps:
                        reasoning_steps.remove(value)
                    render_reasoning_cards()

                ttk.Button(header_row, text="Remove", command=remove_step).pack(side=tk.RIGHT)
                prompt_text = tk.Text(
                    card,
                    height=5,
                    wrap=tk.WORD,
                    bg=self.colors["editor"],
                    fg=self.colors["text"],
                    insertbackground=self.colors["text"],
                    selectbackground=self.colors["select"],
                    selectforeground="#ffffff",
                    highlightbackground=self.colors["line"],
                    font=("Segoe UI", 9),
                    padx=8,
                    pady=6,
                )
                prompt_text.insert("1.0", step.get("prompt", ""))
                prompt_text.pack(fill=tk.X, padx=8, pady=(0, 8))
                step["widget"] = prompt_text
            add_row = ttk.Frame(reasoning_cards)
            add_row.pack(fill=tk.X, pady=(0, 4))

            def add_step():
                reasoning_steps.append(
                    {
                        "key": "custom_{0}".format(len(reasoning_steps) + 1),
                        "title": "Custom reasoning step",
                        "prompt": "",
                        "custom": True,
                    }
                )
                render_reasoning_cards()

            ttk.Button(add_row, text="Add new card", command=add_step).pack(side=tk.LEFT)

        render_reasoning_cards()

        def sync_enable_reasoning_setting(*_args):
            enabled = bool(enable_reasoning_var.get())
            self.set_nested_setting(self.settings, "reasoning.enabled_by_default", enabled)
            if hasattr(self, "reasoning_enabled_var"):
                self.reasoning_enabled_var.set(enabled)
            try:
                self.save_settings_file()
            except Exception:
                try:
                    self.save_settings_profiles()
                except Exception:
                    pass
            if not enabled:
                reasoning_var.set(False)
                reasoning_check.configure(state=tk.DISABLED)
                reasoning_cards.pack_forget()
            else:
                reasoning_check.configure(state=tk.NORMAL)

        def toggle_reasoning_cards(*_args):
            if enable_reasoning_var.get() and reasoning_var.get():
                reasoning_cards.pack(fill=tk.X, pady=(8, 12), after=reasoning_check)
            else:
                reasoning_cards.pack_forget()

        enable_reasoning_var.trace_add("write", sync_enable_reasoning_setting)
        reasoning_var.trace_add("write", toggle_reasoning_cards)
        sync_enable_reasoning_setting()

        self._set_context_section_label(content, "3", "Code snippets")
        summary = "{0} selected snippet(s) for RepoLens".format(len(repolens_snapshots))
        ttk.Label(content, text=summary).pack(anchor="w")
        symbol_box = ttk.Frame(content, padding=8)
        symbol_box.pack(fill=tk.X, pady=(6, 8))
        if symbol_vars:
            for index, item in enumerate(symbol_vars):
                check = tk.Checkbutton(
                    symbol_box,
                    text=item["symbol"],
                    variable=item["var"],
                    bg=self.colors["panel"],
                    fg=self.colors["text"],
                    activebackground=self.colors["panel"],
                    selectcolor=self.colors["editor"],
                    borderwidth=0,
                    anchor="w",
                )
                check.grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 20), pady=2)
        else:
            ttk.Label(symbol_box, text="No symbol candidates detected.").grid(row=0, column=0, sticky="w")
        self._set_context_section_label(content, "4", "Manual cards")
        manual_box = ttk.Frame(content, padding=8)
        manual_box.pack(fill=tk.X, pady=(6, 12))
        if manual_card_vars:
            for index, item in enumerate(manual_card_vars):
                tk.Checkbutton(
                    manual_box,
                    text=item["label"],
                    variable=item["var"],
                    bg=self.colors["panel"],
                    fg=self.colors["text"],
                    activebackground=self.colors["panel"],
                    selectcolor=self.colors["editor"],
                    borderwidth=0,
                    anchor="w",
                ).grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 24), pady=2)
        else:
            ttk.Label(manual_box, text="No manual cards in the active clipboard.").grid(row=0, column=0, sticky="w")

        self._set_context_section_label(content, "5", "RepoLens options")
        mode_label = ttk.Label(content, text="Current mode from settings: {0}".format(self.current_context_mode()))
        mode_label.pack(anchor="w")
        depth_row = ttk.Frame(content)
        depth_row.pack(fill=tk.X, pady=(6, 2))
        ttk.Label(depth_row, text="Depth").pack(side=tk.LEFT)
        tk.Spinbox(
            depth_row,
            from_=0,
            to=8,
            width=5,
            textvariable=depth_var,
            bg=self.colors["editor"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            buttonbackground=self.colors["panel2"],
        ).pack(side=tk.LEFT, padx=(8, 0))
        option_area = ttk.Frame(content)
        option_area.pack(fill=tk.X, pady=(6, 12))
        left = ttk.LabelFrame(option_area, text="Essential and in-depth")
        right = ttk.LabelFrame(option_area, text="Additional and exploratory")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        for option in option_vars:
            parent = left if option.get("tier") == "essential" else right
            tk.Checkbutton(
                parent,
                text=option["label"],
                variable=option["var"],
                bg=self.colors["panel"],
                fg=self.colors["text"],
                activebackground=self.colors["panel"],
                selectcolor=self.colors["editor"],
                borderwidth=0,
                anchor="w",
            ).pack(fill=tk.X, padx=6, pady=2)

        self._set_context_section_label(content, "6", "Metadata options")
        metadata_row = ttk.Frame(content)
        metadata_row.pack(fill=tk.X, pady=(2, 12))
        for label, key in (
            ("Reduced file tree", "reduced_file_tree"),
            ("Chat history in this thread", "chat_history"),
            ("Reasoning artifacts when included", "reasoning_artifacts"),
        ):
            tk.Checkbutton(
                metadata_row,
                text=label,
                variable=metadata_vars[key],
                bg=self.colors["panel"],
                fg=self.colors["text"],
                activebackground=self.colors["panel"],
                selectcolor=self.colors["editor"],
                borderwidth=0,
                anchor="w",
            ).pack(side=tk.LEFT, padx=(0, 18))

        self._set_context_section_label(content, "7", "Inspect Context")
        inspect_frame = ttk.Frame(content)
        inspect_frame.pack(fill=tk.X, pady=(0, 8))
        inspect_button = ttk.Button(inspect_frame, text="Inspect Context")
        inspect_button.pack(side=tk.LEFT)
        inspector_frame = ttk.LabelFrame(content, text="Context Inspector")
        inspector_text = tk.Text(
            inspector_frame,
            height=1,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg=self.colors["editor"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            selectbackground=self.colors["select"],
            selectforeground="#ffffff",
            highlightbackground=self.colors["line"],
        )
        inspector_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        repolens_tree_frame = ttk.LabelFrame(content, text="RepoLens Retrieved Files")
        repolens_tree_body = ttk.Frame(repolens_tree_frame, padding=8)
        repolens_tree_body.pack(fill=tk.X)

        actions = ttk.Frame(dialog, padding=16)
        actions.pack(fill=tk.X)
        copy_button = ttk.Button(actions, text="Copy to Clipboard", state=tk.DISABLED)
        send_button = ttk.Button(actions, text="Send Message", style="Accent.TButton", state=tk.DISABLED)

        def selected_options():
            values = {option["key"]: option["var"].get() for option in option_vars}
            try:
                depth = int(depth_var.get() or 0)
            except (TypeError, ValueError, tk.TclError):
                depth = 0
            values["depth"] = max(0, depth)
            return values

        def selected_symbols():
            return [item["symbol"] for item in symbol_vars if item["var"].get()]

        def selected_manual_cards():
            return [item["snippet"] for item in manual_card_vars if item["var"].get()]

        def selected_repolens_files():
            file_vars = retrieved_state.get("file_vars") or {}
            if not file_vars:
                return list(retrieved_state.get("files") or [])
            selected = [
                path
                for path, data in file_vars.items()
                if data.get("kind") == "file" and data.get("var").get()
            ]
            return selected

        def rebuild_repolens_file_tree():
            for child in repolens_tree_body.winfo_children():
                child.destroy()
            retrieved_state["file_vars"] = {}
            files = list(retrieved_state.get("files") or [])
            if not files:
                ttk.Label(repolens_tree_body, text="No RepoLens files were retrieved.").pack(anchor="w")
            else:
                self.build_repolens_file_checkbox_tree(
                    repolens_tree_body,
                    files,
                    retrieved_state["file_vars"],
                )
            if not repolens_tree_frame.winfo_manager():
                repolens_tree_frame.pack(fill=tk.X, pady=(0, 12))

        def selected_context_data(include_repolens=True):
            task_value = current_task_text()
            symbols = selected_symbols()
            selected_repolens = self.filter_repolens_snapshots_for_symbols(repolens_snapshots, symbols)
            selected_snippets = self.filter_repolens_snapshots_for_symbols(snippet_snapshots, symbols)
            options = selected_options()
            repolens_text = ""
            if include_repolens and selected_repolens:
                key = self.set_context_retrieval_key(selected_repolens, options, task_value)
                if retrieved_state["key"] != key:
                    retrieved_state["key"] = key
                    retrieved_state["error"] = ""
                    retrieved_state["text"] = ""
                    retrieved_state["files"] = []
                    try:
                        retrieval_depth = int(options.get("depth", 1) or 0)
                        if not options.get("direct_dependencies", True):
                            retrieval_depth = 0
                        if options.get("trace_relationships", False):
                            retrieval_depth = max(retrieval_depth, 2)
                        retrieved = self.retrieve_repolens_context_for_snippets(
                            selected_repolens,
                            user_message=task_value,
                            depth=retrieval_depth,
                            update_before=bool(options.get("refresh_index", False)),
                            update_lite=not bool(options.get("large_repo_optimization", False)),
                            retrieval_options=options,
                        )
                        retrieved_state["text"] = str(retrieved.get("text", "") or "").strip()
                        retrieved_state["files"] = self.repolens_files_from_context_text(retrieved_state["text"])
                    except Exception as exc:
                        retrieved_state["error"] = str(exc)
                selected_files = selected_repolens_files()
                repolens_text = self.filter_repolens_context_text(retrieved_state["text"], selected_files)
            else:
                selected_files = []
            assembled = self.assemble_context_from_dialog(
                base_context=context,
                metadata={key: var.get() for key, var in metadata_vars.items()},
                manual_cards=selected_manual_cards(),
                repolens_text=repolens_text,
                repolens_error=retrieved_state["error"],
                repolens_files=selected_files,
            )
            return assembled, selected_snippets, selected_repolens

        def inspect():
            inspect_button.configure(state=tk.DISABLED)
            dialog.update_idletasks()
            selected_context_data(include_repolens=True)
            rebuild_repolens_file_tree()
            assembled, _selected_snippets, _selected_repolens = selected_context_data(include_repolens=True)
            report = self.context_budgeter().evaluate(
                context_text=assembled,
                user_message=current_task_text(),
                settings=getattr(self, "settings", {}),
                stage="Manual inspection",
            )
            score = self.context_quality_score_from_report(report)
            header_heat_bar.set_value(score)
            header_token_label.configure(
                text="Quality {0}/100 | ~{1:,}/{2:,} tokens".format(
                    int(round(score * 100)),
                    int(report.get("total_tokens", 0) or 0),
                    int(report.get("available_prompt_tokens", 0) or 0),
                )
            )
            inspector_text.configure(state=tk.NORMAL)
            inspector_text.delete("1.0", tk.END)
            inspector_value = self.format_set_context_inspector(report, repolens_files=selected_repolens_files())
            inspector_text.insert("1.0", inspector_value)
            inspector_text.configure(height=max(1, inspector_value.count("\n") + 1))
            inspector_text.configure(state=tk.DISABLED)
            if not inspector_frame.winfo_manager():
                inspector_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 12))
            copy_button.configure(state=tk.NORMAL)
            send_button.configure(state=tk.NORMAL)
            inspect_button.configure(state=tk.NORMAL)

        def final_prompt():
            assembled, _selected_snippets, _selected_repolens = selected_context_data(include_repolens=True)
            intent_header = self.format_chat_intent_for_prompt(intent)
            task_value = current_task_text()
            return (
                "{0}\n\n{1}\n\n{2}\n\nUser message:\n{3}".format(
                    self.get_setting("context.wrapper_prompt", ""),
                    intent_header,
                    assembled,
                    task_value,
                )
            ).strip()

        def do_copy():
            result["value"] = {"action": "copy", "prompt": final_prompt()}
            dialog.destroy()

        def do_send():
            assembled, selected_snippets, selected_repolens = selected_context_data(include_repolens=True)
            result["value"] = {
                "action": "send",
                "context": assembled,
                "reasoning_enabled": enable_reasoning_var.get(),
                "task_text": current_task_text(),
                "snippet_snapshots": selected_snippets,
                "repolens_snapshots": [],
                "options": selected_options(),
                "reasoning_prompts": self.reasoning_prompts_from_steps(reasoning_steps),
            }
            dialog.destroy()

        def cancel():
            result["value"] = None
            dialog.destroy()

        inspect_button.configure(command=inspect)
        ttk.Button(actions, text="Cancel", command=cancel).pack(side=tk.LEFT)
        send_button.configure(command=do_send)
        copy_button.configure(command=do_copy)
        send_button.pack(side=tk.RIGHT)
        copy_button.pack(side=tk.RIGHT, padx=(0, 8))

        dialog.protocol("WM_DELETE_WINDOW", cancel)
        dialog.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - dialog.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry("860x760+{0}+{1}".format(x, y))
        dialog.grab_set()
        dialog.wait_window()
        return result["value"]

    def _set_context_section_label(self, parent, number, text):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=(8, 4))
        tk.Label(
            row,
            text=number,
            bg=self.colors["accent"],
            fg="#ffffff",
            width=2,
            font=("Segoe UI", 8, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Label(row, text=text, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(8, 0))

    def default_set_context_symbol_vars(self, snapshots, raw_message):
        symbols = []
        for snippet in snapshots:
            for symbol in self._symbols_for_repolens_snippet(snippet, user_message=raw_message):
                if symbol not in symbols:
                    symbols.append(symbol)
        output = []
        for symbol in symbols[:36]:
            output.append({"symbol": symbol, "var": tk.BooleanVar(value=True)})
        return output

    def default_manual_card_vars(self):
        cards = []
        for index, snippet in enumerate(getattr(self, "snippets", []) or [], start=1):
            if snippet.get("card_type") != "card":
                continue
            label = str(snippet.get("description", "") or "").strip() or "Manual card {0}".format(index)
            cards.append(
                {
                    "label": label[:80],
                    "snippet": snippet,
                    "var": tk.BooleanVar(value=bool(snippet.get("selected", True))),
                }
            )
        return cards

    def default_reasoning_steps(self):
        defaults = [
            ("task_normalization", "Task normalization", thinkingProcess.TASK_NORMALIZATION_PROMPT),
            ("context_classification", "Context classification", thinkingProcess.CONTEXT_CLASSIFICATION_PROMPT),
            ("retrieval_planning", "Retrieval planning", thinkingProcess.RETRIEVAL_PLANNING_PROMPT),
            ("context_summarization", "Context summarization", thinkingProcess.CONTEXT_SUMMARIZATION_PROMPT),
            ("missing_context", "Missing context audit", thinkingProcess.MISSING_CONTEXT_PROMPT),
            ("constraint_extraction", "Constraint extraction", thinkingProcess.CONSTRAINT_EXTRACTION_PROMPT),
            ("architectural_minimization", "Architectural minimization", thinkingProcess.ARCHITECTURAL_MINIMIZATION_PROMPT),
            ("final_synthesis_rules", "Final synthesis rules", thinkingProcess.DEFAULT_FINAL_SYNTHESIS_RULES),
        ]
        steps = []
        for key, title, default in defaults:
            steps.append(
                {
                    "key": key,
                    "title": title,
                    "prompt": self.get_setting("prompts.{0}".format(key), default),
                    "custom": False,
                }
            )
        return steps

    def reasoning_prompts_from_steps(self, steps):
        prompts = {}
        for step in steps or []:
            widget = step.get("widget")
            text = step.get("prompt", "")
            if widget is not None:
                try:
                    text = widget.get("1.0", "end-1c")
                except tk.TclError:
                    text = step.get("prompt", "")
            key = str(step.get("key", "")).strip()
            if key and text.strip():
                prompts[key] = text.strip()
        return prompts

    def settings_with_reasoning_prompts(self, prompts):
        settings = json.loads(json.dumps(getattr(self, "settings", {}) or {}))
        settings["prompts"] = dict(prompts or {})
        reasoning_settings = dict(settings.get("reasoning", {}) or {})
        reasoning_settings["enabled_steps"] = list((prompts or {}).keys())
        settings["reasoning"] = reasoning_settings
        return settings

    def prompt_improvement_template(self, original_prompt):
        return (
            "Original prompt:\n"
            "\"{0}\"\n\n"
            "Requirements:\n"
            "- Clarify the task, inputs, and expected output.\n"
            "- Specify programming language, libraries, and constraints when relevant.\n"
            "- Define edge cases and error handling when applicable.\n"
            "- Ensure the output format is explicit (e.g., code only, explanation + code, tests).\n"
            "- Preserve all special tokens and references exactly as written (e.g., slash commands like /explain, @references, placeholders, or variables). Do not remove, rename, or reinterpret any special tokens; keep them verbatim.\n"
            "- Output only the improved prompt."
        ).format(str(original_prompt))

    def focus_llamacpp_terminal_window(self):
        process = getattr(self, "llamacpp_process", None)
        pid = getattr(process, "pid", None)
        if not pid or os.name != "nt":
            return False
        try:
            import ctypes

            user32 = ctypes.windll.user32
            handles = []

            def callback(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                window_pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
                if int(window_pid.value) == int(pid):
                    handles.append(hwnd)
                    return False
                return True

            enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(callback)
            user32.EnumWindows(enum_proc, 0)
            if not handles:
                return False
            user32.ShowWindow(handles[0], 5)
            user32.SetForegroundWindow(handles[0])
            return True
        except Exception:
            return False

    def default_repolens_option_vars(self, intent):
        depth = self.repolens_depth_for_intent(intent, fallback=1)
        mode = self.current_context_mode()
        essential_defaults = {
            "exact_symbol": True,
            "compact_structure": depth <= 1 or mode in {"Lean", "Balanced"},
            "resolve_symbols": True,
            "situated": depth >= 1,
            "direct_dependencies": depth >= 1,
            "trace_relationships": depth >= 2 or mode in {"Deep", "Exhaustive"},
            "refresh_index": bool(self.get_setting("repolens.chat.update_before_retrieval", False)),
            "quality_report": depth >= 2,
            "external_indexers": mode in {"Deep", "Exhaustive"},
        }
        extra_defaults = {
            "signals": mode == "Exhaustive",
            "impact": mode in {"Deep", "Exhaustive"},
            "architecture_hubs": mode == "Exhaustive",
            "architecture_communities": mode == "Exhaustive",
            "large_repo_optimization": mode == "Exhaustive",
            "symbol_descriptions": False,
        }
        rows = [
            ("exact_symbol", "Fetch only the exact symbols I checked", "essential"),
            ("compact_structure", "Show a compact structural view", "essential"),
            ("resolve_symbols", "Find concrete symbol definitions", "essential"),
            ("situated", "Explain where snippets fit in their files", "essential"),
            ("direct_dependencies", "Expand direct dependencies", "essential"),
            ("trace_relationships", "Trace callers and callees with high confidence", "essential"),
            ("refresh_index", "Refresh the index safely in the background", "essential"),
            ("quality_report", "Generate code health and grounding facts", "essential"),
            ("external_indexers", "Use more accurate external indexers when available", "essential"),
            ("signals", "Include logs, notes, and terminal output", "extra"),
            ("impact", "Show ripple effects of a change", "extra"),
            ("architecture_hubs", "Highlight important architecture hubs", "extra"),
            ("architecture_communities", "Group the repo into functional areas", "extra"),
            ("large_repo_optimization", "Optimize indexing for very large repositories", "extra"),
            ("symbol_descriptions", "Add AI-generated descriptions for symbols", "extra"),
        ]
        options = []
        for key, label, tier in rows:
            default = essential_defaults.get(key, extra_defaults.get(key, False))
            options.append({"key": key, "label": label, "tier": tier, "var": tk.BooleanVar(value=default)})
        return options

    def current_context_mode(self):
        return str(self.get_setting("context.retrieval_mode", "Balanced") or "Balanced")

    def filter_repolens_snapshots_for_symbols(self, snapshots, symbols):
        symbol_set = {str(symbol).strip() for symbol in symbols if str(symbol).strip()}
        if not symbol_set:
            return []
        filtered = []
        for snapshot in snapshots or []:
            item = dict(snapshot)
            item["repolens_symbols"] = list(symbol_set)
            filtered.append(item)
        return filtered

    def set_context_retrieval_key(self, snapshots, options, raw_message):
        symbols = []
        for snapshot in snapshots or []:
            for symbol in snapshot.get("repolens_symbols", []):
                if symbol not in symbols:
                    symbols.append(symbol)
        option_items = sorted((str(key), str(value)) for key, value in (options or {}).items())
        return json.dumps(
            {"symbols": symbols, "options": option_items, "message": raw_message},
            sort_keys=True,
        )

    def repolens_files_from_context_text(self, text):
        files = []
        for line in str(text or "").splitlines():
            value = line.strip()
            if not value.lower().startswith("file:"):
                continue
            path = value.split(":", 1)[1].strip()
            if path and path not in files:
                files.append(path)
        return files

    def filter_repolens_context_text(self, text, selected_files):
        raw = str(text or "")
        selected = {str(path).replace("\\", "/") for path in selected_files or []}
        if not raw.strip() or not selected:
            return "" if raw.strip() else raw

        def keep_block(match):
            block = match.group(0)
            files = self.repolens_files_from_context_text(block)
            if not files:
                return block
            for file_path in files:
                if file_path.replace("\\", "/") in selected:
                    return block
            return ""

        return re.sub(
            r"<related_context>.*?</related_context>",
            keep_block,
            raw,
            flags=re.DOTALL,
        ).strip()

    def build_repolens_file_checkbox_tree(self, parent, files, file_vars):
        normalized_files = []
        for file_path in files:
            value = str(file_path or "").replace("\\", "/").strip()
            if value and value not in normalized_files:
                normalized_files.append(value)
        root_name = self.root_folder.name if self.root_folder else "."
        tree = {}
        for file_path in normalized_files:
            parts = [part for part in file_path.split("/") if part and part != "."]
            node = tree
            for part in parts:
                node = node.setdefault(part, {})

        def set_descendants(path_key, value):
            if not path_key:
                for data in file_vars.values():
                    data["var"].set(value)
                return
            prefix = path_key + "/"
            for key, data in file_vars.items():
                if key == path_key or key.startswith(prefix):
                    data["var"].set(value)

        def add_node(name, children, depth, path_key):
            kind = "folder" if children else "file"
            var = tk.BooleanVar(value=True)
            file_vars[path_key] = {"var": var, "kind": kind}
            check = tk.Checkbutton(
                parent,
                text=name,
                variable=var,
                bg=self.colors["panel"],
                fg=self.colors["text"],
                activebackground=self.colors["panel"],
                activeforeground=self.colors["text"],
                selectcolor=self.colors["editor"],
                borderwidth=0,
                anchor="w",
                command=lambda key=path_key, value_var=var: set_descendants(key, value_var.get()),
            )
            check.pack(fill=tk.X, padx=(depth * 18, 0), anchor="w")
            for child_name, child_children in sorted(children.items(), key=lambda item: (not bool(item[1]), item[0].lower())):
                child_key = "{0}/{1}".format(path_key, child_name) if path_key else child_name
                add_node(child_name, child_children, depth + 1, child_key)

        root_var = tk.BooleanVar(value=True)
        file_vars[""] = {"var": root_var, "kind": "folder"}
        tk.Checkbutton(
            parent,
            text=root_name,
            variable=root_var,
            bg=self.colors["panel"],
            fg=self.colors["text"],
            activebackground=self.colors["panel"],
            activeforeground=self.colors["text"],
            selectcolor=self.colors["editor"],
            borderwidth=0,
            anchor="w",
            command=lambda: set_descendants("", root_var.get()),
        ).pack(fill=tk.X, anchor="w")
        for child_name, children in sorted(tree.items(), key=lambda item: (not bool(item[1]), item[0].lower())):
            add_node(child_name, children, 1, child_name)

    def set_context_reduced_file_tree(self, repolens_files=None):
        paths = []
        for snippet in self.snippets_for_context(selected_only=True):
            if snippet.get("card_type") == "card":
                continue
            source = snippet.get("source")
            if source:
                paths.append(source)
        for file_path in repolens_files or []:
            paths.append(file_path)
        return self.paths_as_reduced_tree(paths)

    def paths_as_reduced_tree(self, paths):
        relative_paths = []
        for raw_path in paths or []:
            path = Path(str(raw_path))
            try:
                if self.root_folder and path.is_absolute():
                    path = path.relative_to(self.root_folder)
            except ValueError:
                pass
            value = os.fspath(path).replace("\\", "/")
            if value and value not in relative_paths:
                relative_paths.append(value)
        if not relative_paths:
            return ""

        tree = {}
        for path in sorted(relative_paths, key=str.lower):
            parts = [part for part in path.split("/") if part and part != "."]
            node = tree
            for part in parts:
                node = node.setdefault(part, {})

        lines = [self.root_folder.name if self.root_folder else "."]
        self._append_tree_lines(tree, lines, "")
        return "\n".join(lines)

    def assemble_context_from_dialog(
        self,
        base_context,
        metadata,
        manual_cards=None,
        repolens_text="",
        repolens_error="",
        repolens_files=None,
    ):
        parts = [str(base_context or "").strip()]
        for index, snippet in enumerate(manual_cards or [], start=1):
            text = str(snippet.get("text", "") or "").strip()
            if text:
                title = str(snippet.get("description", "") or "").strip() or "Manual Card {0}".format(index)
                parts.append("===== Manual Card: {0} =====\n{1}".format(title, text))
        if str(repolens_text or "").strip():
            parts.append("===== RepoLens Retrieved Context =====\n{0}".format(str(repolens_text).strip()))
        if str(repolens_error or "").strip():
            parts.append("===== RepoLens Retrieval Warning =====\n{0}".format(str(repolens_error).strip()))
        if metadata.get("reduced_file_tree"):
            tree = self.set_context_reduced_file_tree(repolens_files or [])
            if tree:
                parts.append("===== Reduced File Tree =====\n{0}".format(tree))
        if metadata.get("chat_history"):
            messages = self.sanitized_chat_messages(self.chat_threads[self.current_chat_index]["messages"])
            if messages:
                history = "\n".join("{0}: {1}".format(item["role"], item["content"]) for item in messages[-12:])
                parts.append("===== Current Chat History =====\n{0}".format(history))
        return "\n\n".join(part for part in parts if part)

    def formatted_snippets_for_set_context(self, selected_only=False, include_cards=True):
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
                "Timestamp: {0}\n\n{1}".format(self.display_timestamp(self.current_timestamp()), tree)
            )
        for snippet in self.snippets_for_context(selected_only=selected_only):
            if not include_cards and snippet.get("card_type") == "card":
                continue
            self.ensure_created_at(snippet)
            snippet_text = snippet["text"].strip()
            if not snippet_text:
                continue
            timestamp_lines = ["Timestamp: {0}".format(self.display_timestamp(snippet.get("created_at")))]
            if snippet.get("updated_at"):
                timestamp_lines.append("Edited: {0}".format(self.display_timestamp(snippet.get("updated_at"))))
            title = "Card" if snippet.get("card_type") == "card" else self._relative(snippet["source"])
            parts.append(
                "===== {0} =====\n{1}\n\n{2}".format(
                    title,
                    "\n".join(timestamp_lines),
                    snippet_text,
                )
            )
        return "\n\n".join(parts)

    def context_quality_score_from_report(self, report):
        quality = report.get("quality", {}) if report else {}
        if not quality:
            return 0.0
        weights = self.CONTEXT_BUDGET_IMPORTANCES if hasattr(self, "CONTEXT_BUDGET_IMPORTANCES") else {}
        values = []
        total_weight = 0.0
        weight_map = {"low": 0.15, "mid": 0.35, "high": 0.50}
        for key, value in quality.items():
            weight = weight_map.get(weights.get(key, "mid"), 0.35)
            values.append(float(value) * weight)
            total_weight += weight
        return max(0.0, min(1.0, sum(values) / max(1.0, total_weight)))

    def format_set_context_inspector(self, report, repolens_files=None):
        quality = report.get("quality", {}) if report else {}
        lines = [
            "Task goal accuracy and precision: {0:.2f}".format(float(quality.get("task_clarity", quality.get("is_focused", 0.0)))),
            "Context completeness: {0:.2f}".format(float(quality.get("has_enough_context", 0.0))),
            "Token usage vs target: ~{0:,}/{1:,} prompt tokens".format(
                int(report.get("total_tokens", 0) or 0),
                int(report.get("available_prompt_tokens", 0) or 0),
            ),
            "Code integrity and grounding: sources {0:.2f}, duplication {1:.2f}, evidence {2:.2f}".format(
                float(quality.get("has_sources", 0.0)),
                float(quality.get("low_duplication", 0.0)),
                float(quality.get("has_evidence", 0.0)),
            ),
            "",
            "RepoLens retrieved files:",
        ]
        files = list(repolens_files or [])
        if files:
            lines.extend("- {0}".format(path) for path in files)
        else:
            lines.append("- none")
        lines.extend(["", report.get("audit_text", "")])
        return "\n".join(lines).strip()

    def normalized_chat_endpoint(self):
        if not bool(self.get_setting("api.use_local_api", True)):
            return "openrouter"
        raw = str(self.get_setting("api.default_base_url", "")).strip()
        if not raw:
            raise ValueError("Local API base URL is missing. Add it in Settings.")
        raw = raw.rstrip("/")
        if raw.endswith("/chat/completions"):
            return raw
        if raw.endswith("/v1"):
            return f"{raw}/chat/completions"
        path = self.get_setting("api.chat_completions_path", "/v1/chat/completions")
        if not str(path).startswith("/"):
            path = f"/{path}"
        return f"{raw}{path}"

    def _send_chat_request(
        self,
        endpoint,
        user_record,
        context,
        reasoning_enabled=False,
        snippet_snapshots=None,
        root_folder=None,
        intent=None,
        raw_message="",
        repolens_snapshots=None,
        thread_index=None,
        request_id=None,
        history_messages=None,
        attach_context=True,
        context_options=None,
        reasoning_prompts=None,
        queue_request=None,
    ):
        if queue_request:
            queue_request.raise_if_interrupted()
        user_message = user_record.get("prompt_content") or user_record.get("content", "")
        thread_index = self.current_chat_index if thread_index is None else thread_index
        messages = list(history_messages or [])
        final_context = context
        exclude_generated_repolens = self.exclude_repolens_generated_context_enabled()
        if (
            attach_context
            and not exclude_generated_repolens
            and bool(self.get_setting("repolens.chat.enabled", True))
            and bool(self.get_setting("smart_context.enabled", True))
            and self.repolens_enabled_for_current_session()
            and repolens_snapshots
        ):
            try:
                self.post_ui(
                    lambda: self.status.configure(
                        text="Building smart RepoLens context for chat..."
                    ),
                )
                smart_context = self.retrieve_smart_context(
                    repolens_snapshots,
                    user_message=raw_message,
                    endpoint=endpoint,
                    intent=intent,
                    create_cards=bool(self.get_setting("repolens.chat.create_card", True)),
                    progress=lambda message: self.post_ui(
                        lambda value=message: self.status.configure(text=value)
                    ),
                )
                smart_text = smart_context.get("text", "").strip()
                if smart_text:
                    final_context = "\n\n".join(
                        part for part in [final_context, "===== Smart RepoLens Retrieved Context =====\n" + smart_text] if part.strip()
                    )
                    self.post_ui(
                        lambda value=final_context, message=user_message: self.publish_context_budget_snapshot(
                            value,
                            user_message=message,
                            stage="Smart Context retrieved",
                        )
                    )
            except Exception as exc:
                self.post_ui(
                    lambda error=str(exc): self.status.configure(text="Smart context retrieval failed: {0}".format(error)),
                )

        elif (
            attach_context
            and not exclude_generated_repolens
            and bool(self.get_setting("repolens.chat.enabled", True))
            and self.repolens_enabled_for_current_session()
            and repolens_snapshots
        ):
            try:
                self.post_ui(lambda: self.status.configure(text="Retrieving RepoLens context for chat..."))
                depth = self.repolens_depth_for_intent(intent, fallback=1)
                effective_options = context_options or {}
                if effective_options.get("direct_dependencies") is False:
                    depth = 0
                elif effective_options.get("trace_relationships"):
                    depth = max(depth, 2)
                retrieved = self.retrieve_repolens_context_for_snippets(
                    repolens_snapshots,
                    user_message=raw_message,
                    depth=depth,
                    update_before=bool(effective_options.get("refresh_index", self.get_setting("repolens.chat.update_before_retrieval", False))),
                    update_lite=bool(self.get_setting("repolens.chat.update_lite", True)),
                    retrieval_options=effective_options,
                    progress=lambda message: self.post_ui(lambda value=message: self.status.configure(text=value)),
                )
                retrieved_text = retrieved.get("text", "").strip()
                if retrieved_text:
                    final_context = "\n\n".join(
                        part for part in [final_context, "===== RepoLens Retrieved Context =====\n" + retrieved_text] if part.strip()
                    )
                    self.post_ui(
                        lambda value=final_context, message=user_message: self.publish_context_budget_snapshot(
                            value,
                            user_message=message,
                            stage="RepoLens context retrieved",
                        )
                    )
                    if bool(self.get_setting("repolens.chat.create_card", True)):
                        self.post_ui(
                            lambda value=retrieved_text, symbols=retrieved.get("symbols", []), depth_value=depth: self.add_repolens_context_card(
                                value,
                                source_request=raw_message,
                                depth=depth_value,
                                symbols=symbols,
                                selected=True,
                            )
                        )
            except Exception as exc:
                self.post_ui(
                    lambda error=str(exc): self.status.configure(text="RepoLens retrieval failed: {0}".format(error)),
                )

        if attach_context and reasoning_enabled:
            try:
                thinking = run_thinking_process(
                    user_message=user_message,
                    context=context,
                    call_ai=lambda stage_messages: self._call_chat_once(endpoint, stage_messages),
                    retrieve_context=None if exclude_generated_repolens else lambda targets: self._retrieve_thinking_context(
                        snippet_snapshots or [],
                        user_message,
                        root_folder,
                        targets,
                    ),
                    progress=self._report_thinking_progress,
                    settings=self.settings_with_reasoning_prompts(reasoning_prompts or {}),
                )
                final_context = thinking.get("final_user_content", context)
                self.after(0, lambda value=format_reasoning_trace(thinking): self._update_reasoning_card(value))
            except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
                self.after(
                    0,
                    lambda error=str(exc): self._update_reasoning_card(
                        f"Reasoning failed, falling back to normal chat.\n{error}"
                    ),
                )
                final_context = context

        if attach_context and final_context.strip():
            final_context, budget_report = self.optimize_context_for_send(
                final_context,
                user_message=user_message,
                stage="Final context",
            )
            self.post_ui(lambda value=budget_report: self.maybe_add_context_audit_card(value))

        if attach_context and final_context.strip():
            intent_header = self.format_chat_intent_for_prompt(intent)
            content = (
                f"{self.get_setting('context.wrapper_prompt', '')}\n\n"
                f"{intent_header}\n\n"
                f"{final_context}\n\nUser message:\n{user_message}"
            )
        elif not attach_context:
            content = user_message
        else:
            intent_header = self.format_chat_intent_for_prompt(intent)
            content = f"{intent_header}\n\nUser message:\n{user_message}" if intent_header else user_message

        max_tokens = int(self.get_setting("generation.max_tokens", 0) or 0)
        messages.append({"role": "user", "content": content})
        payload = {
            "messages": messages,
            "temperature": float(self.get_setting("generation.temperature", 0.2)),
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        timeout = int(self.get_setting("api.request_timeout_seconds", 180) or 180)

        try:
            if queue_request:
                queue_request.raise_if_interrupted()
            if endpoint == "openrouter":
                answer = stream_openrouter_chat(
                    messages,
                    on_chunk=lambda value: self._queued_chat_stream_chunk(value, request_id, queue_request),
                    timeout=timeout,
                    settings=self.chat_settings(),
                )
                self.after(
                    0,
                    lambda: self._chat_request_finished(user_record, answer, None, thread_index, request_id),
                )
                return

            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                endpoint,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if payload["stream"]:
                    answer = self._read_streaming_response(response, request_id=request_id, queue_request=queue_request)
                else:
                    if queue_request:
                        queue_request.raise_if_interrupted()
                    parsed = json.loads(response.read().decode("utf-8", errors="replace"))
                    answer = self.extract_chat_answer(parsed)
                    if answer:
                        self.after(
                            0,
                            lambda value=answer, key=request_id: self._append_stream_chunk(value, key),
                        )
            self.after(
                0,
                lambda: self._chat_request_finished(user_record, answer, None, thread_index, request_id),
            )
        except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
            error = openrouter_error_message(exc) if endpoint == "openrouter" else str(exc)
            self.after(
                0,
                lambda: self._chat_request_finished(user_record, "", error, thread_index, request_id),
            )

    def _queued_chat_stream_chunk(self, value, request_id, queue_request=None):
        if queue_request:
            queue_request.raise_if_interrupted()
        self.after(
            0,
            lambda chunk=value, key=request_id: self._append_stream_chunk(chunk, key),
        )

    def _call_chat_once(self, endpoint, messages):
        queue = getattr(self, "llm_queue", None)
        if queue and not queue.is_worker_thread():
            return queue.call_sync(
                query=messages[-1].get("content", "") if messages and isinstance(messages[-1], dict) else "LLM call",
                target_id=self.next_llm_request_id("llm_once"),
                request_type="background",
                model_key=endpoint,
                restartable=True,
                worker=lambda request: self._call_chat_once_direct(endpoint, messages, queue_request=request),
            )
        return self._call_chat_once_direct(endpoint, messages)

    def _call_chat_once_direct(self, endpoint, messages, queue_request=None, on_chunk=None):
        if queue_request:
            queue_request.raise_if_interrupted()
        messages = self.sanitized_chat_messages(messages)
        if endpoint == "openrouter":
            if queue_request:
                queue_request.raise_if_interrupted()
            return stream_openrouter_chat(
                messages,
                on_chunk=on_chunk,
                timeout=int(self.get_setting("api.request_timeout_seconds", 180) or 180),
                settings=self.chat_settings(),
            )

        max_tokens = int(self.get_setting("generation.max_tokens", 0) or 0)
        payload = {
            "messages": messages,
            "temperature": float(self.get_setting("generation.reasoning_temperature", 0.1)),
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if queue_request:
            queue_request.raise_if_interrupted()
        with urllib.request.urlopen(
            request,
            timeout=int(self.get_setting("api.request_timeout_seconds", 180) or 180),
        ) as response:
            if queue_request:
                queue_request.raise_if_interrupted()
            return self._read_streaming_response(
                response,
                request_id=None,
                queue_request=queue_request,
                on_chunk=on_chunk,
            )

    def _retrieve_thinking_context(self, snippets, user_message, root_folder, retrieval_targets):
        if not self.repolens_enabled_for_current_session():
            return {"text": "", "details": []}
        parts = []
        details = []
        service = RepoLensService()
        index_dir = self._repolens_index_dir()
        service.update(index_dir)
        for snippet in snippets:
            symbols = self._symbols_for_repolens_snippet(snippet)
            for target in retrieval_targets or []:
                if target and target not in symbols:
                    symbols.append(str(target))
            if not symbols:
                continue
            result = service.context(index_dir, symbols[:12], partial=False, include_tree=True, include_types=True, level=1)
            if context_item_count(result) == 0:
                result = service.context(index_dir, symbols[:8], partial=True, include_tree=True, include_types=True, level=1)
            text = format_repolens_context(result).strip()
            if text:
                parts.append(text)
                details.append(
                    {
                        "source": str(snippet.get("source", "")),
                        "query_terms": symbols[:12],
                        "item_count": context_item_count(result),
                    }
                )
        return {"text": "\n\n".join(parts), "details": details}

    def _report_thinking_progress(self, step, total, title, detail):
        message = f"{step}/{total} - {title}\n{detail}"
        self.after(0, lambda value=message: self._update_reasoning_card(value))

    def _read_streaming_response(self, response, request_id=None, queue_request=None, on_chunk=None):
        answer_parts = []
        raw_lines = []

        for raw_line in response:
            if queue_request:
                queue_request.raise_if_interrupted()
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            if not line.startswith("data:"):
                raw_lines.append(line)
                continue

            data = line[5:].strip()
            if data == "[DONE]":
                break

            parsed = json.loads(data)
            chunk = self.extract_stream_delta(parsed)
            if chunk:
                answer_parts.append(chunk)
                if on_chunk:
                    on_chunk(chunk)
                if request_id:
                    self.after(0, lambda value=chunk, key=request_id: self._append_stream_chunk(value, key))

        if answer_parts:
            return "".join(answer_parts)

        raw_response = "\n".join(raw_lines).strip()
        if raw_response:
            parsed = json.loads(raw_response)
            answer = self.extract_chat_answer(parsed)
            if answer:
                if on_chunk:
                    on_chunk(answer)
                if request_id:
                    self.after(0, lambda value=answer, key=request_id: self._append_stream_chunk(value, key))
            return answer

        return ""

    def repolens_chat_snapshots(self, raw_message, file_references=None):
        if not self.repolens_enabled_for_current_session():
            return []
        snippets = []
        seen = set()

        def add(snippet):
            if not snippet or snippet.get("generated_context") or snippet.get("card_type") == "card":
                return
            key = snippet.get("id") or id(snippet)
            if key in seen:
                return
            seen.add(key)
            snippets.append(self._context_retrieval_snapshot(snippet))

        for snippet in self.snippets_for_context(selected_only=True):
            add(snippet)
        for snippet in self.mentioned_snippets(raw_message):
            add(snippet)
        for reference in file_references or []:
            if reference.get("kind") != "lines":
                continue
            add(
                {
                    "source": reference.get("path"),
                    "text": reference.get("text", ""),
                    "description": reference.get("display", ""),
                    "start_line": reference.get("start_line"),
                    "end_line": reference.get("end_line"),
                    "reason": "Chat #file line reference.",
                }
            )
        return snippets

    def chat_file_reference_retrieval_snapshots(self, file_references):
        snapshots = []
        for reference in file_references or []:
            if reference.get("kind") != "lines" or reference.get("error"):
                continue
            snapshots.append(
                {
                    "source": reference.get("path"),
                    "text": reference.get("text", ""),
                    "description": reference.get("display", ""),
                    "start_line": reference.get("start_line"),
                    "end_line": reference.get("end_line"),
                    "reason": "Chat #file line reference.",
                }
            )
        return snapshots

    def repolens_enabled_for_current_session(self):
        session_info = getattr(self, "current_session_info", {}) or {}
        return bool(session_info.get("repolens_enabled", True))

    def mentioned_snippets(self, text):
        tokens = find_mention_tokens(text)
        if not tokens:
            return []
        token_set = {token.lower() for token in tokens}
        snippets = []
        for snippet in self.snippets_for_context(selected_only=False):
            fallback = str(snippet.get("id") or "snippet")
            slug = snippet_mention_slug(str(snippet.get("description", "")), fallback)
            if slug.lower() in token_set:
                snippets.append(snippet)
        return snippets

    def sanitized_chat_messages(self, messages):
        cleaned = []
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant"}:
                continue
            if content is None:
                continue
            content = str(content)
            if not content.strip():
                continue
            cleaned.append({"role": role, "content": content})
        return cleaned

    def format_chat_intent_for_prompt(self, intent):
        if not intent:
            return ""
        return (
            "Task intent: {label}\n"
            "Intent source: {source}\n"
            "Recommended context depth: {depth}"
        ).format(
            label=intent.get("label", intent.get("mode", "Auto")),
            source=intent.get("source", "heuristic"),
            depth=intent.get("depth", 1),
        )

    def formatted_mentioned_snippets(self, text):
        tokens = find_mention_tokens(text)
        if not tokens:
            return ""
        token_set = {token.lower() for token in tokens}
        parts = []
        for snippet in self.snippets_for_context(selected_only=False):
            fallback = str(snippet.get("id") or "snippet")
            slug = snippet_mention_slug(str(snippet.get("description", "")), fallback)
            if slug.lower() not in token_set:
                continue
            title = str(snippet.get("description", "")).strip() or self._relative(snippet.get("source", ""))
            parts.append(
                "===== Mentioned Snippet: @{0} =====\n"
                "Description: {1}\n"
                "Source: {2}\n\n"
                "{3}".format(
                    slug,
                    title,
                    self._relative(snippet.get("source", "")),
                    str(snippet.get("text", "")).strip(),
                )
            )
        return "\n\n".join(parts)

    def chat_file_references(self, text):
        references = []
        registry = getattr(self, "chat_file_reference_registry", {}) or {}
        pattern = re.compile(r"#file:'([^']+)'(?::(\d+)-(\d+))?")
        for match in pattern.finditer(text or ""):
            token = match.group(0)
            raw_path = match.group(1)
            start_line = int(match.group(2)) if match.group(2) else None
            end_line = int(match.group(3)) if match.group(3) else None
            registered = registry.get(token)
            if registered:
                path = Path(registered.get("path", raw_path))
                start_line = registered.get("start_line") or start_line
                end_line = registered.get("end_line") or end_line
            else:
                path = self.resolve_chat_file_reference_path(raw_path)
            if not path:
                references.append(
                    {
                        "token": token,
                        "path": raw_path,
                        "display": Path(raw_path).name,
                        "kind": "missing",
                        "error": "File reference could not be resolved.",
                    }
                )
                continue
            text_value = self.read_chat_file_reference_text(path, start_line, end_line)
            display = self.display_chat_file_reference(path, start_line, end_line)
            references.append(
                {
                    "token": token,
                    "path": path,
                    "display": display,
                    "start_line": start_line,
                    "end_line": end_line,
                    "kind": "lines" if start_line and end_line else "file",
                    "text": text_value,
                    "error": "" if text_value is not None else "File reference could not be read.",
                }
            )
        if "#filetree" in (text or ""):
            references.append(
                {
                    "token": "#filetree",
                    "kind": "filetree",
                    "display": "#filetree",
                    "text": self.chat_open_filetree_text(),
                    "error": "",
                }
            )
        return references

    def resolve_chat_file_reference_path(self, raw_path):
        candidate = Path(raw_path)
        if candidate.is_absolute() and candidate.exists():
            return candidate
        open_tabs = list(getattr(self, "open_file_tabs", {}).values())
        matches = [data["path"] for data in open_tabs if data["path"].name == raw_path]
        if len(matches) == 1:
            return matches[0]
        if getattr(self, "root_folder", None):
            rooted = self.root_folder / raw_path
            if rooted.exists():
                return rooted
        return None

    def read_chat_file_reference_text(self, path, start_line=None, end_line=None):
        try:
            source_text = None
            for editor_data in getattr(self, "open_file_tabs", {}).values():
                if Path(editor_data["path"]) == Path(path):
                    source_text = editor_data["editor"].get("1.0", "end-1c")
                    break
            if source_text is None:
                source_text = Path(path).read_text(encoding="utf-8", errors="replace")
        except (OSError, tk.TclError):
            return None

        if not start_line or not end_line:
            return source_text
        lines = source_text.splitlines()
        start = max(1, int(start_line))
        end = max(start, int(end_line))
        return "\n".join(lines[start - 1:end])

    def display_chat_file_reference(self, path, start_line=None, end_line=None):
        display = "#file:'{0}'".format(Path(path).name)
        if start_line and end_line:
            display += ":{0}-{1}".format(start_line, end_line)
        return display

    def shortened_chat_file_reference_message(self, text, references):
        message = text or ""
        for reference in references or []:
            if reference.get("kind") not in {"file", "lines"}:
                continue
            token = reference.get("token", "")
            display = reference.get("display", "")
            if token and display:
                message = message.replace(token, display)
        return message

    def chat_prompt_message_with_file_references(self, message, references):
        prompt = message or ""
        for reference in references or []:
            token = reference.get("display") or reference.get("token")
            if not token:
                continue
            if reference.get("kind") == "lines":
                replacement = self.inline_chat_file_reference_text(reference)
                prompt = prompt.replace(token, replacement)
            elif reference.get("kind") == "filetree":
                prompt = prompt.replace(reference.get("token", "#filetree"), self.inline_chat_filetree_text(reference))
        return prompt

    def inline_chat_file_reference_text(self, reference):
        if reference.get("error"):
            return "[{0}: {1}]".format(reference.get("display", "file reference"), reference.get("error"))
        return (
            "Referenced lines from {0}:\n"
            "```{1}\n{2}\n```"
        ).format(
            reference.get("display", "file reference"),
            self.language_for_chat_file_reference(reference.get("path")),
            (reference.get("text") or "").strip("\n"),
        )

    def inline_chat_filetree_text(self, reference):
        text = (reference.get("text") or "").strip()
        if not text:
            return "[#filetree: no opened folder or open files available]"
        return "Opened file tree:\n```text\n{0}\n```".format(text)

    def formatted_chat_file_reference_context(self, references):
        parts = []
        for reference in references or []:
            if reference.get("kind") != "file":
                continue
            if reference.get("error"):
                parts.append(
                    "===== Referenced File: {0} =====\n{1}".format(
                        reference.get("display", "file reference"),
                        reference.get("error"),
                    )
                )
                continue
            parts.append(
                "===== Referenced File: {0} =====\n"
                "Source: {1}\n\n"
                "{2}".format(
                    reference.get("display", "file reference"),
                    self._relative(reference.get("path", "")),
                    reference.get("text", ""),
                )
            )
        return "\n\n".join(parts)

    def language_for_chat_file_reference(self, path):
        suffix = Path(path or "").suffix.lower().lstrip(".")
        return suffix or "text"

    def chat_open_filetree_text(self):
        root = getattr(self, "root_folder", None)
        open_tabs = getattr(self, "open_file_tabs", {}) or {}
        if not root or not open_tabs:
            return ""
        try:
            root = Path(root).resolve()
        except OSError:
            root = Path(root)

        relative_paths = []
        for editor_data in open_tabs.values():
            path = Path(editor_data["path"])
            try:
                resolved = path.resolve()
                relative_paths.append(os.fspath(resolved.relative_to(root)))
            except (OSError, ValueError):
                continue
        if not relative_paths:
            return ""

        tree = {}
        for path in sorted(set(relative_paths)):
            normalized = path.replace("\\", "/")
            parts = [part for part in normalized.split("/") if part and part != "."]
            node = tree
            for part in parts:
                node = node.setdefault(part, {})

        lines = [root.name if root.name else os.fspath(root)]
        self._append_tree_lines(tree, lines, "")
        return "\n".join(lines)
