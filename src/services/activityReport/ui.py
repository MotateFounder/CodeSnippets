import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from src.services.activityReport.collector import collect_activity_entries
from src.services.activityReport.file_saver import save_report
from src.services.activityReport.prompt_builder import DEFAULT_REPORT_TEMPLATE, build_report_messages
from src.services.activityReport.validation import default_range, format_datetime, validate_report_options


class ActivityReportMixin:
    def open_write_report_dialog(self):
        ActivityReportDialog(self)

    def start_activity_report_generation(self, dialog, options):
        try:
            self.save_notebook_now()
        except Exception:
            pass
        dialog.set_state("Collecting data")
        entries, warnings = collect_activity_entries(
            getattr(self, "notebook_data", {}),
            getattr(self, "chat_threads", []),
            options["start"],
            options["end"],
        )
        if warnings:
            dialog.set_warning("{0} stored item(s) had missing or invalid timestamps and were skipped.".format(len(warnings)))
        if not entries:
            dialog.set_error("No notes or chat messages exist in the selected period.")
            return
        dialog.set_state("Collected {0} activity item(s).".format(len(entries)))

        try:
            endpoint = self.normalized_chat_endpoint()
        except ValueError as exc:
            dialog.set_error(str(exc))
            return

        messages = build_report_messages(
            entries,
            options["start"],
            options["end"],
            options["bullet_limit"],
            options["include_summary"],
            template=options["prompt_template"],
        )
        cancel_event = threading.Event()
        dialog.begin_generation(cancel_event)
        request_id = self.next_llm_request_id("report") if hasattr(self, "next_llm_request_id") else "report_{0}".format(id(dialog))

        def worker(queue_request):
            self.post_ui(lambda: dialog.set_state("Waiting for LLM"))
            if cancel_event.is_set():
                raise RuntimeError("Report generation cancelled.")
            queue_request.raise_if_interrupted()
            self.post_ui(lambda: dialog.set_state("Generating report"))
            report_text = self._call_chat_once_direct(
                endpoint,
                messages,
                queue_request=queue_request,
                on_chunk=lambda chunk: self.post_ui(lambda value=chunk: dialog.append_report_chunk(value)),
            )
            if cancel_event.is_set():
                raise RuntimeError("Report generation cancelled before saving.")
            queue_request.raise_if_interrupted()
            self.post_ui(lambda: dialog.set_state("Saving report"))
            return save_report(options["folder"], options["start"], options["end"], report_text)

        def on_done(result, error):
            if error:
                self.post_ui(lambda: dialog.generation_failed(str(error)))
                return
            self.post_ui(lambda: dialog.generation_completed(result))

        self.llm_queue.submit(
            query="Write CodeSnippets activity report",
            target_id=request_id,
            worker=worker,
            on_done=on_done,
            request_type="background",
            model_key=endpoint,
            restartable=True,
        )


