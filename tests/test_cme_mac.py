import pytest

from mac_converter.cme import availability_report, lookup_report, parse_config, section_availability

CONFIG = """ephone-dn 85
 number 31085
 name Example Person
!
ephone-dn 86
 number 31086
!
ephone 20
 description Desk 20
 mac-address 0011.2233.4466
 type CIPC
 button 1:85
!
ephone 585
 description Desk 585
 mac-address 0011.2233.4455
 type 7942
 button 1:85 2:86
!
"""


@pytest.mark.parametrize(
    "query,kind", [("585", "ephone"), ("85", "dn"), ("31085", "number"), ("example", "name")]
)
def test_each_search_card_shows_the_mac_of_its_actual_linked_phone(query, kind):
    report, _ = lookup_report(parse_config(CONFIG), query, kind)
    cards = report.split("\nephone ")[1:]
    assert cards
    addresses = {20: "0011.2233.4466", 585: "0011.2233.4455"}
    for card in cards:
        phone = int(card.split(":", 1)[0])
        assert card.splitlines()[1] == f"MAC-адрес аппарата: {addresses[phone]}"
        assert all(mac not in card for tag, mac in addresses.items() if tag != phone)
        assert "; MAC:" not in card


@pytest.mark.parametrize("commands", ["", " mac-address 0011.2233.4455\n no mac-address\n"])
def test_missing_or_removed_mac_is_explicit_and_does_not_free_the_phone(commands):
    config = parse_config(
        "ephone-dn 85\n number 31085\n!\nephone 585\n type 7942\n" + commands + " button 1:85\n!"
    )
    report, _ = lookup_report(config, "85", "dn")
    assert "MAC-адрес аппарата: не указан в конфигурации" in report
    table = section_availability(config, "585", "585")
    assert table.row(585)[3] == "не указан" and table.free_phones == 0


def test_equal_section_numbers_do_not_invent_a_mac_binding_to_dn():
    config = parse_config(
        "ephone-dn 85\n number 31085\n!\nephone 85\n"
        " mac-address aabb.ccdd.ee85\n type 7942\n button 1:86\n!"
    )
    report, _ = lookup_report(config, "85", "dn")
    assert "MAC-адрес аппарата: нет привязанного ephone" in report
    assert "AABB.CCDD.EE85" not in report
    table = section_availability(config, "84", "86")
    assert table.row(85)[3] == "AABB.CCDD.EE85"
    assert "привязка к DN определяется по button" in availability_report(table)[0]


def test_mac_column_and_tsv_keep_each_phone_and_free_slot_distinct():
    table = section_availability(parse_config(CONFIG), "584", "586")
    rows, _ = table.page()
    assert [row[3] for row in rows] == ["-", "0011.2233.4455", "-"]
    text = table.all_text()
    assert text.splitlines()[0] == "Номер\tephone\tephone-dn\tMAC ephone"
    assert all(len(line.split("\t")) == 4 for line in text.splitlines())
    assert text.splitlines()[2].endswith("\t0011.2233.4455")
    assert "MAC ephone" in availability_report(table)[0]


def test_phone_without_buttons_still_shows_its_normalized_mac():
    config = parse_config(
        "ephone 47\n description Unassigned desk\n mac-address aa:bb:cc:dd:ee:ff\n type 7942\n!"
    )
    report, _ = lookup_report(config, "47", "ephone")
    assert "MAC-адрес аппарата: AABB.CCDD.EEFF" in report
    assert "button: привязки к ephone-dn не указаны" in report
    table = section_availability(config, "47", "47")
    assert table.row(47)[3] == "AABB.CCDD.EEFF" and table.free_phones == 0
