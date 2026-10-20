import pytest

pytestmark = pytest.mark.gui


def configure(app, inbound, outbound):
    app.select_tool(4)
    for index, value in enumerate((inbound, outbound)):
        app._set_acl_text(index, value)
    app._acl_flow_update()
    app.root.update()


def test_interface_selection_rechecks_packets_and_keeps_editors_and_flags(app):
    configure(
        app,
        "ip access-list extended IN\n10 permit ip any any",
        "ip access-list extended OUT\n20 deny ip any any",
    )
    original = [editor.text.get("1.0", "end-1c") for editor in app.acl_editors]
    request = app.acl_output.get("1.0", "end-1c").split("Ответ: TCP", 1)[0]
    assert "РАЗРЕШЁН: sequence 10" in request
    app.acl_interface_entry.set("Со стороны назначения")
    report = app.acl_output.get("1.0", "end-1c")
    request, reply = report.split("Ответ: TCP", 1)
    assert "ACL out: OUT; запрос" in request
    assert "БЛОКИРУЕТСЯ: sequence 20" in request
    assert "ACL in: IN; ответ" in reply
    assert "РАЗРЕШЁН: sequence 10" in reply
    assert [editor.text.get("1.0", "end-1c") for editor in app.acl_editors] == original
    app.acl_absent[1].set(True)
    assert "запрос и ответ разрешены" in app.acl_conclusion.get()
    app.acl_interface.set("Со стороны источника")
    assert app.acl_absent[1].get() and not app.acl_absent[0].get()
    assert [editor.text.get("1.0", "end-1c") for editor in app.acl_editors] == original


def test_destination_interface_fallback_matches_correct_named_acl_with_unknown_client_port(app):
    configure(
        app,
        "ip access-list extended SERVICE-FROM\n"
        "10 permit tcp 198.51.100.0 0.0.0.255 any established\n160 permit ip any any log",
        "ip access-list extended SERVICE-TO\n10 permit tcp any any established\n"
        "180 permit tcp 192.0.2.0 0.0.0.255 host 198.51.100.20 eq www 443\n"
        "190 permit tcp 192.0.2.0 0.0.0.255 any eq 22 3389\n250 permit ip any any log",
    )
    app.acl_source.set("203.0.113.198")
    app.acl_destination.set("198.51.100.30")
    app.acl_source_port.set("")
    app.acl_interface.set("Со стороны назначения")
    report = app.acl_output.get("1.0", "end-1c")
    request, reply = report.split("Ответ: TCP", 1)
    assert "ACL out: SERVICE-TO; запрос" in request and "РАЗРЕШЁН: sequence 250" in request
    assert "ACL in: SERVICE-FROM; ответ" in reply and "РАЗРЕШЁН: sequence 10" in reply
    app.acl_copy_button.invoke()
    assert app.root.clipboard_get() == report


@pytest.mark.parametrize("index", [0, 1])
def test_destination_side_error_highlights_same_physical_expanded_editor(app, index):
    configure(app, "permit ip any any", "permit ip any any")
    app.acl_interface.set("Со стороны назначения")
    app.open_acl_editor(index)
    app._set_acl_text(index, "permit ip any any\n180 permit tcp any any eq 443 65536")
    app._acl_flow_update()
    app.root.update()
    window, editor = app._acl_editor_windows[index]
    assert window.title() == f"ACL {('in', 'out')[index]} - Network Tools"
    assert app.acl_flow_error.get().startswith(f"ACL {('in', 'out')[index]}: Строка 2")
    assert app.acl_editors[index].error_line == editor.error_line == 2
    assert app.acl_editors[1 - index].error_line is None
    assert not app.acl_output.get("1.0", "end-1c")
    app._set_acl_text(index, "permit ip any any")
    app._acl_flow_update()
    assert not app.acl_flow_error.get()
    assert app.acl_editors[index].error_line is None and editor.error_line is None


def test_expanded_labels_follow_side_and_example_resets_consistently(app):
    app.select_tool(4)
    app.open_acl_editor(0)
    window, editor = app._acl_editor_windows[0]
    app.acl_interface.set("Со стороны назначения")
    assert "ACL in - ответ" in app.acl_direction_labels[0].get()
    assert window.title() == "ACL in - Network Tools"
    app.acl_example_button.invoke()
    assert app.acl_interface.get() == "Со стороны источника"
    assert "ACL in - запрос" in app.acl_direction_labels[0].get()
    assert "запрос и ответ разрешены" in app.acl_conclusion.get()
    assert editor.text.get("1.0", "end-1c") == app.acl_inbound_input.get("1.0", "end-1c")
