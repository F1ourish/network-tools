from random import Random

import pytest

from mac_converter.cme import (
    MAX_CONFIG_CHARS,
    MAX_CONFIG_LINES,
    CMESyntaxError,
    diagnostics_report,
    section_availability,
    availability_report,
    find_links,
    free_numbers,
    free_report,
    lookup_report,
    parse_config,
)
from mac_converter.network import InvalidNetworkInput

CONFIG = """router#show running-config
Building configuration...
telephony-service
 max-dn 200
 max-ephones 100
!
ephone-dn 85 dual-line
 number 31085 secondary 32085 no-reg both
 description 33085
 name Example Alex
 label Example A.
!
ephone-dn 86
 number 31086
 description 33085 Another
 name Other Person
 label Other Label
!
ephone-dn 30
!
ephone 585
 description Example Alex Office
 mac-address 0011.2233.4455
 type 7942
 button 1:85 2:86
!
ephone 20
 description Spare Desk
 mac-address 0011.2233.4466
 type CIPC
 button 1:85
!
ephone 760
!
router#
"""


def test_full_config_and_mapping_use_button_not_equal_phone_and_dn_ids():
    config = parse_config(CONFIG)
    assert config.dns.keys() == {30, 85, 86}
    assert config.phones.keys() == {20, 585, 760}
    assert (config.max_dn, config.max_ephones) == (200, 100)
    links = find_links(config, "585", "ephone")
    assert [(link.phone, link.dn, link.button.text) for link in links] == [
        (585, 85, "1:85"),
        (585, 86, "2:86"),
    ]
    assert config.phones[585].model == "7942"
    assert config.phones[585].mac == "0011.2233.4455"
    assert config.dns[85].number == "31085"
    assert config.dns[85].secondary == "32085"
    assert config.dns[85].description == "33085"
    assert config.dns[85].line == 7


@pytest.mark.parametrize(
    "query,kind,expected",
    [
        ("585", "all", {(585, 85), (585, 86)}),
        ("85", "dn", {(585, 85), (20, 85)}),
        ("31085", "number", {(585, 85), (20, 85)}),
        ("32085", "number", {(585, 85), (20, 85)}),
        ("33085", "number", {(585, 85), (20, 85), (585, 86)}),
        ("exAMP", "name", {(585, 85), (20, 85), (585, 86)}),
        ("Example A.", "name", {(585, 85), (20, 85)}),
        ("office", "name", {(585, 85), (585, 86)}),
        ("Other Lab", "name", {(585, 86)}),
        ("does not exist", "all", set()),
        ("760", "ephone", {(760, None)}),
        ("30", "dn", {(None, 30)}),
    ],
)
def test_all_requested_search_fields_and_partial_casefold_names(query, kind, expected):
    assert {
        (item.phone, item.dn) for item in find_links(parse_config(CONFIG), query, kind)
    } == expected


def test_reports_show_distinct_description_number_label_name_and_hardware():
    report, pages = lookup_report(parse_config(CONFIG), "585", "ephone")
    for value in (
        "ephone 585: существует в конфигурации",
        "Example Alex Office",
        "button 1:85",
        "ephone-dn 85",
        "Описание (description): 33085",
        "Телефонный номер (number): 31085",
        "Дополнительный номер (secondary): 32085",
        "Имя (name): Example Alex; подпись (label): Example A.",
        "Модель (type): 7942",
        "MAC: 0011.2233.4455",
    ):
        assert value in report
    assert pages == 1
    assert "номер в описании отличается от назначенного" not in report
    assert "номер в описании отличается от назначенного" in diagnostics_report(parse_config(CONFIG))
    empty, _ = lookup_report(parse_config(CONFIG), "no match")
    assert "Совпадений нет" in empty and "фрагменте" in empty


