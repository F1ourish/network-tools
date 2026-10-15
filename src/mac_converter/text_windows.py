"""Live expanded views for route, ACL and ARP fields."""

import tkinter as tk

import ttkbootstrap as ttk

from .acl_editor import AclEditor


def open_text_field(app, source, title, *, numbered=False):
    if not hasattr(app, "_text_windows"):
        app._text_windows = {}
    if source in app._text_windows:
        view = app._text_windows[source]
        view.window.deiconify()
        view.window.lift()
        view.text.focus_set()
    else:
        app._text_windows[source] = TextWindow(app, source, title, numbered=numbered)
    return "break"


class TextWindow:
    def __init__(self, app, source, title, *, numbered):
        self.app, self.source = app, source
        self.syncing = False
        self.readonly = str(source.cget("state")) == "disabled"
        window = self.window = tk.Toplevel(app.root)
        window.title(title + " - Network Tools")
        window.geometry(
            f"{max(640, app.root.winfo_screenwidth() - 60)}x{max(400, app.root.winfo_screenheight() - 100)}+20+20"
        )
        window.minsize(600, 400)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        ttk.Label(
            window,
            text=title
            + (
                " · результат обновляется вместе с вкладкой"
                if self.readonly
                else " · изменения сохраняются во вкладке"
            ),
            padding=12,
        ).grid(row=0, column=0, sticky="ew")
        if numbered:
            editor = AclEditor(app, window, height=20, changed=self._edited)
            area, self.text = editor, editor.text
        else:
            area, self.text = app._text_widget(window, height=20, readonly=self.readonly)
            if not self.readonly:
                self.text.configure(undo=True, maxundo=100)
                self.text.bind("<<Modified>>", self._edited)
        area.grid(row=1, column=0, sticky="nsew", padx=12)
        for name in ("acl_normalize", "paste_normalizer"):
            if hasattr(source, name):
                setattr(self.text, name, getattr(source, name))
        self.source_binding = source.bind("<<Modified>>", self._source_changed, add="+")
        self._source_changed()
        self.text.bind("<Control-Return>", self.close)
        controls = ttk.Frame(window, padding=12)
        controls.grid(row=2, column=0, sticky="ew")
        if not self.readonly:
            ttk.Button(
                controls, text="Вставить", command=lambda: app._paste(self.text, replace=True)
            ).pack(side="left", padx=(0, 6))
        ttk.Button(
            controls, text="Копировать", command=lambda: app._copy(self.text.get("1.0", "end-1c"))
        ).pack(side="left")
        ttk.Button(controls, text="Вернуться · Esc", command=self.close).pack(side="right")
        window.bind("<Escape>", self.close)
        window.bind("<Control-KeyPress>", self._key)
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.bind("<Destroy>", self._destroyed)
        try:
            window.state("zoomed")
        except tk.TclError:
            pass
        app._apply_theme()
        window.after_idle(self.text.focus_set)

    def _source_changed(self, _event=None):
        if self.syncing or not self.text.winfo_exists():
            return
        self.syncing = True
        try:
            value = self.source.get("1.0", "end-1c")
            if value != self.text.get("1.0", "end-1c"):
                self.text.configure(state="normal")
                self.text.delete("1.0", "end")
                self.text.insert("1.0", value)
                if self.readonly:
                    self.text.configure(state="disabled")
                self.text.edit_modified(False)
            self.source.edit_modified(False)
        finally:
            self.syncing = False

    def _edited(self, _event=None):
        if self.syncing or not self.text.edit_modified():
            return
        self.syncing = True
        try:
            value = self.text.get("1.0", "end-1c")
            if value != self.source.get("1.0", "end-1c"):
                self.source.delete("1.0", "end")
                self.source.insert("1.0", value)
            self.text.edit_modified(False)
        finally:
            self.syncing = False

    def _key(self, event):
        key = (
            event.keycode == 76
            if self.app.root.tk.call("tk", "windowingsystem") == "win32"
            else event.keysym.lower() == "l"
        )
        if key:
            self.text.focus_set()
            self.text.tag_add(tk.SEL, "1.0", "end-1c")
            return "break"
        return None

    def close(self, _event=None):
        self.window.destroy()
        if self.source.winfo_exists():
            self.app.root.lift()
            self.source.focus_set()
        return "break"

    def _destroyed(self, event):
        if event.widget == self.window:
            if self.source.winfo_exists():
                self.source.unbind("<<Modified>>", self.source_binding)
            if self.text in self.app._plain_text_widgets:
                self.app._plain_text_widgets.remove(self.text)
            self.app._text_windows.pop(self.source, None)
