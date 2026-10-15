import json
import tkinter as tk

import pytest

from mac_converter.cme import PAIR_RESOURCE
from mac_converter.cme_gui import EXAMPLE_CONFIG

pytestmark = pytest.mark.gui


def load(app, value=EXAMPLE_CONFIG):
    app.select_tool(7)
    app.root.update()
    app.cme_editor.set_text(value)
    app._cme_config_changed()
    app.root.update()
    app._cme_parse()
    app.root.update()
    return app.cme_config


def output(app):
    return app.cme_output.get("1.0", "end-1c")


def test_empty_start_has_no_configuration_or_copyable_results(app):
    assert len(app.notebook.tabs()) == 8
    assert app.cme_config_input.get("1.0", "end-1c") == ""
    assert app.cme_config is None
    assert app.cme_copy_button.instate(["disabled"])
    assert app.cme_copy_numbers_button.instate(["disabled"])


@pytest.mark.parametrize("method", ["button", "ctrl_v", "shift_insert", "menu"])
def test_paste_keeps_exact_config_including_indentation_comments_and_commands(app, method):
    app.select_tool(7)
    app.root.update()
    app.cme_config_input.focus_force()
    app.root.clipboard_clear()
    app.root.clipboard_append(EXAMPLE_CONFIG)
    if method == "button":
        app.cme_paste_button.invoke()
    elif method == "ctrl_v":
        app.cme_config_input.event_generate("<Control-v>")
    elif method == "shift_insert":
        app.cme_config_input.event_generate("<Shift-Insert>")
    else:
        app._paste(app.cme_config_input)
    app.root.update()
    app._cme_parse()
    assert app.cme_config_input.get("1.0", "end-1c") == EXAMPLE_CONFIG
    assert app.cme_config is not None
    assert app.cme_error.get() == ""


def test_queries_modes_tab_theme_and_errors_reuse_model_and_keep_config(app):
    model = load(app)
    for query in ("585", "85", "31085", "Example A.", "Office", "not found", ""):
        app.cme_query.set(query)
        assert app.cme_config is model
        assert app.cme_config_input.get("1.0", "end-1c") == EXAMPLE_CONFIG
    app.cme_search_kind.set("Имя / label")
    app.root.focus_force()
    app.root.update()
    app.cme_free_mode_button.invoke()
    app.root.update()
    assert app.root.focus_get() == app.cme_first_entry
    assert "ephone-dn: 98" in output(app)
    assert app.cme_table.get_children()
    app.cme_first.set("bad")
    assert app.cme_error.get()
    assert output(app) == "" and app.cme_copy_button.instate(["disabled"])
    app.cme_first.set("1")
    app.cme_search_mode_button.invoke()
    assert app.cme_search_kind.get() == "Имя / label"
    app.cme_search_kind.set("Номер ephone")
    app.cme_query.set("585")
    assert "Модель (type): 7942" in output(app)
    assert "MAC: 0011.2233.4455" in output(app)
    app.select_tool(0)
    app.set_theme("night")
    app.select_tool(7)
    app.root.update()
    assert app.cme_config is model
    assert app.cme_config_input.get("1.0", "end-1c") == EXAMPLE_CONFIG
    assert json.loads(app.settings.path.read_text()) == {"theme": "night"}


def test_all_search_fields_show_mapping_without_overwriting_description(app):
    load(app)
    for kind, query in (
        ("Номер ephone", "585"),
        ("Номер ephone-dn", "85"),
        ("Телефон", "31085"),
        ("Имя / label", "Example A."),
        ("Имя / label", "Office"),
    ):
        app.cme_search_kind.set(kind)
        app.cme_query.set(query)
        assert "ephone 585: существует в конфигурации" in output(app)
        assert "button 1:85 -> ephone-dn 85" in output(app)
        assert "Описание (description): 31085" in output(app)
        assert "Имя (name): Example Alex; подпись (label): Example A." in output(app)


