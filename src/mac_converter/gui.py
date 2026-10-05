"""Compact Tkinter interface; conversion rules live exclusively in mac.py."""

import tkinter as tk
from tkinter import ttk
from types import TracebackType

from . import __version__
from .mac import InvalidMacAddress, format_mac


class MacConverterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(f"MAC Address Converter {__version__}")
        root.resizable(True, False)
        root.report_callback_exception = self._report_callback_error

        self.input_value = tk.StringVar(root)
        self.output_format = tk.StringVar(root, value="colon")
        self.uppercase = tk.BooleanVar(root, value=False)
        self.result = tk.StringVar(root)
        self.status = tk.StringVar(root, value="Ready")

        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        fixed_font = (
            "Consolas" if root.tk.call("tk", "windowingsystem") == "win32" else "DejaVu Sans Mono",
            12,
        )

        frame = ttk.Frame(root, padding=18)
        frame.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Input").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.input_entry = ttk.Entry(
            frame, textvariable=self.input_value, font=fixed_font, width=34
        )
        self.input_entry.grid(row=1, column=0, sticky="ew")

        formats = ttk.LabelFrame(frame, text="Output format", padding=(10, 8))
        formats.grid(row=2, column=0, sticky="ew", pady=(15, 10))
        formats.columnconfigure(1, weight=1)
        self.format_buttons: dict[str, ttk.Radiobutton] = {}
        for row, (name, value, example) in enumerate(
            (
                ("Cisco", "cisco", "xxxx.xxxx.xxxx"),
                ("Colon", "colon", "xx:xx:xx:xx:xx:xx"),
                ("Hyphen", "hyphen", "xx-xx-xx-xx-xx-xx"),
                ("Plain", "plain", "xxxxxxxxxxxx"),
            )
        ):
            button = ttk.Radiobutton(formats, text=name, variable=self.output_format, value=value)
            button.grid(row=row, column=0, sticky="w", padx=(0, 22), pady=3)
            ttk.Label(formats, text=example, font=fixed_font).grid(
                row=row, column=1, sticky="w", pady=3
            )
            self.format_buttons[value] = button

        self.uppercase_button = ttk.Checkbutton(frame, text="UPPERCASE", variable=self.uppercase)
        self.uppercase_button.grid(row=3, column=0, sticky="w", pady=(0, 14))

        ttk.Label(frame, text="Result").grid(row=4, column=0, sticky="w", pady=(0, 5))
        result_row = ttk.Frame(frame)
        result_row.grid(row=5, column=0, sticky="ew")
        result_row.columnconfigure(0, weight=1)
        self.result_entry = ttk.Entry(
            result_row, textvariable=self.result, state="readonly", font=fixed_font
        )
        self.result_entry.grid(row=0, column=0, sticky="ew")
        self.copy_button = ttk.Button(
            result_row, text="Copy", command=self.copy_result, state="disabled"
        )
        self.copy_button.grid(row=0, column=1, padx=(9, 0))

        self.status_label = ttk.Label(frame, textvariable=self.status, wraplength=410)
        self.status_label.grid(row=6, column=0, sticky="w", pady=(12, 0))

        for variable in (self.input_value, self.output_format, self.uppercase):
            variable.trace_add("write", self._convert)
        for entry in (self.input_entry, self.result_entry):
            entry.bind("<Control-a>", self._select_all)
            entry.bind("<Control-A>", self._select_all)
        root.bind("<Control-l>", self.focus_input)
        root.bind("<Control-L>", self.focus_input)
        root.after_idle(self.input_entry.focus_set)

        root.update_idletasks()
        root.minsize(max(460, root.winfo_reqwidth()), root.winfo_reqheight())

    def _convert(self, *_trace_args: str) -> None:
        value = self.input_value.get()
        if not value.strip():
            self.result.set("")
            self.copy_button.state(["disabled"])
            self.status.set("Ready")
            return
        try:
            result = format_mac(value, self.output_format.get(), self.uppercase.get())
        except InvalidMacAddress as error:
            self.result.set("")
            self.copy_button.state(["disabled"])
            self.status.set(str(error))
            return
        self.result.set(result)
        self.copy_button.state(["!disabled"])
        self.status.set("Ready")

    def copy_result(self) -> None:
        result = self.result.get()
        if not result:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(result)
        except tk.TclError:
            self.status.set("Clipboard unavailable. Try Copy again.")
            return
        self.status.set("Copied")

    @staticmethod
    def _select_all(event: tk.Event) -> str:
        event.widget.selection_range(0, tk.END)
        event.widget.icursor(tk.END)
        return "break"

    def focus_input(self, _event: tk.Event | None = None) -> str:
        self.input_entry.focus_set()
        self.input_entry.selection_range(0, tk.END)
        return "break"

    def _report_callback_error(
        self,
        _exception: type[BaseException],
        _value: BaseException,
        _traceback: TracebackType | None,
    ) -> None:
        # Do not expose a traceback or persist user-entered MAC addresses.
        self.result.set("")
        self.copy_button.state(["disabled"])
        self.status.set("Unexpected error. Restart the application.")
