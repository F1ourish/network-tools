import json
import tkinter as tk

import pytest

pytestmark = pytest.mark.gui


def test_ipv4_default_and_copy_all(app):
    assert app.ipv4_address.get() == "192.168.1.0"
    assert app.ipv4_mask.get() == "/24"
    assert app.ipv4_addresses_table.values["Первый хост"].get() == "192.168.1.1"
    assert app.ipv4_binary.get() == "11111111.11111111.11111111.00000000"
    app.ipv4_copy_button.invoke()
    assert "Wildcard: 0.0.0.255" in app.root.clipboard_get()
    app.ipv4_mask_table.buttons["Полная маска"].invoke()
    assert app.root.clipboard_get() == "255.255.255.0"


def test_ipv4_invalid_mask_clears_all_results_and_recovers(app):
    app.ipv4_mask.set("255.0.255.0")
    assert app.ipv4_calculation is None
    assert app.ipv4_binary.get() == ""
    assert app.ipv4_copy_button.instate(["disabled"])
    assert app.hosts_button.instate(["disabled"])
    for table in (app.ipv4_addresses_table, app.ipv4_mask_table, app.ipv4_range_table):
        assert all(value.get() == "—" for value in table.values.values())
        assert all(button.instate(["disabled"]) for button in table.buttons.values())
    app.ipv4_mask.set("255.255.255.0")
    assert app.ipv4_calculation.network.prefixlen == 24
    assert app.ipv4_error.get() == ""


def test_ipv4_network_only_validation_and_host_normalization(app):
    app.ipv4_address.set("192.168.1.42")
    assert str(app.ipv4_calculation.network) == "192.168.1.0/24"
    app.ipv4_strict.set(True)
    assert app.ipv4_calculation is None
    assert "Это IP хоста" in app.ipv4_error.get()
    app.ipv4_address.set("192.168.1.0")
    assert app.ipv4_calculation is not None


def test_cidr_paste_is_atomic_and_following_mask_change_applies(app):
    app.root.clipboard_clear()
    app.root.clipboard_append("10.20.30.40/16")
    app.select_tool(1)
    app.root.update()
    app.ipv4_entry.event_generate("<<Paste>>")
    app.root.update()
    assert app.ipv4_address.get() == "10.20.30.40"
    assert app.ipv4_mask.get() == "/16"
    assert str(app.ipv4_calculation.network) == "10.20.0.0/16"
    app.ipv4_mask.set("/24")
    assert str(app.ipv4_calculation.network) == "10.20.30.0/24"


def test_cidr_typing_does_not_erase_a_partial_prefix(app):
    app.ipv4_address.set("10.20.30.40/")
    assert app.ipv4_calculation is None
    app.ipv4_address.set("10.20.30.40/2")
    assert app.ipv4_address.get().endswith("/2")
    app.ipv4_address.set("10.20.30.40/24")
    assert app.ipv4_mask.get() == "/24"
    app._normalize_ipv4()
    assert app.ipv4_address.get() == "10.20.30.40"


def test_empty_partial_ipv4_has_no_stale_result(app):
    app.ipv4_address.set("192.168.")
    assert app.ipv4_error.get() == ""
    assert app.ipv4_calculation is None
    assert app.ipv4_copy_button.instate(["disabled"])


def test_host_pages_copy_last_page_and_snapshot(app):
    app.show_hosts()
    app.root.update()
    assert app.host_text.get("1.0", "end-1c").splitlines()[0] == "192.168.1.1"
    assert app.host_prev_button.instate(["disabled"])
    app._host_move(1)
    assert app.host_text.get("1.0", "end-1c").splitlines()[0] == "192.168.1.101"
    app.host_page_entry_value.set("3")
    app._host_jump()
    assert app.host_text.get("1.0", "end-1c").splitlines()[-1] == "192.168.1.254"
    assert app.host_next_button.instate(["disabled"])
    app.copy_host_page()
    assert len(app.root.clipboard_get().splitlines()) == 54
    app.ipv4_address.set("10.0.0.0")
    assert str(app.host_calculation.network) == "192.168.1.0/24"
    app.host_page_entry_value.set("999")
    app._host_jump()
    assert app.host_page_number == 2
    assert "от 1 до 3" in app.host_page_label.get()


@pytest.mark.parametrize(
    "cidr,count,broadcast",
    [
        ("192.0.2.0/31", "2", "Не применяется"),
        ("192.0.2.1/32", "1", "Не применяется"),
        ("0.0.0.0/0", "—", "255.255.255.255"),
    ],
)
def test_special_ipv4_prefixes_in_ui(app, cidr, count, broadcast):
    app.ipv4_address.set(cidr)
    assert app.ipv4_addresses_table.values["Хостовых позиций"].get() == count
    assert app.ipv4_addresses_table.values["Broadcast подсети"].get() == broadcast
    app.show_hosts()
    if cidr.endswith("/0"):
        app.host_page_entry_value.set("42949673")
        app._host_jump()
        assert app.host_text.get("1.0", "end-1c").splitlines()[-1] == "255.255.255.255"


def test_theme_switch_preserves_all_inputs_results_and_open_host_window(app):
    app.input_value.set("aabb.ccdd.eeff")
    app.ipv4_address.set("10.2.3.4/16")
    app.overhead_value.set("60")
    app.show_hosts()
    old_color = app.routes_input.cget("background")
    app.set_theme("night")
    app.root.update()
    assert app.theme.get() == "night"
    assert app.result.get() == "aa:bb:cc:dd:ee:ff"
    assert str(app.ipv4_calculation.network) == "10.2.0.0/16"
    assert app.mss_table.values["TCP MSS"].get() == "1400"
    assert app.routes_input.cget("background") != old_color
    assert app.host_text.cget("background") == app.routes_input.cget("background")
    assert json.loads(app.settings.path.read_text()) == {"theme": "night"}


