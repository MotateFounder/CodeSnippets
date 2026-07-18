import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from src.services.promptManager.models import (
    add_notebook,
    add_prompt,
    delete_notebook,
    delete_prompt,
    duplicate_prompt,
    filter_prompts,
    notebook_by_id,
    prompt_by_id,
    rename_notebook,
    rename_prompt,
    selected_notebook,
    selected_prompt,
    update_prompt,
)
from src.services.promptManager.references import PromptReferenceResolver
from src.services.promptManager.storage import PromptManagerStorage
from src.services.promptManager.variables import detect_variables, replace_variables, replace_variables_partial
from src.services.chat_intents import snippet_mention_slug
from src.services.repoLens.service import RepoLensService, format_repolens_context


class PromptManagerMixin:
    def initialize_prompt_manager(self):
        self.prompt_manager_dir = Path(__file__).resolve().parent
        self.prompt_manager_store = PromptManagerStorage(self.prompt_manager_dir)
        self.prompt_manager_data = self.prompt_manager_store.load()
        self.prompt_manager_dirty = False
        self.prompt_manager_loading = False
        self.prompt_manager_autosave_after_id = None
        self.prompt_manager_variable_after_id = None
        self.prompt_manager_search_var = tk.StringVar()
        self.prompt_manager_name_var = tk.StringVar()
        self.prompt_manager_warning_var = tk.StringVar()
        self.prompt_manager_variable_widgets = {}
        self.prompt_manager_rendering_preview = False
        self.prompt_manager_template_text = ""
        self.prompt_manager_reference_popup = None
        self.schedule_prompt_manager_periodic_save()

    def _prompt_manager_pane(self, parent):
        frame = tk.Frame(parent, bg=self.colors["panel"])
        frame.columnconfigure(2, weight=1)
        frame.rowconfigure(0, weight=1)

        self.build_prompt_notebook_panel(frame)
        self.build_prompt_list_panel(frame)
        self.build_prompt_editor_panel(frame)
        self.refresh_prompt_manager()
        return frame

    def build_prompt_notebook_panel(self, parent):
        panel = tk.Frame(parent, bg=self.colors["panel"], width=230)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.grid_propagate(False)
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)

        tk.Label(
            panel,
            text="Prompt notebooks",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            anchor="w",
            font=("Segoe UI", 11, "bold"),
            padx=14,
            pady=12,
        ).grid(row=0, column=0, sticky="ew")

        self.prompt_notebook_list = tk.Listbox(
            panel,
            bg=self.colors["editor"],
            fg=self.colors["text"],
            selectbackground=self.colors["accent"],
            selectforeground=self.readable_text_on(self.colors["accent"]),
            exportselection=False,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            activestyle="none",
            font=("Segoe UI", 10),
        )
        self.prompt_notebook_list.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        self.prompt_notebook_list.bind("<<ListboxSelect>>", self.on_prompt_notebook_selected)
        self.prompt_notebook_list.bind("<Button-3>", self.show_prompt_notebook_menu)

        buttons = tk.Frame(panel, bg=self.colors["panel"])
        buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        buttons.columnconfigure((0, 1, 2), weight=1)
        self.prompt_button(buttons, "New", self.create_prompt_notebook).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.prompt_button(buttons, "Rename", self.rename_selected_prompt_notebook).grid(row=0, column=1, sticky="ew", padx=4)
        self.prompt_button(buttons, "Delete", self.delete_selected_prompt_notebook).grid(row=0, column=2, sticky="ew", padx=(4, 0))

    def build_prompt_list_panel(self, parent):
        panel = tk.Frame(parent, bg=self.colors["panel2"], width=280)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.grid_propagate(False)
        panel.rowconfigure(3, weight=1)
        panel.columnconfigure(0, weight=1)

        tk.Label(
            panel,
            text="Prompts",
            bg=self.colors["panel2"],
            fg=self.colors["text"],
            anchor="w",
            font=("Segoe UI", 11, "bold"),
            padx=14,
            pady=12,
        ).grid(row=0, column=0, sticky="ew")

        self.prompt_search_entry = tk.Entry(
            panel,
            textvariable=self.prompt_manager_search_var,
            bg=self.colors["editor"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            highlightcolor=self.colors["accent"],
            font=("Segoe UI", 10),
        )
        self.prompt_search_entry.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10), ipady=5)
        self.prompt_search_entry.insert(0, "")
        self.prompt_search_entry.bind("<KeyRelease>", lambda _event: self.refresh_prompt_list())

        buttons = tk.Frame(panel, bg=self.colors["panel2"])
        buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))
        buttons.columnconfigure((0, 1), weight=1)
        self.prompt_button(buttons, "New prompt", self.create_prompt).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.prompt_button(buttons, "Duplicate", self.duplicate_selected_prompt).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.prompt_button(buttons, "Rename", self.rename_selected_prompt).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(6, 0))
        self.prompt_button(buttons, "Delete", self.delete_selected_prompt).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=(6, 0))

        self.prompt_list = tk.Listbox(
            panel,
            bg=self.colors["editor"],
            fg=self.colors["text"],
            selectbackground=self.colors["accent"],
            selectforeground=self.readable_text_on(self.colors["accent"]),
            exportselection=False,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            activestyle="none",
            font=("Segoe UI", 10),
        )
        self.prompt_list.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.prompt_list.bind("<<ListboxSelect>>", self.on_prompt_selected)
        self.prompt_list.bind("<Button-3>", self.show_prompt_menu)

    def build_prompt_editor_panel(self, parent):
        panel = tk.Frame(parent, bg=self.colors["panel"])
        panel.grid(row=0, column=2, sticky="nsew")
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)

        top = tk.Frame(panel, bg=self.colors["panel"])
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        top.columnconfigure(0, weight=1)
        self.prompt_name_entry = tk.Entry(
            top,
            textvariable=self.prompt_manager_name_var,
            bg=self.colors["panel"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief=tk.FLAT,
            highlightthickness=0,
            font=("Segoe UI", 20),
        )
        self.prompt_name_entry.grid(row=0, column=0, sticky="ew")
        self.prompt_name_entry.bind("<KeyRelease>", self.on_prompt_editor_changed)
        self.prompt_name_entry.bind("<Button-3>", self.show_prompt_entry_menu)

        editor_shell = tk.Frame(panel, bg=self.colors["panel"])
        editor_shell.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 10))
        editor_shell.rowconfigure(0, weight=1)
        editor_shell.columnconfigure(0, weight=1)
        self.prompt_text = tk.Text(
            editor_shell,
            bg=self.colors["editor"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            selectbackground=self.colors["select"],
            selectforeground="#ffffff",
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            highlightcolor=self.colors["accent"],
            wrap=tk.WORD,
            undo=True,
            font=("Segoe UI", 11),
            padx=18,
            pady=12,
            height=10,
        )
        scrollbar = ttk.Scrollbar(editor_shell, orient=tk.VERTICAL, command=self.prompt_text.yview)
        self.prompt_text.configure(yscrollcommand=scrollbar.set)
        self.prompt_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.prompt_text.bind("<KeyRelease>", self.on_prompt_editor_changed)
        self.prompt_text.bind("<Button-3>", self.show_prompt_text_menu)

        variable_area = tk.Frame(panel, bg=self.colors["panel"])
        variable_area.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))
        variable_area.columnconfigure(0, weight=1)
        tk.Label(
            variable_area,
            text="Variables",
            bg=self.colors["panel"],
            fg=self.colors["muted"],
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="ew")
        self.prompt_variable_frame = tk.Frame(variable_area, bg=self.colors["panel"])
        self.prompt_variable_frame.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.prompt_warning_label = tk.Label(
            variable_area,
            textvariable=self.prompt_manager_warning_var,
            bg=self.colors["panel"],
            fg="#b26b00",
            anchor="w",
            font=("Segoe UI", 9),
        )
        self.prompt_warning_label.grid(row=2, column=0, sticky="ew", pady=(5, 0))

        actions = tk.Frame(panel, bg=self.colors["panel"])
        actions.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 18))
        for column in range(4):
            actions.columnconfigure(column, weight=1)
        self.prompt_button(actions, "Save", self.save_prompt_manager_now).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.prompt_button(actions, "Copy Prompt", self.copy_prompt_template).grid(row=0, column=1, sticky="ew", padx=5)
        self.prompt_button(actions, "Paste to Chat", self.copy_completed_prompt).grid(row=0, column=2, sticky="ew", padx=5)
        self.prompt_button(actions, "Clear", self.clear_prompt_variables).grid(row=0, column=3, sticky="ew", padx=(5, 0))

    def prompt_button(self, parent, text, command):
        bg = self.colors.get("accent", "#7c83ff")
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=self.readable_text_on(bg),
            activebackground=self.lighten(bg, 0.25) if hasattr(self, "lighten") else bg,
            activeforeground=self.readable_text_on(bg),
            relief=tk.FLAT,
            borderwidth=0,
            font=("Segoe UI", 9),
            padx=8,
            pady=6,
            cursor="hand2",
        )

    def refresh_prompt_manager(self):
        self.refresh_prompt_notebook_list()
        self.refresh_prompt_list()
        self.load_selected_prompt()

    def refresh_prompt_notebook_list(self):
        if not hasattr(self, "prompt_notebook_list"):
            return
        self.prompt_notebook_list.delete(0, tk.END)
        self.prompt_notebook_ids = []
        selected_id = self.prompt_manager_data.get("selectedNotebookId", "")
        selected_index = 0
        for index, notebook in enumerate(self.prompt_manager_data.get("notebooks", [])):
            self.prompt_notebook_ids.append(notebook["id"])
            self.prompt_notebook_list.insert(tk.END, notebook.get("name", "Untitled Notebook"))
            if notebook["id"] == selected_id:
                selected_index = index
        if self.prompt_notebook_ids:
            self.prompt_notebook_list.selection_clear(0, tk.END)
            self.prompt_notebook_list.selection_set(selected_index)
            self.prompt_notebook_list.see(selected_index)

    def refresh_prompt_list(self):
        if not hasattr(self, "prompt_list"):
            return
        self.prompt_list.delete(0, tk.END)
        self.prompt_ids = []
        notebook = selected_notebook(self.prompt_manager_data)
        prompts = filter_prompts(notebook, self.prompt_manager_search_var.get())
        selected_id = self.prompt_manager_data.get("selectedPromptId", "")
        selected_index = 0
        for index, prompt in enumerate(prompts):
            self.prompt_ids.append(prompt["id"])
            self.prompt_list.insert(tk.END, prompt.get("name", "Untitled Prompt"))
            if prompt["id"] == selected_id:
                selected_index = index
        if self.prompt_ids:
            self.prompt_list.selection_clear(0, tk.END)
            self.prompt_list.selection_set(selected_index)
            self.prompt_list.see(selected_index)

    def load_selected_prompt(self):
        if not hasattr(self, "prompt_text"):
            return
        prompt = selected_prompt(self.prompt_manager_data)
        self.prompt_manager_loading = True
        self.prompt_manager_name_var.set(prompt.get("name", "") if prompt else "")
        self.prompt_text.delete("1.0", tk.END)
        if prompt:
            self.prompt_manager_template_text = prompt.get("text", "")
            self.prompt_text.insert("1.0", self.prompt_manager_template_text)
        else:
            self.prompt_manager_template_text = ""
        self.prompt_manager_loading = False
        self.rebuild_prompt_variable_inputs()

    def on_prompt_notebook_selected(self, _event=None):
        selection = self.prompt_notebook_list.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(getattr(self, "prompt_notebook_ids", [])):
            return
        self.prompt_manager_data["selectedNotebookId"] = self.prompt_notebook_ids[index]
        notebook = selected_notebook(self.prompt_manager_data)
        self.prompt_manager_data["selectedPromptId"] = notebook["prompts"][0]["id"] if notebook and notebook.get("prompts") else ""
        self.mark_prompt_manager_dirty()
        self.refresh_prompt_list()
        self.load_selected_prompt()

    def on_prompt_selected(self, _event=None):
        selection = self.prompt_list.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(getattr(self, "prompt_ids", [])):
            return
        self.prompt_manager_data["selectedPromptId"] = self.prompt_ids[index]
        self.mark_prompt_manager_dirty()
        self.load_selected_prompt()

    def on_prompt_editor_changed(self, _event=None):
        if self.prompt_manager_loading or self.prompt_manager_rendering_preview:
            return
        if _event is not None and getattr(_event, "widget", None) == getattr(self, "prompt_name_entry", None):
            prompt = selected_prompt(self.prompt_manager_data)
            if prompt:
                rename_prompt(prompt, self.prompt_manager_name_var.get())
                self.mark_prompt_manager_dirty()
                self.refresh_prompt_list()
            return
        if _event is not None and getattr(_event, "widget", None) == getattr(self, "prompt_text", None):
            self.prompt_manager_template_text = self.prompt_text.get("1.0", "end-1c")
        self.schedule_prompt_variable_rebuild()

    def schedule_prompt_variable_rebuild(self):
        if self.prompt_manager_variable_after_id:
            self.after_cancel(self.prompt_manager_variable_after_id)
        self.prompt_manager_variable_after_id = self.after(250, self.rebuild_prompt_variable_inputs)

    def rebuild_prompt_variable_inputs(self):
        self.prompt_manager_variable_after_id = None
        values = self.current_prompt_variable_values()
        prompt = selected_prompt(self.prompt_manager_data)
        stored = dict(prompt.get("variables", {}) if prompt else {})
        stored.update(values)
        names = detect_variables(self.prompt_manager_template_text if hasattr(self, "prompt_text") else "")
        for child in self.prompt_variable_frame.winfo_children():
            child.destroy()
        self.prompt_manager_variable_widgets = {}
        if not names:
            tk.Label(
                self.prompt_variable_frame,
                text="No variables detected.",
                bg=self.colors["panel"],
                fg=self.colors["muted"],
                anchor="w",
                font=("Segoe UI", 9),
            ).grid(row=0, column=0, sticky="ew")
            self.prompt_manager_warning_var.set("")
            return
        self.prompt_variable_frame.columnconfigure(1, weight=1)
        for row, name in enumerate(names):
            tk.Label(
                self.prompt_variable_frame,
                text=name,
                bg=self.colors["panel"],
                fg=self.colors["text"],
                anchor="w",
                font=("Segoe UI", 9),
            ).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            entry = tk.Entry(
                self.prompt_variable_frame,
                bg=self.colors["editor"],
                fg=self.colors["text"],
                insertbackground=self.colors["text"],
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground=self.colors["line"],
                highlightcolor=self.colors["accent"],
                font=("Segoe UI", 9),
            )
            entry.insert(0, stored.get(name, ""))
            entry.grid(row=row, column=1, sticky="ew", pady=3, ipady=4)
            entry.bind("<KeyRelease>", lambda event, widget=entry: self.on_prompt_variable_changed(event, widget))
            entry.bind("<Down>", self.handle_prompt_reference_popup_navigation)
            entry.bind("<Up>", self.handle_prompt_reference_popup_navigation)
            entry.bind("<Return>", self.handle_prompt_reference_popup_navigation)
            entry.bind("<Tab>", self.handle_prompt_reference_popup_navigation)
            entry.bind("<Escape>", self.handle_prompt_reference_popup_navigation)
            entry.bind("<Button-3>", self.show_prompt_entry_menu)
            self.prompt_manager_variable_widgets[name] = entry
        self.update_prompt_variable_warning()
        self.save_prompt_variables_to_data()

    def on_prompt_variable_changed(self, event, widget):
        self.save_prompt_variables_to_data()
        self.update_prompt_variable_warning()
        self.refresh_prompt_reference_popup(widget, event)

    def current_prompt_variable_values(self):
        values = {}
        for name, widget in getattr(self, "prompt_manager_variable_widgets", {}).items():
            try:
                values[name] = widget.get()
            except tk.TclError:
                pass
        return values

    def update_prompt_variable_warning(self, extra_warnings=None):
        values = self.current_prompt_variable_values()
        empty = [name for name, value in values.items() if not str(value).strip()]
        warnings = list(extra_warnings or [])
        if empty:
            warnings.insert(0, "Empty variables: {0}".format(", ".join(empty)))
        self.prompt_manager_warning_var.set("  ".join(warnings))

    def save_prompt_editor_to_data(self):
        prompt = selected_prompt(self.prompt_manager_data)
        if not prompt or not hasattr(self, "prompt_text"):
            return False
        changed = update_prompt(
            prompt,
            self.prompt_manager_name_var.get(),
            self.prompt_manager_template_text,
            self.current_prompt_variable_values(),
        )
        if changed:
            self.mark_prompt_manager_dirty()
        return changed

    def current_prompt_template_text(self):
        if hasattr(self, "prompt_text"):
            return self.prompt_manager_template_text
        prompt = selected_prompt(self.prompt_manager_data)
        return prompt.get("text", "") if prompt else ""

    def save_prompt_variables_to_data(self):
        prompt = selected_prompt(self.prompt_manager_data)
        if not prompt:
            return False
        values = self.current_prompt_variable_values()
        if prompt.get("variables", {}) == values:
            return False
        prompt["variables"] = values
        self.mark_prompt_manager_dirty()
        return True

    def refresh_prompt_text_preview(self):
        prompt = selected_prompt(self.prompt_manager_data)
        if not prompt or not hasattr(self, "prompt_text"):
            return
        self.prompt_manager_rendering_preview = True
        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert("1.0", self.current_prompt_template_text())
        self.prompt_manager_rendering_preview = False

    def mark_prompt_manager_dirty(self):
        self.prompt_manager_dirty = True

    def save_prompt_manager_now(self):
        self.save_prompt_editor_to_data()
        self.persist_prompt_manager_data()
        if hasattr(self, "status"):
            self.status.configure(text="Prompt Manager saved.")

    def persist_prompt_manager_data(self):
        self.prompt_manager_data = self.prompt_manager_store.save(self.prompt_manager_data)
        self.prompt_manager_dirty = False
        self.refresh_prompt_notebook_list()
        self.refresh_prompt_list()

    def schedule_prompt_manager_periodic_save(self):
        def save_periodically():
            if getattr(self, "prompt_manager_dirty", False):
                self.persist_prompt_manager_data()
            self.prompt_manager_autosave_after_id = self.after(30000, save_periodically)

        self.prompt_manager_autosave_after_id = self.after(30000, save_periodically)

    def create_prompt_notebook(self):
        name = simpledialog.askstring("New notebook", "Notebook name:", parent=self)
        if not name:
            return
        add_notebook(self.prompt_manager_data, name)
        self.mark_prompt_manager_dirty()
        self.refresh_prompt_manager()

    def rename_selected_prompt_notebook(self):
        notebook = selected_notebook(self.prompt_manager_data)
        if not notebook:
            return
        name = simpledialog.askstring("Rename notebook", "Notebook name:", initialvalue=notebook.get("name", ""), parent=self)
        if not name:
            return
        rename_notebook(notebook, name)
        self.mark_prompt_manager_dirty()
        self.refresh_prompt_notebook_list()

    def delete_selected_prompt_notebook(self):
        notebook = selected_notebook(self.prompt_manager_data)
        if not notebook:
            return
        if not messagebox.askyesno("Delete notebook", "Delete '{0}'?".format(notebook.get("name", "Untitled Notebook")), parent=self):
            return
        delete_notebook(self.prompt_manager_data, notebook["id"])
        self.mark_prompt_manager_dirty()
        self.refresh_prompt_manager()

    def create_prompt(self):
        name = simpledialog.askstring("New prompt", "Prompt name:", parent=self)
        if not name:
            return
        add_prompt(self.prompt_manager_data, name)
        self.mark_prompt_manager_dirty()
        self.refresh_prompt_manager()
        self.prompt_name_entry.focus_set()

    def rename_selected_prompt(self):
        prompt = selected_prompt(self.prompt_manager_data)
        if not prompt:
            return
        name = simpledialog.askstring("Rename prompt", "Prompt name:", initialvalue=prompt.get("name", ""), parent=self)
        if not name:
            return
        rename_prompt(prompt, name)
        self.prompt_manager_name_var.set(prompt["name"])
        self.mark_prompt_manager_dirty()
        self.refresh_prompt_list()

    def duplicate_selected_prompt(self):
        prompt = selected_prompt(self.prompt_manager_data)
        if not prompt:
            return
        duplicate_prompt(self.prompt_manager_data, prompt["id"])
        self.mark_prompt_manager_dirty()
        self.refresh_prompt_manager()

    def delete_selected_prompt(self):
        prompt = selected_prompt(self.prompt_manager_data)
        if not prompt:
            return
        if not messagebox.askyesno("Delete prompt", "Delete '{0}'?".format(prompt.get("name", "Untitled Prompt")), parent=self):
            return
        delete_prompt(self.prompt_manager_data, prompt["id"])
        self.mark_prompt_manager_dirty()
        self.refresh_prompt_manager()

    def copy_prompt_template(self):
        prompt = selected_prompt(self.prompt_manager_data)
        text = replace_variables_partial(self.current_prompt_template_text(), self.current_prompt_variable_values()) if prompt else ""
        self.clipboard_clear()
        self.clipboard_append(text)
        if hasattr(self, "status"):
            self.status.configure(text="Prompt copied.")

    def copy_completed_prompt(self):
        prompt = selected_prompt(self.prompt_manager_data)
        if not prompt:
            return
        values = {}
        warnings = []
        resolver = self.prompt_reference_resolver()
        for name, value in self.current_prompt_variable_values().items():
            resolved, value_warnings = resolver.resolve_text(value)
            values[name] = resolved
            warnings.extend(value_warnings)
        completed = replace_variables_partial(self.current_prompt_template_text(), values)
        if hasattr(self, "chat_input"):
            self.chat_input.focus_set()
            if getattr(self, "chat_input_placeholder_visible", False):
                self._hide_chat_input_placeholder()
            current = self.chat_input.get("1.0", "end-1c")
            prefix = "\n" if current.strip() else ""
            self.chat_input.insert(tk.END, prefix + completed)
            self.refresh_token_count()
        self.update_prompt_variable_warning(warnings)
        if hasattr(self, "status"):
            self.status.configure(text="Prompt pasted to chat.")

    def clear_prompt_variables(self):
        for entry in self.prompt_manager_variable_widgets.values():
            entry.delete(0, tk.END)
        self.save_prompt_variables_to_data()
        self.update_prompt_variable_warning()

    def prompt_reference_resolver(self):
        return PromptReferenceResolver(
            snippets=self.snippets_for_context(selected_only=False) if hasattr(self, "snippets_for_context") else getattr(self, "snippets", []),
            root_folder=getattr(self, "root_folder", None),
            symbol_resolver=self.resolve_prompt_symbol_reference,
        )

    def resolve_prompt_symbol_reference(self, symbol):
        if not getattr(self, "root_folder", None) or not hasattr(self, "_repolens_index_dir"):
            return ""
        service = RepoLensService()
        index_dir = self._repolens_index_dir()
        service.update(index_dir)
        result = service.context(index_dir, [symbol], partial=True, include_tree=True, include_types=True, level=1)
        return format_repolens_context(result).strip()

    def prompt_reference_options(self, prefix):
        options = []
        prefix = (prefix or "").lower()
        for snippet in self.snippets_for_context(selected_only=False) if hasattr(self, "snippets_for_context") else getattr(self, "snippets", []):
            if snippet.get("card_type") == "card":
                continue
            fallback = str(snippet.get("id") or "snippet")
            slug = snippet_mention_slug(str(snippet.get("description", "")), fallback)
            token = "snippet:" + slug
            if not prefix or token.lower().startswith(prefix) or slug.lower().startswith(prefix):
                options.append({"insert": "@" + token + " ", "label": "@" + token})
        if "file:".startswith(prefix) or not prefix:
            options.append({"insert": "@file:", "label": "@file:path/to/file.py"})
        if "symbol:".startswith(prefix) or not prefix:
            options.append({"insert": "@symbol:", "label": "@symbol:ClassName.method"})
        return options[:10]

    def refresh_prompt_reference_popup(self, entry, event=None):
        if event and event.keysym in {"Up", "Down", "Return", "Tab", "Escape"}:
            return
        cursor = entry.index(tk.INSERT)
        before = entry.get()[:cursor]
        start = before.rfind("@")
        if start < 0 or (start > 0 and before[start - 1].isalnum()):
            self.hide_prompt_reference_popup()
            return
        prefix = before[start + 1:]
        if any(character in prefix for character in " \t\r\n"):
            self.hide_prompt_reference_popup()
            return
        options = self.prompt_reference_options(prefix.lower())
        if not options:
            self.hide_prompt_reference_popup()
            return
        self.prompt_reference_entry = entry
        self.prompt_reference_range = (start, cursor)
        self.show_prompt_reference_popup(entry, options)

    def show_prompt_reference_popup(self, entry, options):
        if not getattr(self, "prompt_manager_reference_popup", None):
            popup = tk.Toplevel(self)
            popup.withdraw()
            popup.overrideredirect(True)
            popup.configure(bg=self.colors["panel2"])
            listbox = tk.Listbox(
                popup,
                bg=self.colors["panel2"],
                fg=self.colors["text"],
                selectbackground=self.colors["accent"],
                selectforeground=self.readable_text_on(self.colors["accent"]),
                relief=tk.FLAT,
                borderwidth=0,
                highlightthickness=1,
                highlightbackground=self.colors["line"],
                activestyle="none",
                font=("Segoe UI", 9),
                width=34,
            )
            listbox.pack(fill=tk.BOTH, expand=True)
            listbox.bind("<ButtonRelease-1>", lambda _event: self.accept_prompt_reference_completion())
            self.prompt_manager_reference_popup = popup
            self.prompt_reference_listbox = listbox
        self.prompt_reference_options_list = options
        listbox = self.prompt_reference_listbox
        listbox.delete(0, tk.END)
        listbox.configure(height=min(8, len(options)))
        for option in options:
            listbox.insert(tk.END, option["label"])
        listbox.selection_set(0)
        x = entry.winfo_rootx()
        y = entry.winfo_rooty() + entry.winfo_height() + 3
        self.prompt_manager_reference_popup.geometry("+{0}+{1}".format(x, y))
        self.prompt_manager_reference_popup.deiconify()
        self.prompt_manager_reference_popup.lift()

    def handle_prompt_reference_popup_navigation(self, event):
        popup = getattr(self, "prompt_manager_reference_popup", None)
        if not popup:
            return None
        if event.keysym in {"Up", "Down"}:
            listbox = self.prompt_reference_listbox
            size = listbox.size()
            current = listbox.curselection()
            index = current[0] if current else 0
            index += -1 if event.keysym == "Up" else 1
            index = max(0, min(size - 1, index))
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(index)
            listbox.activate(index)
            return "break"
        if event.keysym in {"Return", "Tab"}:
            self.accept_prompt_reference_completion()
            return "break"
        if event.keysym == "Escape":
            self.hide_prompt_reference_popup()
            return "break"
        return None

    def accept_prompt_reference_completion(self):
        entry = getattr(self, "prompt_reference_entry", None)
        listbox = getattr(self, "prompt_reference_listbox", None)
        options = getattr(self, "prompt_reference_options_list", [])
        if not entry or not listbox or not options:
            return
        selection = listbox.curselection()
        index = selection[0] if selection else 0
        start, end = self.prompt_reference_range
        value = entry.get()
        entry.delete(0, tk.END)
        entry.insert(0, value[:start] + options[index]["insert"] + value[end:])
        entry.icursor(start + len(options[index]["insert"]))
        self.hide_prompt_reference_popup()
        self.save_prompt_variables_to_data()

    def hide_prompt_reference_popup(self):
        popup = getattr(self, "prompt_manager_reference_popup", None)
        if popup:
            popup.destroy()
        self.prompt_manager_reference_popup = None
        self.prompt_reference_listbox = None
        self.prompt_reference_options_list = []
        self.prompt_reference_entry = None
        self.prompt_reference_range = None

    def show_prompt_notebook_menu(self, event):
        self.select_listbox_row_at_event(self.prompt_notebook_list, event)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Rename", command=self.rename_selected_prompt_notebook)
        menu.add_command(label="Delete", command=self.delete_selected_prompt_notebook)
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def show_prompt_menu(self, event):
        self.select_listbox_row_at_event(self.prompt_list, event)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Rename", command=self.rename_selected_prompt)
        menu.add_command(label="Duplicate", command=self.duplicate_selected_prompt)
        menu.add_command(label="Delete", command=self.delete_selected_prompt)
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def show_prompt_text_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Cut", command=lambda: self.prompt_text.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: self.prompt_text.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: self.prompt_text.event_generate("<<Paste>>"))
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def show_prompt_entry_menu(self, event):
        widget = event.widget
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def select_listbox_row_at_event(self, listbox, event):
        index = listbox.nearest(event.y)
        if index >= 0:
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(index)
            listbox.activate(index)
            listbox.event_generate("<<ListboxSelect>>")
