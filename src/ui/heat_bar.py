import tkinter as tk


class WidgetTooltip:
    def __init__(self, widget, text=""):
        self.widget = widget
        self.text = text
        self.window = None
        self.after_id = None
        self.hide_after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide_later, add="+")
        widget.bind("<Motion>", self._move, add="+")

    def set_text(self, text):
        self.text = str(text or "")
        if self.window:
            self._hide()

    def _schedule(self, event=None):
        self._cancel()
        self._cancel_hide()
        self.after_id = self.widget.after(350, lambda: self._show(event))

    def _cancel(self):
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except tk.TclError:
                pass
        self.after_id = None

    def _cancel_hide(self):
        if self.hide_after_id:
            try:
                self.widget.after_cancel(self.hide_after_id)
            except tk.TclError:
                pass
        self.hide_after_id = None

    def _show(self, event=None):
        if not self.text.strip() or self.window:
            return
        x = self.widget.winfo_pointerx() + 12
        y = self.widget.winfo_pointery() + 14
        window = tk.Toplevel(self.widget)
        window.withdraw()
        window.overrideredirect(True)
        window.configure(bg="#111827")
        label = tk.Label(
            window,
            text=self.text,
            justify=tk.LEFT,
            bg="#111827",
            fg="#f9fafb",
            padx=9,
            pady=7,
            font=("Segoe UI", 9),
        )
        label.pack()
        window.geometry("+{0}+{1}".format(x, y))
        window.deiconify()
        self.window = window

    def _move(self, _event=None):
        if not self.window:
            return
        x = self.widget.winfo_pointerx() + 12
        y = self.widget.winfo_pointery() + 14
        try:
            self.window.geometry("+{0}+{1}".format(x, y))
        except tk.TclError:
            self.window = None

    def _hide(self, _event=None):
        self._cancel()
        self._cancel_hide()
        if self.window:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
        self.window = None

    def _hide_later(self, _event=None):
        self._cancel()
        self._cancel_hide()
        self.hide_after_id = self.widget.after(5000, self._hide)


class HeatBar(tk.Canvas):
    """A compact canvas bar that fills with a red-to-green heat gradient."""

    HEIGHT = 10
    BACKGROUND = "#2f2f2f"
    STOPS = (
        (0.0, (220, 52, 47)),
        (0.35, (242, 142, 44)),
        (0.65, (245, 216, 74)),
        (1.0, (76, 175, 80)),
    )

    def __init__(self, master, length=160, value=0.0, **kwargs):
        self.length = max(1, int(length))
        self.value = self._clamp(value)
        super().__init__(
            master,
            width=self.length,
            height=self.HEIGHT,
            background=self.BACKGROUND,
            highlightthickness=0,
            bd=0,
            **kwargs
        )
        self.tooltip = WidgetTooltip(self, "")
        self.draw()

    def set_value(self, value):
        self.value = self._clamp(value)
        self.draw()

    def set_tooltip(self, text):
        self.tooltip.set_text(text)

    def draw(self):
        self.delete("all")
        self.create_rectangle(
            0,
            0,
            self.length,
            self.HEIGHT,
            fill=self.BACKGROUND,
            outline=self.BACKGROUND,
        )

        active_width = int(round(self.value * self.length))
        if active_width <= 0:
            return

        for x in range(active_width):
            color = self._gradient_color(x / max(1, self.length - 1))
            self.create_line(x, 0, x, self.HEIGHT, fill=color)

    def _gradient_color(self, position):
        position = self._clamp(position)
        stops = self.STOPS
        for index in range(len(stops) - 1):
            left_pos, left_color = stops[index]
            right_pos, right_color = stops[index + 1]
            if left_pos <= position <= right_pos:
                span = right_pos - left_pos
                amount = 0.0 if span == 0 else (position - left_pos) / span
                return self._interpolate_color(left_color, right_color, amount)
        return self._rgb_to_hex(stops[-1][1])

    def _interpolate_color(self, left, right, amount):
        amount = self._clamp(amount)
        rgb = tuple(
            int(round(left[channel] + (right[channel] - left[channel]) * amount))
            for channel in range(3)
        )
        return self._rgb_to_hex(rgb)

    def _rgb_to_hex(self, rgb):
        return "#{0:02x}{1:02x}{2:02x}".format(*rgb)

    def _clamp(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        return max(0.0, min(1.0, value))


if __name__ == "__main__":
    root = tk.Tk()
    root.title("HeatBar example")

    bar = HeatBar(root, length=240, value=0.25)
    bar.pack(padx=20, pady=20)

    scale = tk.Scale(
        root,
        from_=0.0,
        to=1.0,
        resolution=0.01,
        orient="horizontal",
        command=lambda value: bar.set_value(value),
    )
    scale.set(0.25)
    scale.pack(fill="x", padx=20, pady=(0, 20))

    root.mainloop()