def test_edit_invalidates_immediately_then_line_error_and_correction_preserve_input(app):
    load(app)
    app.cme_query.set("585")
    bad = EXAMPLE_CONFIG.replace("button 1:85", "button 1z85")
    app.cme_config_input.delete("1.0", "end")
    app.cme_config_input.insert("1.0", bad)
    app.root.update()
    assert app.cme_config is None and output(app) == ""
    app._cme_parse()
    assert (
        app.cme_error.get()
        and app.cme_editor.error_line == EXAMPLE_CONFIG.splitlines().index(" button 1:85") + 1
    )
    assert app.cme_config_input.get("1.0", "end-1c") == bad
    app.root.clipboard_clear()
    app.root.clipboard_append("sentinel")
    app.copy_cme_report()
    assert app.root.clipboard_get() == "sentinel"
    load(app)
    assert app.cme_editor.error_line is None and app.cme_error.get() == ""
    assert "ephone 585: существует в конфигурации" in output(app)


def test_free_resources_copy_and_limit_count_not_phone_tag(app):
    load(app)
    app.cme_mode.set("free")
    app.cme_free_kind.set(PAIR_RESOURCE)
    app.cme_first.set("584")
    app.cme_last.set("586")
    assert app.cme_error.get() == ""
    app.cme_copy_numbers_button.invoke()
    copied = app.root.clipboard_get()
    assert "584\t✓ 584" in copied and "585\t✗ 585" in copied and "586\t✓ 586" in copied
    app.cme_free_kind.set("Телефонные номера")
    app.cme_first.set("31084")
    app.cme_last.set("31086")
    app.cme_copy_numbers_button.invoke()
    assert app.root.clipboard_get() == "31084\n31086"
    assert app.cme_config_input.get("1.0", "end-1c") == EXAMPLE_CONFIG


def test_pages_jump_report_shortcuts_and_readonly(app):
    load(app)
    app.cme_mode.set("free")
    app.cme_free_kind.set(PAIR_RESOURCE)
    app.cme_last.set("1000")
    assert app.cme_free_result.total == 1000
    app.cme_page_value.set("10")
    app.cme_jump_button.invoke()
    assert app.cme_page_number == 9 and "Страница 10 / 10" in output(app)
    app.cme_next_button.invoke()
    assert app.cme_page_number == 9
    app.cme_page_value.set("11")
    app.cme_jump_button.invoke()
    assert app.cme_page_number == 9 and "от 1 до 10" in app.cme_error.get()
    app.cme_page_value.set("10")
    app.cme_jump_button.invoke()
    before = output(app)
    app.cme_output.insert("1.0", "bad")
    assert output(app) == before
    app.root.focus_force()
    app.root.event_generate("<Control-Key-8>")
    app.root.update()
    assert app.root.focus_get() == app.cme_first_entry
    app.root.event_generate("<Control-Shift-C>")
    app.root.update()
    assert app.root.clipboard_get() == before
    app.cme_mode.set("search")
    app.focus_input()
    app.root.update()
    assert app.root.focus_get() == app.cme_query_entry


def test_explicit_clear_discards_model_output_and_editor_undo_history(app):
    load(app)
    app.cme_query.set("585")
    app.cme_clear_button.invoke()
    app.root.update()
    assert app.cme_config is None and output(app) == ""
    assert app.cme_config_input.get("1.0", "end-1c") == ""
    assert app.cme_copy_button.instate(["disabled"])
    with pytest.raises(tk.TclError):
        app.cme_config_input.edit_undo()
    app.cme_example_button.invoke()
    assert "ephone 585: существует в конфигурации" in output(app)


def test_large_free_list_can_copy_report_but_not_entire_list(app):
    load(app)
    app.cme_mode.set("free")
    app.cme_free_kind.set("Телефонные номера")
    app.cme_last.set("9999999999999999")
    assert app.cme_copy_numbers_button.instate(["disabled"])
    assert app.cme_copy_button.instate(["!disabled"])


