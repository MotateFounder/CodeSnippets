import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from src.services.notebook.data_storage import NotebookStorage
from src.services.notebook.note_editor import PlainNoteEditor
from src.services.notebook.operations import (
    add_notebook,
    add_page,
    delete_notebook,
    delete_page,
    duplicate_notebook,
    duplicate_page,
    display_datetime,
    ensure_sample_data,
    filter_pages,
    rename_notebook,
    rename_page,
    selected_notebook,
    selected_page,
    timestamp,
    update_page_content,
)


class NotebookMixin:
    def initialize_notebook(self):
        self.notebook_dir = Path(__file__).resolve().parent
        self.notebook_store = NotebookStorage(self.notebook_dir)
        self.notebook_data = ensure_sample_data(self.notebook_store.load())
        self.notebook_data = self.notebook_store.save(self.notebook_data)
        self.notebook_dirty = False
        self.notebook_loading_editor = False
        self.notebook_search_after_id = None
        self.notebook_autosave_after_id = None
        self.notebook_page_items = {}
        self.notebook_items = {}
        self.notebook_search_var = tk.StringVar()
        self.schedule_notebook_periodic_save()

    def _notebook_pane(self, parent):
        frame = tk.Frame(parent, bg=self.colors["panel"])
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        self.build_notebook_navigation(frame)
        self.build_notebook_editor_area(frame)
        self.refresh_notebook_view()
        return frame

    def build_notebook_navigation(self, parent):
        nav_shell = tk.Frame(parent, bg=self.colors["panel"], width=330)
        nav_shell.grid(row=0, column=0, sticky="nsew")
        nav_shell.grid_propagate(False)
        nav_shell.rowconfigure(0, weight=1)
        nav_shell.columnconfigure(0, weight=1)

        self.notebook_nav_canvas = tk.Canvas(nav_shell, bg=self.colors["panel"], borderwidth=0, highlightthickness=0)
        self.notebook_nav_canvas.grid(row=0, column=0, sticky="nsew")
        nav_scroll = ttk.Scrollbar(nav_shell, orient=tk.VERTICAL, command=self.notebook_nav_canvas.yview)
        nav_scroll.grid(row=0, column=1, sticky="ns")
        self.notebook_nav_canvas.configure(yscrollcommand=nav_scroll.set)

        nav = tk.Frame(self.notebook_nav_canvas, bg=self.colors["panel"])
        self.notebook_nav_window = self.notebook_nav_canvas.create_window((0, 0), window=nav, anchor="nw")
        nav.bind("<Configure>", self.resize_notebook_navigation)
        nav.bind("<Enter>", self.bind_notebook_mousewheel)
        nav.bind("<Leave>", self.unbind_notebook_mousewheel)
        self.notebook_nav_canvas.bind("<Configure>", self.fit_notebook_navigation)
        self.notebook_nav_canvas.bind("<Enter>", self.bind_notebook_mousewheel)
        self.notebook_nav_canvas.bind("<Leave>", self.unbind_notebook_mousewheel)
        nav.columnconfigure(0, weight=1)

        button_bg = self.colors.get("accent", "#8e94ff")
        button_active_bg = self.lighten(button_bg, 0.35)
        search_block = tk.Frame(nav, bg=self.colors["panel"])
        search_block.grid(row=0, column=0, sticky="ew", padx=26, pady=(26, 14))
        search_block.columnconfigure(0, weight=1)
        tk.Label(
            search_block,
            text="Search",
            bg=self.colors["panel"],
            fg=self.readable_text_on(self.colors["panel"]),
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.notebook_search_entry = tk.Entry(
            search_block,
            textvariable=self.notebook_search_var,
            bg="#ffffff",
            fg="#2a2c33",
            insertbackground="#2a2c33",
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors.get("line", "#dddddd"),
            highlightcolor=self.colors.get("accent", "#8e94ff"),
            font=("Segoe UI", 11),
        )
        self.notebook_search_entry.grid(row=1, column=0, sticky="ew", ipady=6)
        self.notebook_search_entry.bind("<KeyRelease>", self.schedule_notebook_search)

        self.new_notebook_button = tk.Button(
            nav,
            text="NEW NOTEBOOK",
            command=self.create_notebook_from_button,
            bg=button_bg,
            fg=self.readable_text_on(button_bg),
            activebackground=button_active_bg,
            activeforeground=self.readable_text_on(button_active_bg),
            relief=tk.FLAT,
            borderwidth=0,
            font=("Segoe UI", 11),
            padx=12,
            pady=6,
            cursor="hand2",
        )
        self.new_notebook_button.grid(row=1, column=0, sticky="w", padx=26, pady=(0, 20))

        self.notebook_list_frame = tk.Frame(nav, bg=self.colors["panel"])
        self.notebook_list_frame.grid(row=2, column=0, sticky="ew", padx=(0, 0))

        separator = tk.Frame(nav, bg=self.colors.get("line", "#dddddd"), height=1)
        separator.grid(row=3, column=0, sticky="ew", padx=26, pady=(20, 22))

        self.selected_notebook_header = tk.Frame(nav, bg=self.selected_color())
        self.selected_notebook_header.grid(row=4, column=0, sticky="ew", padx=(0, 30), pady=(0, 8))
        self.selected_header_color = tk.Frame(self.selected_notebook_header, bg=self.colors.get("accent", "#8e94ff"), width=8)
        self.selected_header_color.pack(side=tk.LEFT, fill=tk.Y)
        self.selected_notebook_label = tk.Label(
            self.selected_notebook_header,
            text="",
            bg=self.selected_color(),
            fg=self.readable_text_on(self.selected_color()),
            anchor="w",
            font=("Segoe UI", 13, "bold"),
            padx=16,
            pady=12,
        )
        self.selected_notebook_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.page_list_frame = tk.Frame(nav, bg=self.colors["panel"])
        self.page_list_frame.grid(row=5, column=0, sticky="ew", padx=30, pady=(0, 16))

        self.new_page_button = tk.Button(
            nav,
            text="NEW PAGE",
            command=self.create_page_from_button,
            bg=button_bg,
            fg=self.readable_text_on(button_bg),
            activebackground=button_active_bg,
            activeforeground=self.readable_text_on(button_active_bg),
            relief=tk.FLAT,
            borderwidth=0,
            font=("Segoe UI", 13),
            padx=14,
            pady=8,
            cursor="hand2",
        )
        self.new_page_button.grid(row=6, column=0, sticky="w", padx=26, pady=(0, 28))

    def build_notebook_editor_area(self, parent):
        editor = tk.Frame(parent, bg=self.colors["panel"])
        editor.grid(row=0, column=1, sticky="nsew")
        editor.columnconfigure(0, weight=1)
        editor.rowconfigure(0, weight=1)

        self.note_editor = PlainNoteEditor(self, editor, self.colors, self.on_note_editor_changed)
        self.note_editor.frame.grid(row=0, column=0, sticky="nsew")

    def resize_notebook_navigation(self, _event=None):
        self.notebook_nav_canvas.configure(scrollregion=self.notebook_nav_canvas.bbox("all"))

    def fit_notebook_navigation(self, event):
        self.notebook_nav_canvas.itemconfigure(self.notebook_nav_window, width=event.width)

    def bind_notebook_mousewheel(self, _event=None):
        self.notebook_nav_canvas.bind_all("<MouseWheel>", self.on_notebook_mousewheel)

    def unbind_notebook_mousewheel(self, _event=None):
        self.notebook_nav_canvas.unbind_all("<MouseWheel>")

    def on_notebook_mousewheel(self, event):
        self.notebook_nav_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def refresh_notebook_view(self):
        selected_notebook(self.notebook_data)
        selected_page(self.notebook_data)
        self.refresh_notebook_list()
        self.refresh_page_list()
        self.load_selected_page()

    def refresh_notebook_list(self):
        for child in self.notebook_list_frame.winfo_children():
            child.destroy()
        self.notebook_items = {}
        current_id = self.notebook_data.get("selectedNotebookId", "")

        for notebook in self.notebook_data.get("notebooks", []):
            color = notebook.get("color", self.colors.get("accent", "#8e94ff"))
            is_selected = notebook.get("id") == current_id
            bg = self.lighten(color, 0.72) if is_selected else self.colors["panel"]
            fg = self.readable_text_on(bg)
            item = tk.Frame(self.notebook_list_frame, bg=bg, cursor="hand2")
            item.pack(fill=tk.X, padx=(0, 26), pady=0)
            swatch = tk.Frame(item, bg=color, width=8)
            swatch.pack(side=tk.LEFT, fill=tk.Y)
            label = tk.Label(
                item,
                text=notebook.get("name", "Untitled Notebook"),
                bg=bg,
                fg=fg,
                anchor="w",
                font=("Segoe UI", 12, "bold" if is_selected else "normal"),
                padx=18,
                pady=13,
            )
            label.pack(side=tk.LEFT, fill=tk.X, expand=True)

            self.bind_notebook_item(item, label, swatch, notebook["id"])
            self.notebook_items[notebook["id"]] = item

    def bind_notebook_item(self, *widgets_and_id):
        notebook_id = widgets_and_id[-1]
        for widget in widgets_and_id[:-1]:
            widget.bind("<Button-1>", lambda _event, value=notebook_id: self.select_notebook(value))
            widget.bind("<Button-3>", lambda event, value=notebook_id: self.show_notebook_menu(event, value))

    def refresh_page_list(self):
        for child in self.page_list_frame.winfo_children():
            child.destroy()
        self.notebook_page_items = {}
        notebook = selected_notebook(self.notebook_data)
        if not notebook:
            self.selected_notebook_label.configure(text="")
            return

        header_bg = self.lighten(notebook.get("color", "#7c83ff"), 0.72)
        self.selected_notebook_header.configure(bg=header_bg)
        self.selected_header_color.configure(bg=notebook.get("color", "#7c83ff"))
        self.selected_notebook_label.configure(
            text=notebook.get("name", "Untitled Notebook"),
            bg=header_bg,
            fg=self.readable_text_on(header_bg),
        )

        current_id = self.notebook_data.get("selectedPageId", "")
        for page in filter_pages(notebook, self.notebook_search_var.get()):
            is_selected = page.get("id") == current_id
            bg = self.selected_color() if is_selected else self.colors["panel"]
            fg = self.readable_text_on(bg)
            label = tk.Label(
                self.page_list_frame,
                text=page.get("title", "Untitled Page"),
                bg=bg,
                fg=fg,
                anchor="w",
                font=("Segoe UI", 15),
                padx=28,
                pady=6,
                cursor="hand2",
            )
            label.pack(fill=tk.X, pady=1)
            label.bind("<Button-1>", lambda _event, value=page["id"]: self.select_page(value))
            label.bind("<Button-3>", lambda event, value=page["id"]: self.show_page_menu(event, value))
            self.notebook_page_items[page["id"]] = label

    def load_selected_page(self):
        notebook = selected_notebook(self.notebook_data)
        page = selected_page(self.notebook_data)
        self.notebook_loading_editor = True
        self.note_editor.load_page(
            page,
            display_datetime(page.get("updatedAt", "")) if page else "",
            notebook.get("name", "") if notebook else "",
        )
        self.notebook_loading_editor = False

    def select_notebook(self, notebook_id):
        self.sync_editor_to_page()
        self.notebook_data["selectedNotebookId"] = notebook_id
        notebook = selected_notebook(self.notebook_data)
        self.notebook_data["selectedPageId"] = notebook["pages"][0]["id"] if notebook and notebook.get("pages") else ""
        self.mark_notebook_dirty()
        self.refresh_notebook_view()

    def select_page(self, page_id):
        self.sync_editor_to_page()
        self.notebook_data["selectedPageId"] = page_id
        self.mark_notebook_dirty()
        self.refresh_page_list()
        self.load_selected_page()

    def create_notebook_from_button(self):
        name = simpledialog.askstring("New notebook", "Notebook name:", parent=self)
        if not name:
            return
        self.sync_editor_to_page()
        add_notebook(self.notebook_data, name)
        self.mark_notebook_dirty()
        self.refresh_notebook_view()
        self.note_editor.focus_title()

    def create_page_from_button(self):
        title = simpledialog.askstring("New page", "Page title:", parent=self)
        if title is None:
            return
        self.sync_editor_to_page()
        add_page(self.notebook_data, title or "Untitled Page")
        self.mark_notebook_dirty()
        self.refresh_notebook_view()
        self.note_editor.focus_title()

    def show_notebook_menu(self, event, notebook_id):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Rename notebook", command=lambda: self.rename_notebook_from_menu(notebook_id))
        menu.add_command(label="Duplicate notebook", command=lambda: self.duplicate_notebook_from_menu(notebook_id))
        menu.add_command(label="Delete notebook", command=lambda: self.delete_notebook_from_menu(notebook_id))
        menu.tk_popup(event.x_root, event.y_root)

    def show_page_menu(self, event, page_id):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Rename page", command=lambda: self.rename_page_from_menu(page_id))
        menu.add_command(label="Duplicate page", command=lambda: self.duplicate_page_from_menu(page_id))
        menu.add_command(label="Delete page", command=lambda: self.delete_page_from_menu(page_id))
        menu.tk_popup(event.x_root, event.y_root)

    def rename_notebook_from_menu(self, notebook_id):
        notebook = next((item for item in self.notebook_data.get("notebooks", []) if item.get("id") == notebook_id), None)
        if not notebook:
            return
        name = simpledialog.askstring("Rename notebook", "Notebook name:", initialvalue=notebook.get("name", ""), parent=self)
        if not name:
            return
        rename_notebook(notebook, name)
        self.mark_notebook_dirty()
        self.refresh_notebook_view()

    def rename_page_from_menu(self, page_id):
        notebook = selected_notebook(self.notebook_data)
        page = next((item for item in notebook.get("pages", []) if item.get("id") == page_id), None) if notebook else None
        if not page:
            return
        title = simpledialog.askstring("Rename page", "Page title:", initialvalue=page.get("title", ""), parent=self)
        if not title:
            return
        rename_page(page, title)
        self.mark_notebook_dirty()
        self.refresh_notebook_view()

    def duplicate_notebook_from_menu(self, notebook_id):
        self.sync_editor_to_page()
        if duplicate_notebook(self.notebook_data, notebook_id):
            self.mark_notebook_dirty()
            self.refresh_notebook_view()

    def duplicate_page_from_menu(self, page_id):
        self.sync_editor_to_page()
        if duplicate_page(self.notebook_data, page_id):
            self.mark_notebook_dirty()
            self.refresh_notebook_view()

    def delete_notebook_from_menu(self, notebook_id):
        notebook = next((item for item in self.notebook_data.get("notebooks", []) if item.get("id") == notebook_id), None)
        if not notebook:
            return
        if not messagebox.askyesno("Delete notebook", "Delete notebook '{0}'?".format(notebook.get("name", "Untitled Notebook"))):
            return
        delete_notebook(self.notebook_data, notebook_id)
        if not self.notebook_data.get("notebooks"):
            add_notebook(self.notebook_data, "Untitled Notebook")
        self.mark_notebook_dirty()
        self.refresh_notebook_view()

    def delete_page_from_menu(self, page_id):
        notebook = selected_notebook(self.notebook_data)
        page = next((item for item in notebook.get("pages", []) if item.get("id") == page_id), None) if notebook else None
        if not page:
            return
        if not messagebox.askyesno("Delete page", "Delete page '{0}'?".format(page.get("title", "Untitled Page"))):
            return
        delete_page(self.notebook_data, page_id)
        if notebook and not notebook.get("pages"):
            add_page(self.notebook_data, "Untitled Page")
        self.mark_notebook_dirty()
        self.refresh_notebook_view()

    def on_note_editor_changed(self):
        if self.notebook_loading_editor:
            return
        self.sync_editor_to_page()
        self.mark_notebook_dirty()
        self.refresh_page_list()

    def sync_editor_to_page(self):
        page = selected_page(self.notebook_data)
        if not page or not hasattr(self, "note_editor"):
            return False
        title, content, spans = self.note_editor.values()
        changed = update_page_content(page, title, content, spans)
        if changed:
            notebook = selected_notebook(self.notebook_data)
            if notebook:
                notebook["updatedAt"] = timestamp()
        return changed

    def schedule_notebook_search(self, _event=None):
        if self.notebook_search_after_id:
            self.after_cancel(self.notebook_search_after_id)
        self.notebook_search_after_id = self.after(120, self.refresh_page_list)

    def mark_notebook_dirty(self):
        self.notebook_dirty = True

    def schedule_notebook_periodic_save(self):
        if self.notebook_autosave_after_id:
            try:
                self.after_cancel(self.notebook_autosave_after_id)
            except tk.TclError:
                pass
        self.notebook_autosave_after_id = self.after(30000, self.periodic_notebook_save)

    def periodic_notebook_save(self):
        self.save_notebook_now()
        self.schedule_notebook_periodic_save()

    def save_notebook_now(self):
        if hasattr(self, "note_editor"):
            self.sync_editor_to_page()
        try:
            self.notebook_data = self.notebook_store.save(self.notebook_data)
            self.notebook_dirty = False
            if hasattr(self, "status"):
                self.status.configure(text="Notebook saved.")
        except OSError as exc:
            self.notebook_dirty = True
            messagebox.showerror("Save notebook failed", "Could not save notes:\n{0}".format(exc))

    def selected_color(self):
        return self.lighten(self.colors.get("select", "#9bbcff"), 0.70)

    def readable_text_on(self, color):
        red, green, blue = self.color_to_rgb(color)
        luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
        return "#101018" if luminance > 0.55 else "#f7f8fb"

    def color_to_rgb(self, color):
        try:
            value = str(color or "").lstrip("#")
            if len(value) == 3:
                value = "".join(character * 2 for character in value)
            return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
        except (ValueError, IndexError):
            return 245, 245, 245

    def lighten(self, color, amount):
        red, green, blue = self.color_to_rgb(color)
        red = int(red + (255 - red) * amount)
        green = int(green + (255 - green) * amount)
        blue = int(blue + (255 - blue) * amount)
        return "#{0:02x}{1:02x}{2:02x}".format(red, green, blue)
