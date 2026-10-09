import json

import pytest

from mac_converter.free_ips import DEFAULT_EXCLUSIONS

pytestmark = pytest.mark.gui

ARP = """switch#show ip arp
Protocol Address Age Hardware Addr Type Interface
  Internet 192.0.2.1 0 0011.2233.4401 ARPA Vlan10
  Internet 192.0.2.2 - Incomplete ARPA Vlan10
switch#
"""


def calculate(app, network="192.0.2.0/24", arp=ARP, exclusions=DEFAULT_EXCLUSIONS):
    app.select_tool(6)
    app.free_ip_network.set(network)
    app.free_ip_exclusions.set(exclusions)
    app.free_ip_arp_editor.set_text(arp)
    app._free_ip_changed()
    app.root.update()
    app._free_ip_update()
    app.root.update()
    return app.free_ip_calculation


def test_defaults_are_empty_and_copy_is_disabled(app):
    assert app.free_ip_exclusions.get() == DEFAULT_EXCLUSIONS
    assert app.free_ip_network.get() == "192.168.1.0"
    assert app.free_ip_mask.get() == "/24"
    assert app.free_ip_calculation is None
    assert app.free_ip_output.get("1.0", "end-1c") == ""
    assert app.free_ip_copy_page_button.instate(["disabled"])
    assert app.free_ip_copy_all_button.instate(["disabled"])
    assert app.free_ip_copy_report_button.instate(["disabled"])


@pytest.mark.parametrize("method", ["button", "ctrl_v", "shift_insert", "menu"])
def test_all_paste_paths_remove_non_ip_rows_and_trim_edges(app, method):
    app.select_tool(6)
    app.free_ip_network.set("192.0.2.0/24")
    app.root.clipboard_clear()
    app.root.clipboard_append(ARP)
    app.root.update()
    editor = app.free_ip_arp_input
    editor.focus_force()
    if method == "button":
        app.free_ip_paste_button.invoke()
    elif method == "ctrl_v":
        editor.event_generate("<Control-v>")
    elif method == "shift_insert":
        editor.event_generate("<Shift-Insert>")
    else:
        app._paste(editor)
    app.root.update()
    app._free_ip_update()
    assert (
        editor.get("1.0", "end-1c")
        == "Internet 192.0.2.1 0 0011.2233.4401 ARPA Vlan10\nInternet 192.0.2.2 - Incomplete ARPA Vlan10"
    )
    assert app.free_ip_calculation.total == 250
    assert app.free_ip_error.get() == ""


def test_clean_existing_text_and_example(app):
    calculate(app)
    app.free_ip_clean_button.invoke()
    app._free_ip_update()
    assert "switch#" not in app.free_ip_arp_input.get("1.0", "end-1c")
    assert app.free_ip_calculation.total == 250
    app.free_ip_example_button.invoke()
    app._free_ip_update()
    assert app.free_ip_calculation.total == 250
    assert "вне: 1" in app.free_ip_summary.get()


def test_pages_copy_all_and_report(app):
    calculate(app)
    assert app.free_ip_prev_button.instate(["disabled"])
    app.free_ip_copy_page_button.invoke()
    first = app.root.clipboard_get().splitlines()
    assert len(first) == 100 and first[0] == "192.0.2.3"
    assert "192.0.2.33" not in first and "192.0.2.34" not in first
    app.free_ip_next_button.invoke()
    assert app.free_ip_page_number == 1
    app.free_ip_page_value.set("3")
    app.free_ip_jump_button.invoke()
    assert app.free_ip_next_button.instate(["disabled"])
    app.free_ip_copy_page_button.invoke()
    last = app.root.clipboard_get().splitlines()
    assert len(last) == 50 and last[-1] == "192.0.2.254"
    app.free_ip_copy_all_button.invoke()
    assert len(app.root.clipboard_get().splitlines()) == 250
    app.copy_current_tool()
    assert "Страница 3 / 3" in app.root.clipboard_get()
    assert "Кандидатов по ARP: 250" in app.root.clipboard_get()
    app.free_ip_page_value.set("999")
    app.free_ip_jump_button.invoke()
    assert app.free_ip_page_number == 2
    assert "от 1 до 3" in app.free_ip_error.get()