def test_keyboard_shortcuts_reach_both_panes_and_expand_buttons_are_local(app):
    load(app)
    app.cme_query.set("585")
    app.root.update()
    assert app.cme_query_entry.tk_focusNext() == app.cme_search_selector
    assert app.cme_query_entry.tk_focusPrev() == app.cme_free_mode_button
    app.root.focus_force()
    app.root.event_generate("<F4>")
    app.root.update()
    assert app.root.focus_get() == app.cme_config_input
    app.root.event_generate("<F6>")
    app.root.update()
    assert app.root.focus_get() == app.cme_output
    assert app.cme_expand_button.master is not app.cme_input_expand_button.master
    app.root.geometry("820x610")
    app.root.update()
    for button in (app.cme_input_expand_button, app.cme_expand_button):
        assert button.winfo_ismapped()
        assert app.root.winfo_rootx() <= button.winfo_rootx()
        assert (
            button.winfo_rootx() + button.winfo_width()
            <= app.root.winfo_rootx() + app.root.winfo_width()
        )


def expanded(app):
    return app.cme_expanded_output.get("1.0", "end-1c")


def test_expand_button_opens_one_large_readonly_report_with_exact_copy_and_theme(app):
    load(app)
    app.cme_query.set("585")
    app.cme_expand_button.invoke()
    app.root.update()
    window = app.cme_report_window
    assert window is not None and window.winfo_exists()
    assert expanded(app) == output(app)
    assert app.cme_expanded_output.winfo_height() > app.cme_output.winfo_height()
    app.cme_expanded_output.insert("1.0", "bad")
    assert expanded(app) == output(app)
    app.cme_expanded_output.focus_force()
    app.cme_expanded_output.event_generate("<Control-Shift-C>")
    app.root.update()
    assert app.root.clipboard_get() == output(app)
    app._cme_report_buttons[0][0].invoke()
    assert app.root.clipboard_get() == output(app)
    app.open_cme_report()
    assert app.cme_report_window is window
    app.set_theme("night")
    assert str(app.cme_expanded_output.cget("background")) == app.style.colors.inputbg
    assert expanded(app) == output(app)
    window.event_generate("<Escape>")
    app.root.update()
    assert app.cme_report_window is None
    assert app.cme_config_input.get("1.0", "end-1c") == EXAMPLE_CONFIG
    app.set_theme("day")
    app.cme_query.set("760")
    app.cme_expand_button.invoke()
    assert expanded(app) == output(app) and "ephone 760: существует" in expanded(app)


def test_open_report_follows_search_pages_and_reports_errors_without_stale_copy(app):
    model = load(app)
    app.cme_query.set("585")
    app.open_cme_report()
    app.cme_query.set("760")
    assert expanded(app) == output(app) and "ephone 760: существует" in expanded(app)
    app.cme_mode.set("free")
    app.cme_free_kind.set(PAIR_RESOURCE)
    app.cme_last.set("1000")
    next_button = app._cme_report_buttons[2][0]
    previous_button = app._cme_report_buttons[1][0]
    next_button.invoke()
    assert "Страница 2 / 10" in expanded(app) and expanded(app) == output(app)
    assert previous_button.instate(["!disabled"])
    previous_button.invoke()
    assert "Страница 1 / 10" in expanded(app)
    app.cme_first.set("bad")
    assert expanded(app) == output(app) == ""
    assert app.cme_error.get()
    assert all(button.instate(["disabled"]) for button, _ in app._cme_report_buttons)
    app.root.clipboard_clear()
    app.root.clipboard_append("sentinel")
    app.copy_cme_report()
    assert app.root.clipboard_get() == "sentinel"
    app.cme_first.set("1")
    assert expanded(app) == output(app) and "Номера секций" in expanded(app)
    assert app.cme_config is model


