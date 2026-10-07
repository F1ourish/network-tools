import pytest

from mac_converter.acl import check_conversation, evaluate_acl, make_flow, parse_acl
from mac_converter.network import InvalidNetworkInput


def flow(source_port="53000", destination_port="443", protocol="TCP", ack=False):
    return make_flow("192.0.2.10", "198.51.100.20", protocol, source_port, destination_port, ack)


def decision(text, **kwargs):
    return evaluate_acl(parse_acl(text), flow(**kwargs))


def test_first_match_and_implicit_deny_are_distinct():
    rules = "deny tcp any host 198.51.100.20 eq 443\npermit ip any any"
    result = decision(rules)
    assert result.allowed is False and result.rule.line == 1
    assert "deny tcp" in result.text()
    assert decision("permit tcp any any eq 80").rule is None
    assert "Неявный deny" in decision("permit tcp any any eq 80").text()
    assert decision("permit ip any any\ndeny tcp any any eq 443").allowed is True


def test_sequence_numbers_sort_and_preserve_source_lines():
    result = decision("Extended IP access list WEB\n30 permit ip any any (8 matches)\n10 remark before\n20 deny tcp any any eq https log")
    assert result.allowed is False
    assert result.rule.sequence == 20 and result.rule.line == 4
    assert "sequence 20, строка 4" in result.text()


@pytest.mark.parametrize("prefix", ["", "access-list 101 ", "access-list WEB "])
def test_raw_named_and_numbered_extended_rules(prefix):
    assert decision(prefix + "permit tcp host 192.0.2.10 eq 53000 198.51.100.0 0.0.0.255 eq https log-input").allowed is True


@pytest.mark.parametrize("rules", [
    "access-list 10 permit 192.0.2.0 0.0.0.255",
    "ip access-list standard SOURCES\n10 permit host 192.0.2.10\n20 deny any",
    "Standard IP access list SOURCES\n10 permit 192.0.2.10 (1 match)",
])
def test_standard_acl_checks_only_source(rules):
    assert decision(rules).allowed is True


def test_noncontiguous_wildcard_is_not_treated_as_subnet_mask():
    rules = "permit ip 192.0.2.0 0.0.0.254 any"
    assert decision(rules).allowed is True
    result = evaluate_acl(parse_acl(rules), make_flow("192.0.2.11", "198.51.100.20", "TCP", "53000", "443"))
    assert result.allowed is False


@pytest.mark.parametrize("operator,port,allowed", [
    ("eq 443", "443", True), ("eq 443", "442", False),
    ("neq 443", "443", False), ("neq 443", "444", True),
    ("lt 443", "442", True), ("lt 443", "443", False),
    ("gt 443", "444", True), ("gt 443", "443", False),
    ("range 400 443", "400", True), ("range 400 443", "443", True),
    ("range 400 443", "444", False), ("range 0 65535", "0", True),
    ("range 0 65535", "65535", True),
])
def test_port_operator_boundaries(operator, port, allowed):
    assert decision(f"permit tcp any any {operator}", destination_port=port).allowed is allowed


def test_source_port_and_protocol_are_independent_conditions():
    text = "permit udp any eq domain any eq 443\npermit tcp any eq 53000 any eq 443"
    assert decision(text).rule.line == 2
    assert decision(text, protocol="UDP", source_port="53").rule.line == 1
    assert decision(text, protocol="UDP").allowed is False


def test_other_protocol_and_icmp_rules_can_be_skipped_only_after_valid_parsing():
    text = "permit icmp any any echo\npermit gre any any\npermit 17 any any eq domain\npermit 6 any any eq 443"
    assert decision(text).rule.line == 4
    assert decision("permit icmp any any 3 4\npermit tcp any any").allowed is True


def test_established_checks_tcp_ack_or_rst_and_does_not_track_state():
    text = "permit tcp any any established"
    assert decision(text).allowed is False
    assert decision(text, ack=True).allowed is True
    assert flow().reverse().ack_or_rst is True
    assert flow(protocol="UDP").reverse().ack_or_rst is False


