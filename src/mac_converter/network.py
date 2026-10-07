"""Offline IPv4, MSS, route-prefix and wildcard calculations."""

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
import re


class InvalidNetworkInput(ValueError):
    """A validation error that may be shown directly to the user."""


def ipv4_address(value: str) -> IPv4Address:
    text = value.strip()
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,2})(?:\.(?:0|[1-9][0-9]{0,2})){3}", text):
        raise InvalidNetworkInput("IPv4: нужны четыре октета 0-255 без ведущих нулей.")
    try:
        return IPv4Address(text)
    except ValueError:
        raise InvalidNetworkInput("IPv4: каждый октет должен быть от 0 до 255.") from None


def prefix_from_mask(value: str) -> int:
    text = value.strip()
    if re.fullmatch(r"/?(?:0|[1-9][0-9]?)", text):
        prefix = int(text.lstrip("/"))
        if prefix <= 32:
            return prefix
        raise InvalidNetworkInput("Префикс должен быть от /0 до /32.")
    if "." in text:
        mask = int(ipv4_address(text))
        inverse = mask ^ 0xFFFFFFFF
        if inverse & (inverse + 1):
            raise InvalidNetworkInput(
                "Полная маска: единицы должны идти перед нулями. Wildcard здесь не принимается."
            )
        return mask.bit_count()
    raise InvalidNetworkInput("Выберите /0-/32 или введите полную маску, например 255.255.255.0.")


@dataclass(frozen=True)
class IPv4Calculation:
    address: IPv4Address
    network: IPv4Network

    @property
    def first_host(self) -> IPv4Address | None:
        if self.network.prefixlen == 0:
            return None
        return IPv4Address(int(self.network.network_address) + (self.network.prefixlen < 31))

    @property
    def last_host(self) -> IPv4Address | None:
        if self.network.prefixlen == 0:
            return None
        return IPv4Address(int(self.network.broadcast_address) - (self.network.prefixlen < 31))

    @property
    def host_count(self) -> int | None:
        if self.network.prefixlen == 0:
            return None
        return self.network.num_addresses - (2 if self.network.prefixlen < 31 else 0)

    @property
    def binary_mask(self) -> str:
        return ".".join(f"{int(octet):08b}" for octet in str(self.network.netmask).split("."))

    @property
    def note(self) -> str:
        prefix = self.network.prefixlen
        if prefix == 0:
            return (
                "Весь IPv4 / default route, включая специальные адреса. "
                "255.255.255.255 - limited broadcast; число адресов не означает число хостов."
            )
        if prefix == 31:
            return "Point-to-point: оба адреса - узлы. Направленный broadcast не применяется."
        if prefix == 32:
            return "Host route: один отдельный адрес, broadcast подсети не применяется."
        if self.address != self.network.network_address:
            return f"Введённый IP {self.address} относится к подсети {self.network}."
        return "Адрес сети совпадает с введённым адресом."

    def rows(self) -> dict[str, str]:
        first, last = self.first_host, self.last_host
        return {
            "Подсеть CIDR": str(self.network),
            "Адрес подсети": str(self.network.network_address),
            "Префикс": f"/{self.network.prefixlen}",
            "Полная маска": str(self.network.netmask),
            "Двоичная маска": self.binary_mask,
            "Wildcard": str(self.network.hostmask),
            "Первый хост": str(first) if first is not None else "Не применяется к /0",
            "Последний хост": str(last) if last is not None else "Не применяется к /0",
            "Диапазон хостов": f"{first} - {last}" if first is not None else "Не применяется к /0",
            "Хостовых позиций": str(self.host_count) if self.host_count is not None else "-",
            "Всего адресов": str(self.network.num_addresses),
            "Broadcast подсети": (
                str(self.network.broadcast_address)
                if self.network.prefixlen < 31
                else "Не применяется"
            ),
        }

    def copy_text(self) -> str:
        return "\n".join(f"{label}: {value}" for label, value in self.rows().items())


def calculate_ipv4(
    address_value: str, mask_value: str = "/24", *, require_network: bool = False
) -> IPv4Calculation:
    parts = address_value.strip().split("/")
    if len(parts) > 2:
        raise InvalidNetworkInput("Введите один IPv4-адрес и один префикс.")
    address = ipv4_address(parts[0])
    if len(parts) == 2:
        if not re.fullmatch(r"(?:0|[1-9][0-9]?)", parts[1]):
            raise InvalidNetworkInput("После / укажите префикс от 0 до 32.")
        prefix = prefix_from_mask(parts[1])
    else:
        prefix = prefix_from_mask(mask_value)
    network = IPv4Network((int(address), prefix), strict=False)
    if require_network and address != network.network_address:
        raise InvalidNetworkInput(
            f"Это IP хоста. Адрес подсети: {network.network_address}/{prefix}."
        )
    return IPv4Calculation(address, network)


@dataclass(frozen=True)
class HostPage:
    addresses: tuple[str, ...]
    page: int
    pages: int
    total: int


def host_page(calculation: IPv4Calculation, page: int = 0, page_size: int = 100) -> HostPage:
    """Use integer offsets, including for /0; never enumerate the entire network."""
    if not 1 <= page_size <= 1000:
        raise InvalidNetworkInput("Размер страницы должен быть от 1 до 1000.")
    total = calculation.host_count
    first = calculation.first_host
    if total is None:
        total = calculation.network.num_addresses
        first = calculation.network.network_address
    pages = (total + page_size - 1) // page_size
    if page < 0 or page >= pages:
        raise InvalidNetworkInput(f"Номер страницы должен быть от 1 до {pages}.")
    offset = page * page_size
    start = int(first) + offset
    count = min(page_size, total - offset)
    return HostPage(tuple(str(IPv4Address(start + i)) for i in range(count)), page, pages, total)


