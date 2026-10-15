import json
import tkinter as tk

import pytest

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
    app.cme_free_mode_button.invoke()
    assert "Свободные ephone-dn ID: 98" in output(app)
    app.cme_first.set("bad")
    assert app.cme_error.get()
    assert output(app) == "" and app.cme_copy_button.instate(["disabled"])
    app.cme_first.set("1")
    app.cme_search_mode_button.invoke()
    app.cme_query.set("585")
    assert "type: 7942" in output(app)
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
        ("ephone ID", "585"),
        ("ephone-dn ID", "85"),
        ("Телефон", "31085"),
        ("Имя / label", "Example A."),
        ("Имя / label", "Office"),
    ):
        app.cme_search_kind.set(kind)
        app.cme_query.set(query)
        assert "ephone 585: ЗАНЯТ" in output(app)
        assert "button 1:85 -> ephone-dn 85" in output(app)
        assert "description DN (телефон): 31085" in output(app)
        assert "name: Example Alex; label: Example A." in output(app)


def test_edit_invalidates_immediately_then_line_error_and_correction_preserve_input(app):
    load(app)
    app.cme_query.set("585")
    bad = EXAMPLE_CONFIG.replace("button 1:85", "button 1z85")
    app.cme_config_input.delete("1.0", "end")
    app.cme_config_input.insert("1.0", bad)
    app.root.update()
    assert app.cme_config is None and output(app) == ""
    app._cme_parse()
    assert app.cme_error.get() and app.cme_editor.error_line == 17
    assert app.cme_config_input.get("1.0", "end-1c") == bad
    app.root.clipboard_clear()
    app.root.clipboard_append("sentinel")
    app.copy_cme_report()
    assert app.root.clipboard_get() == "sentinel"
    load(app)
    assert app.cme_editor.error_line is None and app.cme_error.get() == ""
    assert "ephone 585: ЗАНЯТ" in output(app)


def test_free_resources_copy_and_limit_count_not_phone_tag(app):
    load(app)
    app.cme_mode.set("free")
    app.cme_free_kind.set("ephone ID")
    app.cme_first.set("584")
    app.cme_last.set("586")
    assert app.cme_error.get() == ""
    app.cme_copy_numbers_button.invoke()
    assert app.root.clipboard_get() == "584\n586"
    app.cme_free_kind.set("Телефонные номера")
    app.cme_first.set("31084")
    app.cme_last.set("31086")
    app.cme_copy_numbers_button.invoke()
    assert app.root.clipboard_get() == "31084\n31086"
    assert app.cme_config_input.get("1.0", "end-1c") == EXAMPLE_CONFIG


def test_pages_jump_report_shortcuts_and_readonly(app):
    load(app)
    app.cme_mode.set("free")
    app.cme_free_kind.set("ephone ID")
    app.cme_last.set("1000")
    assert app.cme_free_result.total == 998
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
    assert "ephone 585: ЗАНЯТ" in output(app)


def test_large_free_list_can_copy_report_but_not_entire_list(app):
    load(app)
    app.cme_mode.set("free")
    app.cme_free_kind.set("Телефонные номера")
    app.cme_last.set("9999999999999999")
    assert app.cme_copy_numbers_button.instate(["disabled"])
    assert app.cme_copy_button.instate(["!disabled"])


def test_search_keyboard_traversal_can_reach_configuration_and_actions(app):
    load(app)
    app.cme_query.set("585")
    app.root.update()
    assert app.cme_query_entry.tk_focusNext() == app.cme_search_selector
    assert app.cme_query_entry.tk_focusPrev() == app.cme_free_mode_button
    assert app.cme_free_mode_button.tk_focusPrev() == app.cme_search_mode_button
    assert app.cme_search_mode_button.tk_focusPrev() == app.cme_config_input
    assert app.cme_search_selector.tk_focusNext() == app.cme_output