def test_open_report_clears_on_config_edit_parse_failure_and_explicit_clear(app):
    load(app)
    app.cme_query.set("585")
    app.open_cme_report()
    bad = EXAMPLE_CONFIG.replace("button 1:85", "button bad")
    app.cme_editor.set_text(bad)
    app._cme_config_changed()
    assert expanded(app) == ""
    app._cme_parse()
    assert expanded(app) == "" and app.cme_error.get()
    assert app.cme_config_input.get("1.0", "end-1c") == bad
    load(app)
    assert expanded(app) == output(app) and "ephone 585" in expanded(app)
    app.clear_cme_config()
    assert expanded(app) == "" and app.cme_config is None
    assert all(button.instate(["disabled"]) for button, _ in app._cme_report_buttons)


def test_report_shortcut_destroy_reopen_and_callback_failure_cleanup(app):
    load(app)
    app.cme_query.set("585")
    for widget in (app.cme_query_entry, app.cme_output):
        widget.focus_force()
        widget.event_generate("<Control-Return>")
        app.root.update()
        assert app.cme_report_window is not None
        old_output = app.cme_expanded_output
        app.cme_report_window.destroy()
        assert app.cme_report_window is None and old_output not in app._plain_text_widgets
    app.open_cme_report()
    app._report_callback_error(RuntimeError, RuntimeError("test"), None)
    assert expanded(app) == output(app) == ""
    assert app.cme_config_input.get("1.0", "end-1c") == EXAMPLE_CONFIG
    app.close_cme_report()
    app.set_theme("night")


def test_empty_report_and_empty_query_do_not_offer_stale_copy(app):
    app.open_cme_report()
    assert expanded(app) == ""
    assert all(button.instate(["disabled"]) for button, _ in app._cme_report_buttons)
    load(app)
    app.cme_query.set("585")
    app.cme_query.set("")
    assert expanded(app) == output(app) and "Введите телефон" in expanded(app)
    assert app._cme_report_buttons[0][0].instate(["disabled"])


def test_panes_fill_window_height_and_user_can_redistribute_it(app):
    load(app)
    app.cme_query.set("585")
    app.root.geometry("820x610")
    app.root.update()
    small = app.cme_panes.winfo_height()
    initial = app.cme_panes.sashpos(0)
    app.cme_panes.sashpos(0, initial + 25)
    app.root.update()
    assert app.cme_panes.sashpos(0) >= initial + 20
    app.root.geometry("940x690")
    app.root.update()
    assert app.cme_panes.winfo_height() > small + 30
    assert app.pages[7].winfo_height() >= app._canvases[7].winfo_height()
    assert app.cme_panes.winfo_height() > app.pages[7].winfo_height() / 2
    assert app.cme_config_input.winfo_width() > 600


def test_real_pair_table_and_expanded_table_show_same_rows_and_copy_tsv(app):
    load(app)
    app.cme_mode.set("free")
    app.cme_first.set("84")
    app.cme_last.set("86")
    app.root.update()
    assert app.cme_table.winfo_ismapped() and not app.cme_output.winfo_ismapped()
    rows = [app.cme_table.item(item, "values") for item in app.cme_table.get_children()]
    assert len(rows) == 3
    assert rows[1][0] == "85" and rows[1][1].startswith("✓ 85") and rows[1][2].startswith("✗ 85")
    app.open_cme_report()
    app.root.update()
    mirror = app.cme_expanded_view.table
    assert [mirror.item(item, "values") for item in mirror.get_children()] == rows
    app.cme_report_view.table.selection_set(app.cme_table.get_children()[1])
    app.cme_report_view.copy_rows()
    assert app.root.clipboard_get().splitlines() == ["Номер\tephone\tephone-dn", "\t".join(rows[1])]
    app.cme_copy_numbers_button.invoke()
    assert len(app.root.clipboard_get().splitlines()) == 4
    app.cme_last.set("1000")
    app._cme_move(1)
    assert app.cme_expanded_view.rows == app.cme_report_view.rows
    assert "Страница 2 / 10" in expanded(app)


