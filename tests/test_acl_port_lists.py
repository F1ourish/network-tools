"""Port lists are alternatives, with independent source and destination conditions."""

import pytest

from mac_converter.acl import AclSyntaxError, evaluate_acl, make_flow, parse_acl


def evaluate(rule, *, source="53000", destination="443", protocol="TCP"):
    flow = make_flow("192.0.2.10", "198.51.100.20", protocol, source, destination)
    return evaluate_acl(parse_acl(rule), flow)


@pytest.mark.parametrize("protocol", ["TCP", "UDP"])
@pytest.mark.parametrize(
    "ports,port,allowed",
    [
        ("www 443", "80", True),
        ("www 443", "443", True),
        ("www 443", "81", False),
        ("22 3389", "22", True),
        ("22 3389", "3389", True),
        ("22 3389", "23", False),
    ],
)
def test_destination_eq_list_accepts_each_member_only(protocol, ports, port, allowed):
    result = evaluate(
        f"permit {protocol.lower()} any any eq {ports}", destination=port, protocol=protocol
    )
    assert result.allowed is allowed


@pytest.mark.parametrize(
    "source,destination,allowed",
    [
        ("53", "443", True),
        ("123", "80", True),
        ("123", "443", True),
        ("53000", "443", False),
        ("53", "81", False),
    ],
)
def test_both_lists_match_independently_before_destination_wildcard(source, destination, allowed):
    rule = "permit tcp 192.0.2.0 0.0.0.255 eq domain ntp 198.51.100.0 0.0.0.255 eq www 443"
    assert evaluate(rule, source=source, destination=destination).allowed is allowed


@pytest.mark.parametrize("port,allowed", [("22", False), ("3389", False), ("443", True)])
def test_neq_excludes_every_list_member(port, allowed):
    assert evaluate("permit tcp any any neq 22 3389", destination=port).allowed is allowed


def test_source_neq_list_does_not_consume_host_destination():
    rule = "permit udp any neq domain ntp host 198.51.100.20 eq 443 8443"
    assert evaluate(rule, source="53", protocol="UDP").allowed is False
    assert evaluate(rule, source="123", protocol="UDP").allowed is False
    assert evaluate(rule, source="53000", destination="8443", protocol="UDP").allowed is True


def test_lists_keep_sequence_first_match_and_original_rule_with_log():
    text = "30 permit ip any any\n20 deny tcp any any eq www 443 log-input\n10 permit udp any any"
    result = evaluate(text)
    assert result.allowed is False
    assert result.rule.sequence == 20 and result.rule.line == 2
    assert result.rule.original == "20 deny tcp any any eq www 443 log-input"


def test_source_list_can_precede_network_object_group():
    from mac_converter.acl_objects import parse_object_groups

    groups = parse_object_groups("object-group network SERVERS\n host 198.51.100.20")
    acl = parse_acl(
        "permit tcp any eq 22 53000 object-group SERVERS eq www 443 established",
        object_groups=groups,
    )
    flow = make_flow("192.0.2.10", "198.51.100.20", "TCP", "53000", "443", True)
    assert evaluate_acl(acl, flow).allowed is True


def test_ten_ports_and_boundary_values_are_valid_in_each_list():
    ports = "0 1 2 3 4 5 6 7 8 65535"
    rule = f"permit tcp any eq {ports} any eq {ports}"
    assert evaluate(rule, source="0", destination="65535").allowed is True
    assert evaluate(rule, source="65535", destination="0").allowed is True
    assert evaluate(rule, source="9", destination="0").allowed is False


@pytest.mark.parametrize("operator", ["eq", "neq"])
@pytest.mark.parametrize("side", ["source", "destination"])
def test_eleven_ports_are_rejected_with_original_rule(operator, side):
    condition = operator + " " + " ".join(map(str, range(11)))
    rule = (
        f"180 permit tcp any {condition} any"
        if side == "source"
        else f"180 permit tcp any any {condition}"
    )
    with pytest.raises(AclSyntaxError, match="от 1 до 10 портов") as caught:
        parse_acl(rule)
    assert caught.value.line == 1 and caught.value.rule == rule


@pytest.mark.parametrize(
    "condition",
    [
        "eq 80 65536",
        "neq 22 65536",
        "eq 443 -1",
        "eq www unknown-service",
        "eq 22 3389 time-range OFFICE",
        "gt 22 3389",
        "lt 443 8443",
        "range 80 443 8443",
    ],
)
def test_invalid_or_unsupported_tokens_are_never_silently_dropped(condition):
    with pytest.raises(AclSyntaxError):
        parse_acl("permit tcp any any " + condition)


def test_unknown_source_port_remains_unknown_only_for_potential_match():
    result = evaluate("deny tcp any eq 22 53000 any eq www 443\npermit ip any any", source="")
    assert result.allowed is None and result.rule.line == 1
    result = evaluate(
        "deny tcp any eq 22 53000 any eq www 443\npermit ip any any", source="", destination="8443"
    )
    assert result.allowed is True and result.rule.line == 2
