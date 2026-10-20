import json

import pytest

pytestmark = pytest.mark.gui


def configure(app):
    app.select_tool(6)
    app.free_ip_example()
    app._free_ip_update()
    app.root.update()


def test_default_query_empty_and_example_shows_candidate(app):
    assert app.free_ip_check_value.get() == ""
    assert app.free_ip_address_check is None
    configure(app)
    assert app.free_ip_check_value.get() == "192.0.2.3"
    assert app.free_ip_address_check.candidate
    assert "Кандидат на свободный" in app.free_ip_check_status.get()


@pytest.mark.parametrize(
    "query,status",
    [
        ("192.0.2.1", "Найден в ARP"),
        ("192.0.2.33", "Исключён"),
        ("192.0.2.0", "Адрес сети"),
        ("192.0.2.255", "Broadcast"),
        ("198.51.100.10", "Вне выбранной подсети"),
    ],
)
def test_live_query_status_keeps_arp_candidates_and_current_page(app, query, status):
    configure(app)
    app._free_ip_move(1)
    arp = app.free_ip_arp_input.get("1.0", "end-1c")
    page = app.free_ip_output.get("1.0", "end-1c")
    app.free_ip_check_value.set(query)
    assert status in app.free_ip_check_status.get()
    assert not app.free_ip_address_check.candidate
    assert app.free_ip_page_number == 1
    assert app.free_ip_arp_input.get("1.0", "end-1c") == arp
    assert app.free_ip_output.get("1.0", "end-1c") == page


def test_invalid_query_and_clear_remove_only_the_query_result(app):
    configure(app)
    app.free_ip_check_value.set("192.0.2.999")
    assert app.free_ip_address_check is None
    assert "IPv4" in app.free_ip_check_status.get()
    assert app.free_ip_calculation.total == 250
    assert app.free_ip_copy_page_button.instate(["!disabled"])
    app.copy_free_ip_report()
    assert "Проверка IPv4:" in app.root.clipboard_get()
    assert "Результат: Кандидат" not in app.root.clipboard_get()
    app.free_ip_check_value.set("")
    assert app.free_ip_address_check is None
    app.copy_free_ip_report()
    assert "Проверка IPv4:" not in app.root.clipboard_get()


@pytest.mark.parametrize("kind", ["arp", "exclusions", "network", "mask"])
def test_data_edits_invalidate_then_recheck_the_same_query(app, kind):
    configure(app)
    changes = {
        "exclusions": (app.free_ip_exclusions, ".3"),
        "network": (app.free_ip_network, "198.51.100.0/24"),
        "mask": (app.free_ip_mask, "/32"),
    }
    if kind == "arp":
        app.free_ip_arp_editor.set_text("192.0.2.3")
        app._free_ip_changed()
    else:
        variable, value = changes[kind]
        variable.set(value)
    assert app.free_ip_address_check is None
    assert "Кандидат" not in app.free_ip_check_status.get()
    assert app.free_ip_check_value.get() == "192.0.2.3"
    app._free_ip_update()
    assert app.free_ip_address_check is not None
    assert not app.free_ip_address_check.candidate


def test_empty_or_invalid_arp_never_marks_the_query_as_free(app):
    configure(app)
    for raw in ("", "headers only", "192.0.2.999"):
        app.free_ip_arp_editor.set_text(raw)
        app._free_ip_changed()
        app._free_ip_update()
        assert app.free_ip_address_check is None
        assert "Кандидат" not in app.free_ip_check_status.get()
        assert app.free_ip_copy_report_button.instate(["disabled"])


def test_clipboard_paste_copy_report_theme_and_persistence(app):
    configure(app)
    app.root.clipboard_clear()
    app.root.clipboard_append("192.0.2.1\r\n")
    app.free_ip_check_entry.paste_button.invoke()
    assert app.free_ip_check_value.get() == "192.0.2.1"
    assert app.free_ip_address_check.arp_present
    app.copy_current_tool()
    text = app.root.clipboard_get()
    assert "Проверка IPv4: 192.0.2.1" in text and "Результат: Найден в ARP" in text
    app.set_theme("night")
    app.set_theme("day")
    assert app.free_ip_check_value.get() == "192.0.2.1"
    assert "Найден в ARP" in app.free_ip_check_status.get()
    assert json.loads(app.settings.path.read_text()) == {"theme": "day"}
