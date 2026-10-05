import tkinter as tk

import pytest

pytestmark = pytest.mark.gui


def test_initial_state(app):
    assert app.output_format.get() == "colon"
    assert not app.uppercase.get()
    assert app.result.get() == ""
    assert app.copy_button.instate(["disabled"])
    assert app.status.get() == "Ready"


def test_live_conversion_and_format_switch(app):
    app.input_entry.insert(0, "0011.2233.aabb")
    assert app.result.get() == "00:11:22:33:aa:bb"
    for output_format, expected in (
        ("cisco", "0011.2233.aabb"),
        ("hyphen", "00-11-22-33-aa-bb"),
        ("plain", "00112233aabb"),
        ("colon", "00:11:22:33:aa:bb"),
    ):
        app.format_buttons[output_format].invoke()
        assert app.result.get() == expected
    app.uppercase_button.invoke()
    assert app.result.get() == "00:11:22:33:AA:BB"
    app.format_buttons["cisco"].invoke()
    assert app.result.get() == "0011.2233.AABB"
    app.uppercase_button.invoke()
    assert app.result.get() == "0011.2233.aabb"


def test_copy_contains_only_result(app):
    app.input_value.set("0011.2233.aabb")
    app.copy_button.invoke()
    app.root.update()
    assert app.root.clipboard_get() == "00:11:22:33:aa:bb"
    assert app.status.get() == "Copied"
    app.output_format.set("cisco")
    assert app.status.get() == "Ready"


def test_invalid_input_clears_stale_result_and_recovers(app):
    app.input_value.set("0011.2233.aabb")
    app.input_value.set("00:11:22:ZZ:44:55")
    assert app.result.get() == ""
    assert app.copy_button.instate(["disabled"])
    assert "Invalid MAC address" in app.status.get()
    app.input_value.set("aabb.ccdd.eeff")
    assert app.result.get() == "aa:bb:cc:dd:ee:ff"
    assert app.copy_button.instate(["!disabled"])


def test_empty_input_resets_status_and_disables_copy(app):
    app.input_value.set("123")
    assert "Expected 12" in app.status.get()
    app.input_value.set(" ")
    assert app.result.get() == ""
    assert app.status.get() == "Ready"
    assert app.copy_button.instate(["disabled"])


def test_copy_without_result_preserves_clipboard(app):
    app.root.clipboard_clear()
    app.root.clipboard_append("existing clipboard")
    app.copy_result()
    app.root.update()
    assert app.root.clipboard_get() == "existing clipboard"


def test_clipboard_error_does_not_crash(app, monkeypatch):
    app.input_value.set("0011.2233.aabb")

    def unavailable():
        raise tk.TclError("clipboard busy")

    monkeypatch.setattr(app.root, "clipboard_clear", unavailable)
    app.copy_result()
    assert app.status.get() == "Clipboard unavailable. Try Copy again."
    assert app.result.get() == "00:11:22:33:aa:bb"


def test_paste_updates_result(app):
    app.root.clipboard_clear()
    app.root.clipboard_append("AABB.CCDD.EEFF")
    app.input_entry.event_generate("<<Paste>>")
    app.root.update()
    assert app.result.get() == "aa:bb:cc:dd:ee:ff"


def test_result_is_readonly_but_selectable(app):
    app.input_value.set("00112233aabb")
    app.result_entry.insert(0, "incorrect")
    assert app.result.get() == "00:11:22:33:aa:bb"
    app.result_entry.selection_range(0, tk.END)
    assert app.result_entry.selection_present()


def test_ctrl_l_focuses_and_selects_input(app):
    app.input_value.set("00112233aabb")
    app.result_entry.focus_force()
    app.root.update()
    app.root.event_generate("<Control-l>")
    app.root.update()
    assert app.root.focus_get() == app.input_entry
    assert app.input_entry.selection_present()


def test_ctrl_a_in_result(app):
    app.input_value.set("00112233aabb")
    app.result_entry.focus_force()
    app.root.update()
    app.result_entry.event_generate("<Control-a>")
    app.root.update()
    assert app.result_entry.selection_present()


def test_unexpected_callback_error_is_not_exposed(app):
    app.input_value.set("00112233aabb")
    app.root.report_callback_exception(RuntimeError, RuntimeError("private details"), None)
    assert app.result.get() == ""
    assert app.copy_button.instate(["disabled"])
    assert app.status.get() == "Unexpected error. Restart the application."
