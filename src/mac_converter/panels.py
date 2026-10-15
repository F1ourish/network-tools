"""Shared field grips, bounded resizing and explicit expansion controls."""

import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.widgets import ToolTip


def expand_button(parent, command, title="Развернуть поле · Ctrl+Enter", **options):
    button = ttk.Button(
        parent, text="Развернуть", command=command, bootstyle="secondary-outline", **options
    )
    ToolTip(button, text=title, delay=500)
    return button


class ResizableArea(ttk.Frame):
    """Fill a slot by default; grips resize locally or redistribute adjacent slots."""

    grip = 9

    def __init__(self, app, parent, *, height=100, width=180, vertical="bottom", side="right"):
        super().__init__(parent, height=height, width=width, takefocus=False)
        self.app = app
        self.body = ttk.Frame(self)
        self.vertical_side, self.horizontal_side = vertical, side
        self.width_fraction = self.height_fraction = 1.0
        self.resize_x = self.resize_y = None
        self.reset_x = self.reset_y = None
        self._drag = None
        self._extent = (width, height)
        self.handles = {}
        for axes, cursor, hint in (
            ("x", "sb_h_double_arrow", "Изменить ширину"),
            ("y", "sb_v_double_arrow", "Изменить высоту"),
            ("xy", "sizing", "Изменить ширину и высоту"),
        ):
            handle = tk.Canvas(
                self, highlightthickness=0, borderwidth=0, cursor=cursor, takefocus=False
            )
            self.handles[axes] = handle
            handle.bind("<ButtonPress-1>", lambda event, a=axes: self._start(event, a))
            handle.bind("<B1-Motion>", self._motion)
            handle.bind("<ButtonRelease-1>", self._release)
            handle.bind("<Double-Button-1>", self.reset_size)
            ToolTip(handle, text=hint + ". Двойной щелчок - автоматический размер.", delay=650)
        if not hasattr(app, "_resize_areas"):
            app._resize_areas = []
        app._resize_areas.append(self)
        self.bind("<Configure>", self._layout)
        self.apply_theme()

    def _layout(self, _event=None):
        available_w, available_h = self.winfo_width(), self.winfo_height()
        width = min(available_w, max(100, round(available_w * self.width_fraction)))
        height = min(available_h, max(48, round(available_h * self.height_fraction)))
        self._extent = width, height
        g = self.grip
        left = g if self.horizontal_side == "left" else 0
        top = g if self.vertical_side == "top" else 0
        x = 0 if left else max(0, width - g)
        y = 0 if top else max(0, height - g)
        self.body.place(x=left, y=top, width=max(1, width - g), height=max(1, height - g))
        self.handles["x"].place(x=x, y=top, width=g, height=max(1, height - g))
        self.handles["y"].place(x=left, y=y, width=max(1, width - g), height=g)
        self.handles["xy"].place(x=x, y=y, width=g, height=g)
        self._draw_grips()

    def _draw_grips(self):
        color = self.app.style.colors.secondary
        for axes, handle in self.handles.items():
            handle.delete("all")
            if axes == "x":
                middle = max(10, self._extent[1] // 2)
                for x in (3, 6):
                    handle.create_line(x, middle - 12, x, middle + 12, fill=color)
            elif axes == "y":
                middle = max(10, self._extent[0] // 2)
                for y in (3, 6):
                    handle.create_line(middle - 12, y, middle + 12, y, fill=color)
            else:
                for offset in (2, 5, 8):
                    handle.create_line(offset, 8, 8, offset, fill=color)

    def apply_theme(self):
        for handle in self.handles.values():
            handle.configure(background=self.app.style.colors.bg)
        self._draw_grips()

    def _local_resize(self, axis):
        index = 0 if axis == "x" else 1
        initial = self._extent[index]
        positive = (
            self.horizontal_side == "right" if axis == "x" else self.vertical_side == "bottom"
        )

        def move(delta):
            available = self.winfo_width() if axis == "x" else self.winfo_height()
            minimum = 100 if axis == "x" else 48
            extent = min(available, max(minimum, initial + (delta if positive else -delta)))
            setattr(
                self,
                "width_fraction" if axis == "x" else "height_fraction",
                extent / max(1, available),
            )
            self._layout()

        return move

    def _start(self, event, axes):
        self._drag = (event.x_root, event.y_root, {})
        for axis in axes:
            factory = self.resize_x if axis == "x" else self.resize_y
            self._drag[2][axis] = factory() if factory else self._local_resize(axis)
        event.widget.grab_set()
        return "break"

    def _motion(self, event):
        if self._drag is not None:
            x, y, callbacks = self._drag
            for axis, move in callbacks.items():
                move(event.x_root - x if axis == "x" else event.y_root - y)
        return "break"

    def _release(self, event):
        self._drag = None
        if self.grab_current() == event.widget:
            event.widget.grab_release()
        return "break"

    def reset_size(self, _event=None):
        self.width_fraction = self.height_fraction = 1.0
        for callback in (self.reset_x, self.reset_y):
            if callback:
                callback()
        self._layout()
        return "break"

    def destroy(self):
        if self in self.app._resize_areas:
            self.app._resize_areas.remove(self)
        super().destroy()


def grid_split(parent, first, second, *, axis, slots, areas):
    """Give both adjacent field grips control of one bounded grid divider."""
    configure = parent.columnconfigure if axis == "x" else parent.rowconfigure
    dimension = "width" if axis == "x" else "height"
    requested = "winfo_req" + dimension

    def slot_size(slot):
        columns, rows = parent.grid_size()
        bounds = (
            parent.grid_bbox(slot, 0, slot, rows - 1)
            if axis == "x"
            else parent.grid_bbox(0, slot, columns - 1, slot)
        )
        return bounds[2 if axis == "x" else 3]

    def minimum(slot):
        values = []
        for child in parent.grid_slaves(**{"column" if axis == "x" else "row": slot}):
            info = child.grid_info()
            if int(info.get("columnspan" if axis == "x" else "rowspan", 1)) != 1:
                continue
            raw_padding = info["padx" if axis == "x" else "pady"]
            padding = (
                raw_padding
                if isinstance(raw_padding, (tuple, list))
                else parent.tk.splitlist(str(raw_padding))
            )
            pad = [parent.winfo_pixels(value) for value in padding]
            values.append(getattr(child, requested)() + (2 * pad[0] if len(pad) == 1 else sum(pad)))
        return max(values, default=0)

    def begin():
        initial = slot_size(slots[0])
        total = initial + slot_size(slots[1])
        low, last_min = minimum(slots[0]), minimum(slots[1])
        high = total - last_min

        def move(delta):
            target = min(max(low, initial + delta), max(low, high))
            configure(slots[0], weight=max(1, target - low), uniform="")
            configure(slots[1], weight=max(1, total - target - last_min), uniform="")

        return move

    def reset():
        for slot in slots:
            configure(slot, weight=1, uniform="")

    for area in areas:
        setattr(area, "resize_" + axis, begin)
        setattr(area, "reset_" + axis, reset)


def pane_split(panes, areas):
    """Expose the same vertical sash on the lower input and upper result edges."""

    def begin():
        initial = panes.sashpos(0)

        def move(delta):
            height = panes.winfo_height()
            low = max(80, areas[0].master.winfo_reqheight() - areas[0].winfo_reqheight() + 48)
            last = max(110, areas[1].master.winfo_reqheight() - areas[1].winfo_reqheight() + 48)
            panes.sashpos(0, min(max(low, initial + delta), max(low, height - last)))

        return move

    for area in areas:
        area.resize_y = begin
        area.reset_y = lambda: panes.sashpos(0, panes.winfo_height() // 2)