def test_numeric_auto_search_is_exact_and_does_not_match_longer_description():
    config = parse_config(
        "ephone-dn 1\n number 1585\n name Person\n!\nephone 585\n description Room 1585\n button 1:1\n!"
    )
    assert len(find_links(config, "585")) == 1
    assert find_links(config, "585", "number") == ()
    assert len(find_links(config, "1585", "number")) == 1
    assert find_links(config, "85") == ()


def test_empty_objects_and_dangling_button_references_remain_reserved():
    config = parse_config("ephone-dn 2\n!\nephone 3\n!\nephone 5\n button 1:4\n!")
    assert free_numbers(config, "dn", "1", "5").all_numbers() == ("1", "3", "5")
    assert free_numbers(config, "ephone", "1", "5").all_numbers() == ("1", "2", "4")
    report, _ = lookup_report(config, "4", "dn")
    assert "сама секция отсутствует во вставленном конфиге" in report
    assert any("Телефонный номер (number) не задан" in warning for warning in config.warnings)


@pytest.mark.parametrize("separator", [":", "b", "c", "f", "m", "o", "s", "w"])
def test_supported_button_modes_preserve_relationship(separator):
    config = parse_config(f"ephone-dn 2\n number 1002\n!\nephone 7\n button 1{separator}2\n!")
    (link,) = find_links(config, "7", "ephone")
    assert (link.dn, link.button.mode) == (2, separator)


def test_overlay_and_rollover_resolve_button_references_not_dn_ids():
    config = parse_config("ephone-dn 10\n!\nephone-dn 20\n!\nephone 7\n button 1o10,20 2x1 3x1\n!")
    assert [(link.button.position, link.dn) for link in find_links(config, "7", "ephone")] == [
        (1, 10),
        (1, 20),
        (2, 10),
        (2, 20),
        (3, 10),
        (3, 20),
    ]
    assert config.referenced_dns == {10, 20}
    assert "1" in free_numbers(config, "dn", "1", "20").all_numbers()
    assert "x: ссылка на overlay-кнопку" in lookup_report(config, "20", "dn")[0]


@pytest.mark.parametrize(
    "tail",
    [
        "1x2 2x1",
        "1x3",
        "1:10 2x1",
        "1c10,20 2x1",
        "1:10 1:20",
        "1:10,20",
        "1z10",
        "0:10",
        "1:0",
        "",
    ],
)
def test_bad_button_syntax_or_overlay_does_not_produce_a_partial_inventory(tail):
    with pytest.raises(CMESyntaxError) as error:
        parse_config(f"ephone 1\n button {tail}\n!")
    assert error.value.line == 2


def test_non_numeric_conference_numbers_are_preserved_and_not_phone_identities():
    config = parse_config(
        "ephone-dn 1 octo-line\n number A0001\n name conference\n!\nephone-dn 2 octo-line\n number A0001\n!"
    )
    assert {link.dn for link in find_links(config, "A0001", "number")} == {1, 2}
    assert free_numbers(config, "number", "1", "3").all_numbers() == ("1", "2", "3")


def test_phone_free_range_reserves_primary_secondary_and_numeric_description_tokens():
    config = parse_config(CONFIG)
    for value in ("31085", "32085", "33085"):
        result = free_numbers(config, "number", value, str(int(value) + 1))
        assert (
            result.all_numbers() == (str(int(value) + 1),)
            if value != "31085"
            else result.all_numbers() == ()
        )
    assert free_numbers(config, "dn", "84", "87").all_numbers() == ("84", "87")
    assert free_numbers(config, "ephone", "584", "586").all_numbers() == ("584", "586")


def test_max_ephones_is_not_used_as_a_phone_tag_upper_limit():
    config = parse_config(CONFIG)
    assert config.max_ephones == 100
    assert free_numbers(config, "ephone", "584", "586").all_numbers() == ("584", "586")
    with pytest.raises(InvalidNetworkInput, match="max-dn 200"):
        free_numbers(config, "dn", "1", "201")


