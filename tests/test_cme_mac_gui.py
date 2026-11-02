import pytest

from mac_converter.cme_gui import EXAMPLE_CONFIG

pytestmark = pytest.mark.gui


def load(app, value=EXAMPLE_CONFIG):
    app.select_tool(7)
    app.cme_editor.set_text(value)
    app._cme_config_changed()
    app._cme_parse()
    app.root.update()


def test_separate_mac_field_is_copied_and_mirrored_in_expanded_search(app):
    load(app)
    for kind, query in (
        ("Номер ephone", "585"),
        ("Номер ephone-dn", "85"),
        ("Телефон", "31085"),
        ("Имя / label", "Example"),
    ):
        app.cme_search_kind.set(kind)
        app.cme_query.set(query)
        assert (
            "MAC-адрес аппарата: 0011.2233.4455" in app.cme_output.get("1.0", "end-1c").splitlines()
        )
    app.open_cme_report()
    app.root.update()
    report = app.cme_output.get("1.0", "end-1c")
    assert app.cme_expanded_output.get("1.0", "end-1c") == report
    app.copy_cme_report()
    assert app.root.clipboard_get() == report


def test_mac_table_column_is_visible_and_copies_in_both_windows(app):
    load(app)
    app.cme_mode.set("free")
    app.cme_first.set("584")
    app.cme_last.set("586")
    app.root.update()
    table = app.cme_table
    assert table.heading("mac", "text") == "MAC ephone"
    item = table.get_children()[1]
    assert table.item(item, "values")[3] == "0011.2233.4455"
    table.see(item)
    app.root.update()
    bounds = table.bbox(item, "mac")
    assert bounds and bounds[0] + bounds[2] <= table.winfo_width()
    assert "привязка к DN определяется по button" in app.cme_report_view.summary.get()
    table.selection_set(item)
    app.cme_report_view.copy_rows()
    copied = app.root.clipboard_get()
    assert copied.startswith("Номер\tephone\tephone-dn\tMAC ephone\n")
    assert copied.endswith("\t0011.2233.4455")
    app.open_cme_report()
    app.root.update()
    mirror = app.cme_expanded_view.table
    mirror.selection_set(mirror.get_children()[1])
    app.cme_expanded_view.copy_rows()
    assert app.root.clipboard_get() == copied
    app.cme_copy_numbers_button.invoke()
    assert len(app.root.clipboard_get().splitlines()) == 4
    assert app.root.clipboard_get().splitlines()[2].endswith("\t0011.2233.4455")


def test_replacing_config_removes_old_mac_from_main_and_expanded_results(app):
    load(app)
    app.cme_query.set("585")
    app.open_cme_report()
    load(app, EXAMPLE_CONFIG.replace(" mac-address 0011.2233.4455\n", " no mac-address\n"))
    for widget in (app.cme_output, app.cme_expanded_output):
        text = widget.get("1.0", "end-1c")
        assert "MAC-адрес аппарата: не указан в конфигурации" in text
        assert "0011.2233.4455" not in text