@pytest.mark.parametrize("kind", ["network", "mask", "exclusions", "arp"])
def test_edit_clears_stale_results_immediately_and_recovers(app, kind):
    calculate(app)
    variable, value = {
        "network": (app.free_ip_network, "bad"),
        "mask": (app.free_ip_mask, "255.0.255.0"),
        "exclusions": (app.free_ip_exclusions, ".80-.50"),
        "arp": (None, "192.0.2.999"),
    }[kind]
    if variable is not None:
        variable.set(value)
    else:
        app.free_ip_arp_input.delete("1.0", "end")
        app.free_ip_arp_input.insert("1.0", value)
        app.root.update()
    assert app.free_ip_calculation is None
    assert app.free_ip_output.get("1.0", "end-1c") == ""
    app.root.clipboard_clear()
    app.root.clipboard_append("sentinel")
    app.copy_current_tool()
    assert app.root.clipboard_get() == "sentinel"
    app._free_ip_update()
    assert app.free_ip_error.get()
    if kind == "arp":
        assert app.free_ip_arp_editor.error_line == 1
    calculate(app)
    assert app.free_ip_error.get() == ""
    assert app.free_ip_arp_editor.error_line is None


def test_cidr_paste_and_following_mask_change(app):
    calculate(app)
    app.root.clipboard_clear()
    app.root.clipboard_append("10.20.30.40/16")
    app._paste(app.free_ip_network_entry, replace=True)
    app._free_ip_update()
    assert str(app.free_ip_calculation.network) == "10.20.0.0/16"
    assert app.free_ip_mask.get() == "/16"
    assert app.free_ip_copy_all_button.instate(["disabled"])
    app.free_ip_mask.set("255.255.255.0")
    app._free_ip_update()
    assert str(app.free_ip_calculation.network) == "10.20.30.0/24"


def test_zero_candidates_keeps_report_available(app):
    calculate(app, exclusions=".0-.255")
    assert app.free_ip_calculation.total == 0
    assert app.free_ip_copy_page_button.instate(["disabled"])
    assert app.free_ip_copy_all_button.instate(["disabled"])
    app.free_ip_copy_report_button.invoke()
    assert "Кандидатов по ARP: 0" in app.root.clipboard_get()


def test_shortcuts_theme_readonly_and_focus_order(app):
    calculate(app)
    before = app.free_ip_output.get("1.0", "end-1c")
    app.free_ip_output.insert("1.0", "bad")
    assert app.free_ip_output.get("1.0", "end-1c") == before
    app.root.focus_force()
    app.root.event_generate("<Control-Key-7>")
    app.root.update()
    assert app.root.focus_get() == app.free_ip_network_entry
    app.root.event_generate("<Control-Shift-C>")
    app.root.update()
    assert "Кандидатов по ARP: 250" in app.root.clipboard_get()
    controls = [app.free_ip_network_entry]
    for _ in range(10):
        controls.append(controls[-1].tk_focusNext())
    assert controls == [
        app.free_ip_network_entry,
        app.free_ip_mask_entry,
        app.free_ip_exclusions_entry,
        app.free_ip_arp_input,
        app.free_ip_output,
        app.free_ip_paste_button,
        app.free_ip_clean_button,
        app.free_ip_example_button,
        app.free_ip_copy_page_button,
        app.free_ip_copy_all_button,
        app.free_ip_copy_report_button,
    ]
    app.set_theme("night")
    app.root.update()
    assert app.free_ip_output.get("1.0", "end-1c") == before
    assert app.free_ip_exclusions.get() == DEFAULT_EXCLUSIONS
    assert json.loads(app.settings.path.read_text()) == {"theme": "night"}
