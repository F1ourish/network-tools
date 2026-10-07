import json
import tkinter as tk

import pytest

from mac_converter.help_content import TOOL_HELP

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def synthetic_ui_passwords(monkeypatch):
    from mac_converter import gui

    def synthetic(options):
        groups = options.groups()
        start = "".join(group[0] for group in groups)
        return start + groups[0][0] * (options.length - len(start))

    monkeypatch.setattr(gui, "generate_password", synthetic)


def generate(app):
    app.select_tool(5)
    app.root.update()
    app.password_generate_button.invoke()
    return app.password_result.get()


def test_password_starts_empty_hidden_and_copies_only_secret(app):
    assert len(app.notebook.tabs()) == 6
    assert app.password_length.get() == "20"
    assert app.password_result.get() == ""
    assert app.password_copy_button.instate(["disabled"])
    value = generate(app)
    assert len(value) == 20
    assert app.password_result_entry.cget("show") == "*"
    app.password_copy_button.invoke()
    app.root.update()
    assert app.root.clipboard_get() == value
    assert app._clipboard_job is not None
    app.password_show_button.invoke()
    assert app.password_result_entry.cget("show") == ""
    app.select_tool(0)
    app.root.update()
    assert app.password_result_entry.cget("show") == "*"


def test_bad_options_clear_secret_and_disable_actions_then_recover(app):
    generate(app)
    app.password_length.set("7")
    assert app.password_result.get() == ""
    assert app.password_copy_button.instate(["disabled"])
    assert app.password_generate_button.instate(["disabled"])
    app.password_length.set("24")
    assert app.password_generate_button.instate(["!disabled"])
    assert len(generate(app)) == 24
    for value in app.password_groups.values():
        value.set(False)
    assert app.password_result.get() == ""
    assert app.password_generate_button.instate(["disabled"])


def test_custom_symbols_and_weak_space_hint(app):
    for name in ("lowercase", "uppercase", "digits"):
        app.password_groups[name].set(False)
    app.password_symbols.set("!@")
    assert set(generate(app)) <= {"!", "@"}
    assert "Небольшое пространство" in app.password_info.get()
    app.password_symbols.set("!")
    assert app.password_generate_button.instate(["disabled"])


def test_clipboard_auto_clear_preserves_replaced_clipboard(app):
    value = generate(app)
    app.copy_password()
    app.root.clipboard_clear()
    app.root.clipboard_append("other content")
    app._clear_password_clipboard()
    assert app.root.clipboard_get() == "other content"
    assert app._copied_password is None
    assert app._clipboard_job is None
    assert app.password_result.get() == value
    app.copy_password()
    app._clear_password_clipboard()
    with pytest.raises(tk.TclError):
        app.root.clipboard_get()


def test_clear_button_clears_only_owned_clipboard_and_masks(app):
    generate(app)
    app.copy_password()
    app.password_show_button.invoke()
    app.password_clear_button.invoke()
    assert app.password_result.get() == ""
    assert app.password_result_entry.cget("show") == "*"
    assert app.password_copy_button.instate(["disabled"])
    assert app._copied_password is None


def test_clipboard_timer_can_be_disabled(app):
    generate(app)
    app.password_auto_clear.set(False)
    app.copy_password()
    assert app._clipboard_job is None
    assert app.status.get() == "Copied"


def test_random_and_clipboard_failure_do_not_expose_secret(app, monkeypatch):
    from mac_converter import gui

    def unavailable(*_args):
        raise OSError("sensitive details")

    monkeypatch.setattr(gui, "generate_password", unavailable)
    generate(app)
    assert app.password_result.get() == ""
    assert app.password_copy_button.instate(["disabled"])
    assert "sensitive" not in app.password_error.get()


def test_theme_settings_never_contain_password_and_result_readonly(app):
    value = generate(app)
    app.password_result_entry.insert(0, "bad")
    assert app.password_result.get() == value
    app.set_theme("night")
    assert app.password_result.get() == value
    assert json.loads(app.settings.path.read_text()) == {"theme": "night"}
    assert value not in app.settings.path.read_text()


def test_password_keyboard_selection_and_copy(app):
    app.root.focus_force()
    app.root.event_generate("<Control-Key-6>")
    app.root.update()
    assert app.root.focus_get() == app.password_length_entry
    value = generate(app)
    app.root.event_generate("<Control-Shift-C>")
    app.root.update()
    assert app.root.clipboard_get() == value


@pytest.mark.parametrize("index", range(len(TOOL_HELP)))
def test_help_opens_for_active_tool_and_follows_tab(app, index):
    app.select_tool(index)
    app.root.update()
    app.help_button.invoke()
    app.root.update()
    assert app.help_title.get() == TOOL_HELP[index].name
    assert app.help_text.cget("state") == "disabled"
    assert app.help_text.get("1.0", "end-1c") == TOOL_HELP[index].text()
    app.select_tool((index + 1) % len(TOOL_HELP))
    app.root.update()
    assert app.help_title.get() == TOOL_HELP[(index + 1) % len(TOOL_HELP)].name
    app.help_close_button.invoke()
    app.show_help()
    app.root.update()
    assert app.help_window.winfo_exists()


def test_f1_and_escape_and_help_theme(app):
    app.select_tool(4)
    app.root.focus_force()
    app.root.update()
    app.root.event_generate("<F1>")
    app.root.update()
    assert "permit/deny" in app.help_text.get("1.0", "end-1c")
    app.set_theme("night")
    assert app.help_text.cget("background") == app.routes_input.cget("background")
    app.help_window.focus_force()
    app.help_window.event_generate("<Escape>")
    app.root.update()
    assert not app.help_window.winfo_exists()
