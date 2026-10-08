from ipaddress import IPv4Address

import pytest

from mac_converter.acl import (
    check_conversation,
    evaluate_acl,
    make_flow,
    normalize_acl_paste,
    parse_acl,
)
from mac_converter.acl_objects import (
    ObjectGroupSyntaxError,
    normalize_object_paste,
    parse_object_groups,
)
from mac_converter.network import InvalidNetworkInput


def flow(source="192.0.2.10", destination="198.51.100.20", sport="8801", dport="9000"):
    return make_flow(source, destination, "UDP", sport, dport)


@pytest.mark.parametrize(
    "member,inside,outside",
    [
        ("host 192.0.2.10", "192.0.2.10", "192.0.2.11"),
        ("192.0.2.10", "192.0.2.10", "192.0.2.11"),
        ("192.0.2.128 255.255.255.128", "192.0.2.255", "192.0.2.127"),
        ("192.0.2.128/25", "192.0.2.128", "192.0.2.127"),
        ("192.0.2.128 /25", "192.0.2.129", "192.0.2.127"),
        ("192.0.2.129 255.255.255.128", "192.0.2.128", "192.0.2.127"),
        ("0.0.0.0 0.0.0.0", "203.0.113.255", None),
        ("any", "203.0.113.255", None),
    ],
)
def test_ios_network_members_use_subnet_masks(member, inside, outside):
    group = parse_object_groups("object-group network CLIENTS\n" + member)["CLIENTS"]
    assert group.matches(IPv4Address(inside))
    if outside:
        assert not group.matches(IPv4Address(outside))


def test_show_output_nested_groups_forward_references_and_duplicate_members():
    raw = (
        "edge#show object-group\r\nNetwork object group CLIENTS\r\n"
        " group-object LOCAL\r\n group-object REMOTE\r\n host 192.0.2.10\r\n"
        "Network object group REMOTE\r\n 203.0.113.0 255.255.255.0\r\n"
        "Network object group LOCAL\r\n description office\r\n host 192.0.2.10\r\nedge#"
    )
    groups = parse_object_groups(raw)
    assert len(groups) == 3 and len(groups["CLIENTS"].networks) == 2
    assert groups["CLIENTS"].matches(IPv4Address("203.0.113.100"))
    assert not groups["CLIENTS"].matches(IPv4Address("198.51.100.1"))
    assert "edge#" not in normalize_object_paste(raw)


def test_prompt_prefixed_configuration_and_description_do_not_create_objects():
    groups = parse_object_groups(
        "edge#conf t\nedge(config)#object-group network CLIENTS\n"
        "edge(config-network-group)#description office\n"
        "edge(config-network-group)#host 192.0.2.10\nedge(config-network-group)#end\nedge#"
    )
    assert len(groups["CLIENTS"].networks) == 1


@pytest.mark.parametrize(
    "text,detail,line",
    [
        ("host 192.0.2.10", "Перед адресами", 1),
        ("object-group network X", "пуста", 1),
        ("object-group network X\nhost invalid", "IPv4", 2),
        ("object-group network X\n192.0.2.0 0.0.0.255", "не wildcard", 2),
        ("object-group network X\n192.0.2.0/0.0.0.255", "не wildcard", 2),
        ("object-group network X\n192.0.2.0/33", "0-32", 2),
        ("object-group network X\n2001:db8::/32", "IPv4", 2),
        ("object-group network X\ngroup-object Y", "Не задан состав", 2),
        ("object-group network X\ngroup-object X", "Циклическое", 2),
        (
            "object-group network X\ngroup-object Y\nobject-group network Y\ngroup-object X",
            "Циклическое",
            4,
        ),
        (
            "object-group network X\nhost 192.0.2.1\nobject-group network X\nhost 192.0.2.2",
            "повторно",
            3,
        ),
        ("object-group service X\ntcp eq https", "object-group network", 1),
        ("object-group network X\nnetwork-object host 192.0.2.1", "host IPv4", 2),
    ],
)
def test_invalid_or_incomplete_membership_identifies_object_editor_line(text, detail, line):
    with pytest.raises(ObjectGroupSyntaxError) as caught:
        parse_object_groups(text)
    assert caught.value.line == line
    assert detail in str(caught.value)


