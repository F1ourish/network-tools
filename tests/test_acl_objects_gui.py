import tkinter as tk

import pytest

pytestmark = pytest.mark.gui
GROUPS = "Network object group CLIENTS\nhost 192.0.2.10"


def setup_group_flow(app):
    app.notebook.select(4)
    app.acl_protocol.set("UDP")
    app.acl_source_port.set("8801")
    app.acl_destination_port.set("9000")
    app._set_acl_text(0, "200 permit udp object-group CLIENTS eq 8801 any\n300 deny ip any any")
    app._set_acl_text(
        1, "10 permit udp any eq 9000 object-group CLIENTS eq 8801\n20 deny ip any any"
    )
    app._acl_flow_update()
    app.root.update()


def test_object_window_live_paste_resolves_both_acls_and_escape_keeps_members(app):
    setup_group_flow(app)
    assert "show object-group CLIENTS" in app.acl_flow_error.get()
    app.acl_objects_button.invoke()
    app.root.update()
    window, editor = app.acl_objects_window, app.acl_objects_editor
    assert app.acl_object_name.get() == "CLIENTS"
    app.root.clipboard_clear()
    app.root.clipboard_append("edge#show object-group CLIENTS\n " + GROUPS + " \nedge#")
    app._paste(editor.text, replace=True)
    app.root.update()
    app._acl_flow_update()
    assert app.acl_objects_value == GROUPS
    assert "запрос и ответ разрешены" in app.acl_conclusion.get()
    assert "IP-группа CLIENTS источника" in app.acl_output.get("1.0", "end-1c")
    assert "IP-группа CLIENTS назначения" in app.acl_output.get("1.0", "end-1c")
    app.open_acl_objects()
    assert app.acl_objects_window is window
    window.event_generate("<Escape>")
    app.root.update()
    assert app.acl_objects_window is None and app.acl_objects_value == GROUPS
    app.open_acl_objects()
    app.root.update()
    assert app.acl_objects_editor.text.get("1.0", "end-1c") == GROUPS


def test_group_edit_clears_stale_report_then_rechecks_and_highlights_own_error(app):
    setup_group_flow(app)
    app._set_acl_objects(GROUPS)
    app.open_acl_objects()
    app.root.update()
    editor = app.acl_objects_editor
    editor.text.delete("2.0", "2.end")
    editor.text.insert("2.0", "host 203.0.113.10")
    app.root.update()
    assert app.acl_copy_button.instate(["disabled"])
    assert app.acl_output.get("1.0", "end-1c") == ""
    app._acl_flow_update()
    assert "ACL блокируют" in app.acl_conclusion.get()
    editor.text.insert(tk.END, "\ngroup-object CLIENTS")
    app.root.update()
    app._acl_flow_update()
    assert "Циклическое" in app.acl_flow_error.get()
    assert editor.error_line == 3
    assert all(item.error_line is None for item in app.acl_editors)
    app._set_acl_objects(GROUPS)
    assert not app.acl_objects_error.get() and editor.error_line is None
    assert app.acl_copy_button.instate(["!disabled"])


def test_named_group_accepts_raw_members_and_theme_is_safe_after_close(app):
    setup_group_flow(app)
    app.open_acl_objects()
    app.root.update()
    app._acl_add_object_group()
    assert app.acl_objects_value == "object-group network CLIENTS\n"
    assert "пуста" in app.acl_objects_error.get()
    app.root.clipboard_clear()
    app.root.clipboard_append("  host 192.0.2.10  ")
    app.acl_objects_editor.text.event_generate("<<Paste>>")
    app.root.update()
    app._acl_flow_update()
    assert "запрос и ответ разрешены" in app.acl_conclusion.get()
    app.acl_objects_window.event_generate("<Escape>")
    app.root.update()
    app.set_theme("day")
    app.set_theme("night")
    assert not app.status.get().startswith("Unexpected error")


def test_cleanup_syncs_full_terminal_output_and_preserves_bad_rule(app):
    app.notebook.select(4)
    app.open_acl_editor(0)
    app.root.update()
    app._set_acl_text(
        0,
        "edge#sh ip access-lists WEB\nExtended IP access list WEB\n 10 permit ip any any (9 matches)\nedge#",
    )
    app._acl_flow_update()
    assert app.acl_flow_error.get()
    app.acl_clean_button.invoke()
    expected = "ip access-list extended WEB\n10 permit ip any any"
    assert app.acl_forward_input.get("1.0", "end-1c") == expected
    assert app._acl_editor_windows[0][1].text.get("1.0", "end-1c") == expected
    assert not app.acl_flow_error.get()
    app._set_acl_text(0, "edge#sh ip access-lists WEB\n10 permit tcp any\nedge#")
    app.acl_clean_button.invoke()
    assert "Строка 1" in app.acl_flow_error.get()
    assert app.acl_editors[0].error_line == 1


def test_object_controls_fit_and_ctrl_l_selects_objects(app):
    setup_group_flow(app)
    app._set_acl_objects(GROUPS)
    app.open_acl_objects()
    window, editor = app.acl_objects_window, app.acl_objects_editor
    window.state("normal")
    window.geometry("940x760")
    window.focus_force()
    window.event_generate("<Control-KeyPress-l>")
    app.root.update()
    assert app.root.focus_get() is editor.text
    assert editor.text.get(tk.SEL_FIRST, tk.SEL_LAST) == GROUPS
    controls = window.grid_slaves(row=4)[0]
    assert (
        controls.winfo_rooty() + controls.winfo_height()
        <= window.winfo_rooty() + window.winfo_height()
    )
    assert editor.gutter.itemcget(editor.gutter.find_all()[0], "text") == "1"
