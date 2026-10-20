import pytest

from mac_converter.free_ips import all_candidate_addresses, calculate_free_ips, check_address
from mac_converter.network import InvalidNetworkInput


@pytest.mark.parametrize(
    "address,status,candidate",
    [
        ("192.0.2.1", "Найден в ARP", False),
        ("192.0.2.2", "Кандидат на свободный по ARP", True),
        ("192.0.2.33", "Исключён из назначения", False),
        ("192.0.2.34", "Исключён из назначения", False),
        ("192.0.2.50", "Исключён из назначения", False),
        ("192.0.2.60", "Исключён из назначения", False),
        ("192.0.2.100", "Исключён из назначения", False),
        ("192.0.2.110", "Исключён из назначения", False),
        ("192.0.2.111", "Кандидат на свободный по ARP", True),
        ("192.0.2.0", "Адрес сети", False),
        ("192.0.2.255", "Broadcast", False),
        ("198.51.100.1", "Вне выбранной подсети", False),
    ],
)
def test_status_explains_all_assignment_constraints(address, status, candidate):
    result = calculate_free_ips(
        "192.0.2.0/24", "192.0.2.1", ".33, .34, .50-.60, 192.0.2.100-192.0.2.110"
    )
    check = check_address(result, address)
    assert check.status == status and check.candidate is candidate
    assert address in check.summary() and status in check.summary()
    assert f"Проверка IPv4: {address}" in check.text()


def test_arp_uses_exact_addresses_not_substrings_and_trims_input():
    result = calculate_free_ips("192.0.2.0/24", "192.0.2.10\n192.0.2.100")
    assert check_address(result, " 192.0.2.1\n").candidate
    assert check_address(result, "192.0.2.10").arp_present
    assert check_address(result, "192.0.2.100").arp_present


@pytest.mark.parametrize("state", ["Incomplete", "FAILED", "STALE"])
def test_arp_presence_is_kept_for_incomplete_or_stale_neighbors(state):
    result = calculate_free_ips("192.0.2.0/24", f"192.0.2.20 dev eth0 {state}")
    check = check_address(result, "192.0.2.20")
    assert check.arp_present and not check.candidate


def test_arp_and_exclusion_overlap_and_outside_presence_are_both_explained():
    result = calculate_free_ips("192.0.2.0/24", "192.0.2.33\n198.51.100.1")
    check = check_address(result, "192.0.2.33")
    assert check.arp_present and check.excluded and not check.candidate
    assert "Также входит в исключения" in check.summary()
    outside = check_address(result, "198.51.100.1")
    assert outside.arp_present and not outside.in_subnet and not outside.candidate
    assert "ARP: найден" in outside.summary()


@pytest.mark.parametrize(
    "cidr,address,excluded,candidate",
    [
        ("192.0.2.0/23", "192.0.3.33", True, False),
        ("192.0.2.0/23", "192.0.3.34", True, False),
        ("192.0.2.0/23", "192.0.3.35", False, True),
        ("192.0.2.0/31", "192.0.2.0", False, True),
        ("192.0.2.0/31", "192.0.2.1", False, True),
        ("192.0.2.0/32", "192.0.2.0", False, True),
    ],
)
def test_periodic_exclusions_and_point_to_point_host_positions(cidr, address, excluded, candidate):
    result = calculate_free_ips(cidr, "198.51.100.1")
    check = check_address(result, address)
    assert check.excluded is excluded and check.candidate is candidate


@pytest.mark.parametrize(
    "value", ["", ".33", "192.0.2.999", "192.0.02.1", "192.0.2.1/24", "::1", "192.0.2.1\n192.0.2.2"]
)
def test_query_requires_one_full_valid_ipv4(value):
    result = calculate_free_ips("192.0.2.0/24", "192.0.2.1")
    with pytest.raises(InvalidNetworkInput):
        check_address(result, value)


def test_single_address_results_agree_with_the_full_candidate_list():
    result = calculate_free_ips(
        "192.0.2.0/24",
        "192.0.2.1\n192.0.2.33\n192.0.2.240",
        ".33, .34, .50-.60, 192.0.2.100-192.0.2.110",
    )
    candidates = set(all_candidate_addresses(result))
    for octet in range(256):
        address = f"192.0.2.{octet}"
        assert check_address(result, address).candidate is (address in candidates)


def test_zero_candidates_and_large_subnet_queries_do_not_require_a_host_list():
    empty = calculate_free_ips("192.0.2.0/24", "192.0.2.1", ".0-.255")
    assert not check_address(empty, "192.0.2.200").candidate
    large = calculate_free_ips("0.0.0.0/1", "198.51.100.1")
    assert large.total > 2_000_000_000
    assert check_address(large, "127.255.255.254").candidate
    assert not check_address(large, "127.255.255.255").candidate


def test_candidate_report_states_the_evidence_limit():
    result = calculate_free_ips("192.0.2.0/24", "192.0.2.1")
    check = check_address(result, "192.0.2.3")
    assert "не найден в предоставленном списке" in check.text()
    assert "не подтверждает свободный адрес" in check.text()
