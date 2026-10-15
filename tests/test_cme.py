from random import Random

import pytest

from mac_converter.cme import (
    MAX_CONFIG_CHARS,
    MAX_CONFIG_LINES,
    CMESyntaxError,
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
        "ephone 585: ЗАНЯТ",
        "Example Alex Office",
        "button 1:85",
        "ephone-dn 85",
        "description DN (телефон): 33085",
        "number: 31085",
        "secondary: 32085",
        "name: Example Alex; label: Example A.",
        "type: 7942",
        "MAC: 0011.2233.4455",
    ):
        assert value in report
    assert pages == 1
    assert "number и description различаются" in report
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
    assert "секция не предоставлена, ID не свободен" in report
    assert any("нет number" in warning for warning in config.warnings)


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


def test_templates_keep_direct_phone_fields_but_block_incomplete_free_dn_inference():
    config = parse_config(
        "ephone-dn 2\n number 1002\n!\nephone 7\n ephone-template 1\n type 7942\n button 1:2\n!"
    )
    assert config.phones[7].model == "7942" and find_links(config, "7", "ephone")[0].dn == 2
    with pytest.raises(InvalidNetworkInput, match="шаблоны|SIP"):
        free_numbers(config, "dn", "1", "3")


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
    with pytest.raises(InvalidNetworkInput, match="Для поиска ID") as error:
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
    assert "Свободные ephone-dn ID: 0" in free_report(config, free)[0]


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
