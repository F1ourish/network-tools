"""Themed desktop tools; calculation rules are separate from widgets."""

from pathlib import Path
import re
import tkinter as tk
from tkinter import font
from types import TracebackType

import ttkbootstrap as ttk

from . import __version__
from .mac import InvalidMacAddress, format_mac
from .network import (
    InvalidNetworkInput,
    IPv4Calculation,
    calculate_ipv4,
    calculate_mss,
    check_wildcard,
    host_page,
    lookup_routes,
)
from .settings import ThemeSettings


class OutputTable:
    def __init__(self, app, parent, labels):
        self.frame = ttk.Frame(parent)
        self.frame.columnconfigure(1, weight=1)
        self.values, self.entries, self.buttons = {}, {}, {}
        for row, label in enumerate(labels):
            value = tk.StringVar(app.root, value="—")
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
            variable.set(rows.get(label, "—"))
            self.buttons[label].state(["!disabled" if variable.get() != "—" else "disabled"])

    def clear(self):
        for label, variable in self.values.items():
            variable.set("—")
            self.buttons[label].state(["disabled"])


class MacConverterApp:
    def __init__(self, root: tk.Misc, *, settings_path: Path | None = None) -> None:
        self.root = root
        root.title(f"MAC Address Converter {__version__} — Network Tools")
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
        self.notebook = ttk.Notebook(shell)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        self.pages = []
        for name in ("MAC", "IPv4", "MTU / MSS", "Маршруты", "ACL wildcard"):
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
            ),
            self.pages,
            strict=True,
        ):
            builder(page)
        self.status_label = ttk.Label(shell, textvariable=self.status, wraplength=760)
        self.status_label.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.notebook.bind("<<NotebookTabChanged>>", lambda _event: self.status.set("Ready"))
        root.bind("<Control-l>", self.focus_input)
        root.bind("<Control-L>", self.focus_input)
        for index in range(5):
            root.bind(
                f"<Control-Key-{index + 1}>", lambda event, page=index: self.select_tool(page)
            )
        root.bind("<Control-Shift-c>", self.copy_current_tool)
        root.bind("<Control-Shift-C>", self.copy_current_tool)
        root.bind("<Control-Shift-t>", self.toggle_theme)
        root.bind("<Control-Shift-T>", self.toggle_theme)
        root.bind("<MouseWheel>", self._scroll_tool)
        root.bind("<FocusIn>", self._show_focused_field)
        self._apply_theme()
        self._ipv4_update()
        self._mss_update()
        self._routes_update()
        self._acl_update()
        self.status.set("Ready")
        root.minsize(820, 610)
        root.geometry("940x650")
        root.after_idle(self.input_entry.focus_set)

    def _bind_selection(self, widget):
        widget.bind("<Control-a>", self._select_all)
        widget.bind("<Control-A>", self._select_all)

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
        self.ipv4_entry.bind("<<Paste>>", self._paste_ipv4)
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
        self.mss_error = tk.StringVar(self.root)
        inputs = ttk.Frame(page)
        inputs.grid(row=0, column=0, sticky="ew")
        for column in range(3):
            inputs.columnconfigure(column, weight=1)
        self.mtu_entry = self._field(inputs, "Исходный IP MTU", self.mtu_value)
        self._field(inputs, "Инкапсуляция, байт", self.overhead_value, 1)
        self.version_entry = self._field(
            inputs, "Версия внутреннего IP", self.ip_version, 2, values=("IPv4", "IPv6")
        )
        self.version_entry.configure(state="readonly")
        ttk.Label(page, textvariable=self.mss_error, wraplength=780, bootstyle="danger").grid(
            row=1, column=0, sticky="ew", pady=(12, 4)
        )
        self.mss_table = OutputTable(self, page, calculate_mss("1500").rows().keys())
        self.mss_table.frame.grid(row=2, column=0, sticky="ew", pady=(8, 16))
        ttk.Label(
            page,
            text=(
                "MSS учитывает фиксированные IP/TCP-заголовки. Опции уменьшают фактический объём TCP-данных отдельно. "
                "Инкапсуляция задаётся вручную; Path MTU не измеряется."
            ),
            wraplength=780,
            bootstyle="secondary",
        ).grid(row=3, column=0, sticky="ew")
        for variable in (self.mtu_value, self.overhead_value, self.ip_version):
            variable.trace_add("write", self._mss_update)

    def _text_widget(self, parent, *, height=8, readonly=False):
        container = ttk.Frame(parent)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)
        text = tk.Text(container, height=height, width=50, wrap="word", font=self.fixed_font)
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
        self.acl_base = tk.StringVar(self.root, value="10.10.0.0")
        self.acl_wildcard = tk.StringVar(self.root, value="0.0.255.254")
        self.acl_address = tk.StringVar(self.root, value="10.10.5.2")
        self.acl_error = tk.StringVar(self.root)
        inputs = ttk.Frame(page)
        inputs.grid(row=0, column=0, sticky="ew")
        for column in range(3):
            inputs.columnconfigure(column, weight=1)
        self.acl_entry = self._field(inputs, "Базовый IPv4", self.acl_base)
        self._field(inputs, "Wildcard", self.acl_wildcard, 1)
        self._field(inputs, "Проверяемый IPv4", self.acl_address, 2)
        ttk.Label(page, textvariable=self.acl_error, wraplength=780, bootstyle="danger").grid(
            row=1, column=0, sticky="ew", pady=(12, 4)
        )
        self.acl_table = OutputTable(
            self, page, check_wildcard("10.10.0.0", "0.0.255.254", "10.10.5.2").rows().keys()
        )
        self.acl_table.frame.grid(row=2, column=0, sticky="ew", pady=(8, 16))
        ttk.Label(
            page,
            text=(
                "В wildcard: 0 — сравнить бит, 1 — игнорировать. Поддерживаются прерывистые маски. "
                "Проверяется только адресное условие, без permit/deny, порядка правил и портов."
            ),
            wraplength=780,
            bootstyle="secondary",
        ).grid(row=3, column=0, sticky="ew")
        for variable in (self.acl_base, self.acl_wildcard, self.acl_address):
            variable.trace_add("write", self._acl_update)

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

    def _paste_ipv4(self, _event):
        try:
            text = self.root.clipboard_get().strip()
            if "/" not in text:
                return None
            result = calculate_ipv4(text)
        except (tk.TclError, InvalidNetworkInput):
            return None
        self._syncing_ipv4 = True
        self.ipv4_address.set(str(result.address))
        self.ipv4_mask.set(f"/{result.network.prefixlen}")
        self._syncing_ipv4 = False
        self._ipv4_update()
        return "break"

    def _normalize_ipv4(self, _event=None):
        if self.ipv4_calculation is not None and "/" in self.ipv4_address.get():
            self.ipv4_address.set(str(self.ipv4_calculation.address))

    def _mss_update(self, *_args):
        try:
            version = {"IPv4": 4, "IPv6": 6}[self.ip_version.get()]
            result = calculate_mss(self.mtu_value.get(), version, self.overhead_value.get())
        except (InvalidNetworkInput, KeyError) as error:
            self.mss_table.clear()
            self.mss_error.set(str(error))
            return
        self.mss_table.update(result.rows())
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
        else:
            table = self.mss_table if index == 2 else self.acl_table
            if all(value.get() != "—" for value in table.values.values()):
                self._copy(
                    "\n".join(f"{label}: {value.get()}" for label, value in table.values.items())
                )
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
        for button in (
            self.ipv4_copy_button,
            self.ipv4_binary_copy,
            self.hosts_button,
            self.routes_copy_button,
        ):
            button.state(["disabled"])
        self.status.set("Unexpected error. Restart the application.")
