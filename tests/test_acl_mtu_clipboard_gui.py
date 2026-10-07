import ctypes
import sys
import tkinter as tk
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.gui


def set_acl(app, forward, reverse=""):
    for widget, value in zip(app.acl_inputs, (forward, reverse), strict=True):
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value)
    app.root.update()
    ready = tk.BooleanVar(app.root, value=False)
    app.root.after(250, ready.set, True)
    app.root.wait_variable(ready)


def clipboard(app, value):
    app.root.clipboard_clear()
    app.root.clipboard_append(value)


def test_default_conversation_copy_and_reverse_block(app):
    assert "запрос и ответ разрешены" in app.acl_output.get("1.0", "end-1c")
    app.acl_copy_button.invoke()
    assert "198.51.100.20:443 -> 192.0.2.10:53000" in app.root.clipboard_get()
    set_acl(app, "permit ip any any", "deny ip any any")
    assert "БЛОКИРУЕТСЯ: строка 1" in app.acl_output.get("1.0", "end-1c")
    assert "ACL блокируют" in app.acl_output.get("1.0", "end-1c")


def test_unknown_source_port_and_implicit_deny(app):
    app.acl_source_port.set("")
    assert "НЕДОСТАТОЧНО ДАННЫХ" in app.acl_output.get("1.0", "end-1c")
    set_acl(app, "permit tcp any any eq 80")
    assert "Неявный deny" in app.acl_output.get("1.0", "end-1c")
    assert "обратный поток не проверен" in app.acl_output.get("1.0", "end-1c")


def test_invalid_acl_and_flow_clear_output_and_copy_then_recover(app):
    set_acl(app, "permit ip any any\npermit tcp any any time-range DAY")
    assert "Строка 2" in app.acl_flow_error.get()
    assert app.acl_output.get("1.0", "end-1c") == ""
    assert app.acl_copy_button.instate(["disabled"])
    assert "исправьте" in app.acl_conclusion.get()
    clipboard(app, "preserve")
    app.copy_acl()
    assert app.root.clipboard_get() == "preserve"
    app.acl_example_button.invoke()
    assert "запрос и ответ разрешены" in app.acl_output.get("1.0", "end-1c")
    app.acl_destination_port.set("65536")
    assert app.acl_output.get("1.0", "end-1c") == ""
    assert app.acl_copy_button.instate(["disabled"])


def test_edit_clears_stale_acl_report_before_debounce(app):
    app.acl_forward_input.insert(tk.END, "\nunsupported")
    app._acl_modified(SimpleNamespace(widget=app.acl_forward_input))
    assert app.acl_output.get("1.0", "end-1c") == ""
    assert app.acl_copy_button.instate(["disabled"])
    assert app._acl_job is not None
    assert app.acl_conclusion.get() == "Проверка правил..."


def test_acl_udp_ignores_tcp_established_and_wildcard_tool_is_collapsible(app):
    set_acl(app, "permit udp any any eq domain", "permit udp any eq domain any")
    app.acl_protocol.set("UDP")
    app.acl_destination_port.set("53")
    assert app.acl_ack_button.instate(["disabled"])
    assert "запрос и ответ разрешены" in app.acl_output.get("1.0", "end-1c")
    assert not app.acl_wildcard_frame.winfo_manager()
    app.acl_wildcard_visible.set(True)
    app._toggle_wildcard()
    assert app.acl_wildcard_frame.winfo_manager() == "grid"
    app.acl_address.set("10.10.5.3")
    assert app.acl_table.values["Совпадение"].get() == "Не совпадает"


@pytest.mark.parametrize(
    "profile,mss",
    [
        ("GRE", "1436"),
        ("WireGuard", "1400"),
        ("VXLAN", "1410"),
        ("IPsec ESP", "1406"),
        ("OpenVPN UDP AEAD", "1408"),
        ("L2TP/IPsec", "1388"),
    ],
)
def test_mtu_profiles_and_copy_explanation(app, profile, mss):
    app.mtu_profile.set(profile)
    assert app.mss_table.values["TCP MSS"].get() == mss
    app.select_tool(2)
    app.copy_current_tool()
    assert f"TCP MSS: {mss}" in app.root.clipboard_get()
    assert "Размер кадра включает FCS" in app.root.clipboard_get()