def test_sccp_limits_are_scoped_to_telephony_service_not_sip():
    config = parse_config(
        "telephony-service\n max-dn 200 preference 1\n max-ephones 100\n!\nvoice register global\n max-dn 20\n!\nephone-dn 1\n number 1001\n!"
    )
    assert config.max_dn == 200 and config.max_ephones == 100
    assert config.has_sip
    with pytest.raises(InvalidNetworkInput, match="SIP"):
        free_numbers(config, "number", "1000", "1002")
    assert free_numbers(config, "dn", "1", "3").all_numbers() == ("2", "3")


def test_templates_keep_direct_fields_and_do_not_block_explicit_sccp_section_numbers():
    config = parse_config(
        "ephone-dn 2\n number 1002\n!\nephone 7\n ephone-template 1\n type 7942\n button 1:2\n!"
    )
    assert config.phones[7].model == "7942" and find_links(config, "7", "ephone")[0].dn == 2
    assert free_numbers(config, "dn", "1", "3").all_numbers() == ("1", "3")
    assert "ограничение анализа" in diagnostics_report(config)


def test_wildcard_number_does_not_generate_false_free_phone_numbers():
    config = parse_config("ephone-dn 1\n number 31...\n!")
    with pytest.raises(InvalidNetworkInput, match="шаблоны"):
        free_numbers(config, "number", "31000", "31999")


def test_preserves_leading_zero_directory_numbers_in_search_and_free_pages():
    config = parse_config("ephone-dn 1\n number 0002\n description 0003\n!")
    assert free_numbers(config, "number", "0001", "0004").all_numbers() == ("0001", "0004")
    assert len(find_links(config, "0002", "number")) == 1
    assert find_links(config, "2", "number") == ()


def test_common_paste_indentation_does_not_leak_unrelated_interface_description():
    config = parse_config(
        "  ephone-dn 1\n   number 1001\n  interface Gi0\n   description Unrelated\n  !\n"
    )
    assert config.dns[1].number == "1001" and config.dns[1].description == ""


def test_plus_prefixed_numbers_are_conservatively_reserved_in_decimal_range():
    config = parse_config("ephone-dn 1\n number +1002\n description +1003\n!")
    assert free_numbers(config, "number", "1001", "1004").all_numbers() == ("1001", "1004")


@pytest.mark.parametrize("query", ["0", "abc", "1000001", "١"])
def test_invalid_search_id_is_an_input_error_not_config_line_zero(query):
    with pytest.raises(InvalidNetworkInput, match="Для поиска номера секции") as error:
        find_links(parse_config("ephone 1"), query, "ephone")
    assert "строка" not in str(error.value)


def test_cli_prompts_tabs_unrelated_sections_and_explicit_no_commands():
    config = parse_config(
        "r(config)#ephone-dn 1 dual-line\nr(config-ephone-dn)#number\t1001\nr(config-ephone-dn)#label\tExample\n!\ninterface GigabitEthernet0\n description Unrelated\n!\nephone 9\n mac-address aa:bb:cc:dd:ee:ff\n type CIPC\n button 1:1\n no button 1:1\n button 2:1\n!"
    )
    assert config.dns[1].label == "Example"
    assert config.dns[1].description == ""
    assert config.phones[9].mac == "AABB.CCDD.EEFF"
    assert find_links(config, "9", "ephone")[0].button.text == "2:1"


@pytest.mark.parametrize(
    "value,line",
    [
        ("ephone-dn 0", 1),
        ("ephone 1 dual-line", 1),
        ("ephone invalid", 1),
        ("no ephone 1", 1),
        ("ephone 1\n!\nephone 1", 3),
        ("ephone-dn 1\n!\nephone-dn 1", 3),
        ("ephone 1\n mac-address invalid", 2),
        ("ephone-dn 1\n number", 2),
        ("ephone-dn 1\n number 1001 secondary", 2),
        ("ephone-dn 1\n number 1001 unknown", 2),
        ("ephone 1\n--More--", 2),
    ],
)
def test_malformed_config_identifies_the_physical_line(value, line):
    with pytest.raises(CMESyntaxError) as error:
        parse_config(value)
    assert error.value.line == line


