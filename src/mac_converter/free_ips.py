"""Offline IPv4 candidates from supplied ARP data; never probe or allocate addresses."""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
import re

from .network import HostPage, InvalidNetworkInput, calculate_ipv4, ipv4_address

DEFAULT_EXCLUSIONS = ".33, .34"
MAX_ARP_LINES = 10000
MAX_ARP_CHARS = 1024 * 1024
MAX_EXCLUSION_CHARS = 16384
MAX_EXCLUSIONS = 1024
COPY_ALL_LIMIT = 10000

_IP_TOKEN = re.compile(r"(?<![\w.:])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![\w.:])")
_COMMAND = re.compile(
    r"^(?:[^\n]*[>#]\s*)?(?:(?:show|sh)\s+|arp\s+-|ip\s+neigh(?:bor)?\b|Get-NetNeighbor\b)",
    re.IGNORECASE,
)


class ArpSyntaxError(InvalidNetworkInput):
    def __init__(self, line: int, address: str, detail: str):
        self.line = line
        super().__init__(f"Строка ARP {line}: неверный IPv4 {address}. {detail}")


@dataclass(frozen=True)
class ArpInput:
    addresses: frozenset[int]
    rows: tuple[str, ...]
    ignored_lines: int


def _arp_tokens(line: str) -> tuple[str, ...]:
    return () if _COMMAND.match(line.strip()) else tuple(_IP_TOKEN.findall(line))


def normalize_arp_paste(value: str) -> str:
    """Keep IP-bearing rows, including invalid IP-like tokens for visible diagnostics."""
    if len(value) > MAX_ARP_CHARS:
        return value
    return "\n".join(line.strip() for line in value.splitlines() if _arp_tokens(line))


def parse_arp(value: str) -> ArpInput:
    if len(value) > MAX_ARP_CHARS:
        raise InvalidNetworkInput("ARP: допускается не более 1 МБ текста.")
    lines = value.splitlines()
    if len(lines) > MAX_ARP_LINES:
        raise InvalidNetworkInput("ARP: допускается не более 10000 строк.")
    addresses, rows, ignored = set(), [], 0
    for number, line in enumerate(lines, 1):
        tokens = _arp_tokens(line)
        if not tokens:
            ignored += 1
            continue
        for token in tokens:
            try:
                addresses.add(int(ipv4_address(token)))
            except InvalidNetworkInput as error:
                raise ArpSyntaxError(number, token, str(error)) from None
        rows.append(line.strip())
    return ArpInput(frozenset(addresses), tuple(rows), ignored)


def _merge(intervals) -> tuple[tuple[int, int], ...]:
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return tuple(merged)


def _exclusion_endpoint(value: str) -> tuple[str, int]:
    text = value.strip()
    if re.fullmatch(r"\.?(?:0|[1-9][0-9]{0,2})", text):
        octet = int(text.lstrip("."))
        if octet <= 255:
            return "octet", octet
        raise InvalidNetworkInput("Последний октет исключения должен быть от 0 до 255.")
    return "address", int(ipv4_address(text))


@dataclass(frozen=True)
class Exclusions:
    last_octets: frozenset[int]
    intervals: tuple[tuple[int, int], ...]


def parse_exclusions(value: str) -> Exclusions:
    if len(value) > MAX_EXCLUSION_CHARS:
        raise InvalidNetworkInput("Исключения: допускается не более 16384 символов.")
    entries = [item.strip() for item in re.split(r"[,;\n]", value) if item.strip()]
    if len(entries) > MAX_EXCLUSIONS:
        raise InvalidNetworkInput("Допускается не более 1024 исключений.")
    octets, intervals = set(), []
    for item in entries:
        try:
            parts = item.split("-")
            if len(parts) not in (1, 2):
                raise InvalidNetworkInput("Диапазон задаётся двумя границами через один дефис.")
            kind, first = _exclusion_endpoint(parts[0])
            other_kind, last = _exclusion_endpoint(parts[-1])
            if kind != other_kind:
                raise InvalidNetworkInput(
                    "Обе границы должны быть полными IPv4 или последними октетами."
                )
            if first > last:
                raise InvalidNetworkInput("Начало диапазона должно быть не больше конца.")
        except InvalidNetworkInput as error:
            raise InvalidNetworkInput(f"Исключение «{item}»: {error}") from None
        if kind == "octet":
            octets.update(range(first, last + 1))
        else:
            intervals.append((first, last))
    return Exclusions(frozenset(octets), _merge(intervals))


def _allowed_before(limit: int, allowed: tuple[int, ...]) -> int:
    blocks, remainder = divmod(limit, 256)
    return blocks * len(allowed) + bisect_left(allowed, remainder)


def _allowed_count(start: int, end: int, allowed: tuple[int, ...]) -> int:
    return _allowed_before(end + 1, allowed) - _allowed_before(start, allowed)