def test_mtu_layer_selection_vlan_pppoe_and_invalid_clear(app):
    app.mtu_vlan_tags.set("1")
    assert app.mss_table.values["TCP MSS"].get() == "1460"
    assert app.mss_table.values["Ethernet-кадр с FCS"].get() == "1522"
    app.mtu_basis.set("Ethernet payload")
    app.mtu_pppoe.set(True)
    assert app.mss_table.values["Эффективный IP MTU"].get() == "1492"
    app.mtu_value.set("1492")
    app.mtu_basis.set("IP MTU уже известен")
    assert app.mss_table.values["Эффективный IP MTU"].get() == "1492"
    app.mtu_value.set("0")
    assert app.mtu_calculation is None
    assert app.mtu_breakdown.get("1.0", "end-1c") == ""
    assert all(button.instate(["disabled"]) for button in app.mss_table.buttons.values())


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_entry", "00112233aabb"),
        ("route_entry", "203.0.113.8"),
        ("acl_entry", "203.0.113.10"),
        ("acl_destination_entry", "203.0.113.20"),
    ],
)
def test_paste_button_replaces_single_line_field(app, field, value):
    entry = getattr(app, field)
    clipboard(app, value + "\r\n")
    entry.paste_button.invoke()
    assert entry.get() == value


def test_standard_paste_replaces_selection_once_and_preserves_caret(app):
    app.input_value.set("00112233aaaa")
    app.input_entry.selection_range(8, 12)
    clipboard(app, "bbbb")
    app.input_entry.event_generate("<<Paste>>")
    assert app.input_value.get() == "00112233bbbb"
    assert app.result.get() == "00:11:22:33:bb:bb"


def test_cidr_paste_button_applies_address_and_prefix_atomically(app):
    clipboard(app, "203.0.113.7/16")
    app.ipv4_entry.paste_button.invoke()
    assert app.ipv4_address.get() == "203.0.113.7" and app.ipv4_mask.get() == "/16"
    assert str(app.ipv4_calculation.network) == "203.0.0.0/16"


def test_multi_line_entry_paste_is_rejected_without_destroying_input(app):
    app.input_value.set("00112233aabb")
    clipboard(app, "00112233aabb\n112233445566")
    app.input_entry.paste_button.invoke()
    assert app.input_value.get() == "00112233aabb"
    assert "одну строку" in app.status.get()


def test_multiline_acl_and_routes_paste_buttons(app):
    rules = "10 permit tcp any any eq https\n20 deny ip any any"
    clipboard(app, rules)
    app.acl_forward_input.paste_button.invoke()
    assert app.acl_forward_input.get("1.0", "end-1c") == rules
    app._acl_flow_update()
    assert "РАЗРЕШЁН: sequence 10" in app.acl_output.get("1.0", "end-1c")
    routes = "0.0.0.0/0 default\n10.20.30.0/24 access"
    clipboard(app, routes)
    app.routes_paste_button.invoke()
    app.root.update()
    assert "[LPM] 10.20.30.0/24" in app.routes_output.get("1.0", "end-1c")


def test_readonly_fields_block_paste_and_cut_but_allow_selected_copy(app):
    app.input_value.set("00112233aabb")
    clipboard(app, "bad")
    app.result_entry.selection_range(0, tk.END)
    app.result_entry.event_generate("<<Paste>>")
    app.result_entry.event_generate("<<Cut>>")
    assert app.result.get() == "00:11:22:33:aa:bb"
    assert app.root.clipboard_get() == "bad"
    app.result_entry.event_generate("<<Copy>>")
    assert app.root.clipboard_get() == "00:11:22:33:aa:bb"


def test_password_selection_copy_uses_existing_auto_clear_ownership(app):
    app.generate_password()
    app.password_result_entry.selection_range(0, 8)
    app.password_result_entry.event_generate("<<Copy>>")
    assert app._copied_password == app.password_result.get()[:8]
    assert app._clipboard_job is not None
    app.clear_password()
    if sys.platform == "win32":
        assert not ctypes.WinDLL("user32").IsClipboardFormatAvailable(13)
    else:
        with pytest.raises(tk.TclError):
            app.root.clipboard_get()


def test_windows_physical_ctrl_v_works_with_non_latin_keysym(app):
    if app.root.tk.call("tk", "windowingsystem") != "win32":
        pytest.skip("Physical virtual-key codes are a Windows facility")
    app.input_value.set("")
    clipboard(app, "00112233aabb")
    event = SimpleNamespace(widget=app.input_entry, state=4, keycode=86, keysym="Cyrillic_em")
    assert app._clipboard_key(event) == "break"
    assert app.input_value.get() == "00112233aabb"
