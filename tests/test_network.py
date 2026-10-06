from ipaddress import IPv4Address, IPv4Network
import random

import pytest

from mac_converter.network import (
    InvalidNetworkInput,
    calculate_ipv4,
    calculate_mss,
    check_wildcard,
    host_page,
    ipv4_address,
    lookup_routes,
    prefix_from_mask,
)


@pytest.mark.parametrize("prefix", range(33))
def test_every_mask_representation_and_address_boundaries(prefix):
    mask = str(IPv4Network(f"0.0.0.0/{prefix}").netmask)
    assert prefix_from_mask(mask) == prefix_from_mask(f"/{prefix}") == prefix
    for address in ("0.0.0.0", "192.168.1.129", "255.255.255.255"):
        result = calculate_ipv4(address, mask)
        expected = IPv4Network(f"{address}/{prefix}", strict=False)
        assert result.network == expected
        assert result.rows()["Wildcard"] == str(expected.hostmask)
        assert result.binary_mask.replace(".", "") == "1" * prefix + "0" * (32 - prefix)
        assert result.rows()["Всего адресов"] == str(2 ** (32 - prefix))


@pytest.mark.parametrize(
    "address",
    ["", "1.2.3", "1.2.3.4.5", "256.1.2.3", "01.2.3.4", "１.2.3.4", "-1.2.3.4", "0x1.2.3.4"],
)
def test_invalid_ipv4(address):
    with pytest.raises(InvalidNetworkInput):
        ipv4_address(address)


@pytest.mark.parametrize(
    "mask",
    [
        "",
        "/33",
        "-1",
        "/-1",
        "024",
        "２４",
        "255.0.255.0",
        "0.0.0.255",
        "255.255.255.1",
        "255.255.255.256",
    ],
)
def test_invalid_or_non_contiguous_netmask(mask):
    with pytest.raises(InvalidNetworkInput):
        prefix_from_mask(mask)


def test_ipv4_copy_default_host_normalization_and_strict_network():
    result = calculate_ipv4(" 192.168.1.42 ", "255.255.255.0")
    assert str(result.network) == "192.168.1.0/24"
    assert result.rows()["Диапазон хостов"] == "192.168.1.1 – 192.168.1.254"
    assert result.host_count == 254
    assert "Broadcast подсети: 192.168.1.255" in result.copy_text()
    with pytest.raises(InvalidNetworkInput, match="192.168.1.0/24"):
        calculate_ipv4("192.168.1.42", require_network=True)
    assert str(calculate_ipv4("192.168.1.0", require_network=True).network) == "192.168.1.0/24"


@pytest.mark.parametrize(
    "text", ["1.2.3.4/", "1.2.3.4/33", "1.2.3.4//24", "1.2.3.4/024", "1.2.3.4/255.255.255.0"]
)
def test_invalid_cidr(text):
    with pytest.raises(InvalidNetworkInput):
        calculate_ipv4(text)


def test_cidr_suffix_takes_precedence_over_mask():
    result = calculate_ipv4("10.2.3.4/16", "/24")
    assert str(result.network) == "10.2.0.0/16"


@pytest.mark.parametrize(
    "cidr,first,last,count",
    [
        ("192.0.2.0/30", "192.0.2.1", "192.0.2.2", 2),
        ("192.0.2.1/31", "192.0.2.0", "192.0.2.1", 2),
        ("192.0.2.9/32", "192.0.2.9", "192.0.2.9", 1),
    ],
)
def test_host_boundaries(cidr, first, last, count):
    result = calculate_ipv4(cidr)
    assert str(result.first_host) == first
    assert str(result.last_host) == last
    assert result.host_count == count
    assert host_page(result).addresses == tuple(
        str(IPv4Address(int(IPv4Address(first)) + i)) for i in range(count)
    )
    if result.network.prefixlen >= 31:
        assert result.rows()["Broadcast подсети"] == "Не применяется"


def test_large_host_pagination_and_last_page_do_not_enumerate_network():
    result = calculate_ipv4("10.0.0.0/8")
    first = host_page(result)
    last = host_page(result, first.pages - 1)
    assert len(first.addresses) == 100
    assert first.addresses[0] == "10.0.0.1"
    assert last.addresses[-1] == "10.255.255.254"
    assert (first.pages - 1) * 100 + len(last.addresses) == 16777214


def test_default_route_is_address_block_not_usable_hosts():
    result = calculate_ipv4("0.0.0.0/0")
    assert result.first_host is result.last_host is result.host_count is None
    assert result.rows()["Хостовых позиций"] == "—"
    assert "limited broadcast" in result.note
    page = host_page(result)
    assert page.total == 4294967296
    assert page.addresses[0] == "0.0.0.0"
    assert host_page(result, page.pages - 1).addresses[-1] == "255.255.255.255"