def test_size_and_line_limits_and_no_sections():
    for value in (
        "",
        "interface Gi0\n description Example",
        "!\n" * (MAX_CONFIG_LINES + 1),
        "x" * (MAX_CONFIG_CHARS + 1),
    ):
        with pytest.raises(InvalidNetworkInput):
            parse_config(value)


@pytest.mark.parametrize(
    "first,last",
    [("0", "1"), ("1", "1000001"), ("10", "1"), ("a", "10"), ("1", "١"), ("01", "100")],
)
def test_invalid_id_range(first, last):
    with pytest.raises(InvalidNetworkInput):
        free_numbers(parse_config("ephone 1"), "ephone", first, last)


def test_large_range_is_compact_and_can_jump_without_enumerating_earlier_pages():
    result = free_numbers(
        parse_config("ephone-dn 1\n number 1001\n!"), "number", "1", "9999999999999999"
    )
    assert result.total == 9999999999999998
    assert len(result.intervals) == 2
    assert result.page()[0][0] == "1"
    assert result.page((result.total - 1) // 100)[0][-1] == "9999999999999999"
    with pytest.raises(InvalidNetworkInput, match="10000"):
        result.all_numbers()


def test_search_and_free_pagination_and_invalid_pages():
    config = parse_config(
        "\n!\n".join(f"ephone-dn {i}\n number {1000 + i}\n name Example User" for i in range(1, 26))
    )
    first, pages = lookup_report(config, "example", "name")
    last, _ = lookup_report(config, "example", "name", 2)
    assert pages == 3 and "ephone-dn 10:" in first and "ephone-dn 11:" not in first
    assert "ephone-dn 25:" in last and "ephone-dn 20:" not in last
    for page in (-1, 3, True):
        with pytest.raises(InvalidNetworkInput):
            lookup_report(config, "example", "name", page)
    free = free_numbers(config, "dn", "1", "25")
    assert free.total == 0 and free.page() == ((), 1)
    assert "Свободные номера ephone-dn: 0" in free_report(config, free)[0]


@pytest.mark.parametrize("seed", range(5))
def test_free_intervals_match_independent_full_enumeration(seed):
    random = Random(seed)
    occupied = set(random.sample(range(1, 1001), 127))
    config = parse_config("\n!\n".join(f"ephone-dn {i}" for i in occupied))
    result = free_numbers(config, "dn", "1", "1000")
    expected = tuple(str(value) for value in range(1, 1001) if value not in occupied)
    assert result.all_numbers() == expected
    assert (
        tuple(
            value for page in range((len(expected) + 6) // 7) for value in result.page(page, 7)[0]
        )
        == expected
    )


def test_free_description_is_visible_but_existing_section_remains_reserved():
    config = parse_config("ephone 38\n description FREE\n!\n")
    (warning,) = config.warnings
    assert "ephone 38 существует в конфигурации (строка 1)" in warning
    assert "Описание (description): FREE" in warning
    assert "MAC-адрес (mac-address), модель телефона (type)" in warning
    assert "Номер секции ephone 38 исключён из списка свободных" in warning
    report, _ = lookup_report(config, "38", "ephone")
    assert "Описание аппарата (description): FREE" in report
    assert "button: привязки к ephone-dn не указаны" in report
    assert "ID" not in report and "ЗАНЯТ" not in report
    assert free_numbers(config, "ephone", "37", "39").all_numbers() == ("37", "39")


@pytest.mark.parametrize(
    "fields,missing,present",
    [
        (" type 7942", "MAC-адрес (mac-address)", "модель телефона (type)"),
        (" mac-address 0011.2233.4455", "модель телефона (type)", "MAC-адрес (mac-address)"),
    ],
)
def test_hardware_warning_names_only_the_fields_that_are_missing(fields, missing, present):
    (warning,) = parse_config(f"ephone 7\n description Spare desk\n{fields}\n!\n").warnings
    assert missing in warning and present not in warning
    assert "Описание (description): Spare desk" in warning


def test_number_description_note_gives_actual_values_and_explains_the_fields():
    config = parse_config("ephone-dn 202\n number 31202\n description 31201\n!\n")
    (warning,) = config.warnings
    assert "ephone-dn 202 (строка 1)" in warning
    assert "Телефонный номер (number): 31202" in warning
    assert "Описание (description): 31201" in warning
    assert "number задаёт телефонный номер, description - произвольное описание" in warning
    assert "не означает ошибку" in warning
    report, _ = lookup_report(config, "202", "dn")
    assert "Телефонный номер (number): 31202" in report
    assert "Описание (description): 31201" in report
    assert "показаны оба поля" not in report


def test_notes_explicitly_cover_whole_config_and_are_separate_numbered_paragraphs():
    config = parse_config(
        "ephone 38\n description FREE\n!\nephone-dn 202\n number 31202\n description 31201\n!"
    )
    report = diagnostics_report(config)
    assert "Замечания по всей конфигурации: 2.\n\n1. ephone 38" in report
    assert "\n\n2. ephone-dn 202" in report
    assert "первые 20" not in report
    assert "\n   Описание (description): FREE" in report
    many = parse_config("\n!\n".join(f"ephone {i}" for i in range(1, 23)))
    limited = diagnostics_report(many)
    assert "Замечания по всей конфигурации: 22" in limited
    assert "Показаны первые" not in limited
    assert "\n\n20. ephone 20" in limited and "\n\n22. ephone 22" in limited


def test_paired_table_preserves_independent_namespaces_and_dangling_references():
    config = parse_config(
        "telephony-service\n max-dn 50\n!\nephone 47\n button 1:49\n!\nephone-dn 48\n number 31048\n!"
    )
    table = section_availability(config, "46", "51")
    rows, pages = table.page()
    assert pages == 1 and len(rows) == 6
    assert rows[0] == ("46", "✓ 46 - секция не создана", "✓ 46 - секция не создана")
    assert rows[1][1].startswith("✗ 47") and rows[1][2].startswith("✓ 47")
    assert rows[2][1].startswith("✓ 48") and rows[2][2].startswith("✗ 48")
    assert rows[3][2] == "✗ 49 - ссылка button"
    assert rows[5][2] == "✗ 51 - выше max-dn 50"
    assert table.free_phones == 5 and table.free_dns == 3
    report, _ = availability_report(table)
    assert "Номер\tephone\tephone-dn" in report
    assert "не привязка аппарата к DN" in report
    assert table.all_text().splitlines()[1].startswith("46\t✓ 46")


def test_sip_and_templates_do_not_block_paired_or_individual_sccp_sections():
    config = parse_config(
        "voice register global\n max-dn 20\n!\nephone-dn-template 1\n call-forward busy 31900\n!\nephone-dn 47\n number 31047\n ephone-dn-template 1\n!\nephone 48\n!"
    )
    rows, _ = section_availability(config, "47", "49").page()
    assert rows[0][1].startswith("✓ 47") and rows[0][2].startswith("✗ 47")
    assert rows[1][1].startswith("✗ 48") and rows[1][2].startswith("✓ 48")
    assert free_numbers(config, "dn", "47", "49").all_numbers() == ("48", "49")
    notes = diagnostics_report(config)
    assert "не ошибка Cisco-конфига" in notes
    assert "voice register global (строка 1)" in notes
    with pytest.raises(InvalidNetworkInput, match="Выберите «ephone / ephone-dn»"):
        free_numbers(config, "number", "31000", "31999")


@pytest.mark.parametrize(
    "first,last", [("0", "10"), ("10", "1"), ("1", "1000001"), ("bad", "10"), ("1", "")]
)
def test_pair_range_rejects_invalid_boundaries(first, last):
    with pytest.raises(InvalidNetworkInput):
        section_availability(parse_config("ephone 1"), first, last)


def test_pair_pages_stay_bounded_for_a_million_section_numbers():
    result = section_availability(parse_config("ephone 1"), "1", "1000000")
    rows, pages = result.page(9999)
    assert pages == 10000 and len(rows) == 100 and rows[-1][0] == "1000000"
    with pytest.raises(InvalidNetworkInput, match="10000 строк"):
        result.all_text()
    with pytest.raises(InvalidNetworkInput):
        result.page(10000)


def test_four_call_forward_conditions_are_retained_and_not_reserved_as_owned_numbers():
    value = "ephone-dn 47\n number 31047\n call-forward all 31900\n call-forward busy 31901\n call-forward noan 31902 timeout 20 primary\n call-forward night-service 31903\n!"
    config = parse_config(value)
    report, _ = lookup_report(config, "47", "dn")
    for text in [
        "Все вызовы (all): 31900",
        "Если занято (busy): 31901",
        "Если нет ответа (noan): 31902 timeout 20 primary",
        "В ночном режиме (night-service): 31903",
    ]:
        assert text in report
    assert "timeout указаны в секундах" in report
    assert free_numbers(config, "number", "31900", "31903").total == 4


def test_call_forward_template_is_resolved_even_when_declared_later_with_direct_override():
    value = "ephone-dn 47\n number 31047\n ephone-dn-template 3\n call-forward busy 31999\n no call-forward all\n!\nephone-dn-template 3\n call-forward all 31900\n call-forward busy 31901\n call-forward noan 31902 timeout 20\n!"
    config = parse_config(value)
    commands = {item.kind: item for item in config.dns[47].effective_forwarding}
    assert set(commands) == {"busy", "noan"}
    assert commands["busy"].argument == "31999" and commands["busy"].template is None
    assert commands["noan"].template == 3 and commands["noan"].line == 10
    assert 3 not in config.dns
    report, _ = lookup_report(config, "47", "dn")
    assert "шаблон ephone-dn-template 3" in report


def test_missing_template_does_not_claim_forwarding_is_unconfigured():
    config = parse_config("ephone-dn 47\n number 31047\n ephone-dn-template 3\n!")
    report, _ = lookup_report(config, "47", "dn")
    assert "переадресации известны не полностью" in report
    assert "Не заданы" not in report
    assert "его содержимое не предоставлено" in diagnostics_report(config)


def test_forwarding_removal_and_unrelated_sections_do_not_leak_into_dn():
    config = parse_config(
        "ephone-dn-template 3\n call-forward busy 31901\n!\nephone-dn 47\n ephone-dn-template 3\n no call-forward\n call-forward noan 31902 timeout 15\n!\ninterface Gi0\n description Other\n call-forward all 31999\n!"
    )
    assert [item.kind for item in config.dns[47].effective_forwarding] == ["noan"]
    report, _ = lookup_report(config, "47", "dn")
    assert "31999" not in report and "31901" not in report


def test_diagnostics_explains_the_physical_error_line_without_mixing_warnings_into_results():
    raw = "ephone 47\n button bad\n!"
    try:
        parse_config(raw)
    except CMESyntaxError as error:
        notes = diagnostics_report(None, str(error), raw)
    else:
        pytest.fail("Invalid button was accepted")
    assert "Текст строки 2:  button bad" in notes and "Исправьте указанную строку" in notes
    config = parse_config("ephone 47\n description FREE\n!")
    assert "Замечания по всей конфигурации" in diagnostics_report(config)
    assert "Замечания по всей конфигурации" not in lookup_report(config, "47")[0]
    assert (
        "Замечания по всей конфигурации"
        not in availability_report(section_availability(config, "46", "48"))[0]
    )