def test_expanded_config_is_editable_synchronized_and_clear_removes_both_undo_histories(app):
    load(app)
    app.cme_query.set("585")
    app.open_cme_report()
    app.cme_input_expand_button.invoke()
    app.root.update()
    editor = app.cme_expanded_editor
    assert editor.text.get("1.0", "end-1c") == EXAMPLE_CONFIG
    updated = EXAMPLE_CONFIG.replace("31900", "31999")
    editor.text.delete("1.0", "end")
    editor.text.insert("1.0", updated)
    app.root.update()
    app._cme_parse()
    assert app.cme_config_input.get("1.0", "end-1c") == updated
    assert "31999" in output(app) and expanded(app) == output(app)
    app.cme_config_input.delete("1.0", "end")
    app.cme_config_input.insert("1.0", EXAMPLE_CONFIG)
    app.root.update()
    app._cme_parse()
    assert editor.text.get("1.0", "end-1c") == EXAMPLE_CONFIG
    app.clear_cme_config()
    assert editor.text.get("1.0", "end-1c") == ""
    for text in (editor.text, app.cme_config_input):
        with pytest.raises(tk.TclError):
            text.edit_undo()
    app.close_cme_input()
    assert app.cme_input_window is None
    app.set_theme("night")


def test_diagnostics_window_is_separate_and_explains_sip_template_limit_without_blocking_tags(app):
    value = (
        EXAMPLE_CONFIG
        + "voice register global\n max-dn 20\n!\nephone-template 1\n codec g711ulaw\n!\n"
    )
    load(app, value)
    app.cme_query.set("585")
    assert "Замечания по всей конфигурации" not in output(app)
    app.cme_mode.set("free")
    assert app.cme_error.get() == "" and app.cme_table.get_children()
    app.open_cme_notes()
    app.root.update()
    app.cme_free_kind.set("Телефонные номера")
    assert output(app) == "" and app.cme_error.get()
    notes = app.cme_notes_output.get("1.0", "end-1c")
    assert "не ошибка конфига" in notes and "Выберите «ephone / ephone-dn»" in notes
    assert "voice register global (строка" in notes
    assert app.cme_copy_button.instate(["disabled"])
    app.cme_free_kind.set(PAIR_RESOURCE)
    assert app.cme_error.get() == "" and app.cme_table.get_children()
    assert "Не удалось выполнить" not in app.cme_notes_output.get("1.0", "end-1c")
    app.clear_cme_config()
    assert "Вставьте конфигурацию" in app.cme_notes_output.get("1.0", "end-1c")
    app.close_cme_notes()
    app.set_theme("day")


def test_notes_follow_physical_parse_error_and_both_editors_highlight_it(app):
    load(app)
    app.open_cme_input()
    app.open_cme_notes()
    bad = EXAMPLE_CONFIG.replace("button 1:85", "button bad")
    app.cme_editor.set_text(bad)
    app._cme_config_changed()
    app._cme_parse()
    line = bad.splitlines().index(" button bad") + 1
    assert app.cme_editor.error_line == app.cme_expanded_editor.error_line == line
    notes = app.cme_notes_output.get("1.0", "end-1c")
    assert f"Текст строки {line}:  button bad" in notes
    assert "Исправьте указанную строку" in notes
    assert output(app) == "" and app.cme_config_input.get("1.0", "end-1c") == bad
    app._report_callback_error(RuntimeError, RuntimeError("test"), None)
    assert "Внутренняя ошибка" in app.cme_notes_output.get("1.0", "end-1c")


def test_lookup_displays_configured_forwarding_without_config_warnings(app):
    load(app)
    app.cme_query.set("585")
    assert "Если занято (busy): 31900" in output(app)
    assert "Если нет ответа (noan): 31901 timeout 20" in output(app)
    assert "Замечания по всей конфигурации" not in output(app)
    assert app.cme_output.tag_ranges("heading")
