"""Resizable CUCME result surface with readable text and a real paired table."""

import tkinter as tk
from tkinter import font

import ttkbootstrap as ttk

from .acl_editor import AutoScrollbar
from .cme import PAIR_HEADERS, PAIR_MAC_NOTE
from .panels import ResizableArea


class CMEReportView(ResizableArea):
    def __init__(self, app, parent, *, large=False):
        super().__init__(app, parent, height=100, vertical="top")
        self.app = app
        self.rows = ()
        self._fit_job = None
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(0, weight=1)
        self.text_frame, self.text = app._text_widget(
            self.body, height=4, readonly=True, resizable=False
        )
        self.text.configure(font="TkDefaultFont", spacing1=2, spacing3=2)
        self.text_frame.grid(row=0, column=0, sticky="nsew")
        self.heading_font = font.nametofont("TkDefaultFont").copy()
        self.heading_font.configure(weight="bold", size=11 if large else 10)
        self.text.tag_configure("heading", font=self.heading_font, spacing1=7, spacing3=3)
        self.table_frame = ttk.Frame(self.body)
        self.table_frame.grid(row=0, column=0, sticky="nsew")
        self.table_frame.columnconfigure(0, weight=1)
        self.table_frame.rowconfigure(1, weight=1)
        self.summary = tk.StringVar(app.root)
        self.summary_label = ttk.Label(self.table_frame, textvariable=self.summary, padding=(0, 3))
        self.summary_label.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.table = ttk.Treeview(
            self.table_frame,
            columns=("number", "ephone", "dn", "mac"),
            show="headings",
            height=4,
            selectmode="extended",
            takefocus=True,
        )
        mac_width = max(178, font.nametofont("TkDefaultFont").measure("FFFF.FFFF.FFFF") + 28)
        for (name, width), title in zip(
            (("number", 75), ("ephone", 220), ("dn", 240), ("mac", mac_width)),
            PAIR_HEADERS,
            strict=True,
        ):
            self.table.heading(name, text=title)
            self.table.column(
                name,
                width=width,
                minwidth=mac_width if name == "mac" else 60,
                stretch=name in ("ephone", "dn"),
                anchor="w",
            )
        self.table.grid(row=1, column=0, sticky="nsew")
        vertical = AutoScrollbar(
            self.table_frame, orient="vertical", command=self.table.yview, takefocus=False
        )
        vertical.grid(row=1, column=1, sticky="ns")
        horizontal = AutoScrollbar(
            self.table_frame, orient="horizontal", command=self.table.xview, takefocus=False
        )
        horizontal.grid(row=2, column=0, sticky="ew")
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.table.bind("<Control-KeyPress>", self._table_key)
        self.table.bind("<Button-3>", self._table_menu)
        self.table.bind("<Shift-F10>", self._table_menu)
        self.table_frame.bind("<Configure>", self._table_layout)
        self.table_frame.grid_remove()

    def _table_layout(self, event):
        self.summary_label.configure(wraplength=max(200, event.width - 12))
        self._schedule_fit()

    def _schedule_fit(self):
        if self._fit_job is None:
            self._fit_job = self.after_idle(self._fit_table)

    def _fit_table(self):
        self._fit_job = None
        requested = max(100, self.table_frame.winfo_reqheight() + self.grip) if self.rows else 100
        self.minimum_height = requested if self.rows else 48
        if self.winfo_reqheight() != requested:
            self.configure(height=requested)
        if getattr(self.app, "cme_report_view", None) is self:
            self.app._cme_limit_panes()

    def set_report(self, value, rows=()):
        self.app._set_text(self.text, value)
        self.text.yview_moveto(0)
        self.rows = rows
        if rows:
            self.text_frame.grid_remove()
            self.table_frame.grid()
            self.table.delete(*self.table.get_children())
            for row in rows:
                self.table.insert("", "end", values=row)
            self.summary.set("\n".join([*value.splitlines()[:2], PAIR_MAC_NOTE]))
            self.table.yview_moveto(0)
        else:
            self.table_frame.grid_remove()
            self.text_frame.grid()
            self.table.delete(*self.table.get_children())
            for index, line in enumerate(value.splitlines(), 1):
                if line.startswith(("ephone ", "ephone-dn ", "Переадресации:")):
                    self.text.tag_add("heading", f"{index}.0", f"{index}.end")
        self._schedule_fit()

    def _table_key(self, event):
        if event.state & 1:
            return None
        key = (
            {65: "a", 67: "c"}.get(event.keycode)
            if self.app.root.tk.call("tk", "windowingsystem") == "win32"
            else event.keysym.lower()
        )
        if key == "a":
            self.table.selection_set(self.table.get_children())
            return "break"
        if key == "c":
            self.copy_rows()
            return "break"
        return None

    def copy_rows(self):
        selected = self.table.selection() or self.table.get_children()
        if selected:
            value = (
                "\t".join(PAIR_HEADERS)
                + "\n"
                + "\n".join(
                    "\t".join(map(str, self.table.item(item, "values"))) for item in selected
                )
            )
            self.app._copy(value)

    def _table_menu(self, event):
        menu = tk.Menu(self.table, tearoff=False)
        menu.add_command(label="Копировать строки", command=self.copy_rows)
        menu.add_command(
            label="Выделить все",
            command=lambda: self.table.selection_set(self.table.get_children()),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def focus_result(self):
        (self.table if self.rows else self.text).focus_set()

    def destroy(self):
        if self._fit_job is not None:
            self.after_cancel(self._fit_job)
        if self.text in self.app._plain_text_widgets:
            self.app._plain_text_widgets.remove(self.text)
        super().destroy()