class ActivityReportDialog:
    def __init__(self, owner):
        self.owner = owner
        self.cancel_event = None
        self.completed_path = None
        start, end = default_range(datetime.now())

        self.window = tk.Toplevel(owner)
        self.window.title("Write Report")
        self.window.transient(owner)
        self.window.grab_set()
        self.window.resizable(False, False)
        self.window.configure(bg=owner.colors["panel"])
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)

        self.from_var = tk.StringVar(value=format_datetime(start))
        self.to_var = tk.StringVar(value=format_datetime(end))
        self.bullet_var = tk.StringVar(value="3")
        self.summary_var = tk.BooleanVar(value=False)
        self.folder_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")
        self.warning_var = tk.StringVar()

        self.build()

    def build(self):
        body = tk.Frame(self.window, bg=self.owner.colors["panel"], padx=18, pady=16)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)

        self.label(body, "From date and time").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.from_entry = self.entry(body, self.from_var)
        self.from_entry.grid(row=0, column=1, sticky="ew", pady=(0, 6))

        self.label(body, "To date and time").grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.to_entry = self.entry(body, self.to_var)
        self.to_entry.grid(row=1, column=1, sticky="ew", pady=(0, 6))

        self.label(body, "Bullet points per section").grid(row=2, column=0, sticky="w", pady=(0, 6))
        self.bullet_entry = self.entry(body, self.bullet_var)
        self.bullet_entry.grid(row=2, column=1, sticky="ew", pady=(0, 6))

        self.summary_check = tk.Checkbutton(
            body,
            text="Add summary",
            variable=self.summary_var,
            bg=self.owner.colors["panel"],
            fg=self.owner.colors["text"],
            activebackground=self.owner.colors["panel"],
            activeforeground=self.owner.colors["text"],
            selectcolor=self.owner.colors["editor"],
            borderwidth=0,
        )
        self.summary_check.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 10))

        self.label(body, "Destination folder").grid(row=4, column=0, sticky="w", pady=(0, 6))
        folder_row = tk.Frame(body, bg=self.owner.colors["panel"])
        folder_row.grid(row=4, column=1, sticky="ew", pady=(0, 6))
        folder_row.columnconfigure(0, weight=1)
        self.folder_entry = self.entry(folder_row, self.folder_var, readonly=True)
        self.folder_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(folder_row, text="Browse", command=self.browse_folder).grid(row=0, column=1, padx=(8, 0))

        self.label(body, "Report prompt template").grid(row=5, column=0, sticky="nw", pady=(8, 6))
        prompt_shell = tk.Frame(body, bg=self.owner.colors["panel"])
        prompt_shell.grid(row=5, column=1, sticky="ew", pady=(8, 6))
        prompt_shell.columnconfigure(0, weight=1)
        self.prompt_template = tk.Text(
            prompt_shell,
            height=12,
            bg=self.owner.colors["editor"],
            fg=self.owner.colors["text"],
            insertbackground=self.owner.colors["text"],
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.owner.colors["line"],
            wrap=tk.WORD,
            font=("Segoe UI", 9),
            padx=8,
            pady=6,
        )
        prompt_scroll = ttk.Scrollbar(prompt_shell, orient=tk.VERTICAL, command=self.prompt_template.yview)
        self.prompt_template.configure(yscrollcommand=prompt_scroll.set)
        self.prompt_template.grid(row=0, column=0, sticky="ew")
        prompt_scroll.grid(row=0, column=1, sticky="ns")
        self.prompt_template.insert("1.0", DEFAULT_REPORT_TEMPLATE)
        self.prompt_template.bind("<Button-3>", self.show_prompt_template_menu)

        self.label(body, "Live report output").grid(row=6, column=0, sticky="nw", pady=(8, 6))
        live_shell = tk.Frame(body, bg=self.owner.colors["panel"])
        live_shell.grid(row=6, column=1, sticky="ew", pady=(8, 6))
        live_shell.columnconfigure(0, weight=1)
        self.report_output = tk.Text(
            live_shell,
            height=10,
            bg=self.owner.colors["editor"],
            fg=self.owner.colors["text"],
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.owner.colors["line"],
            wrap=tk.WORD,
            font=("Segoe UI", 9),
            padx=8,
            pady=6,
        )
        output_scroll = ttk.Scrollbar(live_shell, orient=tk.VERTICAL, command=self.report_output.yview)
        self.report_output.configure(yscrollcommand=output_scroll.set)
        self.report_output.grid(row=0, column=0, sticky="ew")
        output_scroll.grid(row=0, column=1, sticky="ns")
        self.report_output.insert("1.0", "Generated report text will stream here.")
        self.report_output.configure(state=tk.DISABLED)

        self.warning_label = tk.Label(
            body,
            textvariable=self.warning_var,
            bg=self.owner.colors["panel"],
            fg="#b26b00",
            anchor="w",
            justify=tk.LEFT,
            wraplength=520,
        )
        self.warning_label.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.status_label = tk.Label(
            body,
            textvariable=self.status_var,
            bg=self.owner.colors["panel"],
            fg=self.owner.colors["muted"],
            anchor="w",
            justify=tk.LEFT,
            wraplength=520,
        )
        self.status_label.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        actions = ttk.Frame(body, style="Panel.TFrame")
        actions.grid(row=9, column=0, columnspan=2, sticky="e", pady=(16, 0))
        self.generate_button = ttk.Button(actions, text="Generate Report", command=self.generate)
        self.generate_button.pack(side=tk.LEFT, padx=(0, 8))
        self.cancel_button = ttk.Button(actions, text="Cancel", command=self.cancel)
        self.cancel_button.pack(side=tk.LEFT)

    def label(self, parent, text):
        return tk.Label(
            parent,
            text=text,
            bg=self.owner.colors["panel"],
            fg=self.owner.colors["text"],
            anchor="w",
            font=("Segoe UI", 9, "bold"),
            padx=0,
        )

    def entry(self, parent, variable, readonly=False):
        entry = tk.Entry(
            parent,
            textvariable=variable,
            bg=self.owner.colors["editor"],
            fg=self.owner.colors["text"],
            insertbackground=self.owner.colors["text"],
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.owner.colors["line"],
            highlightcolor=self.owner.colors["accent"],
            font=("Segoe UI", 10),
            width=42,
        )
        if readonly:
            entry.configure(state="readonly", readonlybackground=self.owner.colors["editor"])
        return entry

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Choose report destination", parent=self.window)
        if folder:
            self.folder_var.set(folder)
            self.set_state("Ready.")

    def generate(self):
        try:
            options = validate_report_options(
                self.from_var.get(),
                self.to_var.get(),
                self.bullet_var.get(),
                self.folder_var.get(),
            )
        except ValueError as exc:
            self.set_error(str(exc))
            return
        options["include_summary"] = bool(self.summary_var.get())
        options["prompt_template"] = self.prompt_template_text()
        self.owner.start_activity_report_generation(self, options)

    def begin_generation(self, cancel_event):
        self.cancel_event = cancel_event
        self.generate_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(text="Cancel")
        self.clear_report_output()
        self.set_state("Waiting for LLM")

    def prompt_template_text(self):
        if not hasattr(self, "prompt_template"):
            return DEFAULT_REPORT_TEMPLATE
        value = self.prompt_template.get("1.0", "end-1c").strip()
        return value or DEFAULT_REPORT_TEMPLATE

    def show_prompt_template_menu(self, event):
        menu = tk.Menu(self.window, tearoff=0)
        menu.add_command(label="Cut", command=lambda: self.prompt_template.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: self.prompt_template.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: self.prompt_template.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Reset template", command=self.reset_prompt_template)
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def reset_prompt_template(self):
        self.prompt_template.delete("1.0", tk.END)
        self.prompt_template.insert("1.0", DEFAULT_REPORT_TEMPLATE)

    def clear_report_output(self):
        if not hasattr(self, "report_output"):
            return
        self.report_output.configure(state=tk.NORMAL)
        self.report_output.delete("1.0", tk.END)
        self.report_output.configure(state=tk.DISABLED)

    def append_report_chunk(self, chunk):
        if not self.window.winfo_exists() or not hasattr(self, "report_output"):
            return
        self.report_output.configure(state=tk.NORMAL)
        self.report_output.insert(tk.END, str(chunk or ""))
        self.report_output.see(tk.END)
        self.report_output.configure(state=tk.DISABLED)

    def set_state(self, text):
        if not self.window.winfo_exists():
            return
        self.status_var.set(text)
        if hasattr(self.owner, "status"):
            self.owner.status.configure(text="Write Report: {0}".format(text))

    def set_warning(self, text):
        if self.window.winfo_exists():
            self.warning_var.set(text)

    def set_error(self, text):
        self.status_var.set("Failed: {0}".format(text))
        if hasattr(self.owner, "status"):
            self.owner.status.configure(text="Write Report failed: {0}".format(text))

    def generation_failed(self, text):
        if not self.window.winfo_exists():
            return
        self.generate_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(text="Cancel")
        self.set_error(text)

    def generation_completed(self, path):
        if not self.window.winfo_exists():
            return
        self.completed_path = path
        self.generate_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(text="Close")
        self.set_state("Completed")
        self.show_completed_actions(path)

    def show_completed_actions(self, path):
        result = tk.Toplevel(self.window)
        result.title("Report Saved")
        result.transient(self.window)
        result.grab_set()
        result.configure(bg=self.owner.colors["panel"])
        body = tk.Frame(result, bg=self.owner.colors["panel"], padx=16, pady=14)
        body.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            body,
            text="Report saved:\n{0}".format(path),
            bg=self.owner.colors["panel"],
            fg=self.owner.colors["text"],
            justify=tk.LEFT,
            wraplength=540,
        ).pack(fill=tk.X, pady=(0, 12))
        actions = ttk.Frame(body, style="Panel.TFrame")
        actions.pack(fill=tk.X)
        ttk.Button(actions, text="Open Folder", command=lambda: self.open_path(path.parent)).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions, text="Open Report", command=lambda: self.open_path(path)).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions, text="Close", command=result.destroy).pack(side=tk.RIGHT)

    def open_path(self, path):
        try:
            os.startfile(os.fspath(path))
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc), parent=self.window)

    def cancel(self):
        if self.cancel_event and not self.completed_path:
            self.cancel_event.set()
            self.set_state("Cancellation requested. The report will stop before saving.")
            self.cancel_button.configure(state=tk.DISABLED)
            return
        try:
            self.window.destroy()
        except tk.TclError:
            pass
