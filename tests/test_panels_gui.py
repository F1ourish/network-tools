import pytest

from mac_converter.cme_gui import EXAMPLE_CONFIG

pytestmark = pytest.mark.gui


def activate(app, tab, geometry="1040x1000"):
    app.root.maxsize(2000, 2000)
    app.root.geometry(geometry)
    app.select_tool(tab)
    app.root.update()


def drag(app, area, axes, dx=0, dy=0):
    handle = area.handles[axes]
    x, y = handle.winfo_rootx() + 3, handle.winfo_rooty() + 3
    handle.event_generate("<ButtonPress-1>", x=3, y=3, rootx=x, rooty=y)
    handle.event_generate("<B1-Motion>", x=3 + dx, y=3 + dy, rootx=x + dx, rooty=y + dy)
    handle.event_generate("<ButtonRelease-1>", x=3 + dx, y=3 + dy, rootx=x + dx, rooty=y + dy)
    app.root.update()
    assert area.grab_current() is None


@pytest.mark.parametrize(
    "tab,names",
    [
        (3, ("routes_input_area", "routes_output_area")),
        (4, ("acl_output_area",)),
        (6, ("free_ip_arp_editor", "free_ip_output_area")),
        (7, ("cme_editor", "cme_report_view")),
    ],
)
def test_large_fields_receive_spare_window_height(app, tab, names):
    activate(app, tab, "820x610")
    small = [getattr(app, name).body.winfo_height() for name in names]
    activate(app, tab)
    for name, height in zip(names, small, strict=True):
        area = getattr(app, name)
        assert area.body.winfo_height() > height + 35
        assert area.body.winfo_width() > 250
    if tab == 4:
        assert all(editor.body.winfo_height() > 100 for editor in app.acl_editors)


def test_cme_both_fields_resize_from_edges_and_corners_without_changing_config(app):
    activate(app, 7)
    app.cme_editor.set_text(EXAMPLE_CONFIG)
    app._cme_config_changed()
    app._cme_parse()
    app.cme_query.set("585")
    app.root.update()
    input_area, result = app.cme_editor, app.cme_report_view
    before = input_area.winfo_height(), result.winfo_height()
    drag(app, input_area, "y", dy=55)
    assert input_area.winfo_height() > before[0] + 45
    assert result.winfo_height() < before[1] - 45
    height, width = result.winfo_height(), result.body.winfo_width()
    drag(app, result, "xy", dx=-120, dy=-40)
    assert result.body.winfo_width() < width - 100
    assert result.winfo_height() > height + 30
    width = input_area.body.winfo_width()
    drag(app, input_area, "x", dx=-100)
    assert input_area.body.winfo_width() < width - 85
    result.reset_size()
    input_area.reset_size()
    app.root.update()
    assert result.body.winfo_width() == input_area.body.winfo_width()
    assert app.cme_config_input.get("1.0", "end-1c") == EXAMPLE_CONFIG
    assert "ephone 585" in app.cme_output.get("1.0", "end-1c")


def test_acl_fields_share_width_and_result_height_and_keep_all_controls_in_bounds(app):
    activate(app, 4)
    left, right = app.acl_editors
    widths = left.winfo_width(), right.winfo_width()
    drag(app, left, "x", dx=60)
    assert left.winfo_width() > widths[0] + 40
    assert right.winfo_width() < widths[1] - 40
    before = app.acl_output_area.winfo_height()
    drag(app, right, "y", dy=-50)
    assert app.acl_output_area.winfo_height() > before + 35
    right.reset_size()
    app.root.update()
    before = app.acl_output_area.winfo_height()
    drag(app, app.acl_output_area, "xy", dx=-100, dy=-35)
    assert app.acl_output_area.winfo_height() > before + 20
    assert app.acl_output_area.width_fraction < 1
    for editor in (left, right):
        assert editor.text.winfo_height() >= 25
        assert editor.winfo_rootx() >= app.pages[4].winfo_rootx()
        assert (
            editor.winfo_rootx() + editor.winfo_width()
            <= app.pages[4].winfo_rootx() + app.pages[4].winfo_width()
        )


def test_free_ip_fields_resize_in_both_axes_and_grow_proportionally_afterwards(app):
    activate(app, 6)
    left, right = app.free_ip_arp_editor, app.free_ip_output_area
    before = right.winfo_width(), right.body.winfo_height()
    drag(app, right, "xy", dx=-50, dy=-80)
    assert right.winfo_width() > before[0] + 35
    assert right.body.winfo_height() < before[1] - 60
    fraction = right.height_fraction
    activate(app, 6, "1100x1100")
    assert right.height_fraction == fraction
    assert right.body.winfo_height() > before[1] - 80
    right.reset_size()
    app.root.update()
    assert right.height_fraction == 1
    assert abs(right.body.winfo_height() - left.body.winfo_height()) <= 2


def test_route_result_can_resize_from_its_own_top_edge(app):
    activate(app, 3)
    height = app.routes_output_area.winfo_height()
    drag(app, app.routes_output_area, "y", dy=-55)
    assert app.routes_output_area.winfo_height() > height + 40
    assert "[LPM]" in app.routes_output.get("1.0", "end-1c")


