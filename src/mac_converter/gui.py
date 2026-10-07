"""Themed desktop tools; calculation rules are separate from widgets."""

from pathlib import Path
import re
import tkinter as tk
from tkinter import font
from types import TracebackType

import ttkbootstrap as ttk

from . import __version__
from .acl import check_conversation, make_flow
from .clipboard import ClipboardUnavailable, clear_if_matches
from .help_content import TOOL_HELP
from .mac import InvalidMacAddress, format_mac
from .passwords import (
    DEFAULT_SYMBOLS,
    InvalidPasswordOptions,
    PasswordOptions,
    entropy_bits,
    generate_password,
)
from .network import (
    InvalidNetworkInput,
    IPv4Calculation,
    calculate_ipv4,
    check_wildcard,
    host_page,
    lookup_routes,
)
from .mtu import BASES, CIPHERS, PROFILES, MtuOptions, calculate_mtu
from .settings import ThemeSettings


class OutputTable:
    def __init__(self, app, parent, labels):
        self.frame = ttk.Frame(parent)
        self.frame.columnconfigure(1, weight=1)
        self.values, self.entries, self.buttons = {}, {}, {}
        for row, label in enumerate(labels):
            value = tk.StringVar(app.root, value="-")
            self.values[label] = value
            ttk.Label(self.frame, text=label, wraplength=145).grid(
                row=row, column=0, sticky="w", padx=(0, 10), pady=4
            )
            entry = ttk.Entry(
                self.frame, textvariable=value, state="readonly", width=18, font=app.fixed_font
            )
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            app._bind_selection(entry)
            self.entries[label] = entry
            button = ttk.Button(
                self.frame,
                text="Copy",
                width=5,
                command=lambda variable=value: app._copy(variable.get()),
                state="disabled",
            )
            button.grid(row=row, column=2, padx=(7, 0), pady=4)
            self.buttons[label] = button

    def update(self, rows):
        for label, variable in self.values.items():
            variable.set(rows.get(label, "-"))
            self.buttons[label].state(["!disabled" if variable.get() != "-" else "disabled"])

    def clear(self):
        for label, variable in self.values.items():
            variable.set("-")
            self.buttons[label].state(["disabled"])