@pytest.mark.parametrize("page,size", [(-1, 100), (3, 100), (0, 0), (0, 1001)])
def test_invalid_host_pagination(page, size):
    with pytest.raises(InvalidNetworkInput):
        host_page(calculate_ipv4("192.168.1.0/24"), page, size)


@pytest.mark.parametrize(
    "mtu,version,overhead,expected",
    [
        ("1500", 4, "0", 1460),
        ("1500", 6, "0", 1440),
        ("1492", 4, "0", 1452),
        ("1500", 4, "60", 1400),
        ("9000", 6, "80", 8860),
    ],
)
def test_mss(mtu, version, overhead, expected):
    result = calculate_mss(mtu, version, overhead)
    assert result.mss == expected
    assert result.effective_mtu == int(mtu) - int(overhead)


@pytest.mark.parametrize(
    "mtu,version,overhead",
    [
        ("0", 4, "0"),
        ("65536", 4, "0"),
        ("40", 4, "0"),
        ("60", 6, "0"),
        ("1500", 4, "1460"),
        ("1500", 4, "1501"),
        ("1.5", 4, "0"),
        ("1500", 4, "-1"),
        ("1500", 5, "0"),
        ("９０００", 4, "0"),
    ],
)
def test_invalid_mss(mtu, version, overhead):
    with pytest.raises(InvalidNetworkInput):
        calculate_mss(mtu, version, overhead)


def test_route_longest_prefix_equal_candidates_and_default():
    routes = "# copied routes\n0.0.0.0/0 default\n10.0.0.0/8 agg\n10.20.30.0/24 via A\n10.20.0.0/16 core\n10.20.30.0/24 via B # equal"
    result = lookup_routes("10.20.30.40", routes)
    assert [entry.network.prefixlen for entry in result.matches] == [24, 24, 16, 8, 0]
    assert [entry.label for entry in result.best] == ["via A", "via B"]
    assert result.best[0].line == 4
    assert result.copy_text().count("[LPM]") == 2
    assert lookup_routes("192.0.2.1", routes).best[0].label == "default"


def test_route_no_match_and_host_route():
    result = lookup_routes("10.20.30.40", "10.20.30.40/32 host\n10.20.30.0/24 access")
    assert result.best[0].network.prefixlen == 32
    absent = lookup_routes("192.0.2.1", "10.0.0.0/8")
    assert absent.best == ()
    assert "Совпадений нет" in absent.copy_text()


@pytest.mark.parametrize(
    "routes",
    [
        "",
        "# only comment",
        "10.20.30.40/24",
        "10.20.0.0",
        "::/0",
        "0.0.0.0/0\ninvalid",
        "0.0.0.0/0\n" * 10001,
    ],
    ids=["empty", "comments", "host-bits", "missing-prefix", "ipv6", "bad-line", "too-many-routes"],
)
def test_invalid_route_input(routes):
    with pytest.raises(InvalidNetworkInput):
        lookup_routes("10.20.30.40", routes)


@pytest.mark.parametrize(
    "wildcard,ip,expected",
    [
        ("0.0.255.254", "10.10.5.2", True),
        ("0.0.255.254", "10.10.5.3", False),
        ("255.255.255.255", "203.0.113.1", True),
        ("0.0.0.0", "10.10.0.0", True),
        ("0.0.0.0", "10.10.0.1", False),
    ],
)
def test_acl_contiguous_and_non_contiguous_wildcards(wildcard, ip, expected):
    result = check_wildcard("10.10.0.0", wildcard, ip)
    assert result.matches is expected
    assert result.rows()["Совпадение"] == ("Совпадает" if expected else "Не совпадает")


def test_random_wildcards_against_independent_per_octet_check():
    rng = random.Random(821)
    for _ in range(300):
        base, wildcard, address = (str(IPv4Address(rng.getrandbits(32))) for _ in range(3))
        expected = all(
            ((a ^ b) & (255 - w)) == 0
            for a, b, w in zip(
                IPv4Address(base).packed, IPv4Address(address).packed, IPv4Address(wildcard).packed
            )
        )
        assert check_wildcard(base, wildcard, address).matches is expected


@pytest.mark.parametrize(
    "base,wildcard,address",
    [
        ("256.0.0.0", "0.0.0.255", "1.2.3.4"),
        ("1.2.3.4", "/24", "1.2.3.4"),
        ("1.2.3.4", "0.0.0.255", "01.2.3.4"),
    ],
)
def test_invalid_acl(base, wildcard, address):
    with pytest.raises(InvalidNetworkInput):
        check_wildcard(base, wildcard, address)