def test_all_expand_controls_have_the_same_explicit_label_and_style(app):
    buttons = (
        *app.acl_expand_buttons,
        app.acl_output_expand_button,
        app.routes_input_expand_button,
        app.routes_expand_button,
        app.free_ip_input_expand_button,
        app.free_ip_output_expand_button,
        app.cme_input_expand_button,
        app.cme_expand_button,
    )
    assert {str(button.cget("text")) for button in buttons} == {"Развернуть"}
    assert len({str(button.cget("style")) for button in buttons}) == 1


def test_expanded_routes_input_and_result_follow_edits_errors_and_reopening(app):
    activate(app, 3)
    app.routes_input_expand_button.invoke()
    app.routes_expand_button.invoke()
    app.root.update()
    source = app._text_windows[app.routes_input]
    result = app._text_windows[app.routes_output]
    source.text.delete("1.0", "end")
    source.text.insert("1.0", "10.20.30.0/24 Example")
    app.root.update()
    assert app.routes_input.get("1.0", "end-1c") == "10.20.30.0/24 Example"
    assert "[LPM]" in result.text.get("1.0", "end-1c")
    before = result.text.get("1.0", "end-1c")
    result.text.insert("1.0", "unexpected")
    assert result.text.get("1.0", "end-1c") == before
    source.text.delete("1.0", "end")
    source.text.insert("1.0", "10.20.30.40/24")
    app.root.update()
    assert app.routes_error.get()
    assert result.text.get("1.0", "end-1c") == ""
    app.routes_input_expand_button.invoke()
    assert app._text_windows[app.routes_input] is source
    source.close()
    result.close()
    assert app._text_windows == {}
    app.routes_input_expand_button.invoke()
    app.root.update()
    assert app._text_windows[app.routes_input].text.get("1.0", "end-1c") == "10.20.30.40/24"
    app.set_theme("night")


def test_expanded_arp_input_normalizes_paste_and_shares_live_paged_results(app):
    activate(app, 6)
    app.free_ip_network.set("192.0.2.0/24")
    app.free_ip_input_expand_button.invoke()
    app.free_ip_output_expand_button.invoke()
    app.root.update()
    source = app._text_windows[app.free_ip_arp_input]
    result = app._text_windows[app.free_ip_output]
    app.root.clipboard_clear()
    app.root.clipboard_append(
        "switch#show arp\n Internet 192.0.2.1 0 0011.2233.4401 ARPA Vlan10\nswitch#"
    )
    app._paste(source.text, replace=True)
    app.root.update()
    app._free_ip_update()
    app.root.update()
    assert "switch#" not in app.free_ip_arp_input.get("1.0", "end-1c")
    assert "192.0.2.1" in app.free_ip_arp_input.get("1.0", "end-1c")
    assert result.text.get("1.0", "end-1c").startswith("192.0.2.2\n")
    app._free_ip_move(1)
    app.root.update()
    assert result.text.get("1.0", "end-1c") == app.free_ip_output.get("1.0", "end-1c")
    source.close()
    app.free_ip_input_expand_button.invoke()
    app.root.update()
    assert app._text_windows[app.free_ip_arp_input].text.get("1.0", "end-1c").startswith("Internet")


def test_expanded_acl_conclusion_clears_when_rule_becomes_invalid(app):
    activate(app, 4)
    app.acl_output_expand_button.invoke()
    app.root.update()
    view = app._text_windows[app.acl_output]
    assert view.text.get("1.0", "end-1c") == app.acl_output.get("1.0", "end-1c")
    app.acl_editors[0].set_text("permit ip any any time-range WORK")
    app._acl_flow_update()
    app.root.update()
    assert app.acl_flow_error.get()
    assert view.text.get("1.0", "end-1c") == ""
    view.window.event_generate("<Escape>")
    app.root.update()
    assert app.acl_output not in app._text_windows


def test_expansion_shortcut_is_available_in_route_and_arp_fields(app):
    for tab, widget in ((3, app.routes_input), (6, app.free_ip_arp_input)):
        activate(app, tab)
        widget.focus_force()
        widget.event_generate("<Control-Return>")
        app.root.update()
        assert widget in app._text_windows
        view = app._text_windows[widget]
        view.text.focus_force()
        view.text.event_generate("<Control-Return>")
        app.root.update()
        assert widget not in app._text_windows


def test_wheel_over_cme_table_scrolls_result_without_moving_the_page(app):
    activate(app, 7, "820x610")
    app.cme_editor.set_text(EXAMPLE_CONFIG)
    app._cme_config_changed()
    app._cme_parse()
    app.cme_mode.set("free")
    app.root.update()
    table = app.cme_table
    canvas = app._canvases[7]
    canvas.yview_moveto(0)
    before = canvas.yview()
    table.event_generate("<MouseWheel>", delta=-120)
    app.root.update()
    assert table.yview()[0] > 0
    assert canvas.yview() == before
