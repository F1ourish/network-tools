"""Cisco in/out always refer to the selected device interface, not to the client."""

import pytest

from mac_converter.acl import AclSyntaxError, check_interface_acls, make_flow
from mac_converter.network import InvalidNetworkInput

INBOUND = """ip access-list extended SERVICE-FROM
10 permit tcp 198.51.100.0 0.0.0.255 any established
160 permit ip any any log"""
OUTBOUND = """ip access-list extended SERVICE-TO
10 permit tcp any any established
110 permit tcp 192.0.2.0 0.0.0.255 host 198.51.100.30 eq 443
180 permit tcp 192.0.2.0 0.0.0.255 host 198.51.100.20 eq www 443
190 permit tcp 192.0.2.0 0.0.0.255 any eq 22 3389
200 permit tcp host 192.0.2.196 198.51.100.10 0.0.0.1 eq 22 3389
250 permit ip any any log"""


@pytest.mark.parametrize("source_port", ["", "53000"])
def test_destination_interface_uses_out_request_and_in_reply_with_names(source_port):
    flow = make_flow("203.0.113.198", "198.51.100.30", "TCP", source_port, "443")
    report = check_interface_acls(INBOUND, OUTBOUND, flow, interface_at_source=False)
    request, reply = report.split("Ответ: TCP", 1)
    assert "со стороны назначения" in request
    assert "ACL out: SERVICE-TO; запрос; ip access-group SERVICE-TO out" in request
    assert "РАЗРЕШЁН: sequence 250" in request
    assert "sequence 160" not in request
    assert "ACL in: SERVICE-FROM; ответ; ip access-group SERVICE-FROM in" in reply
    assert "РАЗРЕШЁН: sequence 10" in reply
    assert "запрос и ответ разрешены" in reply


@pytest.mark.parametrize("at_source", [True, False])
def test_same_lists_change_actual_packet_checks_when_interface_side_changes(at_source):
    flow = make_flow("192.0.2.10", "198.51.100.20", "TCP", "53000", "443")
    report = check_interface_acls(
        "permit ip any any", "deny ip any any", flow, interface_at_source=at_source
    )
    request, reply = report.split("Ответ: TCP", 1)
    assert ("РАЗРЕШЁН:" in request) is at_source
    assert ("БЛОКИРУЕТСЯ:" in request) is not at_source
    assert ("РАЗРЕШЁН:" in reply) is not at_source
    assert ("БЛОКИРУЕТСЯ:" in reply) is at_source


@pytest.mark.parametrize("at_source", [True, False])
@pytest.mark.parametrize("physical_side", [0, 1])
def test_syntax_error_targets_physical_in_out_editor(at_source, physical_side):
    values = ["permit ip any any", "permit ip any any"]
    values[physical_side] = "permit ip any any\n180 permit tcp any any eq 80 65536"
    flow = make_flow("192.0.2.10", "198.51.100.20", "TCP", "53000", "443")
    with pytest.raises(AclSyntaxError) as caught:
        check_interface_acls(*values, flow, interface_at_source=at_source)
    error = caught.value
    assert error.side == physical_side and error.line == 2
    assert str(error).startswith(f"ACL {('in', 'out')[physical_side]}: Строка 2 (sequence 180)")


@pytest.mark.parametrize("at_source", [True, False])
@pytest.mark.parametrize("physical_side", [0, 1])
def test_absent_flag_stays_with_its_in_out_list(at_source, physical_side):
    values = ["permit ip any any", "permit ip any any"]
    values[physical_side] = "invalid but retained"
    flow = make_flow("192.0.2.10", "198.51.100.20", "TCP", "", "443")
    report = check_interface_acls(
        *values,
        flow,
        interface_at_source=at_source,
        inbound_absent=physical_side == 0,
        outbound_absent=physical_side == 1,
    )
    assert "запрос и ответ разрешены" in report
    assert f"ACL {('in', 'out')[physical_side]}: не назначена" in report


def test_unprovided_request_acl_is_not_treated_as_unrestricted():
    flow = make_flow("192.0.2.10", "198.51.100.20", "TCP", "", "443")
    with pytest.raises(InvalidNetworkInput, match="ACL out"):
        check_interface_acls("permit ip any any", "", flow, interface_at_source=False)
    report = check_interface_acls("", "permit ip any any", flow, interface_at_source=False)
    assert "обратный поток не проверен" in report


def test_permissive_tail_removal_changes_the_real_conclusion():
    flow = make_flow("203.0.113.198", "198.51.100.30", "TCP", "", "443")
    report = check_interface_acls(
        INBOUND, OUTBOUND.rsplit("\n", 1)[0], flow, interface_at_source=False
    )
    assert "Неявный deny" in report
    assert "запрос или ответ" in report
