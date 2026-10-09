from ipaddress import IPv4Address, IPv4Network
from random import Random

import pytest

from mac_converter.free_ips import (
    COPY_ALL_LIMIT,
    DEFAULT_EXCLUSIONS,
    MAX_ARP_CHARS,
    MAX_ARP_LINES,
    ArpSyntaxError,
    all_candidate_addresses,
    calculate_free_ips,
    free_ip_page,
    normalize_arp_paste,
    parse_arp,
    parse_exclusions,
)
from mac_converter.network import InvalidNetworkInput

ARP = """switch#show ip arp 192.0.2.1
Protocol Address Age (min) Hardware Addr Type Interface
    Internet 192.0.2.1 0 0011.2233.4401 ARPA Vlan10
    Internet 192.0.2.2 - Incomplete ARPA Vlan10
    Internet 192.0.2.2 1 0011.2233.4402 ARPA Vlan10
    Internet 198.51.100.10 0 0011.2233.4410 ARPA Vlan20
switch#
"""


def test_full_cisco_output_cleanup_and_deduplication():
    value = parse_arp(ARP)
    assert value.addresses == frozenset(
        map(lambda ip: int(IPv4Address(ip)), ("192.0.2.1", "192.0.2.2", "198.51.100.10"))
    )
    assert len(value.rows) == 4
    assert value.ignored_lines == 3
    cleaned = normalize_arp_paste(ARP)
    assert cleaned == "\n".join(value.rows)
    assert normalize_arp_paste(cleaned) == cleaned
    assert parse_arp(cleaned).addresses == value.addresses


def test_windows_linux_and_plain_ip_rows_are_accepted_conservatively():
    value = parse_arp(
        "Interface: 192.0.2.10 --- 0x6\n"
        "  192.0.2.20 aa-bb-cc-dd-ee-ff dynamic\n"
        "192.0.2.30 dev eth0 lladdr aa:bb:cc:dd:ee:ff STALE\n"
        "192.0.2.40 dev eth0 FAILED\n192.0.2.50\n"
        "fe80::1 dev eth0\n::ffff:192.0.2.60\n0011.2233.4455\n"
        "arp -a 192.0.2.70\nip neigh show to 192.0.2.80\n"
        "Get-NetNeighbor -IPAddress 192.0.2.90"
    )
    assert sorted(map(lambda ip: str(IPv4Address(ip)), value.addresses)) == [
        "192.0.2.10",
        "192.0.2.20",
        "192.0.2.30",
        "192.0.2.40",
        "192.0.2.50",
    ]


@pytest.mark.parametrize("token", ["192.0.2.999", "192.00.2.1"])
def test_invalid_ip_is_retained_on_paste_and_has_a_physical_line(token):
    raw = f"header\n192.0.2.1\nInternet {token} Incomplete"
    assert token in normalize_arp_paste(raw)
    with pytest.raises(ArpSyntaxError) as error:
        parse_arp(raw)
    assert error.value.line == 3
    assert token in str(error.value)


def test_default_exclusions_and_documented_example():
    assert DEFAULT_EXCLUSIONS == ".33, .34"
    result = calculate_free_ips("192.0.2.42/24", ARP)
    assert str(result.network) == "192.0.2.0/24"
    assert (result.host_count, result.arp_in_subnet, result.occupied_hosts) == (254, 2, 2)
    assert result.excluded_hosts == 2
    assert result.total == 250
    addresses = all_candidate_addresses(result)
    assert addresses[0] == "192.0.2.3" and addresses[-1] == "192.0.2.254"
    assert not set(addresses) & {
        "192.0.2.0",
        "192.0.2.1",
        "192.0.2.2",
        "192.0.2.33",
        "192.0.2.34",
        "192.0.2.255",
    }
    assert "Вне подсети: 1" in result.report()
    assert "не подтверждение" in result.report()


def test_list_ranges_whitespace_and_overlap_count_once():
    exclusions = " .33, 34; .50 - 60\n192.0.2.55-192.0.2.65,192.0.2.65-192.0.2.70, .33, "
    result = calculate_free_ips("192.0.2.0/24", "192.0.2.33\n192.0.2.60\n192.0.2.80", exclusions)
    assert result.excluded_hosts == 23  # .33/.34 and the inclusive .50-.70 union.
    assert result.total == 230  # Only .80 is occupied beyond that union.
    addresses = all_candidate_addresses(result)
    assert "192.0.2.49" in addresses and "192.0.2.71" in addresses
    assert "192.0.2.80" not in addresses


def test_short_exclusions_repeat_per_last_octet_but_full_addresses_do_not():
    result = calculate_free_ips(
        "192.0.2.0/23", "198.51.100.1", ".33-.34,192.0.2.50,192.0.2.254-192.0.3.1"
    )
    addresses = all_candidate_addresses(result)
    assert result.excluded_hosts == 9
    assert result.total == 501
    assert "192.0.3.50" in addresses
    assert "192.0.2.50" not in addresses
    assert all(
        ip not in addresses for ip in ("192.0.2.33", "192.0.3.33", "192.0.2.34", "192.0.3.34")
    )
    assert "192.0.3.2" in addresses


