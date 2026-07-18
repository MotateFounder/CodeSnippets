import tkinter as tk


class WidgetHintsMixin:
    def set_text_command_placeholder(self, widget, text):
        """Show a visual-only hint that never becomes part of the Text value."""
        label = tk.Label(
            widget,
            text=text,
            bg=self.colors["editor"],
            fg=self.colors["muted"],
            justify=tk.LEFT,
            anchor="nw",
            font=("Segoe UI", 9, "italic"),
            padx=0,
            pady=0,
        )
        widget.command_placeholder_label = label

        def refresh(_event=None):
            try:
                has_text = bool(widget.get("1.0", "end-1c").strip())
                focused = widget.focus_get() == widget
            except tk.TclError:
                return
            if has_text or focused:
                label.place_forget()
            else:
                label.place(x=10, y=8, anchor="nw")

        label.bind("<Button-1>", lambda _event: widget.focus_set())
        widget.bind("<FocusIn>", refresh, add="+")
        widget.bind("<FocusOut>", refresh, add="+")
        widget.bind("<KeyRelease>", refresh, add="+")
        widget.refresh_command_placeholder = refresh
        widget.after_idle(refresh)
        return label

    def refresh_text_command_placeholder(self, widget):
        refresh = getattr(widget, "refresh_command_placeholder", None)
        if refresh:
            widget.after_idle(refresh)

    def attach_tooltip(self, widget, text, delay_ms=450):
        tooltip = {"window": None, "after_id": None}

        def hide(_event=None):
            after_id = tooltip.get("after_id")
            if after_id:
                try:
                    widget.after_cancel(after_id)
                except tk.TclError:
                    pass
                tooltip["after_id"] = None
            window = tooltip.get("window")
            if window:
                try:
                    window.destroy()
                except tk.TclError:
                    pass
                tooltip["window"] = None

        def show():
            if tooltip.get("window"):
                return
            window = tk.Toplevel(widget)
            window.withdraw()
            window.overrideredirect(True)
            window.configure(bg=self.colors["panel2"])
            label = tk.Label(
                window,
                text=text,
                bg=self.colors["panel2"],
                fg=self.colors["text"],
                justify=tk.LEFT,
                anchor="w",
                wraplength=320,
                padx=10,
                pady=7,
                font=("Segoe UI", 8),
            )
            label.pack()
            x = widget.winfo_rootx() + 12
            y = widget.winfo_rooty() + widget.winfo_height() + 6
            window.geometry("+{0}+{1}".format(x, y))
            window.deiconify()
            window.lift()
            tooltip["window"] = window

        def schedule(_event=None):
            hide()
            tooltip["after_id"] = widget.after(delay_ms, show)

        widget.bind("<Enter>", schedule, add="+")
        widget.bind("<Leave>", hide, add="+")
        widget.bind("<ButtonPress>", hide, add="+")
        return widget