def test_unknown_source_port_does_not_jump_to_later_permit_or_deny():
    for action in ("permit", "deny"):
        text = f"{action} tcp any eq 53000 any eq 443\npermit ip any any"
        result = decision(text, source_port="")
        assert result.allowed is None and result.rule.line == 1
        assert "Неизвестен порт источника" in result.text()
    # A definitely false known condition rules out the earlier rule.
    assert decision("deny tcp any eq 53000 any eq 80\npermit ip any any", source_port="").allowed is True
    assert decision("permit ip any any", source_port="").allowed is True


def test_conversation_reverses_both_addresses_and_ports():
    request = "permit tcp host 192.0.2.10 eq 53000 host 198.51.100.20 eq 443"
    reply = "permit tcp host 198.51.100.20 eq 443 host 192.0.2.10 eq 53000 established"
    result = check_conversation(request, reply, flow())
    assert "198.51.100.20:443 -> 192.0.2.10:53000" in result
    assert "запрос и ответ разрешены" in result
    assert "ACL блокируют" in check_conversation(request, "deny ip any any", flow())
    assert "ACL блокируют" in check_conversation("deny ip any any", reply, flow())


def test_empty_reply_acl_is_explicitly_unchecked_and_missing_port_is_unknown():
    assert "обратный поток не проверен" in check_conversation("permit ip any any", "", flow())
    assert "запрос разрешён" in check_conversation("permit ip any any", "", flow())
    assert "недостаточно данных" in check_conversation("permit ip any any", "permit tcp any any eq 53000", flow(source_port=""))


@pytest.mark.parametrize("rules", [
    "", "remark no rules", "permit tcp any", "permit tcp any any eq",
    "permit tcp any any eq 65536", "permit tcp any any eq unsupported-service",
    "permit tcp any any range 500 100", "permit tcp any any eq -1",
    "permit ip any any eq 443", "permit udp any any established",
    "permit tcp any any time-range NIGHT", "permit tcp any any fragments",
    "permit tcp object-group USERS any", "permit tcp any any log unexpected",
    "permit made-up any any", "permit icmp any any 3 256",
    "permit ip any any\nunsupported command", "permit tcp 192.0.2.0/24 any",
    "ip access-list extended A\npermit ip any any\nip access-list extended B\npermit ip any any",
    "access-list 101 permit ip any any\naccess-list 102 permit ip any any",
    "ip access-list standard 101\npermit any", "access-list 300 permit ip any any",
    "10 permit ip any any\n10 deny ip any any", "0 permit ip any any",
    "2147483648 permit ip any any", "10 permit ip any any\npermit ip any any",
    "permit ip any any\nip access-list extended LATE", "access-list " + "9" * 5000 + " permit ip any any",
    "9" * 5000 + " permit ip any any",
])
def test_unsupported_or_malformed_acl_never_returns_a_verdict(rules):
    with pytest.raises(InvalidNetworkInput):
        parse_acl(rules)


def test_entire_both_lists_are_validated_even_after_decisive_deny():
    with pytest.raises(InvalidNetworkInput, match="Строка 2"):
        check_conversation("deny ip any any", "permit ip any any\npermit tcp any any time-range DAY", flow())


@pytest.mark.parametrize("source,destination,protocol,sport,dport", [
    ("bad", "198.51.100.20", "TCP", "1", "443"),
    ("192.0.2.10", "::1", "TCP", "1", "443"),
    ("192.0.2.10", "198.51.100.20", "ICMP", "1", "443"),
    ("192.0.2.10", "198.51.100.20", "TCP", "65536", "443"),
    ("192.0.2.10", "198.51.100.20", "TCP", "1", ""),
])
def test_invalid_flow_is_rejected(source, destination, protocol, sport, dport):
    with pytest.raises(InvalidNetworkInput):
        make_flow(source, destination, protocol, sport, dport)


def test_acl_size_limits():
    with pytest.raises(InvalidNetworkInput, match="10000"):
        parse_acl("! comment\n" * 10001 + "permit ip any any")
    with pytest.raises(InvalidNetworkInput, match="1 МБ"):
        parse_acl("!" * 1_000_001)
