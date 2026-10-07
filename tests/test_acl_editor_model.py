import pytest

from mac_converter.acl import (
    AclSyntaxError,
    check_conversation,
    make_flow,
    normalize_acl_paste,
    parse_acl,
)


def test_paste_cleans_telemetry_and_spaces_without_moving_line_numbers():
    text = "  10 permit ip any any (123 matches)  \r\n \r\n\t20 deny ip any any (1 match)\t"
    assert normalize_acl_paste(text) == "10 permit ip any any\n\n20 deny ip any any"
    acl = parse_acl(text)
    assert [r.line for r in acl.rules] == [1, 3]
    assert all("match" not in r.original for r in acl.rules)


def test_catalyst_object_group_error_identifies_physical_line_sequence_and_rule():
    value = "\n".join(
        ["! comment"] * 18 + ["200 permit udp object-group CONFERENCE_NET eq 8801 any (1 match)"]
    )
    with pytest.raises(AclSyntaxError) as caught:
        check_conversation(value, "", make_flow("192.0.2.1", "198.51.100.2", "udp", "8801", "9000"))
    error = caught.value
    assert error.line == 19 and error.side == 0
    assert "sequence 200" in str(error)
    assert "object-group 'CONFERENCE_NET'" in str(error)
    assert "show object-group CONFERENCE_NET" in str(error)
    assert "IPv4: нужны" not in str(error)


@pytest.mark.parametrize("side", [0, 1])
def test_absent_acl_does_not_parse_retained_invalid_text(side):
    values = ["permit ip any any", "permit ip any any"]
    values[side] = "invalid retained example"
    report = check_conversation(
        *values,
        make_flow("192.0.2.1", "198.51.100.2", "tcp", "53000", "443"),
        forward_absent=side == 0,
        reverse_absent=side == 1,
    )
    assert "явно не назначена" in report
    assert "запрос и ответ разрешены" in report


def test_both_absent_is_explicit_and_differs_from_empty_unchecked_reply():
    flow = make_flow("192.0.2.1", "198.51.100.2", "tcp", "53000", "443")
    report = check_conversation("", "", flow, forward_absent=True, reverse_absent=True)
    assert "ACL в обоих направлениях не назначены" in report
    assert "обратный поток не проверен" not in report
    assert "обратный поток не проверен" in check_conversation("permit ip any any", "", flow)
    request_absent = check_conversation("ignored", "", flow, forward_absent=True)
    assert "Вывод: ACL запроса не назначена; обратный поток не проверен." in request_absent
    assert "разрешён указанной ACL" not in request_absent


def test_absence_in_one_direction_does_not_override_deny_in_other():
    flow = make_flow("192.0.2.1", "198.51.100.2", "tcp", "53000", "443")
    report = check_conversation("ignored", "deny ip any any", flow, forward_absent=True)
    assert "ACL блокируют запрос или ответ" in report


def test_reverse_error_keeps_side_for_editor_highlight():
    with pytest.raises(AclSyntaxError) as caught:
        check_conversation(
            "permit ip any any",
            "10 permit tcp any any time-range OFFICE",
            make_flow("192.0.2.1", "198.51.100.2", "tcp", "53000", "443"),
        )
    assert caught.value.side == 1 and caught.value.line == 1
