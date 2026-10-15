"""CUCME panel; one in-memory configuration shared by lookup and free-number modes."""

import re
import tkinter as tk

import ttkbootstrap as ttk

from .acl_editor import AclEditor
from .cme import (
    COPY_LIMIT,
    FREE_KINDS,
    SEARCH_KINDS,
    CMESyntaxError,
    free_numbers,
    free_report,
    lookup_report,
    parse_config,
)
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
        self.cme_config = None
        self.cme_free_result = None
        self.cme_page_number, self.cme_pages = 0, 1
        self.cme_mode = tk.StringVar(self.root, value="search")
        self.cme_query = tk.StringVar(self.root)
        self.cme_search_kind = tk.StringVar(self.root, value="Любое поле")
        self.cme_free_kind = tk.StringVar(self.root, value="ephone-dn ID")
        self.cme_first = tk.StringVar(self.root, value="1")
        self.cme_last = tk.StringVar(self.root, value="100")
        self.cme_error = tk.StringVar(self.root)
        self.cme_summary = tk.StringVar(self.root, value="Вставьте конфигурацию ephone/ephone-dn.")
        self.cme_page_label = tk.StringVar(self.root)
        self.cme_page_value = tk.StringVar(self.root, value="1")
        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(header, text="Конфигурация CUCME").pack(side="left")
        self.cme_example_button = ttk.Button(header, text="Пример", command=self.cme_example)
        self.cme_example_button.pack(side="right")
        self.cme_clear_button = ttk.Button(
            header, text="Очистить конфиг", command=self.clear_cme_config
        )
        self.cme_clear_button.pack(side="right", padx=5)
        self.cme_paste_button = ttk.Button(
            header,
            text="Вставить конфиг",
            command=lambda: self._paste(self.cme_config_input, replace=True),
        )
        self.cme_paste_button.pack(side="right")
        self.cme_editor = AclEditor(self, page, height=5, changed=self._cme_config_changed)
        self.cme_editor.grid(row=1, column=0, sticky="nsew")
        self.cme_config_input = self.cme_editor.text
        self.cme_config_input.acl_normalize = False
        ttk.Label(page, textvariable=self.cme_summary, wraplength=780).grid(
            row=2, column=0, sticky="ew", pady=(5, 0)
        )
        ttk.Label(page, textvariable=self.cme_error, bootstyle="danger", wraplength=780).grid(
            row=3, column=0, sticky="ew"
        )
        modes = ttk.Frame(page)
        modes.grid(row=4, column=0, sticky="ew", pady=(4, 7))
        self.cme_search_mode_button = ttk.Radiobutton(
            modes, text="Поиск / проверка", variable=self.cme_mode, value="search", takefocus=True
        )
        self.cme_search_mode_button.pack(side="left")
        self.cme_free_mode_button = ttk.Radiobutton(
            modes, text="Свободные номера", variable=self.cme_mode, value="free", takefocus=True
        )
        self.cme_free_mode_button.pack(side="left", padx=(18, 0))
        self.cme_search_frame = ttk.Frame(page)
        self.cme_search_frame.grid(row=5, column=0, sticky="ew", pady=(0, 7))
        for column in range(2):
            self.cme_search_frame.columnconfigure(column, weight=1)
        self.cme_query_entry = self._field(
            self.cme_search_frame, "Номер, ID или часть имени", self.cme_query
        )
        self.cme_search_selector = self._field(
            self.cme_search_frame, "Искать по", self.cme_search_kind, 1, values=tuple(SEARCH_KINDS)
        )
        self.cme_search_selector.configure(state="readonly")
        self.cme_free_frame = ttk.Frame(page)
        self.cme_free_frame.grid(row=5, column=0, sticky="ew", pady=(0, 7))
        for column in range(3):
            self.cme_free_frame.columnconfigure(column, weight=1)
        self.cme_free_selector = self._field(
            self.cme_free_frame, "Ресурс", self.cme_free_kind, values=tuple(FREE_KINDS)
        )
        self.cme_free_selector.configure(state="readonly")
        self.cme_first_entry = self._field(self.cme_free_frame, "Диапазон от", self.cme_first, 1)
        self.cme_last_entry = self._field(
            self.cme_free_frame, "до (включительно)", self.cme_last, 2
        )
        self.cme_free_frame.grid_remove()
        container, self.cme_output = self._text_widget(page, height=7, readonly=True)
        container.grid(row=6, column=0, sticky="nsew")
        actions = ttk.Frame(page)
        actions.grid(row=7, column=0, sticky="ew", pady=(7, 0))
        self.cme_copy_button = ttk.Button(
            actions, text="Копировать отчёт", command=self.copy_cme_report
        )
        self.cme_copy_button.pack(side="left")
        self.cme_copy_numbers_button = ttk.Button(
            actions, text="Все номера", command=self.copy_cme_numbers
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
        ttk.Label(actions, textvariable=self.cme_page_label).pack(side="left", padx=(4, 0))
        ttk.Label(
            page,
            text="Конфиг остаётся до явной очистки или закрытия. Данные не записываются на диск. Поиск по снимку, без проверки регистрации.",
            wraplength=780,
            bootstyle="secondary",
        ).grid(row=8, column=0, sticky="ew", pady=(7, 0))
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

    def _cancel_cme_job(self):
        if self._cme_job is not None:
            self.root.after_cancel(self._cme_job)
            self._cme_job = None

    def _cme_clear_result(self):
        self.cme_free_result = None
        self.cme_pages = 1
        self.cme_page_label.set("")
        self._set_text(self.cme_output, "")
        for button in (
            self.cme_copy_button,
            self.cme_copy_numbers_button,
            self.cme_prev_button,
            self.cme_next_button,
            self.cme_jump_button,
            self.cme_jump_entry,
        ):
            button.state(["disabled"])

    def _cme_config_changed(self, *_args):
        self._cancel_cme_job()
        self.cme_config = None
        self.cme_page_number = 0
        self._cme_clear_result()
        self.cme_error.set("")
        self.cme_editor.show_error()
        self.cme_summary.set("Конфигурация изменена; выполняется проверка.")
        self._cme_job = self.root.after(180, self._cme_parse)

    def _cme_parse(self):
        self._cancel_cme_job()
        self.cme_config = None
        self._cme_clear_result()
        self.cme_editor.show_error()
        value = self.cme_config_input.get("1.0", "end-1c")
        if not value.strip():
            self.cme_error.set("")
            self.cme_summary.set("Вставьте конфигурацию ephone/ephone-dn.")
            return
        try:
            self.cme_config = parse_config(value)
        except InvalidNetworkInput as error:
            self.cme_error.set(str(error))
            self.cme_summary.set("Конфигурация не разобрана; прежний результат очищен.")
            if isinstance(error, CMESyntaxError):
                self.cme_editor.show_error(error.line)
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
        try:
            if self.cme_mode.get() == "free":
                result = free_numbers(
                    config,
                    FREE_KINDS.get(self.cme_free_kind.get(), ""),
                    self.cme_first.get(),
                    self.cme_last.get(),
                )
                value, pages = free_report(config, result, self.cme_page_number)
            else:
                result = None
                if not self.cme_query.get().strip():
                    self.cme_error.set("")
                    self._set_text(
                        self.cme_output,
                        "Введите телефон, ID ephone/ephone-dn или часть имени. Конфигурация сохранена в памяти.",
                    )
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
            return
        self.cme_error.set("")
        self.cme_free_result, self.cme_pages = result, pages
        self._set_text(self.cme_output, value)
        self.cme_output.yview_moveto(0)
        self.cme_page_value.set(str(self.cme_page_number + 1))
        self.cme_page_label.set(f"{self.cme_page_number + 1} / {pages}")
        self.cme_copy_button.state(["!disabled"])
        self.cme_copy_numbers_button.state(
            ["!disabled"] if result is not None and 0 < result.total <= COPY_LIMIT else ["disabled"]
        )
        self.cme_prev_button.state(["disabled"] if self.cme_page_number == 0 else ["!disabled"])
        self.cme_next_button.state(
            ["disabled"] if self.cme_page_number + 1 == pages else ["!disabled"]
        )
        self.cme_jump_entry.state(["!disabled"])
        self.cme_jump_button.state(["!disabled"])

    def _cme_move(self, delta):
        target = self.cme_page_number + delta
        if self.cme_config is not None and 0 <= target < self.cme_pages:
            self.cme_page_number = target
            self._cme_render()

    def _cme_jump(self):
        text = self.cme_page_value.get().strip()
        if not re.fullmatch(r"[0-9]{1,16}", text) or not 1 <= int(text) <= self.cme_pages:
            self.cme_error.set(f"Номер страницы должен быть от 1 до {self.cme_pages}.")
            return
        self.cme_page_number = int(text) - 1
        self._cme_render()

    def clear_cme_config(self):
        self.cme_editor.set_text("")
        self.cme_config_input.edit_reset()
        self._cme_config_changed()
        self._cme_parse()

    def cme_example(self):
        self.cme_editor.set_text(EXAMPLE_CONFIG)
        self.cme_config_input.edit_reset()
        self.cme_query.set("585")
        self._cme_config_changed()
        self._cme_parse()

    def copy_cme_report(self):
        if self.cme_copy_button.instate(["!disabled"]):
            self._copy(self.cme_output.get("1.0", "end-1c"))

    def copy_cme_numbers(self):
        if self.cme_copy_numbers_button.instate(["!disabled"]) and self.cme_free_result is not None:
            self._copy("\n".join(self.cme_free_result.all_numbers()))