@pytest.mark.parametrize(
    "value",
    [
        ".256",
        "-1",
        ".01",
        ".60-.50",
        ".33-192.0.2.34",
        "1-2-3",
        "foo",
        "192.0.2.999",
        "192.0.2.2-192.0.2.1",
        "1 2",
        "١",
        "192.0.02.1",
    ],
)
def test_invalid_exclusions_identify_the_item(value):
    with pytest.raises(InvalidNetworkInput, match="Исключение") as error:
        parse_exclusions(value)
    assert value in str(error.value)


@pytest.mark.parametrize(
    "cidr,arp,exclusions,expected",
    [
        ("192.0.2.0/31", "198.51.100.1", "", ("192.0.2.0", "192.0.2.1")),
        ("192.0.2.0/31", "192.0.2.0", "", ("192.0.2.1",)),
        ("192.0.2.33/32", "198.51.100.1", DEFAULT_EXCLUSIONS, ()),
        ("192.0.2.33/32", "198.51.100.1", "", ("192.0.2.33",)),
        ("192.0.2.33/32", "192.0.2.33", "", ()),
        ("192.0.2.0/30", "192.0.2.0\n192.0.2.3", "", ("192.0.2.1", "192.0.2.2")),
        ("192.0.2.0/24", "198.51.100.1", ".0-.255", ()),
        ("192.0.2.0/24", "198.51.100.1", "0.0.0.0-255.255.255.255", ()),
    ],
)
def test_host_boundaries_and_empty_results(cidr, arp, exclusions, expected):
    result = calculate_free_ips(cidr, arp, exclusions)
    assert all_candidate_addresses(result) == expected
    assert free_ip_page(result).pages == 1
    assert result.total == len(expected)


def test_large_network_uses_compact_segments_and_can_jump_to_last_page():
    result = calculate_free_ips("0.0.0.0/1", "198.51.100.1")
    assert result.total == (1 << 31) - 2 - 2 * (1 << 23)
    assert len(result.intervals) == 1
    assert free_ip_page(result).addresses[0] == "0.0.0.1"
    last = free_ip_page(result, (result.total - 1) // 100)
    assert last.addresses[-1] == "127.255.255.254"
    with pytest.raises(InvalidNetworkInput, match="10000"):
        all_candidate_addresses(result)
    clipped = calculate_free_ips("0.0.0.0/1", "198.51.100.1", "0.0.0.1-127.255.255.250")
    assert all_candidate_addresses(clipped) == tuple(f"127.255.255.{i}" for i in range(251, 255))


@pytest.mark.parametrize("seed", range(8))
def test_pages_and_counts_match_independent_enumeration(seed):
    random = Random(seed)
    for prefix in (23, 24, 27, 30, 31, 32):
        network = IPv4Network(f"192.0.2.33/{prefix}", strict=False)
        hosts = list(map(int, network.hosts()))
        occupied = set(random.sample(hosts, min(9, len(hosts))))
        octets = set(random.sample(range(256), 8))
        range_start = random.choice(hosts)
        range_end = min(range_start + random.randrange(20), int(network.broadcast_address) + 2)
        manual = f"{IPv4Address(range_start)}-{IPv4Address(range_end)}"
        result = calculate_free_ips(
            str(network),
            "\n".join(
                map(lambda ip: str(IPv4Address(ip)), occupied | {int(IPv4Address("198.51.100.1"))})
            ),
            ",".join([*(f".{octet}" for octet in octets), manual]),
        )
        excluded = {ip for ip in hosts if ip % 256 in octets or range_start <= ip <= range_end}
        expected = tuple(str(IPv4Address(ip)) for ip in hosts if ip not in occupied | excluded)
        actual = tuple(
            ip
            for page in range(max(1, (len(expected) + 6) // 7))
            for ip in free_ip_page(result, page, 7).addresses
        )
        assert actual == expected
        assert result.total == len(expected)
        assert result.excluded_hosts == len(excluded)
        assert result.occupied_hosts == len(occupied)


@pytest.mark.parametrize(
    "page,size", [(-1, 100), (3, 100), (True, 100), (0, 0), (0, 1001), (0, True)]
)
def test_page_bounds(page, size):
    with pytest.raises(InvalidNetworkInput):
        free_ip_page(calculate_free_ips("192.0.2.0/24", ARP), page, size)


def test_input_limits_and_missing_arp():
    for raw in (
        "",
        "header\nswitch#",
        "192.0.2.1\n" * (MAX_ARP_LINES + 1),
        "x" * (MAX_ARP_CHARS + 1),
    ):
        with pytest.raises(InvalidNetworkInput):
            calculate_free_ips("192.0.2.0/24", raw)
    for exclusions in (".1," * 1025, "x" * 16385):
        with pytest.raises(InvalidNetworkInput):
            parse_exclusions(exclusions)
    with pytest.raises(InvalidNetworkInput, match="/1-/32"):
        calculate_free_ips("0.0.0.0/0", ARP)
    assert COPY_ALL_LIMIT == 10000