def test_saved_theme_loaded_by_new_window(app):
    from mac_converter.gui import MacConverterApp

    app.set_theme("night")
    root = tk.Toplevel(app.root)
    try:
        reopened = MacConverterApp(root, settings_path=app.settings.path)
        assert reopened.theme.get() == "night"
        assert reopened.theme_label.get() == "Ночная"
        assert reopened.input_value.get() == ""
        assert reopened.ipv4_address.get() == "192.168.1.0"
    finally:
        root.destroy()


def test_theme_save_error_keeps_selected_theme(app, monkeypatch):
    def denied(_theme):
        raise PermissionError("read only")

    monkeypatch.setattr(app.settings, "save", denied)
    app.set_theme("night")
    assert app.theme.get() == "night"
    assert "сохранить настройку не удалось" in app.status.get()


def test_mss_inputs_update_and_invalid_clears_copy(app):
    assert app.mss_table.values["TCP MSS"].get() == "1460"
    app.ip_version.set("IPv6")
    assert app.mss_table.values["TCP MSS"].get() == "1440"
    app.overhead_value.set("60")
    assert app.mss_table.values["TCP MSS"].get() == "1380"
    app.mtu_value.set("40")
    assert all(button.instate(["disabled"]) for button in app.mss_table.buttons.values())
    app.root.clipboard_clear()
    app.root.clipboard_append("sentinel")
    app.select_tool(2)
    app.copy_current_tool()
    assert app.root.clipboard_get() == "sentinel"


def test_routes_recalculation_invalid_and_no_match(app):
    assert "[LPM] 10.20.30.0/24" in app.routes_output.get("1.0", "end-1c")
    app.routes_input.delete("1.0", tk.END)
    app.routes_input.insert("1.0", "10.0.0.0/8 core\n10.20.30.40/32 host")
    app.root.update()
    assert "[LPM] 10.20.30.40/32" in app.routes_output.get("1.0", "end-1c")
    app.route_address.set("192.0.2.1")
    assert "Совпадений нет" in app.routes_output.get("1.0", "end-1c")
    app.route_address.set("invalid")
    assert app.routes_copy_button.instate(["disabled"])
    assert app.routes_output.get("1.0", "end-1c") == ""


def test_acl_noncontiguous_match_mismatch_and_invalid(app):
    assert app.acl_table.values["Совпадение"].get() == "Совпадает"
    app.acl_address.set("10.10.5.3")
    assert app.acl_table.values["Совпадение"].get() == "Не совпадает"
    app.acl_wildcard.set("/24")
    assert app.acl_error.get()
    assert all(button.instate(["disabled"]) for button in app.acl_table.buttons.values())


@pytest.mark.parametrize("index", range(5))
def test_keyboard_navigation_and_copy_current_tool(app, index):
    app.input_value.set("aabb.ccdd.eeff")
    app.root.focus_force()
    app.root.event_generate(f"<Control-Key-{index + 1}>")
    app.root.update()
    assert app.notebook.index(app.notebook.select()) == index
    assert (
        app.root.focus_get()
        == (app.input_entry, app.ipv4_entry, app.mtu_entry, app.route_entry, app.acl_entry)[index]
    )
    app.root.clipboard_clear()
    app.root.clipboard_append("previous result")
    app.root.focus_get().event_generate("<Control-Shift-C>")
    app.root.update()
    expected = (
        "aa:bb:cc:dd:ee:ff",
        "Подсеть CIDR: 192.168.1.0/24",
        "TCP MSS: 1460",
        "[LPM] 10.20.30.0/24",
        "Совпадение: Совпадает",
    )[index]
    assert expected in app.root.clipboard_get()


def test_keyboard_theme_toggle(app):
    app.root.focus_force()
    app.root.event_generate("<Control-Shift-T>")
    app.root.update()
    assert app.theme.get() == "night"


def test_small_window_scrolls_to_keyboard_focused_output(app):
    app.select_tool(1)
    app.root.geometry("820x610")
    app.root.update()
    app.hosts_button.focus_force()
    app.root.update()
    canvas = app._canvases[1]
    assert app.hosts_button.winfo_rooty() >= canvas.winfo_rooty()
    assert (
        app.hosts_button.winfo_rooty() + app.hosts_button.winfo_height()
        <= canvas.winfo_rooty() + canvas.winfo_height()
    )
    app.focus_input()
    app.root.update()
    assert canvas.yview()[0] == 0


def test_range_is_full_width_readonly_and_copyable(app):
    app.select_tool(1)
    app.root.update()
    entry = app.ipv4_range_table.entries["Диапазон хостов"]
    assert entry.winfo_width() > app.ipv4_addresses_table.entries["Первый хост"].winfo_width()
    entry.insert(0, "incorrect")
    app.ipv4_range_table.buttons["Диапазон хостов"].invoke()
    assert app.root.clipboard_get() == "192.168.1.1 – 192.168.1.254"


def test_readonly_host_list_remains_reachable_with_tab(app):
    app.show_hosts()
    app.root.update()
    assert app.host_text.tk_focusNext() == app.host_next_button
    app._host_move(1)
    assert app.host_prev_button.tk_focusPrev() == app.host_text
    assert app.host_text.cget("state") == "disabled"