def _clip(intervals, first: int, last: int) -> tuple[tuple[int, int], ...]:
    return _merge(
        (max(first, start), min(last, end))
        for start, end in intervals
        if start <= last and end >= first
    )


@dataclass(frozen=True)
class FreeIPCalculation:
    network: IPv4Network
    arp: ArpInput
    host_count: int
    arp_in_subnet: int
    occupied_hosts: int
    excluded_hosts: int
    allowed_octets: tuple[int, ...]
    intervals: tuple[tuple[int, int], ...]
    cumulative: tuple[int, ...]

    @property
    def total(self) -> int:
        return self.cumulative[-1] if self.cumulative else 0

    def report(self, page: int = 0) -> str:
        result = free_ip_page(self, page)
        lines = [
            f"Подсеть: {self.network}",
            f"Хостовых позиций: {self.host_count}",
            f"IPv4 в ARP: {len(self.arp.addresses)} уникальных; в подсети: {self.arp_in_subnet}",
            f"Вне подсети: {len(self.arp.addresses) - self.arp_in_subnet}",
            f"Занятых хостовых позиций по ARP: {self.occupied_hosts}",
            f"Исключения охватывают: {self.excluded_hosts}",
            f"Кандидатов по ARP: {self.total}",
            "Пересечения ARP и исключений учитываются один раз.",
            f"Страница {result.page + 1} / {result.pages}",
            "Адреса отсутствуют в предоставленном ARP и не входят в исключения.",
            "Это кандидаты, а не подтверждение свободного адреса; сверить IPAM/DHCP и проверить конфликт.",
        ]
        return "\n".join(lines + ["", *result.addresses])


def calculate_free_ips(
    network_value: str,
    arp_value: str,
    exclusion_value: str = DEFAULT_EXCLUSIONS,
    mask_value: str = "/24",
) -> FreeIPCalculation:
    network = calculate_ipv4(network_value, mask_value).network
    if network.prefixlen == 0:
        raise InvalidNetworkInput(
            "Укажите локальную подсеть /1-/32. /0 не является подсетью для назначения IP."
        )
    arp = parse_arp(arp_value)
    if not arp.addresses:
        raise InvalidNetworkInput(
            "В ARP-списке нет IPv4-адресов. Вставьте ARP-таблицу или список IP."
        )
    exclusions = parse_exclusions(exclusion_value)
    first = int(network.network_address) + (network.prefixlen < 31)
    last = int(network.broadcast_address) - (network.prefixlen < 31)
    host_count = last - first + 1
    occupied = tuple(address for address in arp.addresses if first <= address <= last)
    manual = _clip(exclusions.intervals, first, last)
    allowed = tuple(octet for octet in range(256) if octet not in exclusions.last_octets)
    periodic_excluded = host_count - _allowed_count(first, last, allowed)
    excluded_hosts = periodic_excluded + sum(_allowed_count(a, b, allowed) for a, b in manual)
    blocked = _clip((*manual, *((address, address) for address in occupied)), first, last)
    intervals, cumulative, current, total = [], [], first, 0
    for start, end in (*blocked, (last + 1, last + 1)):
        if current < start:
            count = _allowed_count(current, start - 1, allowed)
            if count:
                intervals.append((current, start - 1))
                total += count
                cumulative.append(total)
        current = end + 1
    return FreeIPCalculation(
        network,
        arp,
        host_count,
        sum(IPv4Address(address) in network for address in arp.addresses),
        len(occupied),
        excluded_hosts,
        allowed,
        tuple(intervals),
        tuple(cumulative),
    )


def free_ip_page(result: FreeIPCalculation, page: int = 0, page_size: int = 100) -> HostPage:
    if type(page_size) is not int or not 1 <= page_size <= 1000:
        raise InvalidNetworkInput("Размер страницы должен быть от 1 до 1000.")
    pages = max(1, (result.total + page_size - 1) // page_size)
    if type(page) is not int or not 0 <= page < pages:
        raise InvalidNetworkInput(f"Номер страницы должен быть от 1 до {pages}.")
    addresses = []
    for index in range(page * page_size, min((page + 1) * page_size, result.total)):
        segment = bisect_right(result.cumulative, index)
        offset = index - (result.cumulative[segment - 1] if segment else 0)
        rank = _allowed_before(result.intervals[segment][0], result.allowed_octets) + offset
        block, octet = divmod(rank, len(result.allowed_octets))
        addresses.append(str(IPv4Address(block * 256 + result.allowed_octets[octet])))
    return HostPage(tuple(addresses), page, pages, result.total)


def all_candidate_addresses(result: FreeIPCalculation) -> tuple[str, ...]:
    if result.total > COPY_ALL_LIMIT:
        raise InvalidNetworkInput(
            "Все IP копируются до 10000 адресов; для больших списков используйте страницы."
        )
    return tuple(
        address
        for page in range(max(1, (result.total + 999) // 1000))
        for address in free_ip_page(result, page, 1000).addresses
    )