class MacConverterApp:
    def __init__(self, root: tk.Misc, *, settings_path: Path | None = None) -> None:
        self.root = root
        root.title(f"MAC Address Converter {__version__} - Network Tools")
        root.resizable(True, True)
        root.report_callback_exception = self._report_callback_error
        self.settings = ThemeSettings(settings_path)
        self.theme = tk.StringVar(root, value=self.settings.load())
        self.theme_label = tk.StringVar(
            root, value="Дневная" if self.theme.get() == "day" else "Ночная"
        )
        self.style = ttk.Style()
        windows = root.tk.call("tk", "windowingsystem") == "win32"
        self.fixed_font = ("Consolas" if windows else "DejaVu Sans Mono", 10)
        family = "Segoe UI" if windows else "DejaVu Sans"
        font.nametofont("TkDefaultFont").configure(family=family, size=10)
        self._plain_text_widgets = []
        self._canvases = []
        self._syncing_ipv4 = False
        self.ipv4_calculation: IPv4Calculation | None = None
        self.host_window = None
        self.host_page_number = 0
        self.help_window = None
        self._clipboard_job = None
        self._copied_password = None
        self._clipboard_retries = 0
        self._acl_job = None
        self.mtu_calculation = None
        self.status = tk.StringVar(root, value="Ready")

        shell = ttk.Frame(root, padding=(20, 16))
        shell.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)
        header = ttk.Frame(shell)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Network Tools", font=(family, 17, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(header, text=f"{__version__} · локальные расчёты", bootstyle="secondary").grid(
            row=1, column=0, sticky="w", pady=(3, 0)
        )
        ttk.Label(header, text="Тема").grid(row=0, column=1, padx=(10, 8))
        self.theme_selector = ttk.Combobox(
            header,
            textvariable=self.theme_label,
            values=("Дневная", "Ночная"),
            state="readonly",
            width=11,
        )
        self.theme_selector.grid(row=0, column=2)
        self.theme_selector.bind("<<ComboboxSelected>>", self._theme_selected)
        self.help_button = ttk.Button(header, text="Помощь · F1", command=self.show_help)
        self.help_button.grid(row=1, column=1, columnspan=2, sticky="e", pady=(5, 0))
        self.notebook = ttk.Notebook(shell)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        self.pages = []
        for topic in TOOL_HELP:
            name = topic.name
            viewport = ttk.Frame(self.notebook)
            viewport.columnconfigure(0, weight=1)
            viewport.rowconfigure(0, weight=1)
            canvas = tk.Canvas(viewport, highlightthickness=0, borderwidth=0, takefocus=False)
            canvas.grid(row=0, column=0, sticky="nsew")
            scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
            scrollbar.grid(row=0, column=1, sticky="ns")
            canvas.configure(yscrollcommand=scrollbar.set)
            page = ttk.Frame(canvas, padding=16)
            content = canvas.create_window(0, 0, window=page, anchor="nw")
            page.bind(
                "<Configure>",
                lambda event, surface=canvas: surface.configure(scrollregion=surface.bbox("all")),
            )
            canvas.bind(
                "<Configure>",
                lambda event, surface=canvas, item=content: surface.itemconfigure(
                    item, width=event.width
                ),
            )
            page.columnconfigure(0, weight=1)
            self.notebook.add(viewport, text=name)
            self.pages.append(page)
            self._canvases.append(canvas)
        for builder, page in zip(
            (
                self._build_mac,
                self._build_ipv4,
                self._build_mss,
                self._build_routes,
                self._build_acl,
                self._build_passwords,
            ),
            self.pages,
            strict=True,
        ):
            builder(page)
        self.status_label = ttk.Label(shell, textvariable=self.status, wraplength=760)
        self.status_label.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.notebook.bind("<<NotebookTabChanged>>", self._tool_changed)
        root.bind("<F1>", self.show_help)
        root.bind("<Destroy>", self._destroyed, add="+")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-l>", self.focus_input)
        root.bind("<Control-L>", self.focus_input)
        for index in range(len(TOOL_HELP)):
            root.bind(
                f"<Control-Key-{index + 1}>", lambda event, page=index: self.select_tool(page)
            )
        root.bind("<Control-Shift-c>", self.copy_current_tool)
        root.bind("<Control-Shift-C>", self.copy_current_tool)
        root.bind("<Control-Shift-t>", self.toggle_theme)
        root.bind("<Control-Shift-T>", self.toggle_theme)
        root.bind("<Control-KeyPress>", self._tool_key)
        root.bind("<MouseWheel>", self._scroll_tool)
        root.bind("<FocusIn>", self._show_focused_field)
        self._apply_theme()
        self._ipv4_update()
        self._mss_update()
        self._routes_update()
        self._acl_update()
        self._acl_flow_update()
        self.status.set("Ready")
        root.minsize(820, 610)
        width = max(820, min(940, root.winfo_screenwidth() - 80))
        height = max(610, min(760, root.winfo_screenheight() - 90))
        x = max(0, (root.winfo_screenwidth() - width) // 2)
        y = max(0, (root.winfo_screenheight() - height - 90) // 2)
        root.geometry(f"{width}x{height}+{x}+{y}")
        root.after_idle(self.input_entry.focus_set)

    def _bind_selection(self, widget):
        widget.bind("<Control-a>", self._select_all)
        widget.bind("<Control-A>", self._select_all)
        widget.bind("<<Paste>>", lambda event: self._paste(event.widget))
        widget.bind("<<Copy>>", lambda event: self._copy_selection(event.widget))
        widget.bind("<<Cut>>", lambda event: self._cut_selection(event.widget))
        widget.bind("<Control-KeyPress>", self._clipboard_key)
        widget.bind("<Button-3>", self._clipboard_menu)
        widget.bind("<Shift-F10>", self._clipboard_menu)

    @staticmethod
    def _editable(widget):
        return str(widget.cget("state")) == "normal"

    def _clipboard_key(self, event):
        if event.state & 1:  # Keep Ctrl+Shift+C for the complete tool report.
            return None
        if self.root.tk.call("tk", "windowingsystem") == "win32":
            key = {65: "a", 67: "c", 86: "v", 88: "x"}.get(event.keycode)
        else:
            key = event.keysym.lower()
        if key == "a":
            return self._select_all(event)
        action = {"c": "<<Copy>>", "v": "<<Paste>>", "x": "<<Cut>>"}.get(key)
        if action:
            event.widget.event_generate(action)
            return "break"
        return None

    def _tool_key(self, event):
        if self.root.tk.call("tk", "windowingsystem") != "win32":
            return None
        if event.state & 1:
            if event.keycode == 67:
                return self.copy_current_tool(event)
            if event.keycode == 84:
                return self.toggle_theme(event)
        elif event.keycode == 76:
            return self.focus_input(event)
        elif 49 <= event.keycode <= 54:
            return self.select_tool(event.keycode - 49)
        return None

    def _paste(self, widget, *, replace=False):
        if not self._editable(widget):
            return "break"
        try:
            value = self.root.clipboard_get()
        except tk.TclError:
            self.status.set("В буфере нет доступного текста. Попробуйте вставить ещё раз.")
            return "break"
        if not isinstance(widget, tk.Text):
            value = value.strip()
            if "\n" in value or "\r" in value:
                self.status.set("Для этого поля вставьте одну строку.")
                return "break"
        if widget is getattr(self, "ipv4_entry", None) and "/" in value:
            try:
                result = calculate_ipv4(value)
            except InvalidNetworkInput:
                pass
            else:
                self._syncing_ipv4 = True
                self.ipv4_address.set(str(result.address))
                self.ipv4_mask.set(f"/{result.network.prefixlen}")
                self._syncing_ipv4 = False
                self._ipv4_update()
                return "break"
        if isinstance(widget, tk.Text):
            if replace:
                widget.delete("1.0", tk.END)
            elif widget.tag_ranges(tk.SEL):
                widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
            widget.insert(tk.INSERT, value)
        else:
            if replace:
                widget.delete(0, tk.END)
            elif widget.selection_present():
                start = widget.index(tk.SEL_FIRST)
                widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                widget.icursor(start)
            widget.insert(tk.INSERT, value)
        return "break"

    @staticmethod
    def _selection(widget):
        try:
            if isinstance(widget, tk.Text):
                return widget.get(tk.SEL_FIRST, tk.SEL_LAST)
            return widget.get()[widget.index(tk.SEL_FIRST):widget.index(tk.SEL_LAST)]
        except tk.TclError:
            return ""

    def _copy_selection(self, widget):
        value = self._selection(widget)
        if widget is getattr(self, "password_result_entry", None):
            self._copy_password_value(value)
        else:
            self._copy(value)
        return "break"

    def _cut_selection(self, widget):
        if self._editable(widget) and self._selection(widget):
            self._copy_selection(widget)
            if isinstance(widget, tk.Text):
                widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
            else:
                widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
        return "break"

    def _clipboard_menu(self, event):
        widget = event.widget
        widget.focus_set()
        menu = tk.Menu(widget, tearoff=False)
        editable = self._editable(widget)
        selected = bool(self._selection(widget))
        menu.add_command(label="Вырезать", command=lambda: self._cut_selection(widget),
                         state="normal" if editable and selected else "disabled")
        menu.add_command(label="Копировать", command=lambda: self._copy_selection(widget),
                         state="normal" if selected else "disabled")
        menu.add_command(label="Вставить", command=lambda: self._paste(widget),
                         state="normal" if editable else "disabled")
        menu.add_separator()
        menu.add_command(label="Выделить всё", command=lambda: self._select_all(event))
        # Keep a reference for inspection and destroy the previous menu.
        previous = getattr(self, "clipboard_menu", None)
        if previous is not None:
            previous.destroy()
        self.clipboard_menu = menu
        x = event.x_root or widget.winfo_rootx()
        y = event.y_root or widget.winfo_rooty() + widget.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()
        return "break"

    def _field(self, parent, label, variable, column=0, *, values=None):
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=column, sticky="ew", padx=(0, 12) if column == 0 else (0, 0))
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=label).grid(row=0, column=0, sticky="w", pady=(0, 7))
        if values is None:
            entry = ttk.Entry(frame, textvariable=variable, font=self.fixed_font)
        else:
            entry = ttk.Combobox(
                frame, textvariable=variable, values=values, font=self.fixed_font, width=24
            )
        entry.grid(row=1, column=0, sticky="ew")
        self._bind_selection(entry)
        if values is None:
            button = ttk.Button(frame, text="Вставить", takefocus=False,
                                command=lambda: self._paste(entry, replace=True))
            button.grid(row=1, column=1, padx=(6, 0))
            entry.paste_button = button
        return entry

    def _build_mac(self, page):
        self.input_value = tk.StringVar(self.root)
        self.output_format = tk.StringVar(self.root, value="colon")
        self.uppercase = tk.BooleanVar(self.root, value=False)
        self.result = tk.StringVar(self.root)
        inputs = ttk.Frame(page)
        inputs.grid(row=0, column=0, sticky="ew")
        inputs.columnconfigure(0, weight=1)
        self.input_entry = self._field(inputs, "MAC-адрес", self.input_value)
        ttk.Label(
            page,
            text="Пример: 0011.2233.aabb · 00:11:22:33:aa:bb · 00112233aabb",
            bootstyle="secondary",
        ).grid(row=1, column=0, sticky="w", pady=(8, 20))
        ttk.Label(page, text="Формат результата").grid(row=2, column=0, sticky="w")
        formats = ttk.Frame(page)
        formats.grid(row=3, column=0, sticky="w", pady=(9, 16))
        self.format_buttons = {}
        for column, (name, value) in enumerate(
            (("Cisco", "cisco"), ("Colon", "colon"), ("Hyphen", "hyphen"), ("Plain", "plain"))
        ):
            button = ttk.Radiobutton(
                formats, text=name, variable=self.output_format, value=value, takefocus=True
            )
            button.grid(row=0, column=column, padx=(0, 24))
            self.format_buttons[value] = button
        self.uppercase_button = ttk.Checkbutton(
            page, text="Верхний регистр", variable=self.uppercase, takefocus=True
        )
        self.uppercase_button.grid(row=4, column=0, sticky="w", pady=(0, 22))
        ttk.Label(page, text="Результат").grid(row=5, column=0, sticky="w", pady=(0, 7))
        output = ttk.Frame(page)
        output.grid(row=6, column=0, sticky="ew")
        output.columnconfigure(0, weight=1)
        self.result_entry = ttk.Entry(
            output, textvariable=self.result, state="readonly", font=self.fixed_font
        )
        self.result_entry.grid(row=0, column=0, sticky="ew")
        self._bind_selection(self.result_entry)
        self.copy_button = ttk.Button(
            output, text="Copy", command=self.copy_result, state="disabled", bootstyle="primary"
        )
        self.copy_button.grid(row=0, column=1, padx=(10, 0))
        for variable in (self.input_value, self.output_format, self.uppercase):
            variable.trace_add("write", self._convert)

    def _build_ipv4(self, page):
        self.ipv4_address = tk.StringVar(self.root, value="192.168.1.0")
        self.ipv4_mask = tk.StringVar(self.root, value="/24")
        self.ipv4_strict = tk.BooleanVar(self.root, value=False)
        self.ipv4_note = tk.StringVar(self.root)
        self.ipv4_error = tk.StringVar(self.root)
        inputs = ttk.Frame(page)
        inputs.grid(row=0, column=0, sticky="ew")
        inputs.columnconfigure(0, weight=3)
        inputs.columnconfigure(1, weight=2)
        self.ipv4_entry = self._field(inputs, "IPv4 / сеть", self.ipv4_address)
        self.ipv4_mask_entry = self._field(
            inputs, "Маска / префикс", self.ipv4_mask, 1, values=[f"/{p}" for p in range(33)]
        )
        self.ipv4_entry.bind("<FocusOut>", self._normalize_ipv4)
        self.ipv4_entry.bind("<Return>", self._normalize_ipv4)
        options = ttk.Frame(page)
        options.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        options.columnconfigure(0, weight=1)
        ttk.Checkbutton(
            options, text="Проверить именно адрес сети", variable=self.ipv4_strict
        ).grid(row=0, column=0, sticky="w")
        self.ipv4_copy_button = ttk.Button(
            options, text="Копировать всё", command=self.copy_ipv4, bootstyle="primary"
        )
        self.ipv4_copy_button.grid(row=0, column=1)
        ttk.Label(page, textvariable=self.ipv4_error, bootstyle="danger", wraplength=780).grid(
            row=2, column=0, sticky="ew", pady=(0, 4)
        )
        results = ttk.Frame(page)
        results.grid(row=3, column=0, sticky="ew")
        results.columnconfigure(0, weight=1, uniform="results")
        results.columnconfigure(1, weight=1, uniform="results")
        self.ipv4_addresses_table = OutputTable(
            self,
            results,
            (
                "Адрес подсети",
                "Первый хост",
                "Последний хост",
                "Хостовых позиций",
                "Всего адресов",
                "Broadcast подсети",
            ),
        )
        self.ipv4_addresses_table.frame.grid(row=0, column=0, sticky="new", padx=(0, 20))
        self.ipv4_mask_table = OutputTable(
            self, results, ("Подсеть CIDR", "Префикс", "Полная маска", "Wildcard")
        )
        self.ipv4_mask_table.frame.grid(row=0, column=1, sticky="new")
        self.ipv4_range_table = OutputTable(self, page, ("Диапазон хостов",))
        self.ipv4_range_table.frame.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.ipv4_binary = tk.StringVar(self.root)
        binary_frame = ttk.Frame(page)
        binary_frame.grid(row=5, column=0, sticky="ew", pady=(14, 6))
        binary_frame.columnconfigure(1, weight=1)
        ttk.Label(binary_frame, text="Двоичная маска").grid(row=0, column=0, padx=(0, 12))
        self.ipv4_binary_entry = ttk.Entry(
            binary_frame, textvariable=self.ipv4_binary, state="readonly", font=self.fixed_font
        )
        self.ipv4_binary_entry.grid(row=0, column=1, sticky="ew")
        self._bind_selection(self.ipv4_binary_entry)
        self.ipv4_binary_copy = ttk.Button(
            binary_frame, text="Copy", command=lambda: self._copy(self.ipv4_binary.get())
        )
        self.ipv4_binary_copy.grid(row=0, column=2, padx=(8, 0))
        ttk.Label(page, textvariable=self.ipv4_note, wraplength=780, bootstyle="secondary").grid(
            row=6, column=0, sticky="ew", pady=(8, 10)
        )
        self.hosts_button = ttk.Button(page, text="Список хостов", command=self.show_hosts)
        self.hosts_button.grid(row=7, column=0, sticky="w")
        self.ipv4_address.trace_add("write", self._ipv4_update)
        self.ipv4_mask.trace_add("write", self._ipv4_mask_changed)
        self.ipv4_strict.trace_add("write", self._ipv4_update)

    def _build_mss(self, page):
        self.mtu_value = tk.StringVar(self.root, value="1500")
        self.overhead_value = tk.StringVar(self.root, value="0")
        self.ip_version = tk.StringVar(self.root, value="IPv4")
        self.outer_ip_version = tk.StringVar(self.root, value="IPv4")
        self.mtu_basis = tk.StringVar(self.root, value=next(iter(BASES)))
        self.mtu_profile = tk.StringVar(self.root, value=next(iter(PROFILES)))
        self.mtu_vlan_tags = tk.StringVar(self.root, value="0")
        self.mtu_inner_tags = tk.StringVar(self.root, value="0")
        self.mtu_pppoe = tk.BooleanVar(self.root, value=False)
        self.mtu_gre_checksum = tk.BooleanVar(self.root, value=False)
        self.mtu_gre_key = tk.BooleanVar(self.root, value=False)
        self.mtu_gre_sequence = tk.BooleanVar(self.root, value=False)
        self.mtu_esp_mode = tk.StringVar(self.root, value="tunnel")
        self.mtu_esp_cipher = tk.StringVar(self.root, value="AES-GCM-16")
        self.mtu_nat_t = tk.BooleanVar(self.root, value=False)
        self.mtu_openvpn_format = tk.StringVar(self.root, value="DATA_V2")
        self.mtu_openvpn_mode = tk.StringVar(self.root, value="TUN")
        self.mtu_l2tp_length = tk.BooleanVar(self.root, value=False)
        self.mtu_l2tp_sequence = tk.BooleanVar(self.root, value=False)
        self.mtu_ppp_header = tk.StringVar(self.root, value="4")
        self.mss_error = tk.StringVar(self.root)
        self.mtu_controls = {}

        def row(number):
            frame = ttk.Frame(page)
            frame.grid(row=number, column=0, sticky="ew", pady=(0, 12))
            for column in range(3):
                frame.columnconfigure(column, weight=1, uniform="fields")
            return frame

        def choice(parent, label, variable, column, values):
            entry = self._field(parent, label, variable, column, values=values)
            entry.configure(state="readonly")
            self.mtu_controls[label] = entry
            return entry

        inputs = row(0)
        self.mtu_entry = self._field(inputs, "Исходный размер, байт", self.mtu_value)
        choice(inputs, "Что измерено", self.mtu_basis, 1, tuple(BASES))
        self.version_entry = choice(inputs, "Внутренний IP", self.ip_version, 2, ("IPv4", "IPv6"))
        inputs = row(1)
        choice(inputs, "Инкапсуляция", self.mtu_profile, 0, tuple(PROFILES))
        choice(inputs, "Внешний IP", self.outer_ip_version, 1, ("IPv4", "IPv6"))
        self.overhead_entry = self._field(inputs, "Дополнительно, байт", self.overhead_value, 2)
        inputs = row(2)
        choice(inputs, "Внешние VLAN: 0 / dot1q / QinQ", self.mtu_vlan_tags, 0, ("0", "1", "2"))
        ttk.Checkbutton(inputs, text="PPPoE (6 + PPP 2 байта)", variable=self.mtu_pppoe).grid(
            row=0, column=1, columnspan=2, sticky="w", padx=12)
        advanced = ttk.Frame(page)
        advanced.grid(row=3, column=0, sticky="ew")
        advanced.columnconfigure(0, weight=1)
        self.mtu_advanced = {}
        for profile in ("gre", "vxlan", "ipsec", "openvpn", "l2tp"):
            frame = ttk.Frame(advanced)
            frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
            for column in range(3):
                frame.columnconfigure(column, weight=1)
            self.mtu_advanced[profile] = frame
        frame = self.mtu_advanced["gre"]
        for col, (label, variable) in enumerate((("Checksum", self.mtu_gre_checksum),
                                               ("Key", self.mtu_gre_key),
                                               ("Sequence", self.mtu_gre_sequence))):
            ttk.Checkbutton(frame, text=f"GRE {label} (+4)", variable=variable).grid(
                row=0, column=col, sticky="w")
        choice(self.mtu_advanced["vxlan"], "Внутренние VLAN-теги", self.mtu_inner_tags, 0, ("0", "1", "2"))
        frame = self.mtu_advanced["ipsec"]
        choice(frame, "ESP mode", self.mtu_esp_mode, 0, ("tunnel", "transport"))
        choice(frame, "ESP cipher / integrity", self.mtu_esp_cipher, 1, tuple(CIPHERS))
        ttk.Checkbutton(frame, text="NAT-T UDP (+8)", variable=self.mtu_nat_t).grid(row=0, column=2, sticky="w")
        frame = self.mtu_advanced["openvpn"]
        choice(frame, "OpenVPN data format", self.mtu_openvpn_format, 0, ("DATA_V1", "DATA_V2"))
        choice(frame, "OpenVPN interface", self.mtu_openvpn_mode, 1, ("TUN", "TAP"))
        choice(frame, "TAP VLAN-теги", self.mtu_inner_tags, 2, ("0", "1", "2"))
        frame = self.mtu_advanced["l2tp"]
        choice(frame, "ESP cipher / integrity", self.mtu_esp_cipher, 0, tuple(CIPHERS))
        choice(frame, "PPP header, байт", self.mtu_ppp_header, 1, ("1", "2", "4"))
        options = ttk.Frame(frame)
        options.grid(row=0, column=2, sticky="w")
        for label, variable in (("NAT-T (+8)", self.mtu_nat_t),
                                ("L2TP Length (+2)", self.mtu_l2tp_length),
                                ("L2TP Sequence (+4)", self.mtu_l2tp_sequence)):
            ttk.Checkbutton(options, text=label, variable=variable).pack(anchor="w")
        ttk.Label(page, textvariable=self.mss_error, wraplength=780, bootstyle="danger").grid(
            row=4, column=0, sticky="ew", pady=(4, 4))
        self.mss_table = OutputTable(self, page, calculate_mtu(MtuOptions()).rows().keys())
        self.mss_table.frame.grid(row=5, column=0, sticky="ew", pady=(8, 12))
        container, self.mtu_breakdown = self._text_widget(page, height=7, readonly=True)
        container.grid(row=6, column=0, sticky="ew")
        for variable in (self.mtu_value, self.overhead_value, self.ip_version,
                         self.outer_ip_version, self.mtu_basis, self.mtu_profile,
                         self.mtu_vlan_tags, self.mtu_inner_tags, self.mtu_pppoe,
                         self.mtu_gre_checksum, self.mtu_gre_key, self.mtu_gre_sequence,
                         self.mtu_esp_mode, self.mtu_esp_cipher, self.mtu_nat_t,
                         self.mtu_openvpn_format, self.mtu_openvpn_mode,
                         self.mtu_l2tp_length, self.mtu_l2tp_sequence, self.mtu_ppp_header):
            variable.trace_add("write", self._mss_update)

    def _text_widget(self, parent, *, height=8, readonly=False):
        container = ttk.Frame(parent)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)
        text = tk.Text(
            container, height=height, width=50, wrap="word", font=self.fixed_font, takefocus=True
        )
        text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scrollbar.set)
        self._bind_selection(text)
        if readonly:
            text.configure(state="disabled")
        self._plain_text_widgets.append(text)
        return container, text

    def _build_routes(self, page):
        page.rowconfigure(2, weight=1)
        page.rowconfigure(5, weight=1)
        self.route_address = tk.StringVar(self.root, value="10.20.30.40")
        self.routes_error = tk.StringVar(self.root)
        inputs = ttk.Frame(page)
        inputs.grid(row=0, column=0, sticky="ew")
        inputs.columnconfigure(0, weight=1)
        self.route_entry = self._field(inputs, "IP назначения", self.route_address)
        ttk.Label(
            page, text="Маршруты: один CIDR на строку; далее необязательная подпись / next-hop"
        ).grid(row=1, column=0, sticky="w", pady=(12, 7))
        container, self.routes_input = self._text_widget(page, height=5)
        container.grid(row=2, column=0, sticky="nsew")
        self.routes_paste_button = ttk.Button(
            inputs, text="Вставить маршруты", takefocus=False,
            command=lambda: self._paste(self.routes_input, replace=True))
        self.routes_paste_button.grid(row=0, column=1, padx=(10, 0), sticky="s")
        self.routes_input.insert(
            "1.0", "0.0.0.0/0 default\n10.20.0.0/16 core\n10.20.30.0/24 access"
        )
        self.routes_input.edit_modified(False)
        self.routes_input.bind("<<Modified>>", self._routes_modified)
        ttk.Label(page, textvariable=self.routes_error, bootstyle="danger", wraplength=780).grid(
            row=3, column=0, sticky="ew", pady=(8, 4)
        )
        actions = ttk.Frame(page)
        actions.grid(row=4, column=0, sticky="ew", pady=(4, 8))
        actions.columnconfigure(0, weight=1)
        ttk.Label(actions, text="Совпадения по длине префикса").grid(row=0, column=0, sticky="w")
        self.routes_copy_button = ttk.Button(
            actions, text="Копировать", command=self.copy_routes, bootstyle="primary"
        )
        self.routes_copy_button.grid(row=0, column=1)
        container, self.routes_output = self._text_widget(page, height=5, readonly=True)
        container.grid(row=5, column=0, sticky="nsew")
        ttk.Label(
            page,
            text="Анализируется введённый список. Выбор VRF, PBR и разрешение next-hop не моделируются.",
            wraplength=780,
            bootstyle="secondary",
        ).grid(row=6, column=0, sticky="ew", pady=(12, 0))
        self.route_address.trace_add("write", self._routes_update)

    def _build_acl(self, page):
        self.acl_source = tk.StringVar(self.root, value="192.0.2.10")
        self.acl_destination = tk.StringVar(self.root, value="198.51.100.20")
        self.acl_protocol = tk.StringVar(self.root, value="TCP")
        self.acl_source_port = tk.StringVar(self.root, value="53000")
        self.acl_destination_port = tk.StringVar(self.root, value="443")
        self.acl_ack = tk.BooleanVar(self.root, value=False)
        self.acl_flow_error = tk.StringVar(self.root)
        inputs = ttk.Frame(page)
        inputs.grid(row=0, column=0, sticky="ew")
        for column in range(3):
            inputs.columnconfigure(column, weight=1, uniform="aclfields")
        self.acl_entry = self._field(inputs, "IPv4 источника", self.acl_source)
        self.acl_destination_entry = self._field(inputs, "IPv4 назначения", self.acl_destination, 1)
        self.acl_protocol_entry = self._field(inputs, "Тип трафика", self.acl_protocol, 2, values=("TCP", "UDP"))
        self.acl_protocol_entry.configure(state="readonly")
        ports = ttk.Frame(page)
        ports.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        for column in range(3):
            ports.columnconfigure(column, weight=1, uniform="aclfields")
        self.acl_source_port_entry = self._field(ports, "Порт источника (можно пустой)", self.acl_source_port)
        self.acl_destination_port_entry = self._field(ports, "Порт назначения", self.acl_destination_port, 1)
        self.acl_ack_button = ttk.Checkbutton(ports, text="TCP-запрос: ACK или RST", variable=self.acl_ack)
        self.acl_ack_button.grid(row=0, column=2, sticky="w", padx=12)
        ttk.Label(page, text="ACL Cisco IOS IPv4. Вторая ACL проверяет ответ: IP и порты меняются местами.",
                  wraplength=780, bootstyle="secondary").grid(row=2, column=0, sticky="ew", pady=(12, 8))
        lists = ttk.Frame(page)
        lists.grid(row=3, column=0, sticky="ew")
        self.acl_inputs = []
        for column, label in enumerate(("ACL запроса", "ACL ответа (необязательно)")):
            lists.columnconfigure(column, weight=1, uniform="acllists")
            frame = ttk.Frame(lists)
            frame.grid(row=0, column=column, sticky="nsew", padx=(0, 8) if column == 0 else (8, 0))
            frame.columnconfigure(0, weight=1)
            ttk.Label(frame, text=label).grid(row=0, column=0, sticky="w")
            container, widget = self._text_widget(frame, height=7)
            container.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
            widget.configure(width=30, wrap="none")
            horizontal = ttk.Scrollbar(frame, orient="horizontal", command=widget.xview)
            horizontal.grid(row=2, column=0, sticky="ew")
            widget.configure(xscrollcommand=horizontal.set)
            button = ttk.Button(frame, text="Вставить ACL", command=lambda entry=widget: self._paste(entry, replace=True))
            button.grid(row=3, column=0, sticky="w", pady=(6, 0))
            widget.paste_button = button
            self.acl_inputs.append(widget)
        self.acl_forward_input, self.acl_reverse_input = self.acl_inputs
        actions = ttk.Frame(page)
        actions.grid(row=4, column=0, sticky="ew", pady=(10, 4))
        self.acl_example_button = ttk.Button(actions, text="Пример HTTPS", command=self._acl_example)
        self.acl_example_button.pack(side="left")
        ttk.Button(actions, text="Очистить ACL", command=self._acl_clear).pack(side="left", padx=8)
        self.acl_copy_button = ttk.Button(actions, text="Копировать заключение", command=self.copy_acl)
        self.acl_copy_button.pack(side="right")
        ttk.Label(page, textvariable=self.acl_flow_error, wraplength=780, bootstyle="danger").grid(
            row=5, column=0, sticky="ew", pady=(4, 4))
        container, self.acl_output = self._text_widget(page, height=9, readonly=True)
        container.grid(row=6, column=0, sticky="ew")
        ttk.Label(page, text="«Пример HTTPS» загружает тестовые адреса и правила. Первый permit/deny определяет результат; без совпадения действует неявный deny. Неизвестный порт может требовать уточнения.",
                  wraplength=780, bootstyle="secondary").grid(row=7, column=0, sticky="ew", pady=(8, 8))
        self.acl_wildcard_visible = tk.BooleanVar(self.root, value=False)
        ttk.Checkbutton(page, text="Дополнительно: проверить одно условие wildcard",
                        variable=self.acl_wildcard_visible, command=self._toggle_wildcard).grid(row=8, column=0, sticky="w")
        extra = ttk.Frame(page)
        extra.grid(row=9, column=0, sticky="ew", pady=(12, 0))
        extra.columnconfigure(0, weight=1)
        self.acl_wildcard_frame = extra
        self.acl_base = tk.StringVar(self.root, value="10.10.0.0")
        self.acl_wildcard = tk.StringVar(self.root, value="0.0.255.254")
        self.acl_address = tk.StringVar(self.root, value="10.10.5.2")
        self.acl_error = tk.StringVar(self.root)
        inputs = ttk.Frame(extra)
        inputs.grid(row=0, column=0, sticky="ew")
        for column in range(3):
            inputs.columnconfigure(column, weight=1)
        self.acl_base_entry = self._field(inputs, "Базовый IPv4", self.acl_base)
        self._field(inputs, "Wildcard", self.acl_wildcard, 1)
        self._field(inputs, "Проверяемый IPv4", self.acl_address, 2)
        ttk.Label(extra, textvariable=self.acl_error, wraplength=780, bootstyle="danger").grid(row=1, column=0, sticky="ew")
        self.acl_table = OutputTable(self, extra, check_wildcard("10.10.0.0", "0.0.255.254", "10.10.5.2").rows().keys())
        self.acl_table.frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for variable in (self.acl_base, self.acl_wildcard, self.acl_address):
            variable.trace_add("write", self._acl_update)
        self._toggle_wildcard()
        self._acl_example()
        for variable in (self.acl_source, self.acl_destination, self.acl_protocol,
                         self.acl_source_port, self.acl_destination_port, self.acl_ack):
            variable.trace_add("write", self._acl_flow_update)
        for widget in self.acl_inputs:
            widget.edit_modified(False)
            widget.bind("<<Modified>>", self._acl_modified)

    def _toggle_wildcard(self):
        if self.acl_wildcard_visible.get():
            self.acl_wildcard_frame.grid()
        else:
            self.acl_wildcard_frame.grid_remove()

    def _acl_example(self):
        self.acl_source.set("192.0.2.10")
        self.acl_destination.set("198.51.100.20")
        self.acl_protocol.set("TCP")
        self.acl_source_port.set("53000")
        self.acl_destination_port.set("443")
        self.acl_ack.set(False)
        examples = ("ip access-list extended REQUEST\n10 permit tcp host 192.0.2.10 host 198.51.100.20 eq https\n20 deny ip any any log",
                    "ip access-list extended REPLY\n10 permit tcp host 198.51.100.20 eq https host 192.0.2.10 range 1024 65535 established\n20 deny ip any any log")
        for widget, text in zip(self.acl_inputs, examples, strict=True):
            widget.delete("1.0", tk.END)
            widget.insert("1.0", text)
            widget.edit_modified(False)
        self._acl_flow_update()

    def _acl_clear(self):
        for widget in self.acl_inputs:
            widget.delete("1.0", tk.END)
            widget.edit_modified(False)
        self._acl_flow_update()

    def _acl_modified(self, event):
        if not event.widget.edit_modified():
            return
        event.widget.edit_modified(False)
        if self._acl_job is not None:
            self.root.after_cancel(self._acl_job)
        self._set_text(self.acl_output, "")
        self.acl_copy_button.state(["disabled"])
        self.acl_flow_error.set("Проверка правил...")
        self._acl_job = self.root.after(180, self._acl_flow_update)

    def _acl_flow_update(self, *_args):
        if self._acl_job is not None:
            self.root.after_cancel(self._acl_job)
            self._acl_job = None
        self.acl_ack_button.state(["!disabled" if self.acl_protocol.get() == "TCP" else "disabled"])
        try:
            flow = make_flow(self.acl_source.get(), self.acl_destination.get(), self.acl_protocol.get(),
                             self.acl_source_port.get(), self.acl_destination_port.get(), self.acl_ack.get())
            result = check_conversation(self.acl_forward_input.get("1.0", "end-1c"),
                                        self.acl_reverse_input.get("1.0", "end-1c"), flow)
        except InvalidNetworkInput as error:
            self.acl_flow_error.set(str(error))
            self._set_text(self.acl_output, "")
            self.acl_copy_button.state(["disabled"])
            return
        self.acl_flow_error.set("")
        self._set_text(self.acl_output, result)
        self.acl_copy_button.state(["!disabled"])

    def copy_acl(self):
        if self.acl_copy_button.instate(["!disabled"]):
            self._copy(self.acl_output.get("1.0", "end-1c"))

    def _build_passwords(self, page):
        self.password_length = tk.StringVar(self.root, value="20")
        self.password_groups = {
            name: tk.BooleanVar(self.root, value=True)
            for name in ("lowercase", "uppercase", "digits", "symbols")
        }
        self.password_ambiguous = tk.BooleanVar(self.root, value=True)
        self.password_symbols = tk.StringVar(self.root, value=DEFAULT_SYMBOLS)
        self.password_result = tk.StringVar(self.root)
        self.password_error = tk.StringVar(self.root)
        self.password_info = tk.StringVar(self.root)
        self.password_show = tk.BooleanVar(self.root, value=False)
        self.password_auto_clear = tk.BooleanVar(self.root, value=True)
        inputs = ttk.Frame(page)
        inputs.grid(row=0, column=0, sticky="ew")
        inputs.columnconfigure(0, weight=1)
        inputs.columnconfigure(1, weight=3)
        self.password_length_entry = self._field(inputs, "Длина · 8-128", self.password_length)
        self.password_symbols_entry = self._field(
            inputs, "Допустимые спецсимволы", self.password_symbols, 1
        )
        choices = ttk.Frame(page)
        choices.grid(row=1, column=0, sticky="w", pady=(16, 10))
        self.password_group_buttons = {}
        for col, (name, label) in enumerate(
            (
                ("lowercase", "a-z"),
                ("uppercase", "A-Z"),
                ("digits", "0-9"),
                ("symbols", "Спецсимволы"),
            )
        ):
            button = ttk.Checkbutton(
                choices, text=label, variable=self.password_groups[name], takefocus=True
            )
            button.grid(row=0, column=col, padx=(0, 24))
            self.password_group_buttons[name] = button
        self.password_ambiguous_button = ttk.Checkbutton(
            page, text="Без похожих символов: 0 O 1 I l |", variable=self.password_ambiguous
        )
        self.password_ambiguous_button.grid(row=2, column=0, sticky="w", pady=(2, 10))
        ttk.Label(page, textvariable=self.password_error, bootstyle="danger", wraplength=780).grid(
            row=3, column=0, sticky="ew", pady=(0, 8)
        )
        self.password_generate_button = ttk.Button(
            page, text="Сгенерировать", command=self.generate_password, bootstyle="primary"
        )
        self.password_generate_button.grid(row=4, column=0, sticky="w", pady=(0, 16))
        output = ttk.Frame(page)
        output.grid(row=5, column=0, sticky="ew")
        output.columnconfigure(0, weight=1)
        self.password_result_entry = ttk.Entry(
            output,
            textvariable=self.password_result,
            state="readonly",
            show="*",
            font=self.fixed_font,
        )
        self.password_result_entry.grid(row=0, column=0, sticky="ew")
        self._bind_selection(self.password_result_entry)
        self.password_copy_button = ttk.Button(
            output, text="Copy", command=self.copy_password, state="disabled"
        )
        self.password_copy_button.grid(row=0, column=1, padx=(10, 0))
        self.password_clear_button = ttk.Button(
            output, text="Очистить", command=self.clear_password
        )
        self.password_clear_button.grid(row=0, column=2, padx=(8, 0))
        self.password_show_button = ttk.Checkbutton(
            page, text="Показать", variable=self.password_show, command=self._password_visibility
        )
        self.password_show_button.grid(row=6, column=0, sticky="w", pady=(12, 8))
        ttk.Checkbutton(
            page,
            text="Очищать скопированный пароль из буфера через 30 с",
            variable=self.password_auto_clear,
        ).grid(row=7, column=0, sticky="w", pady=(0, 12))
        ttk.Label(
            page, textvariable=self.password_info, bootstyle="secondary", wraplength=780
        ).grid(row=8, column=0, sticky="ew")
        ttk.Label(
            page,
            text="Каждая выбранная группа попадёт в пароль. Генерация выполняется локально; пароли не сохраняются. Правила целевой системы могут ограничивать символы.",
            wraplength=780,
            bootstyle="secondary",
        ).grid(row=9, column=0, sticky="ew", pady=(16, 0))
        for variable in (
            self.password_length,
            self.password_symbols,
            self.password_ambiguous,
            *self.password_groups.values(),
        ):
            variable.trace_add("write", self._password_options_changed)
        self.password_auto_clear.trace_add("write", self._password_auto_clear_changed)
        self._password_options_changed()

    def _password_options(self):
        text = self.password_length.get().strip()
        if not re.fullmatch(r"[0-9]{1,3}", text):
            raise InvalidPasswordOptions("Длина: целое число от 8 до 128.")
        return PasswordOptions(
            length=int(text),
            exclude_ambiguous=self.password_ambiguous.get(),
            symbol_chars=self.password_symbols.get(),
            **{name: value.get() for name, value in self.password_groups.items()},
        )

    def _password_options_changed(self, *_args):
        self.password_result.set("")
        self.password_copy_button.state(["disabled"])
        self.password_show.set(False)
        self._password_visibility()
        self.password_symbols_entry.configure(
            state="normal" if self.password_groups["symbols"].get() else "disabled"
        )
        try:
            options = self._password_options()
            bits = entropy_bits(options)
        except InvalidPasswordOptions as error:
            self.password_error.set(str(error))
            self.password_info.set("")
            self.password_generate_button.state(["disabled"])
            return
        self.password_error.set("")
        self.password_generate_button.state(["!disabled"])
        hint = (
            " Для обычных учётных записей лучше использовать 16-20 и более символов."
            if options.length < 16
            else ""
        )
        if bits < 64:
            hint += " Небольшое пространство вариантов: увеличьте длину или набор символов."
        self.password_info.set(f"Энтропия равномерной генерации: ≈{bits:.1f} бит.{hint}")

    def generate_password(self):
        self.password_result.set("")
        self.password_copy_button.state(["disabled"])
        self.password_show.set(False)
        self._password_visibility()
        try:
            value = generate_password(self._password_options())
        except InvalidPasswordOptions as error:
            self.password_error.set(str(error))
            return
        except OSError:
            self.password_error.set("Системный источник случайности недоступен. Пароль не создан.")
            return
        self.password_result.set(value)
        self.password_error.set("")
        self.password_copy_button.state(["!disabled"])
        self.status.set("Пароль создан")

    def _password_visibility(self):
        self.password_result_entry.configure(show="" if self.password_show.get() else "*")

    def copy_password(self):
        self._copy_password_value(self.password_result.get())

    def _copy_password_value(self, value):
        if not value:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            self.root.update_idletasks()
        except tk.TclError:
            self.status.set("Clipboard unavailable. Try Copy again.")
            return
        self._cancel_clipboard_job()
        self._copied_password = value
        self._clipboard_retries = 0
        if self.password_auto_clear.get():
            self._clipboard_job = self.root.after(30000, self._clear_password_clipboard)
            self.status.set("Copied · автоочистка буфера через 30 с")
        else:
            self.status.set("Copied")

    def _password_auto_clear_changed(self, *_args):
        self._cancel_clipboard_job()
        if self.password_auto_clear.get() and self._copied_password:
            self._clipboard_job = self.root.after(30000, self._clear_password_clipboard)

    def _cancel_clipboard_job(self):
        if self._clipboard_job is not None:
            self.root.after_cancel(self._clipboard_job)
            self._clipboard_job = None

    def _clear_password_clipboard(self, *, retry=True):
        self._cancel_clipboard_job()
        if self._copied_password is None:
            return
        try:
            cleared = clear_if_matches(self.root, self._copied_password)
        except ClipboardUnavailable:
            if retry and self._clipboard_retries < 3:
                self._clipboard_retries += 1
                self._clipboard_job = self.root.after(1000, self._clear_password_clipboard)
                return
            self.status.set("Очистить буфер не удалось; проверьте его вручную.")
        else:
            if cleared:
                self.status.set("Пароль удалён из буфера")
        self._copied_password = None
        self._clipboard_retries = 0

    def clear_password(self):
        self.password_result.set("")
        self.password_copy_button.state(["disabled"])
        self.password_show.set(False)
        self._password_visibility()
        self._clear_password_clipboard()
        self.status.set("Пароль очищен")

    def close(self):
        if self._acl_job is not None:
            self.root.after_cancel(self._acl_job)
            self._acl_job = None
        self._clear_password_clipboard(retry=False)
        self.password_result.set("")
        self.root.destroy()

    def _destroyed(self, event):
        if event.widget == self.root:
            if self._acl_job is not None:
                self.root.after_cancel(self._acl_job)
                self._acl_job = None
            self._clear_password_clipboard(retry=False)
            self.password_result.set("")

    def _tool_changed(self, _event=None):
        self.status.set("Ready")
        if hasattr(self, "password_show"):
            self.password_show.set(False)
            self._password_visibility()
        if self.help_window is not None and self.help_window.winfo_exists():
            self._update_help()

    def show_help(self, _event=None):
        if self.help_window is not None and self.help_window.winfo_exists():
            self._update_help()
            self.help_window.lift()
            self.help_text.focus_set()
            return "break"
        window = tk.Toplevel(self.root)
        self.help_window = window
        window.transient(self.root)
        window.geometry("700x570")
        window.minsize(540, 400)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        self.help_title = tk.StringVar(window)
        ttk.Label(frame, textvariable=self.help_title, font=("TkDefaultFont", 14, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 12)
        )
        container, self.help_text = self._text_widget(frame, height=20, readonly=True)
        self.help_text.configure(font="TkDefaultFont")
        container.grid(row=1, column=0, sticky="nsew")
        self.help_close_button = ttk.Button(frame, text="Закрыть", command=window.destroy)
        self.help_close_button.grid(row=2, column=0, sticky="e", pady=(12, 0))
        window.bind("<Escape>", lambda _event: window.destroy())
        self._update_help()
        self._apply_theme()
        window.after_idle(self.help_text.focus_set)
        return "break"

    def _update_help(self):
        index = self.notebook.index(self.notebook.select())
        topic = TOOL_HELP[index]
        self.help_window.title(f"Помощь - {topic.name}")
        self.help_title.set(topic.name)
        self._set_text(self.help_text, topic.text())

    def _theme_selected(self, _event=None):
        self.set_theme("night" if self.theme_label.get() == "Ночная" else "day")

    def set_theme(self, theme):
        if theme not in ("day", "night"):
            raise ValueError("Unknown theme")
        self.theme.set(theme)
        self.theme_label.set("Дневная" if theme == "day" else "Ночная")
        self._apply_theme()
        try:
            self.settings.save(theme)
        except OSError:
            self.status.set("Тема изменена; сохранить настройку не удалось.")
        else:
            self.status.set("Ready")

    def toggle_theme(self, _event=None):
        self.set_theme("night" if self.theme.get() == "day" else "day")
        return "break"

    def _apply_theme(self):
        self.style.theme_use("bootstrap-light" if self.theme.get() == "day" else "bootstrap-dark")
        colors = self.style.colors
        self.root.configure(background=colors.bg)
        for canvas in self._canvases:
            canvas.configure(background=colors.bg)
        for text in self._plain_text_widgets:
            if text.winfo_exists():
                text.configure(
                    background=colors.inputbg,
                    foreground=colors.inputfg,
                    insertbackground=colors.inputfg,
                    selectbackground=colors.selectbg,
                    selectforeground=colors.selectfg,
                    relief="flat",
                    padx=10,
                    pady=8,
                )

    def _convert(self, *_trace_args):
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

    def _ipv4_mask_changed(self, *_args):
        if self._syncing_ipv4:
            return
        if "/" in self.ipv4_address.get():
            self._syncing_ipv4 = True
            self.ipv4_address.set(self.ipv4_address.get().split("/", 1)[0])
            self._syncing_ipv4 = False
        self._ipv4_update()

    def _ipv4_update(self, *_args):
        if self._syncing_ipv4:
            return
        try:
            result = calculate_ipv4(
                self.ipv4_address.get(),
                self.ipv4_mask.get(),
                require_network=self.ipv4_strict.get(),
            )
        except InvalidNetworkInput as error:
            self.ipv4_calculation = None
            self.ipv4_addresses_table.clear()
            self.ipv4_mask_table.clear()
            self.ipv4_range_table.clear()
            self.ipv4_binary.set("")
            for button in (self.ipv4_copy_button, self.ipv4_binary_copy, self.hosts_button):
                button.state(["disabled"])
            text = self.ipv4_address.get().strip()
            incomplete = (
                not text
                or not self.ipv4_mask.get().strip().strip("/")
                or text.endswith("/")
                or re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{0,3}){0,2}\.?", text)
            )
            self.ipv4_error.set("" if incomplete else str(error))
            self.ipv4_note.set("Введите полный IPv4-адрес и маску." if incomplete else "")
            return
        if "/" in self.ipv4_address.get():
            self._syncing_ipv4 = True
            self.ipv4_mask.set(f"/{result.network.prefixlen}")
            self._syncing_ipv4 = False
        self.ipv4_calculation = result
        self.ipv4_addresses_table.update(result.rows())
        self.ipv4_mask_table.update(result.rows())
        self.ipv4_range_table.update(result.rows())
        self.ipv4_binary.set(result.binary_mask)
        self.ipv4_note.set(result.note)
        self.ipv4_error.set("")
        for button in (self.ipv4_copy_button, self.ipv4_binary_copy, self.hosts_button):
            button.state(["!disabled"])
        self.hosts_button.configure(
            text="Адреса блока (/0)" if result.network.prefixlen == 0 else "Список хостов"
        )

    def _normalize_ipv4(self, _event=None):
        if self.ipv4_calculation is not None and "/" in self.ipv4_address.get():
            self.ipv4_address.set(str(self.ipv4_calculation.address))

    def _mss_update(self, *_args):
        profile = PROFILES.get(self.mtu_profile.get(), "")
        for key, frame in self.mtu_advanced.items():
            if key == profile:
                frame.grid()
            else:
                frame.grid_remove()
        try:
            def integer(variable):
                text = variable.get().strip()
                if not re.fullmatch(r"[0-9]{1,5}", text):
                    raise InvalidNetworkInput("Размеры и overhead: целые неотрицательные числа.")
                return int(text)
            result = calculate_mtu(MtuOptions(
                size=integer(self.mtu_value), basis=BASES[self.mtu_basis.get()], profile=profile,
                inner_ip={"IPv4": 4, "IPv6": 6}[self.ip_version.get()],
                outer_ip={"IPv4": 4, "IPv6": 6}[self.outer_ip_version.get()],
                extra=integer(self.overhead_value), vlan_tags=integer(self.mtu_vlan_tags),
                pppoe=self.mtu_pppoe.get(), inner_tags=integer(self.mtu_inner_tags),
                gre_checksum=self.mtu_gre_checksum.get(), gre_key=self.mtu_gre_key.get(),
                gre_sequence=self.mtu_gre_sequence.get(), esp_mode=self.mtu_esp_mode.get(),
                esp_cipher=self.mtu_esp_cipher.get(), nat_t=self.mtu_nat_t.get(),
                openvpn_v2=self.mtu_openvpn_format.get() == "DATA_V2",
                openvpn_tap=self.mtu_openvpn_mode.get() == "TAP",
                l2tp_length=self.mtu_l2tp_length.get(), l2tp_sequence=self.mtu_l2tp_sequence.get(),
                ppp_header=integer(self.mtu_ppp_header)))
        except (InvalidNetworkInput, KeyError) as error:
            self.mtu_calculation = None
            self.mss_table.clear()
            self._set_text(self.mtu_breakdown, "")
            self.mss_error.set(str(error) if isinstance(error, InvalidNetworkInput) else "Выберите параметры из списка.")
            return
        self.mtu_calculation = result
        self.mss_table.update(result.rows())
        self._set_text(self.mtu_breakdown, result.explanation())
        self.mss_error.set("")

    def _routes_modified(self, _event):
        if self.routes_input.edit_modified():
            self.routes_input.edit_modified(False)
            self._routes_update()

    @staticmethod
    def _set_text(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _routes_update(self, *_args):
        try:
            result = lookup_routes(self.route_address.get(), self.routes_input.get("1.0", "end-1c"))
        except InvalidNetworkInput as error:
            self.routes_error.set(str(error))
            self._set_text(self.routes_output, "")
            self.routes_copy_button.state(["disabled"])
            return
        self.routes_error.set("")
        self._set_text(self.routes_output, result.copy_text())
        self.routes_copy_button.state(["!disabled"])

    def _acl_update(self, *_args):
        try:
            result = check_wildcard(
                self.acl_base.get(), self.acl_wildcard.get(), self.acl_address.get()
            )
        except InvalidNetworkInput as error:
            self.acl_table.clear()
            self.acl_error.set(str(error))
            return
        self.acl_error.set("")
        self.acl_table.update(result.rows())

    def _copy(self, value):
        if not value:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            self.root.update_idletasks()
        except tk.TclError:
            self.status.set("Clipboard unavailable. Try Copy again.")
            return
        self.status.set("Copied")

    def copy_result(self):
        self._copy(self.result.get())

    def copy_ipv4(self):
        if self.ipv4_calculation is not None:
            self._copy(self.ipv4_calculation.copy_text())

    def copy_routes(self):
        if self.routes_copy_button.instate(["!disabled"]):
            self._copy(self.routes_output.get("1.0", "end-1c"))

    def copy_current_tool(self, _event=None):
        index = self.notebook.index(self.notebook.select())
        if index == 0:
            self.copy_result()
        elif index == 1:
            self.copy_ipv4()
        elif index == 3:
            self.copy_routes()
        elif index == 5:
            self.copy_password()
        elif index == 4:
            self.copy_acl()
        elif self.mtu_calculation is not None:
            self._copy(self.mtu_calculation.copy_text())
        return "break"

    def show_hosts(self):
        if self.ipv4_calculation is None:
            return
        if self.host_window is not None and self.host_window.winfo_exists():
            self.host_window.destroy()
        self.host_calculation = self.ipv4_calculation
        self.host_page_number = 0
        window = tk.Toplevel(self.root)
        self.host_window = window
        window.title(f"Адреса: {self.host_calculation.network}")
        window.transient(self.root)
        window.geometry("490x540")
        window.minsize(440, 400)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        label = "Адреса блока" if self.host_calculation.network.prefixlen == 0 else "Адреса хостов"
        ttk.Label(frame, text=f"{label}: {self.host_calculation.network}").grid(
            row=0, column=0, sticky="w"
        )
        self.host_page_label = tk.StringVar(window)
        ttk.Label(frame, textvariable=self.host_page_label).grid(
            row=1, column=0, sticky="w", pady=(7, 10)
        )
        container, self.host_text = self._text_widget(frame, height=15, readonly=True)
        container.grid(row=2, column=0, sticky="nsew")
        navigation = ttk.Frame(frame)
        navigation.grid(row=3, column=0, sticky="ew", pady=(12, 8))
        self.host_prev_button = ttk.Button(
            navigation, text="Назад", command=lambda: self._host_move(-1)
        )
        self.host_prev_button.pack(side="left")
        self.host_next_button = ttk.Button(
            navigation, text="Далее", command=lambda: self._host_move(1)
        )
        self.host_next_button.pack(side="left", padx=8)
        self.host_page_entry_value = tk.StringVar(window, value="1")
        ttk.Entry(navigation, textvariable=self.host_page_entry_value, width=10).pack(side="left")
        ttk.Button(navigation, text="Перейти", command=self._host_jump).pack(side="left", padx=8)
        ttk.Button(frame, text="Копировать страницу", command=self.copy_host_page).grid(
            row=4, column=0, sticky="w"
        )
        self._render_host_page()
        self._apply_theme()
        window.after_idle(self.host_text.focus_set)

    def _render_host_page(self):
        result = host_page(self.host_calculation, self.host_page_number)
        self.host_page_label.set(
            f"Страница {result.page + 1} / {result.pages} · адресов {result.total}"
        )
        self.host_page_entry_value.set(str(result.page + 1))
        self._set_text(self.host_text, "\n".join(result.addresses))
        self.host_prev_button.state(["disabled" if result.page == 0 else "!disabled"])
        self.host_next_button.state(
            ["disabled" if result.page + 1 == result.pages else "!disabled"]
        )

    def _host_move(self, delta):
        result = host_page(self.host_calculation, self.host_page_number)
        target = result.page + delta
        if 0 <= target < result.pages:
            self.host_page_number = target
            self._render_host_page()

    def _host_jump(self):
        try:
            text = self.host_page_entry_value.get().strip()
            if not re.fullmatch(r"[0-9]{1,10}", text):
                raise InvalidNetworkInput("Введите номер страницы.")
            target = int(text) - 1
            host_page(self.host_calculation, target)
        except InvalidNetworkInput as error:
            self.host_page_label.set(str(error))
            return
        self.host_page_number = target
        self._render_host_page()

    def copy_host_page(self):
        self._copy(self.host_text.get("1.0", "end-1c"))

    @staticmethod
    def _select_all(event):
        if isinstance(event.widget, tk.Text):
            event.widget.tag_add(tk.SEL, "1.0", "end-1c")
        else:
            event.widget.selection_range(0, tk.END)
            event.widget.icursor(tk.END)
        return "break"

    def focus_input(self, _event=None):
        index = self.notebook.index(self.notebook.select())
        self._canvases[index].yview_moveto(0)
        entry = (
            self.input_entry,
            self.ipv4_entry,
            self.mtu_entry,
            self.route_entry,
            self.acl_entry,
            self.password_length_entry,
        )[index]
        entry.focus_set()
        entry.selection_range(0, tk.END)
        return "break"

    def select_tool(self, index):
        self.notebook.select(index)
        self.root.after_idle(self.focus_input)
        return "break"

    def _scroll_tool(self, event):
        if isinstance(event.widget, tk.Text):
            return None
        canvas = self._canvases[self.notebook.index(self.notebook.select())]
        canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _show_focused_field(self, event):
        if not isinstance(event.widget, tk.Misc):
            return
        index = self.notebook.index(self.notebook.select())
        page, canvas = self.pages[index], self._canvases[index]
        if not str(event.widget).startswith(str(page) + "."):
            return
        height = max(page.winfo_height(), 1)
        top = event.widget.winfo_rooty() - page.winfo_rooty()
        bottom = top + event.widget.winfo_height()
        visible_top = canvas.yview()[0] * height
        visible_bottom = visible_top + canvas.winfo_height()
        if top < visible_top:
            canvas.yview_moveto(max(0, top - 8) / height)
        elif bottom > visible_bottom:
            canvas.yview_moveto((bottom + 8 - canvas.winfo_height()) / height)

    def _report_callback_error(
        self,
        _exception: type[BaseException],
        _value: BaseException,
        _traceback: TracebackType | None,
    ) -> None:
        self.result.set("")
        self.copy_button.state(["disabled"])
        self.clear_password()
        self.ipv4_calculation = None
        self.ipv4_binary.set("")
        for table in (
            self.ipv4_addresses_table,
            self.ipv4_mask_table,
            self.ipv4_range_table,
            self.mss_table,
            self.acl_table,
        ):
            table.clear()
        self._set_text(self.routes_output, "")
        self._set_text(self.acl_output, "")
        self._set_text(self.mtu_breakdown, "")
        self.mtu_calculation = None
        for button in (
            self.acl_copy_button,
            self.ipv4_copy_button,
            self.ipv4_binary_copy,
            self.hosts_button,
            self.routes_copy_button,
        ):
            button.state(["disabled"])
        self.status.set("Unexpected error. Restart the application.")