def test_source_destination_groups_match_without_expanding_or_reordering_acl():
    groups = parse_object_groups(
        "object-group network CLIENTS\nhost 192.0.2.10\nhost 192.0.2.11\n"
        "object-group network SERVERS\n198.51.100.0/24"
    )
    value = (
        "200 permit udp object-group CLIENTS eq 8801 object-group SERVERS range 8000 9000\n"
        "100 deny udp host 192.0.2.11 any\n300 deny ip any any"
    )
    acl = parse_acl(value, object_groups=groups)
    assert len(acl.rules) == 3
    allowed = evaluate_acl(acl, flow())
    assert allowed.allowed and allowed.rule.sequence == 200 and allowed.rule.line == 1
    assert "IP-группа CLIENTS источника" in allowed.text()
    assert "IP-группа SERVERS назначения" in allowed.text()
    assert evaluate_acl(acl, flow(source="192.0.2.11")).allowed is False
    assert evaluate_acl(acl, flow(source="192.0.2.12")).rule.sequence == 300
    assert evaluate_acl(acl, flow(destination="203.0.113.20")).allowed is False
    assert evaluate_acl(acl, flow(sport="8802")).allowed is False
    assert evaluate_acl(acl, flow(sport="")).allowed is None


def test_shared_groups_check_reply_and_edits_change_result():
    groups = "Network object group CLIENTS\n192.0.2.0 255.255.255.0"
    forward = "200 permit udp object-group CLIENTS eq 8801 any\n300 deny ip any any"
    reverse = "10 permit udp any eq 9000 object-group CLIENTS eq 8801\n20 deny ip any any"
    assert "запрос и ответ разрешены" in check_conversation(
        forward, reverse, flow(), object_group_value=groups
    )
    changed = groups.replace("192.0.2.0", "203.0.113.0")
    assert "ACL блокируют" in check_conversation(
        forward, reverse, flow(), object_group_value=changed
    )
    assert "обратный поток не проверен" in check_conversation(
        forward, "", flow(), object_group_value=groups
    )


def test_absent_group_acl_does_not_require_membership_and_invalid_definitions_are_not_partial():
    text = "permit udp object-group MISSING any"
    report = check_conversation(
        text, "permit ip any any", flow(), forward_absent=True, object_group_value="malformed"
    )
    assert "запрос и ответ разрешены" in report
    with pytest.raises(ObjectGroupSyntaxError):
        check_conversation(
            text,
            "",
            flow(),
            object_group_value="object-group network MISSING\nhost 192.0.2.10\nbad",
        )
    with pytest.raises(InvalidNetworkInput, match="Группы сервисов"):
        parse_acl("permit object-group SERVICES any any")
    with pytest.raises(InvalidNetworkInput, match="extended"):
        parse_acl("ip access-list standard X\npermit object-group CLIENTS")


def test_full_terminal_acl_paste_removes_wrappers_but_retains_identity_and_bad_rules():
    value = (
        '"edge#sh ip access-lists ADMIN\r\nExtended IP access list ADMIN\r\n'
        "    10 permit udp any any eq domain (27 matches)\r\n"
        '    20 deny ip any any log (1 match)\r\nedge#\r\n"'
    )
    cleaned = normalize_acl_paste(value)
    assert (
        cleaned
        == "ip access-list extended ADMIN\n10 permit udp any any eq domain\n20 deny ip any any log"
    )
    assert parse_acl(cleaned).name == "ADMIN"
    broken = normalize_acl_paste(
        "edge#sh ip access-lists X\n10 permit tcp any\n20 deny ip any any\nedge#"
    )
    with pytest.raises(InvalidNetworkInput, match="Строка 1"):
        parse_acl(broken)
    unsupported = normalize_acl_paste("permit ip any any\npermit tcp any any time-range OFFICE")
    with pytest.raises(InvalidNetworkInput, match="time-range"):
        parse_acl(unsupported)


def test_standard_header_and_multiple_acl_boundaries_survive_cleanup():
    cleaned = normalize_acl_paste(
        "edge#show ip access-lists\nStandard IP access list SOURCES\n10 permit 192.0.2.10\nedge#"
    )
    assert "ip access-list standard SOURCES" in cleaned
    assert evaluate_acl(parse_acl(cleaned), flow()).allowed
    with pytest.raises(InvalidNetworkInput, match="один список ACL"):
        parse_acl(
            normalize_acl_paste(
                "Extended IP access list A\npermit ip any any\nExtended IP access list B\npermit ip any any"
            )
        )


def test_input_limits_and_deep_nesting_do_not_crash_with_recursion_error():
    with pytest.raises(InvalidNetworkInput, match="10000 строк"):
        parse_object_groups("\n" * 10001)
    value = (
        "\n".join(f"object-group network G{n}\ngroup-object G{n + 1}" for n in range(1100))
        + "\nobject-group network G1100\nhost 192.0.2.10"
    )
    groups = parse_object_groups(value)
    assert groups["G0"].matches(IPv4Address("192.0.2.10"))
