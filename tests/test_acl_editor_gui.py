import tkinter as tk

import pytest

pytestmark = pytest.mark.gui


def activate(app):
    app.notebook.select(4)
    app.root.update()


def test_editor_controls_remain_visible_in_normal_window(app):
    app.root.geometry("940x760")
    activate(app)
    canvas = app._canvases[4]
    bottom = canvas.winfo_rooty() + canvas.winfo_height()
    for control in (*app.acl_expand_buttons, *app.acl_absent_buttons):
        assert control.winfo_rooty() + control.winfo_height() <= bottom


def test_acl_scrollbars_follow_content_and_resize(app):
    activate(app)
    editor = app.acl_editors[0]
    editor.set_text("permit ip any any")
    app.root.update()
    assert not editor.vertical.winfo_ismapped()
    assert not editor.horizontal.winfo_ismapped()
    editor.set_text("\n".join(["! " + "long " * 100] * 60))
    app.root.update()
    assert editor.vertical.winfo_ismapped()
    assert editor.horizontal.winfo_ismapped()
    editor.set_text("permit ip any any")
    app.root.update()
    assert not editor.vertical.winfo_ismapped()
    assert not editor.horizontal.winfo_ismapped()


def test_button_and_ctrl_paste_clean_acl_but_preserve_route_text(app):
    activate(app)
    raw = "   10 permit ip any any (4 matches)  \n 20 deny ip any any (1 match) "
    app.root.clipboard_clear()
    app.root.clipboard_append(raw)
    app.acl_forward_input.paste_button.invoke()
    app.root.update()
    assert app.acl_forward_input.get("1.0", "end-1c") == "10 permit ip any any\n20 deny ip any any"
    app.acl_reverse_input.tag_add(tk.SEL, "1.0", "end")
    app.acl_reverse_input.event_generate("<<Paste>>")
    app.root.update()
    assert "matches" not in app.acl_reverse_input.get("1.0", "end-1c")
    app._paste(app.routes_input, replace=True)
    assert app.routes_input.get("1.0", "end-1c") == raw


def test_absent_check_keeps_acl_text_and_rechecks_when_reenabled(app):
    activate(app)
    editor = app.acl_editors[0]
    editor.set_text("200 permit udp object-group CONFERENCE_NET eq 8801 any")
    app._acl_flow_update()
    assert "object-group" in app.acl_flow_error.get()
    original = editor.text.get("1.0", "end-1c")
    app.acl_absent[0].set(True)
    assert not app.acl_flow_error.get()
    assert "разрешены" in app.acl_conclusion.get()
    assert editor.text.get("1.0", "end-1c") == original
    app.acl_absent[0].set(False)
    assert "object-group" in app.acl_flow_error.get()
    assert editor.error_line == 1


def test_expanded_editor_syncs_live_and_closing_keeps_changes(app):
    activate(app)
    app.acl_expand_buttons[0].invoke()
    app.root.update()
    window, editor = app._acl_editor_windows[0]
    assert editor.text.winfo_width() > app.acl_forward_input.winfo_width()
    window.focus_force()
    window.event_generate("<Control-KeyPress-l>")
    app.root.update()
    assert app.root.focus_get() is editor.text
    assert editor.text.get(tk.SEL_FIRST, tk.SEL_LAST) == app.acl_forward_input.get("1.0", "end-1c")
    editor.text.delete("1.0", "end")
    editor.text.insert("1.0", "permit ip any any")
    app.root.update()
    assert app.acl_forward_input.get("1.0", "end-1c") == "permit ip any any"
    app.acl_absent[0].set(True)
    window.event_generate("<Escape>")
    app.root.update()
    assert 0 not in app._acl_editor_windows
    assert app.acl_absent[0].get()
    app.set_theme("day")
    app.set_theme("night")
    assert not app.status.get().startswith("Unexpected error")


def test_error_highlights_correct_editor_line_and_clears_when_fixed(app):
    activate(app)
    editor = app.acl_editors[1]
    editor.set_text("permit ip any any\npermit tcp any any time-range OFFICE")
    app._acl_flow_update()
    assert editor.error_line == 2
    assert tuple(map(str, editor.text.tag_ranges("acl_error"))) == (
        "2.0",
        editor.text.index("2.end"),
    )
    assert app.acl_editors[0].error_line is None
    editor.set_text("permit ip any any")
    app._acl_flow_update()
    assert editor.error_line is None
    assert not editor.text.tag_ranges("acl_error")


def test_cisco_direction_labels_follow_selected_interface_side(app):
    assert "<name> in" in app.acl_direction_labels[0].get()
    assert "<name> out" in app.acl_direction_labels[1].get()
    app.acl_interface.set("Со стороны назначения")
    assert "<name> out" in app.acl_direction_labels[0].get()
    assert "<name> in" in app.acl_direction_labels[1].get()


def test_expanded_editor_follows_main_edits_examples_and_clear(app):
    activate(app)
    app.open_acl_editor(0)
    app.root.update()
    window, editor = app._acl_editor_windows[0]
    app.acl_forward_input.delete("1.0", "end")
    app.acl_forward_input.insert("1.0", "deny ip any any")
    app.root.update()
    assert editor.text.get("1.0", "end-1c") == "deny ip any any"
    app._acl_example()
    app.root.update()
    assert "ip access-list extended REQUEST" in editor.text.get("1.0", "end-1c")
    app._acl_clear()
    app.root.update()
    assert editor.text.get("1.0", "end-1c") == ""
    app.open_acl_editor(0)
    assert app._acl_editor_windows[0][0] is window


def test_visible_line_numbers_follow_vertical_scroll(app):
    activate(app)
    editor = app.acl_editors[0]
    editor.set_text("\n".join(f"! line {number}" for number in range(1, 61)))
    app.root.update()
    assert editor.gutter.itemcget(editor.gutter.find_all()[0], "text") == "1"
    editor.text.yview_moveto(1)
    app.root.update()
    numbers = [int(editor.gutter.itemcget(item, "text")) for item in editor.gutter.find_all()]
    assert numbers[0] > 1
    assert numbers[-1] == 60
