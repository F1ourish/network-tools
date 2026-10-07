"""Numbered ACL text editor with scrollbars that follow the visible range."""

import tkinter as tk
from tkinter import font

import ttkbootstrap as ttk


class AutoScrollbar(ttk.Scrollbar):
    def set(self, first, last):
        if float(first) <= 0 and float(last) >= 1:
            self.grid_remove()
        else:
            self.grid()
        super().set(first, last)


class AclEditor(ttk.Frame):
    def __init__(self, app, parent, *, height=7, changed=None):
        super().__init__(parent)
        self.app, self.changed = app, changed
        self.error_line = None
        self._draw_job = None
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.gutter = tk.Canvas(self, width=38, height=1, highlightthickness=0, takefocus=False)
        self.gutter.grid(row=0, column=0, sticky="ns")
        self.text = tk.Text(
            self,
            height=height,
            width=30,
            wrap="none",
            font=app.fixed_font,
            takefocus=True,
            undo=True,
            maxundo=100,
        )
        self.text.grid(row=0, column=1, sticky="nsew")
        self.text.acl_normalize = True
        self.vertical = AutoScrollbar(
            self, orient="vertical", command=self.text.yview, takefocus=False
        )
        self.vertical.grid(row=0, column=2, sticky="ns")
        self.horizontal = AutoScrollbar(
            self, orient="horizontal", command=self.text.xview, takefocus=False
        )
        self.horizontal.grid(row=1, column=1, sticky="ew")
        self.text.configure(yscrollcommand=self._yscroll, xscrollcommand=self.horizontal.set)
        app._bind_selection(self.text)
        self.text.bind("<Tab>", app._traverse_text)
        self.text.bind("<Shift-Tab>", lambda e: app._traverse_text(e, backwards=True))
        self.text.bind("<ISO_Left_Tab>", lambda e: app._traverse_text(e, backwards=True))
        self.text.bind("<<Modified>>", self._modified)
        self.text.bind("<Configure>", lambda _e: self.redraw_later())
        self.gutter.bind("<MouseWheel>", self._wheel)
        app._plain_text_widgets.append(self.text)
        app._canvases.append(self.gutter)

    def _modified(self, event):
        if self.text.edit_modified():
            if self.changed:
                self.changed(event)
            self.text.edit_modified(False)
        self.redraw_later()

    def _yscroll(self, first, last):
        self.vertical.set(first, last)
        self.redraw_later()

    def _wheel(self, event):
        self.text.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def redraw_later(self):
        if self._draw_job is None and self.winfo_exists():
            self._draw_job = self.after_idle(self.redraw)

    def redraw(self):
        self._draw_job = None
        self.gutter.configure(background=self.text.cget("background"))
        self.gutter.delete("all")
        total = int(self.text.index("end-1c").split(".")[0])
        face = font.Font(font=self.app.fixed_font)
        width = max(38, face.measure(str(total)) + 14)
        self.gutter.configure(width=width)
        index = self.text.index("@0,0")
        while info := self.text.dlineinfo(index):
            line = int(index.split(".")[0])
            self.gutter.create_text(
                width - 7,
                info[1],
                anchor="ne",
                text=str(line),
                font=self.app.fixed_font,
                fill=self.app.style.colors.danger
                if line == self.error_line
                else self.text.cget("foreground"),
            )
            index = self.text.index(f"{index}+1line")
            if int(index.split(".")[0]) > total:
                break

    def show_error(self, line=None):
        self.error_line = line
        self.text.tag_remove("acl_error", "1.0", "end")
        if line is not None:
            self.text.tag_configure(
                "acl_error", background=self.app.style.colors.danger, foreground="white"
            )
            self.text.tag_add("acl_error", f"{line}.0", f"{line}.end")
            self.text.see(f"{line}.0")
        self.redraw_later()

    def set_text(self, value):
        if self.text.get("1.0", "end-1c") == value:
            return
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.text.edit_modified(False)
        self.redraw_later()

    def destroy(self):
        if self._draw_job is not None:
            self.after_cancel(self._draw_job)
        if self.text in self.app._plain_text_widgets:
            self.app._plain_text_widgets.remove(self.text)
        if self.gutter in self.app._canvases:
            self.app._canvases.remove(self.gutter)
        super().destroy()