def _unsigned_integer(value: str, label: str) -> int:
    if not re.fullmatch(r"[0-9]+", value.strip()) or len(value.strip()) > 10:
        raise InvalidNetworkInput(f"{label}: введите целое неотрицательное число.")
    return int(value.strip())


@dataclass(frozen=True)
class MssCalculation:
    mtu: int
    overhead: int
    ip_version: int
    effective_mtu: int
    mss: int

    def rows(self) -> dict[str, str]:
        return {
            "Исходный IP MTU": str(self.mtu),
            "Инкапсуляция, байт": str(self.overhead),
            "Эффективный IP MTU": str(self.effective_mtu),
            "Фиксированный IP-заголовок": "20" if self.ip_version == 4 else "40",
            "Фиксированный TCP-заголовок": "20",
            "TCP MSS": str(self.mss),
        }


def calculate_mss(mtu_value: str, ip_version: int = 4, overhead_value: str = "0") -> MssCalculation:
    if ip_version not in (4, 6):
        raise InvalidNetworkInput("Выберите IPv4 или IPv6.")
    mtu = _unsigned_integer(mtu_value, "IP MTU")
    overhead = _unsigned_integer(overhead_value, "Инкапсуляция")
    header_size = 40 if ip_version == 4 else 60
    if not 1 <= mtu <= 65535:
        raise InvalidNetworkInput("Для этого калькулятора IP MTU должен быть от 1 до 65535.")
    if overhead >= mtu or mtu - overhead <= header_size:
        raise InvalidNetworkInput(
            "После вычета инкапсуляции и IP/TCP-заголовков должен остаться MSS > 0."
        )
    effective = mtu - overhead
    return MssCalculation(mtu, overhead, ip_version, effective, effective - header_size)


@dataclass(frozen=True)
class RouteEntry:
    network: IPv4Network
    label: str
    line: int


@dataclass(frozen=True)
class RouteLookup:
    address: IPv4Address
    matches: tuple[RouteEntry, ...]

    @property
    def best(self) -> tuple[RouteEntry, ...]:
        if not self.matches:
            return ()
        prefix = self.matches[0].network.prefixlen
        return tuple(route for route in self.matches if route.network.prefixlen == prefix)

    def copy_text(self) -> str:
        if not self.matches:
            return f"IP назначения: {self.address}\nСовпадений нет."
        lines = [f"IP назначения: {self.address}", "Совпадения по длине префикса:"]
        longest = self.matches[0].network.prefixlen
        for entry in self.matches:
            marker = "[LPM] " if entry.network.prefixlen == longest else ""
            label = f"  {entry.label}" if entry.label else ""
            lines.append(f"{marker}{entry.network}{label}")
        if len(self.best) > 1:
            lines.append("Несколько равных наиболее специфичных кандидатов.")
        return "\n".join(lines)


def lookup_routes(address_value: str, routes_value: str) -> RouteLookup:
    address = ipv4_address(address_value)
    lines = routes_value.splitlines()
    if len(lines) > 10000:
        raise InvalidNetworkInput("Допускается не более 10000 строк маршрутов.")
    matches = []
    entries = 0
    for index, line in enumerate(lines, 1):
        text = line.split("#", 1)[0].strip()
        if not text:
            continue
        fields = text.split(maxsplit=1)
        if "/" not in fields[0]:
            raise InvalidNetworkInput(
                f"Строка {index}: ожидается IPv4 CIDR, например 10.20.0.0/16."
            )
        try:
            result = calculate_ipv4(fields[0], require_network=True)
        except InvalidNetworkInput as error:
            raise InvalidNetworkInput(f"Строка {index}: {error}") from None
        entries += 1
        if address in result.network:
            matches.append(RouteEntry(result.network, fields[1] if len(fields) > 1 else "", index))
    if not entries:
        raise InvalidNetworkInput("Введите хотя бы один маршрут в CIDR.")
    matches.sort(key=lambda entry: -entry.network.prefixlen)
    return RouteLookup(address, tuple(matches))


@dataclass(frozen=True)
class WildcardMatch:
    base: IPv4Address
    wildcard: IPv4Address
    address: IPv4Address
    compared_mask: int
    differing_bits: int

    @property
    def matches(self) -> bool:
        return self.differing_bits == 0

    def rows(self) -> dict[str, str]:
        return {
            "Адресное условие": f"{self.base} {self.wildcard}",
            "Проверяемый IP": str(self.address),
            "Совпадение": "Совпадает" if self.matches else "Не совпадает",
            "Wildcard, двоичный": f"{int(self.wildcard):032b}",
            "Сравниваемые биты": f"{self.compared_mask:032b}",
            "Отличающиеся значимые биты": f"{self.differing_bits:032b}",
        }


def check_wildcard(base_value: str, wildcard_value: str, address_value: str) -> WildcardMatch:
    base = ipv4_address(base_value)
    wildcard = ipv4_address(wildcard_value)
    address = ipv4_address(address_value)
    compared = int(wildcard) ^ 0xFFFFFFFF
    return WildcardMatch(base, wildcard, address, compared, (int(base) ^ int(address)) & compared)
