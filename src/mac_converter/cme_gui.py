"""CUCME workspace: adjustable panes, paired inventory and separate diagnostics."""

import re
import tkinter as tk

import ttkbootstrap as ttk

from .acl_editor import AclEditor
from .cme import (
    COPY_LIMIT,
    PAIR_RESOURCE,
    RESOURCE_KINDS,
    SEARCH_KINDS,
    CMESyntaxError,
    SectionAvailability,
    availability_report,
    diagnostics_report,
    free_numbers,
    free_report,
    lookup_report,
    parse_config,
    section_availability,
)
from .cme_view import CMEReportView, expand_button
from .network import InvalidNetworkInput

EXAMPLE_CONFIG = """telephony-service
 max-dn 200
 max-ephones 100
!
ephone-dn 85 dual-line
 number 31085
 description 31085
 name Example Alex
 label Example A.
 call-forward busy 31900
 call-forward noan 31901 timeout 20
!
ephone-dn 30
!
ephone 585
 description Example Alex Office
 mac-address 0011.2233.4455
 type 7942
 button 1:85
!
ephone 760
!
"""


class CMEPanel:
    def _build_cme(self, page):
        self._cme_job = None
        self.cme_config = self.cme_free_result = None
        self.cme_report_window = self.cme_expanded_output = None
        self.cme_input_window = self.cme_expanded_editor = None
        self.cme_notes_window = self.cme_notes_output = None
        self._cme_report_buttons = []
        self._cme_rows = ()
        self._cme_syncing_input = False
        self.cme_page_number, self.cme_pages = 0, 1
        self.cme_mode = tk.StringVar(self.root, value="search")
        self.cme_query = tk.StringVar(self.root)
        self.cme_search_kind = tk.StringVar(self.root, value="Любое поле")
        self.cme_free_kind = tk.StringVar(self.root, value=PAIR_RESOURCE)
        self.cme_first = tk.StringVar(self.root, value="1")
        self.cme_last = tk.StringVar(self.root, value="100")
        self.cme_error = tk.StringVar(self.root)
        self.cme_notice = tk.StringVar(self.root)
        self.cme_summary = tk.StringVar(self.root, value="Вставьте конфигурацию ephone/ephone-dn.")
        self.cme_page_label = tk.StringVar(self.root)
        self.cme_page_value = tk.StringVar(self.root, value="1")
        self.cme_notes_label = tk.StringVar(self.root, value="Замечания · F8")
        page.rowconfigure(3, weight=1)
        modes = ttk.Frame(page)
        modes.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.cme_search_mode_button = ttk.Radiobutton(
            modes, text="Поиск / проверка", variable=self.cme_mode, value="search", takefocus=True
        )
        self.cme_search_mode_button.pack(side="left")
        self.cme_free_mode_button = ttk.Radiobutton(
            modes, text="Свободные номера", variable=self.cme_mode, value="free", takefocus=True
        )
        self.cme_free_mode_button.pack(side="left", padx=(18, 0))
        self.cme_search_frame = ttk.Frame(page)
        self.cme_search_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        for column in range(2):
            self.cme_search_frame.columnconfigure(column, weight=1)
        self.cme_query_entry = self._field(
            self.cme_search_frame, "Телефон, ephone/DN или имя", self.cme_query
        )
        self.cme_search_selector = self._field(
            self.cme_search_frame, "Искать по", self.cme_search_kind, 1, values=tuple(SEARCH_KINDS)
        )
        self.cme_search_selector.configure(state="readonly")
        self.cme_free_frame = ttk.Frame(page)
        self.cme_free_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        for column in range(3):
            self.cme_free_frame.columnconfigure(column, weight=1)
        self.cme_free_selector = self._field(
            self.cme_free_frame, "Ресурс", self.cme_free_kind, values=RESOURCE_KINDS
        )
        self.cme_free_selector.configure(state="readonly")
        self.cme_first_entry = self._field(self.cme_free_frame, "Диапазон от", self.cme_first, 1)
        self.cme_last_entry = self._field(
            self.cme_free_frame, "до (включительно)", self.cme_last, 2
        )
        self.cme_free_frame.grid_remove()
        ttk.Label(page, textvariable=self.cme_notice, bootstyle="secondary").grid(
            row=2, column=0, sticky="ew", pady=(0, 3)
        )
        self.cme_panes = ttk.Panedwindow(page, orient="vertical")
        self.cme_panes.grid(row=3, column=0, sticky="nsew")
        input_panel = ttk.Frame(self.cme_panes)
        input_panel.columnconfigure(0, weight=1)
        input_panel.rowconfigure(1, weight=1)
        self.cme_panes.add(input_panel, weight=1)
        header = ttk.Frame(input_panel)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(header, text="Конфигурация · F4").pack(side="left")
        self.cme_example_button = ttk.Button(header, text="Пример", command=self.cme_example)
        self.cme_example_button.pack(side="right", padx=(5, 0))
        self.cme_clear_button = ttk.Button(header, text="Очистить", command=self.clear_cme_config)
        self.cme_clear_button.pack(side="right", padx=(5, 0))
        self.cme_paste_button = ttk.Button(
            header,
            text="Вставить конфиг",
            command=lambda: self._paste(self.cme_config_input, replace=True),
        )
        self.cme_paste_button.pack(side="right", padx=(5, 0))
        self.cme_input_expand_button = expand_button(
            header, self.open_cme_input, "Развернуть редактор конфигурации · Ctrl+Enter в редакторе"
        )
        self.cme_input_expand_button.pack(side="right", padx=(5, 0))
        self.cme_editor = AclEditor(self, input_panel, height=3, changed=self._cme_config_changed)
        self.cme_editor.grid(row=1, column=0, sticky="nsew")
        self.cme_config_input = self.cme_editor.text
        self.cme_config_input.acl_normalize = False
        self.cme_config_input.bind("<Control-Return>", self.open_cme_input)
        output_panel = ttk.Frame(self.cme_panes, padding=(0, 5, 0, 0))
        output_panel.columnconfigure(0, weight=1)
        output_panel.rowconfigure(1, weight=1)
        self.cme_panes.add(output_panel, weight=2)
        header = ttk.Frame(output_panel)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(header, text="Результат · F6").pack(side="left")
        self.cme_expand_button = expand_button(
            header, self.open_cme_report, "Развернуть результат · Ctrl+Enter"
        )
        self.cme_expand_button.pack(side="right")
        self.cme_report_view = CMEReportView(self, output_panel)
        self.cme_report_view.grid(row=1, column=0, sticky="nsew")
        self.cme_output = self.cme_report_view.text
        self.cme_table = self.cme_report_view.table
        actions = ttk.Frame(output_panel)
        actions.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        self.cme_copy_button = ttk.Button(
            actions, text="Копировать отчёт", command=self.copy_cme_report
        )
        self.cme_copy_button.pack(side="left")
        self.cme_copy_numbers_button = ttk.Button(
            actions, text="Все строки", command=self.copy_cme_numbers
        )
        self.cme_copy_numbers_button.pack(side="left", padx=5)
        self.cme_prev_button = ttk.Button(actions, text="Назад", command=lambda: self._cme_move(-1))
        self.cme_prev_button.pack(side="left", padx=(8, 0))
        self.cme_next_button = ttk.Button(actions, text="Далее", command=lambda: self._cme_move(1))
        self.cme_next_button.pack(side="left", padx=5)
        self.cme_jump_entry = ttk.Entry(actions, textvariable=self.cme_page_value, width=6)
        self.cme_jump_entry.pack(side="left")
        self._bind_selection(self.cme_jump_entry)
        self.cme_jump_button = ttk.Button(actions, text="Перейти", command=self._cme_jump)
        self.cme_jump_button.pack(side="left", padx=5)
        ttk.Label(actions, textvariable=self.cme_page_label).pack(side="left", padx=4)
        footer = ttk.Frame(page)
        footer.grid(row=4, column=0, sticky="ew", pady=(5, 0))
        footer.columnconfigure(0, weight=1)
        summary = ttk.Label(footer, textvariable=self.cme_summary)
        summary.grid(row=0, column=0, sticky="w")
        self.cme_notes_button = ttk.Button(
            footer, textvariable=self.cme_notes_label, command=self.open_cme_notes
        )
        self.cme_notes_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        footer.bind(
            "<Configure>",
            lambda event: summary.configure(
                wraplength=max(250, event.width - self.cme_notes_button.winfo_width() - 20)
            ),
        )
        self.cme_panes.bind("<ButtonRelease-1>", self._cme_limit_panes)
        for widget in (
            self.cme_query_entry,
            self.cme_first_entry,
            self.cme_last_entry,
            self.cme_output,
            self.cme_table,
        ):
            widget.bind("<Control-Return>", self.open_cme_report)
        for key, command in (
            ("F4", self.focus_cme_config),
            ("F6", self.focus_cme_result),
            ("F8", self.open_cme_notes),
        ):
            self.root.bind(
                f"<{key}>",
                lambda event, action=command: action(event)
                if self.notebook.index(self.notebook.select()) == 7
                else None,
            )
        self.cme_mode.trace_add("write", self._cme_mode_changed)
        for variable in (
            self.cme_query,
            self.cme_search_kind,
            self.cme_free_kind,
            self.cme_first,
            self.cme_last,
        ):
            variable.trace_add("write", self._cme_controls_changed)
        self._cme_clear_result()
        self._cme_update_notes()

    def _cme_limit_panes(self, _event=None):
        height = self.cme_panes.winfo_height()
        if height > 220:
            self.cme_panes.sashpos(0, min(max(90, self.cme_panes.sashpos(0)), height - 130))

    def focus_cme_config(self, _event=None):
        self.cme_config_input.focus_set()
        return "break"

    def focus_cme_result(self, _event=None):
        self.cme_report_view.focus_result()
        return "break"

    def _cancel_cme_job(self):
        if self._cme_job is not None:
            self.root.after_cancel(self._cme_job)
            self._cme_job = None

    def _cme_clear_result(self):
        self.cme_free_result = None
        self.cme_pages = 1
        self.cme_page_label.set("")
        self._cme_rows = ()
        self.cme_report_view.set_report("")
        for button in (
            self.cme_copy_button,
            self.cme_copy_numbers_button,
            self.cme_prev_button,
            self.cme_next_button,
            self.cme_jump_button,
            self.cme_jump_entry,
        ):
            button.state(["disabled"])
        self._sync_cme_report()

    def _sync_cme_report(self):
        if self.cme_report_window is None:
            return
        value = self.cme_output.get("1.0", "end-1c")
        self.cme_expanded_view.set_report(value, self._cme_rows)
        for mirror, source in self._cme_report_buttons:
            mirror.state(["disabled"] if source.instate(["disabled"]) else ["!disabled"])

    def _cme_update_notes(self):
        error = self.cme_error.get()
        count = len(self.cme_config.warnings) if self.cme_config is not None else 0
        self.cme_notes_label.set(f"Замечания: {count}" + (" · ошибка" if error else " · F8"))
        self.cme_notice.set(
            "Операция не выполнена. Причина и исправление - в «Замечаниях»."
            if error
            else "Разделитель меняет высоту областей. Конфиг остаётся в памяти до очистки или закрытия."
        )
        if self.cme_notes_window is not None:
            self._set_text(
                self.cme_notes_output,
                diagnostics_report(
                    self.cme_config, error, self.cme_config_input.get("1.0", "end-1c")
                ),
            )

    def _cme_window(self, title):
        window = tk.Toplevel(self.root)
        window.title(title + " - Network Tools")
        window.geometry(
            f"{max(640, self.root.winfo_screenwidth() - 60)}x{max(400, self.root.winfo_screenheight() - 100)}+20+20"
        )
        window.minsize(640, 400)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        try:
            window.state("zoomed")
        except tk.TclError:
            pass
        return window

    def open_cme_input(self, _event=None):
        if self.cme_input_window is not None:
            self.cme_input_window.deiconify()
            self.cme_input_window.lift()
            self.cme_expanded_editor.text.focus_set()
            return "break"
        window = self._cme_window("Конфигурация CUCME")
        self.cme_input_window = window
        ttk.Label(
            window, text="Конфигурация CUCME · изменения сразу передаются во вкладку", padding=12
        ).grid(row=0, column=0, sticky="ew")
        editor = AclEditor(self, window, height=20, changed=self._cme_config_changed)
        self.cme_expanded_editor = editor
        editor.text.acl_normalize = False
        editor.set_text(self.cme_config_input.get("1.0", "end-1c"))
        editor.grid(row=1, column=0, sticky="nsew", padx=12)
        if self.cme_editor.error_line:
            editor.show_error(self.cme_editor.error_line)
        controls = ttk.Frame(window, padding=12)
        controls.grid(row=2, column=0, sticky="ew")
        ttk.Button(
            controls, text="Вставить конфиг", command=lambda: self._paste(editor.text, replace=True)
        ).pack(side="left")
        ttk.Button(controls, textvariable=self.cme_notes_label, command=self.open_cme_notes).pack(
            side="left", padx=6
        )
        ttk.Button(controls, text="Вернуться · Esc", command=self.close_cme_input).pack(
            side="right"
        )
        window.bind("<Escape>", self.close_cme_input)
        window.protocol("WM_DELETE_WINDOW", self.close_cme_input)
        window.bind(
            "<Destroy>",
            lambda event: self._cme_input_destroyed() if event.widget == window else None,
        )
        self._apply_theme()
        window.after_idle(editor.text.focus_set)
        return "break"

    def _cme_input_destroyed(self):
        self.cme_input_window = self.cme_expanded_editor = None

    def close_cme_input(self, _event=None):
        if self.cme_input_window is not None:
            self.cme_input_window.destroy()
            self.root.lift()
            self.cme_config_input.focus_set()
        return "break"

    def open_cme_report(self, _event=None):
        if self.cme_report_window is not None:
            self.cme_report_window.deiconify()
            self.cme_report_window.lift()
            self.cme_expanded_view.focus_result()
            return "break"
        window = self._cme_window("Отчёт CUCME")
        self.cme_report_window = window
        ttk.Label(window, text="Результат CUCME · та же страница, что во вкладке", padding=12).grid(
            row=0, column=0, sticky="ew"
        )
        self.cme_expanded_view = CMEReportView(self, window, large=True)
        self.cme_expanded_view.grid(row=1, column=0, sticky="nsew", padx=12)
        self.cme_expanded_output = self.cme_expanded_view.text
        for widget in (self.cme_expanded_output, self.cme_expanded_view.table):
            widget.bind("<Control-Return>", self.close_cme_report)
        controls = ttk.Frame(window, padding=12)
        controls.grid(row=2, column=0, sticky="ew")
        for text, command, source in (
            ("Копировать отчёт", self.copy_cme_report, self.cme_copy_button),
            ("Назад", lambda: self._cme_move(-1), self.cme_prev_button),
            ("Далее", lambda: self._cme_move(1), self.cme_next_button),
        ):
            button = ttk.Button(controls, text=text, command=command)
            button.pack(side="left", padx=(0, 6))
            self._cme_report_buttons.append((button, source))
        ttk.Label(controls, textvariable=self.cme_page_label).pack(side="left", padx=6)
        ttk.Button(controls, text="Вернуться · Esc", command=self.close_cme_report).pack(
            side="right"
        )
        window.protocol("WM_DELETE_WINDOW", self.close_cme_report)
        window.bind("<Escape>", self.close_cme_report)
        window.bind("<Control-KeyPress>", self._cme_report_key)
        window.bind(
            "<Destroy>",
            lambda event: self._cme_report_destroyed() if event.widget == window else None,
        )
        self._sync_cme_report()
        self._apply_theme()
        window.after_idle(self.cme_expanded_view.focus_result)
        return "break"

    def _cme_report_destroyed(self):
        self.cme_report_window = self.cme_expanded_output = None
        self._cme_report_buttons = []

    def _cme_report_key(self, event):
        key = (
            event.keycode == 67
            if self.root.tk.call("tk", "windowingsystem") == "win32"
            else event.keysym.lower() == "c"
        )
        if event.state & 1 and key:
            self.copy_cme_report()
            return "break"
        return None

    def close_cme_report(self, _event=None):
        if self.cme_report_window is not None:
            self.cme_report_window.destroy()
            self.root.lift()
            self.cme_report_view.focus_result()
        return "break"

    def open_cme_notes(self, _event=None):
        if self.cme_notes_window is not None:
            self.cme_notes_window.deiconify()
            self.cme_notes_window.lift()
            self.cme_notes_output.focus_set()
            return "break"
        window = self._cme_window("Замечания CUCME")
        self.cme_notes_window = window
        ttk.Label(
            window, text="Замечания относятся ко всему вставленному конфигу", padding=12
        ).grid(row=0, column=0, sticky="ew")
        container, text = self._text_widget(window, height=20, readonly=True)
        self.cme_notes_output = text
        text.configure(font="TkDefaultFont", spacing1=2, spacing3=2)
        container.grid(row=1, column=0, sticky="nsew", padx=12)
        controls = ttk.Frame(window, padding=12)
        controls.grid(row=2, column=0, sticky="ew")
        ttk.Button(
            controls,
            text="Копировать замечания",
            command=lambda: self._copy(text.get("1.0", "end-1c")),
        ).pack(side="left")
        ttk.Button(controls, text="Вернуться · Esc", command=self.close_cme_notes).pack(
            side="right"
        )
        window.bind("<Escape>", self.close_cme_notes)
        window.protocol("WM_DELETE_WINDOW", self.close_cme_notes)

        def destroyed(event):
            if event.widget == window:
                self._plain_text_widgets.remove(text)
                self.cme_notes_window = self.cme_notes_output = None

        window.bind("<Destroy>", destroyed)
        self._cme_update_notes()
        self._apply_theme()
        window.after_idle(text.focus_set)
        return "break"

    def close_cme_notes(self, _event=None):
        if self.cme_notes_window is not None:
            self.cme_notes_window.destroy()
            self.root.lift()
            self.cme_notes_button.focus_set()
        return "break"

    def _cme_config_changed(self, event=None):
        if self._cme_syncing_input:
            return
        self._cme_syncing_input = True
        try:
            source = event.widget if event is not None else self.cme_config_input
            value = source.get("1.0", "end-1c")
            for editor in (self.cme_editor, self.cme_expanded_editor):
                if editor is not None and editor.text is not source:
                    editor.set_text(value)
                if editor is not None:
                    editor.show_error()
        finally:
            self._cme_syncing_input = False
        self._cancel_cme_job()
        self.cme_config = None
        self.cme_page_number = 0
        self._cme_clear_result()
        self.cme_error.set("")
        self.cme_summary.set("Конфигурация изменена; выполняется проверка.")
        self._cme_update_notes()
        self._cme_job = self.root.after(180, self._cme_parse)

    def _cme_parse(self):
        self._cancel_cme_job()
        self.cme_config = None
        self._cme_clear_result()
        for editor in (self.cme_editor, self.cme_expanded_editor):
            if editor is not None:
                editor.show_error()
        value = self.cme_config_input.get("1.0", "end-1c")
        if not value.strip():
            self.cme_error.set("")
            self.cme_summary.set("Вставьте конфигурацию ephone/ephone-dn.")
            self._cme_update_notes()
            return
        try:
            self.cme_config = parse_config(value)
        except InvalidNetworkInput as error:
            self.cme_error.set(str(error))
            self.cme_summary.set(
                "Конфигурация не разобрана. Конфиг сохранён; подробности в «Замечаниях»."
            )
            if isinstance(error, CMESyntaxError):
                for editor in (self.cme_editor, self.cme_expanded_editor):
                    if editor is not None:
                        editor.show_error(error.line)
            self._cme_update_notes()
            return
        self.cme_summary.set(self.cme_config.summary())
        self._cme_render()

    def _cme_mode_changed(self, *_args):
        if self.cme_mode.get() == "free":
            self.cme_search_frame.grid_remove()
            self.cme_free_frame.grid()
        else:
            self.cme_free_frame.grid_remove()
            self.cme_search_frame.grid()
        self._cme_controls_changed()
        # Map the newly selected fields before accepting Ctrl+L / paste.
        self.root.update_idletasks()
        if self.notebook.index(self.notebook.select()) == 7:
            self.focus_input()

    def _cme_controls_changed(self, *_args):
        self.cme_page_number = 0
        self.cme_page_value.set("1")
        self._cme_clear_result()
        if self.cme_config is not None:
            self._cme_render()

    def _cme_render(self):
        config = self.cme_config
        if config is None:
            return
        rows = ()
        try:
            if self.cme_mode.get() == "free":
                if self.cme_free_kind.get() == PAIR_RESOURCE:
                    result = section_availability(config, self.cme_first.get(), self.cme_last.get())
                    value, pages = availability_report(result, self.cme_page_number)
                    rows, _ = result.page(self.cme_page_number)
                else:
                    result = free_numbers(
                        config, "number", self.cme_first.get(), self.cme_last.get()
                    )
                    value, pages = free_report(config, result, self.cme_page_number)
            else:
                result = None
                if not self.cme_query.get().strip():
                    self.cme_error.set("")
                    self.cme_report_view.set_report(
                        "Введите телефон, номер ephone/ephone-dn или часть имени. Конфиг остаётся в редакторе."
                    )
                    self._sync_cme_report()
                    self._cme_update_notes()
                    return
                value, pages = lookup_report(
                    config,
                    self.cme_query.get(),
                    SEARCH_KINDS.get(self.cme_search_kind.get(), ""),
                    self.cme_page_number,
                )
        except InvalidNetworkInput as error:
            self.cme_error.set(str(error))
            self._cme_clear_result()
            self._cme_update_notes()
            return
        self.cme_error.set("")
        self.cme_free_result, self.cme_pages, self._cme_rows = result, pages, rows
        self.cme_report_view.set_report(value, rows)
        self.cme_page_value.set(str(self.cme_page_number + 1))
        self.cme_page_label.set(f"{self.cme_page_number + 1} / {pages}")
        self.cme_copy_button.state(["!disabled"])
        self.cme_copy_numbers_button.configure(text="Все строки" if rows else "Все номера")
        self.cme_copy_numbers_button.state(
            ["!disabled"] if result is not None and 0 < result.total <= COPY_LIMIT else ["disabled"]
        )
        self.cme_prev_button.state(["disabled"] if self.cme_page_number == 0 else ["!disabled"])
        self.cme_next_button.state(
            ["disabled"] if self.cme_page_number + 1 == pages else ["!disabled"]
        )
        self.cme_jump_entry.state(["!disabled"])
        self.cme_jump_button.state(["!disabled"])
        self._sync_cme_report()
        self._cme_update_notes()

    def _cme_move(self, delta):
        target = self.cme_page_number + delta
        if self.cme_config is not None and 0 <= target < self.cme_pages:
            self.cme_page_number = target
            self._cme_render()

    def _cme_jump(self):
        text = self.cme_page_value.get().strip()
        if not re.fullmatch(r"[0-9]{1,16}", text) or not 1 <= int(text) <= self.cme_pages:
            self.cme_error.set(f"Номер страницы должен быть от 1 до {self.cme_pages}.")
            self._cme_update_notes()
            return
        self.cme_page_number = int(text) - 1
        self._cme_render()

    def clear_cme_config(self):
        for editor in (self.cme_editor, self.cme_expanded_editor):
            if editor is not None:
                editor.set_text("")
                editor.text.edit_reset()
        self._cme_config_changed()
        self._cme_parse()

    def cme_example(self):
        for editor in (self.cme_editor, self.cme_expanded_editor):
            if editor is not None:
                editor.set_text(EXAMPLE_CONFIG)
                editor.text.edit_reset()
        self.cme_query.set("585")
        self._cme_config_changed()
        self._cme_parse()

    def copy_cme_report(self):
        if self.cme_copy_button.instate(["!disabled"]):
            self._copy(self.cme_output.get("1.0", "end-1c"))

    def copy_cme_numbers(self):
        result = self.cme_free_result
        if self.cme_copy_numbers_button.instate(["!disabled"]) and result is not None:
            self._copy(
                result.all_text()
                if isinstance(result, SectionAvailability)
                else "\n".join(result.all_numbers())
            )
