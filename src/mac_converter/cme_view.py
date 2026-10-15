"""Resizable CUCME result surface with readable text and a real paired table."""

import tkinter as tk
from tkinter import font

import ttkbootstrap as ttk
from ttkbootstrap.widgets import ToolTip

from .acl_editor import AutoScrollbar


def expand_button(parent, command, title):
    button = ttk.Button(parent, text="↗", width=3, command=command, bootstyle="secondary-outline")
    ToolTip(button, text=title, delay=500)
    return button


class CMEReportView(ttk.Frame):
    def __init__(self, app, parent, *, large=False):
        super().__init__(parent)
        self.app = app
        self.rows = ()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.text_frame, self.text = app._text_widget(self, height=4, readonly=True)
        self.text.configure(font="TkDefaultFont", spacing1=2, spacing3=2)
        self.text_frame.grid(row=0, column=0, sticky="nsew")
        self.heading_font = font.nametofont("TkDefaultFont").copy()
        self.heading_font.configure(weight="bold", size=11 if large else 10)
        self.text.tag_configure("heading", font=self.heading_font, spacing1=7, spacing3=3)
        self.table_frame = ttk.Frame(self)
        self.table_frame.grid(row=0, column=0, sticky="nsew")
        self.table_frame.columnconfigure(0, weight=1)
        self.table_frame.rowconfigure(1, weight=1)
        self.summary = tk.StringVar(app.root)
        summary = ttk.Label(self.table_frame, textvariable=self.summary, padding=(0, 3))
        summary.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.table = ttk.Treeview(
            self.table_frame,
            columns=("number", "ephone", "dn"),
            show="headings",
            height=4,
            selectmode="extended",
            takefocus=True,
        )
        for name, title, width in (
            ("number", "Номер", 75),
            ("ephone", "ephone", 260),
            ("dn", "ephone-dn", 280),
        ):
            self.table.heading(name, text=title)
            self.table.column(name, width=width, minwidth=60, stretch=name != "number", anchor="w")
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
        self.table_frame.bind(
            "<Configure>", lambda event: summary.configure(wraplength=max(200, event.width - 12))
        )
        self.table_frame.grid_remove()

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
            self.summary.set("\n".join(value.splitlines()[:2]))
            self.table.yview_moveto(0)
        else:
            self.table_frame.grid_remove()
            self.text_frame.grid()
            self.table.delete(*self.table.get_children())
            for index, line in enumerate(value.splitlines(), 1):
                if line.startswith(("ephone ", "ephone-dn ", "Переадресации:")):
                    self.text.tag_add("heading", f"{index}.0", f"{index}.end")

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
            value = "Номер\tephone\tephone-dn\n" + "\n".join(
                "\t".join(map(str, self.table.item(item, "values"))) for item in selected
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
        if self.text in self.app._plain_text_widgets:
            self.app._plain_text_widgets.remove(self.text)
        super().destroy()
