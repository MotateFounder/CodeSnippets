import tkinter as tk

from src.services.chat_intents import snippet_mention_slug


class PlainNoteEditor:
    def __init__(self, owner, parent, colors, on_change):
        self.owner = owner
        self.colors = colors
        self.on_change = on_change
        self.loading = False

        self.frame = tk.Frame(parent, bg=self.editor_background)
        self.notebook_title_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.date_var = tk.StringVar()
        self.snippet_popup = None
        self.snippet_listbox = None
        self.snippet_options = []
        self.snippet_at_range = None

        self.notebook_title = tk.Label(
            self.frame,
            textvariable=self.notebook_title_var,
            bg=self.editor_background,
            fg=self.readable_text_on(self.editor_background),
            anchor="w",
            font=("Segoe UI", 11, "bold"),
        )
        self.notebook_title.pack(fill=tk.X, padx=48, pady=(20, 0))

        title_row = tk.Frame(self.frame, bg=self.editor_background)
        title_row.pack(fill=tk.X, padx=42, pady=(8, 4))
        title_row.columnconfigure(0, weight=1)

        self.title = tk.Entry(
            title_row,
            textvariable=self.title_var,
            bg=self.editor_background,
            fg=self.readable_text_on(self.editor_background),
            insertbackground=self.readable_text_on(self.editor_background),
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 24),
        )
        self.title.grid(row=0, column=0, sticky="ew", ipady=6, padx=(0, 16))
        self.title.bind("<KeyRelease>", self._changed)
        self.title.bind("<Button-3>", self.show_title_menu)

        toolbar = tk.Frame(title_row, bg=self.editor_background)
        toolbar.grid(row=0, column=1, sticky="e")
        self.bold_button = self.toolbar_button(toolbar, "B", self.toggle_bold, bold=True)
        self.bold_button.pack(side=tk.LEFT, padx=(0, 6))
        self.italic_button = self.toolbar_button(toolbar, "I", self.toggle_italic, italic=True)
        self.italic_button.pack(side=tk.LEFT, padx=(0, 6))
        self.bullet_button = self.toolbar_button(toolbar, "*", self.insert_bullet)
        self.bullet_button.pack(side=tk.LEFT)

        self.date = tk.Label(
            self.frame,
            textvariable=self.date_var,
            bg=self.editor_background,
            fg=self.secondary_text_on(self.editor_background),
            anchor="w",
            font=("Segoe UI", 10),
        )
        self.date.pack(fill=tk.X, padx=48, pady=(0, 16))

        text_shell = tk.Frame(self.frame, bg=self.editor_background)
        text_shell.pack(fill=tk.BOTH, expand=True, padx=42, pady=(0, 34))
        self.text = tk.Text(
            text_shell,
            bg="#ffffff",
            fg="#1e1f24",
            insertbackground="#1e1f24",
            selectbackground=self.colors.get("select", "#9bbcff"),
            selectforeground="#ffffff",
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors.get("line", "#dddddd"),
            highlightcolor=self.colors.get("accent", "#8e94ff"),
            wrap=tk.WORD,
            undo=True,
            font=("Segoe UI", 12),
            padx=26,
            pady=24,
        )
        scrollbar = tk.Scrollbar(text_shell, command=self.text.yview, relief=tk.FLAT, borderwidth=0)
        self.text.tag_configure("bold", font=("Segoe UI", 12, "bold"))
        self.text.tag_configure("italic", font=("Segoe UI", 12, "italic"))
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.bind("<KeyRelease>", self._changed)
        self.text.bind("<Control-s>", lambda _event: (self.owner.save_notebook_now(), "break")[1])
        self.text.bind("<Control-b>", lambda _event: self.shortcut(self.toggle_bold))
        self.text.bind("<Control-i>", lambda _event: self.shortcut(self.toggle_italic))
        self.text.bind("<Control-asterisk>", lambda _event: self.shortcut(self.insert_bullet))
        self.text.bind("<Control-8>", lambda _event: self.shortcut(self.insert_bullet))
        self.text.bind("<Button-3>", self.show_text_menu)
        self.text.bind("<Double-Button-1>", self.open_snippet_reference_at_cursor)
        self.text.bind("<Up>", self.handle_snippet_popup_navigation)
        self.text.bind("<Down>", self.handle_snippet_popup_navigation)
        self.text.bind("<Return>", self.handle_snippet_popup_navigation)
        self.text.bind("<Tab>", self.handle_snippet_popup_navigation)
        self.text.bind("<Escape>", self.handle_snippet_popup_navigation)

    def toolbar_button(self, parent, text, command, bold=False, italic=False):
        bg = self.colors.get("panel2", self.editor_background)
        fg = self.readable_text_on(bg)
        font = ("Segoe UI", 10, "bold" if bold else "italic" if italic else "normal")
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=self.colors.get("accent", "#8e94ff"),
            activeforeground=self.readable_text_on(self.colors.get("accent", "#8e94ff")),
            relief=tk.FLAT,
            borderwidth=0,
            width=3,
            font=font,
            cursor="hand2",
        )

    @property
    def editor_background(self):
        return self.colors.get("panel", "#f4f4f4")

    def readable_text_on(self, color):
        red, green, blue = self.color_to_rgb(color)
        luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
        return "#101018" if luminance > 0.55 else "#f7f8fb"

    def secondary_text_on(self, color):
        red, green, blue = self.color_to_rgb(color)
        luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
        return "#747985" if luminance > 0.55 else "#c9ced8"

    def color_to_rgb(self, color):
        try:
            value = str(color or "").lstrip("#")
            if len(value) == 3:
                value = "".join(character * 2 for character in value)
            return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
        except (ValueError, IndexError):
            return 245, 245, 245

    def _changed(self, _event=None):
        if not self.loading:
            self.refresh_snippet_completion(_event)
            self.on_change()

    def load_page(self, page, date_text, notebook_title=""):
        self.loading = True
        self.notebook_title_var.set(notebook_title)
        self.title_var.set(page.get("title", "Untitled Page") if page else "")
        self.date_var.set(date_text if page else "")
        self.text.delete("1.0", tk.END)
        if page:
            self.text.insert("1.0", page.get("content", ""))
            self.apply_spans(page.get("spans", []))
        self.loading = False

    def values(self):
        return self.title_var.get(), self.text.get("1.0", "end-1c"), self.spans()

    def focus_title(self):
        self.title.focus_set()
        self.title.selection_range(0, tk.END)

    def shortcut(self, command):
        command()
        return "break"

    def show_title_menu(self, event):
        menu = tk.Menu(self.owner, tearoff=0)
        menu.add_command(label="Cut", command=lambda: self.title.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: self.title.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: self.title.event_generate("<<Paste>>"))
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def show_text_menu(self, event):
        self.text.focus_set()
        menu = tk.Menu(self.owner, tearoff=0)
        menu.add_command(label="Cut", command=lambda: self.text.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: self.text.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: self.text.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Bold", command=self.toggle_bold)
        menu.add_command(label="Italic", command=self.toggle_italic)
        menu.add_command(label="Bullet point", command=self.insert_bullet)
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def toggle_bold(self):
        self.toggle_tag("bold")

    def toggle_italic(self):
        self.toggle_tag("italic")

    def toggle_tag(self, tag):
        try:
            start = self.text.index(tk.SEL_FIRST)
            end = self.text.index(tk.SEL_LAST)
        except tk.TclError:
            return
        if self.text.tag_ranges(tag) and tag in self.text.tag_names(start):
            self.text.tag_remove(tag, start, end)
        else:
            self.text.tag_add(tag, start, end)
        self.on_change()

    def insert_bullet(self):
        try:
            start = self.text.index(tk.SEL_FIRST)
            end = self.text.index(tk.SEL_LAST)
        except tk.TclError:
            start = self.text.index(tk.INSERT)
            line_start = self.text.index("{0} linestart".format(start))
            self.text.insert(line_start, "- ")
            self.on_change()
            return
        first_line = int(start.split(".", 1)[0])
        last_line = int(end.split(".", 1)[0])
        for line in range(first_line, last_line + 1):
            line_start = "{0}.0".format(line)
            if not self.text.get(line_start, "{0}+2c".format(line_start)) == "- ":
                self.text.insert(line_start, "- ")
        self.on_change()

    def spans(self):
        result = []
        content_length = len(self.text.get("1.0", "end-1c"))
        for tag in ("bold", "italic"):
            ranges = self.text.tag_ranges(tag)
            for index in range(0, len(ranges), 2):
                start = self.text.count("1.0", ranges[index], "chars")[0]
                end = self.text.count("1.0", ranges[index + 1], "chars")[0]
                if 0 <= start < end <= content_length:
                    result.append({"tag": tag, "start": start, "end": end})
        return result

    def apply_spans(self, spans):
        self.text.tag_remove("bold", "1.0", tk.END)
        self.text.tag_remove("italic", "1.0", tk.END)
        for span in spans or []:
            tag = span.get("tag")
            if tag not in {"bold", "italic"}:
                continue
            start = "1.0+{0}c".format(int(span.get("start", 0)))
            end = "1.0+{0}c".format(int(span.get("end", 0)))
            self.text.tag_add(tag, start, end)

    def refresh_snippet_completion(self, event=None):
        if event and event.keysym in {"Up", "Down", "Return", "Tab", "Escape", "Control_L", "Control_R", "Shift_L", "Shift_R"}:
            return
        trigger = self.current_at_trigger()
        if not trigger:
            self.hide_snippet_popup()
            return
        prefix, start_index, end_index = trigger
        options = self.snippet_options_for(prefix)
        if not options:
            self.hide_snippet_popup()
            return
        self.show_snippet_popup(options, start_index, end_index)

    def current_at_trigger(self):
        insert = self.text.index(tk.INSERT)
        line_start = self.text.index("{0} linestart".format(insert))
        before = self.text.get(line_start, insert)
        word_start = max(before.rfind(" "), before.rfind("\t"), before.rfind("\n")) + 1
        word = before[word_start:]
        if len(word) < 1 or word[0] != "@":
            return None
        if any(character in word for character in "([{,;"):
            return None
        return word[1:].lower(), "{0}+{1}c".format(line_start, word_start), insert

    def snippet_options_for(self, prefix):
        options = []
        for index, snippet in enumerate(getattr(self.owner, "snippets", []) or [], start=1):
            if snippet.get("generated_context"):
                continue
            fallback = str(snippet.get("id") or "snippet{0}".format(index))
            slug = snippet_mention_slug(str(snippet.get("description", "")), fallback)
            label = str(snippet.get("description", "") or snippet.get("source", "") or fallback)
            if prefix and not slug.lower().startswith(prefix) and not label.lower().replace(" ", "_").startswith(prefix):
                continue
            options.append({"insert": "@{0}".format(slug), "label": label, "slug": slug, "snippet": snippet})
        return options[:12]

    def show_snippet_popup(self, options, start_index, end_index):
        self.snippet_options = options
        self.snippet_at_range = (start_index, end_index)
        if not self.snippet_popup:
            popup = tk.Toplevel(self.owner)
            popup.withdraw()
            popup.overrideredirect(True)
            popup.configure(bg=self.colors.get("panel2", "#f5f5f5"))
            listbox = tk.Listbox(
                popup,
                height=min(8, len(options)),
                bg=self.colors.get("panel2", "#f5f5f5"),
                fg=self.readable_text_on(self.colors.get("panel2", "#f5f5f5")),
                selectbackground=self.colors.get("accent", "#8e94ff"),
                selectforeground=self.readable_text_on(self.colors.get("accent", "#8e94ff")),
                relief=tk.FLAT,
                borderwidth=0,
                highlightthickness=1,
                highlightbackground=self.colors.get("line", "#dddddd"),
                font=("Segoe UI", 9),
                activestyle="none",
                width=48,
            )
            listbox.pack(fill=tk.BOTH, expand=True)
            listbox.bind("<Double-Button-1>", self.open_selected_snippet_reference)
            self.snippet_popup = popup
            self.snippet_listbox = listbox
        self.snippet_listbox.delete(0, tk.END)
        self.snippet_listbox.configure(height=min(8, len(options)))
        for option in options:
            self.snippet_listbox.insert(tk.END, "@{0} - {1}".format(option["slug"], option["label"]))
        self.snippet_listbox.selection_clear(0, tk.END)
        self.snippet_listbox.selection_set(0)
        self.snippet_listbox.activate(0)
        x, y, _width, height = self.text.bbox(tk.INSERT) or (0, 0, 0, 18)
        self.snippet_popup.geometry("+{0}+{1}".format(self.text.winfo_rootx() + x, self.text.winfo_rooty() + y + height + 4))
        self.snippet_popup.deiconify()
        self.snippet_popup.lift()

    def handle_snippet_popup_navigation(self, event):
        if not self.snippet_popup:
            return None
        if event.keysym in {"Up", "Down"}:
            self.move_snippet_popup(-1 if event.keysym == "Up" else 1)
            return "break"
        if event.keysym in {"Return", "Tab"}:
            self.accept_snippet_reference()
            return "break"
        if event.keysym == "Escape":
            self.hide_snippet_popup()
            return "break"
        return None

    def move_snippet_popup(self, delta):
        current = self.snippet_listbox.curselection()
        index = current[0] if current else 0
        index = max(0, min(self.snippet_listbox.size() - 1, index + delta))
        self.snippet_listbox.selection_clear(0, tk.END)
        self.snippet_listbox.selection_set(index)
        self.snippet_listbox.activate(index)
        self.snippet_listbox.see(index)

    def accept_snippet_reference(self):
        if not self.snippet_options:
            return
        selection = self.snippet_listbox.curselection() if self.snippet_listbox else ()
        index = selection[0] if selection else 0
        if index < 0 or index >= len(self.snippet_options):
            return
        start_index, end_index = self.snippet_at_range
        self.text.delete(start_index, end_index)
        self.text.insert(start_index, self.snippet_options[index]["insert"])
        self.hide_snippet_popup()
        self.text.focus_set()
        self.on_change()

    def open_selected_snippet_reference(self, _event=None):
        selection = self.snippet_listbox.curselection() if self.snippet_listbox else ()
        index = selection[0] if selection else 0
        if 0 <= index < len(self.snippet_options):
            self.owner.open_snippet_source(self.snippet_options[index]["snippet"])
        self.hide_snippet_popup()
        return "break"

    def open_snippet_reference_at_cursor(self, _event=None):
        token = self.snippet_token_at_insert()
        if not token:
            return None
        for option in self.snippet_options_for(""):
            if option["slug"].lower() == token.lower().lstrip("@"):
                self.owner.open_snippet_source(option["snippet"])
                return "break"
        return None

    def snippet_token_at_insert(self):
        insert = self.text.index(tk.INSERT)
        line_start = self.text.index("{0} linestart".format(insert))
        line_end = self.text.index("{0} lineend".format(insert))
        line = self.text.get(line_start, line_end)
        column = int(insert.split(".", 1)[1])
        for match_start, match_end, token in self.tokens_in_line(line):
            if match_start <= column <= match_end:
                return token
        return ""

    def tokens_in_line(self, line):
        import re

        for match in re.finditer(r"@[A-Za-z0-9_.-]+", line or ""):
            yield match.start(), match.end(), match.group(0)

    def hide_snippet_popup(self):
        if self.snippet_popup:
            self.snippet_popup.destroy()
        self.snippet_popup = None
        self.snippet_listbox = None
        self.snippet_options = []
        self.snippet_at_range = None
