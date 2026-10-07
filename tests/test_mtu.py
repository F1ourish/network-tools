from dataclasses import replace

import pytest

from mac_converter.mtu import CIPHERS, MtuOptions, calculate_mtu, packet_size
from mac_converter.network import InvalidNetworkInput


@pytest.mark.parametrize(
    "parameters,inner,mss",
    [
        ({}, 1500, 1460),
        ({"inner_ip": 6}, 1500, 1440),
        ({"profile": "ipip"}, 1480, 1440),
        ({"profile": "ipip", "outer_ip": 6}, 1460, 1420),
        ({"profile": "gre"}, 1476, 1436),
        (
            {"profile": "gre", "gre_checksum": True, "gre_key": True, "gre_sequence": True},
            1464,
            1424,
        ),
        ({"profile": "wireguard"}, 1440, 1400),
        ({"profile": "wireguard", "outer_ip": 6}, 1420, 1380),
        ({"profile": "vxlan"}, 1450, 1410),
        ({"profile": "vxlan", "inner_tags": 1}, 1446, 1406),
        ({"profile": "vxlan", "outer_ip": 6, "inner_tags": 2}, 1422, 1382),
        ({"profile": "ipsec"}, 1446, 1406),
        ({"profile": "ipsec", "outer_ip": 6}, 1426, 1386),
        ({"profile": "ipsec", "nat_t": True}, 1438, 1398),
        ({"profile": "ipsec", "esp_mode": "transport"}, 1466, 1426),
        ({"profile": "ipsec", "esp_cipher": "AES-CBC + HMAC-SHA1-96"}, 1438, 1398),
        ({"profile": "openvpn"}, 1448, 1408),
        ({"profile": "openvpn", "openvpn_v2": False}, 1451, 1411),
        ({"profile": "openvpn", "outer_ip": 6}, 1428, 1388),
        ({"profile": "openvpn", "openvpn_tap": True, "inner_tags": 1}, 1430, 1390),
        ({"profile": "l2tp"}, 1428, 1388),
    ],
)
def test_known_wire_formats(parameters, inner, mss):
    result = calculate_mtu(MtuOptions(**parameters))
    assert result.inner_mtu == inner and result.mss == mss


@pytest.mark.parametrize("tags,frame", [(0, 1518), (1, 1522), (2, 1526)])
def test_vlan_preserves_known_ip_mtu_and_increases_ethernet_frame(tags, frame):
    result = calculate_mtu(MtuOptions(vlan_tags=tags))
    assert result.inner_mtu == 1500 and result.frame == frame
    assert calculate_mtu(MtuOptions(size=frame, basis="frame", vlan_tags=tags)).inner_mtu == 1500
    assert (
        calculate_mtu(MtuOptions(size=1518, basis="frame", vlan_tags=tags)).inner_mtu
        == 1500 - 4 * tags
    )


def test_pppoe_is_subtracted_only_from_l2_budget():
    from_payload = calculate_mtu(MtuOptions(size=1500, basis="payload", pppoe=True, vlan_tags=1))
    from_ip = calculate_mtu(MtuOptions(size=1492, pppoe=True, vlan_tags=1))
    from_frame = calculate_mtu(MtuOptions(size=1522, basis="frame", pppoe=True, vlan_tags=1))
    for result in (from_payload, from_ip, from_frame):
        assert result.outer_mtu == result.inner_mtu == 1492
        assert result.mss == 1452 and result.frame == 1522
    assert "повторно не вычитается" in from_ip.explanation()
    assert calculate_mtu(MtuOptions(size=1508, basis="payload", pppoe=True)).inner_mtu == 1500


def test_wireguard_non_aligned_tunnel_mtu_is_not_rounded_down():
    result = calculate_mtu(MtuOptions(size=1492, profile="wireguard"))
    assert result.inner_mtu == 1432 and result.packet == 1492
    assert "как в реализации Linux" in result.explanation()


@pytest.mark.parametrize("cipher", CIPHERS)
@pytest.mark.parametrize("profile", ["ipsec", "l2tp"])
@pytest.mark.parametrize("size", [1280, 1492, 1500, 1501, 9000])
def test_esp_padding_maximality_and_frame_budget(cipher, profile, size):
    options = MtuOptions(
        size=size,
        profile=profile,
        esp_cipher=cipher,
        nat_t=True,
        pppoe=True,
        vlan_tags=2,
        basis="payload",
        l2tp_length=True,
        l2tp_sequence=True,
        ppp_header=2,
    )
    result = calculate_mtu(options)
    assert result.packet <= result.outer_mtu
    assert packet_size(result.inner_mtu + 1, options) > result.outer_mtu
    assert result.frame <= size + 26
    assert result.packet - result.inner_mtu == sum(value for _, value in result.breakdown)
    padding = dict(result.breakdown)["ESP padding"]
    assert 0 <= padding < CIPHERS[cipher][2]
    assert dict(result.breakdown)["NAT-T UDP (без IKE marker)"] == 8


def test_manual_overhead_is_added_to_selected_profile():
    base = calculate_mtu(MtuOptions(profile="gre"))
    extra = calculate_mtu(replace(base.options, extra=12))
    assert extra.inner_mtu == base.inner_mtu - 12
    assert dict(extra.breakdown)["Дополнительный overhead"] == 12


def test_small_ipv6_budget_is_reported_and_tcp_options_not_guessed():
    text = calculate_mtu(MtuOptions(size=1280, profile="wireguard", inner_ip=6)).explanation()
    assert "ниже 1280" in text and "опции уменьшают TCP-данные отдельно" in text


@pytest.mark.parametrize(
    "parameters",
    [
        {"size": 0},
        {"size": 40},
        {"size": -1},
        {"size": 65536},
        {"size": True},
        {"basis": "unknown"},
        {"profile": "unknown"},
        {"extra": -1},
        {"extra": 65536},
        {"extra": True},
        {"vlan_tags": 3},
        {"inner_tags": -1},
        {"inner_ip": 5},
        {"esp_cipher": "unknown"},
        {"esp_mode": "unknown"},
        {"ppp_header": 3},
        {"profile": "ipsec", "esp_mode": "transport", "inner_ip": 6, "outer_ip": 4},
        {"size": 18, "basis": "frame"},
        {"size": 40, "profile": "wireguard"},
    ],
)
def test_invalid_or_unusable_budget_is_rejected(parameters):
    with pytest.raises(InvalidNetworkInput):
        calculate_mtu(MtuOptions(**parameters))


def test_maximum_supported_frame_budget_with_qinq_and_pppoe():
    result = calculate_mtu(MtuOptions(size=65569, basis="frame", vlan_tags=2, pppoe=True))
    assert result.outer_mtu == result.inner_mtu == 65535
    assert result.frame == 65569
    with pytest.raises(InvalidNetworkInput):
        calculate_mtu(MtuOptions(size=65570, basis="frame", vlan_tags=2, pppoe=True))
