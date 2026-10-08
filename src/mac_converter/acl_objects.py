"""Offline Cisco IOS IPv4 network object groups (subnet masks, not wildcards)."""

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
import re

from .network import InvalidNetworkInput, ipv4_address

PROMPT = re.compile(r"^[\w./:@()-]+[>#]\s*(.*)$")
SHOW_COMMAND = re.compile(r"^(?:sh(?:ow)?\s+|conf(?:igure)?\s+|enable$)", re.I)
GROUP_HEADER = re.compile(r"(?:object-group\s+network|Network\s+object\s+group)\s+(\S+)", re.I)


def cli_payload(line: str) -> str | None:
    """Remove Cisco terminal wrappers; keep commands that may contain policy."""
    text = line.strip()
    if text in ('"', "'", "```", "```text", "```cisco"):
        return None
    if match := PROMPT.fullmatch(text.lstrip('"')):
        text = match[1].strip()
        if not text:
            return None
    if SHOW_COMMAND.match(text) or re.match(
        r"^(?:Building configuration|Current configuration\s*:)", text, re.I
    ):
        return None
    return text


def normalize_object_paste(value: str) -> str:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(text for line in lines if (text := cli_payload(line)) is not None)


class ObjectGroupSyntaxError(InvalidNetworkInput):
    def __init__(self, line: int, text: str, detail: str):
        self.line, self.rule, self.detail = line, text, detail
        super().__init__(f"IP-группы: строка {line}: {detail}\nОбъект: {text[:300]}")


@dataclass(frozen=True)
class NetworkGroup:
    name: str
    networks: tuple[IPv4Network, ...]

    def matches(self, address: IPv4Address) -> bool:
        return any(address in network for network in self.networks)

    def match_text(self, address: IPv4Address, direction: str) -> str:
        network = next(network for network in self.networks if address in network)
        member = str(network.network_address) if network.prefixlen == 32 else str(network)
        return f"IP-группа {self.name} {direction}: {address} входит в {member}."


def _network(text: str) -> IPv4Network:
    words = text.split()
    if len(words) == 1 and words[0].lower() == "any":
        return IPv4Network("0.0.0.0/0")
    if len(words) == 2 and words[0].lower() == "host":
        return IPv4Network((int(ipv4_address(words[1])), 32))
    if len(words) not in (1, 2):
        raise InvalidNetworkInput("Нужен host IPv4, IPv4/префикс или IPv4 с маской подсети.")
    address = words[0]
    mask = words[1] if len(words) == 2 else None
    if mask is not None:
        if "/" in address:
            raise InvalidNetworkInput("Укажите маску один раз.")
        if mask.startswith("/"):
            address += mask
        else:
            # IPv4Network also accepts wildcard masks; IOS network groups do not.
            bits = int(ipv4_address(mask))
            inverse = bits ^ 0xFFFFFFFF
            if inverse & (inverse + 1):
                raise InvalidNetworkInput(
                    "В IP-группе нужна непрерывная маска подсети, не wildcard."
                )
            address += f"/{bits.bit_count()}"
    if "/" in address and not re.fullmatch(r"[0-9]{1,2}", address.split("/", 1)[1]):
        raise InvalidNetworkInput("После / нужен числовой префикс 0-32, не wildcard.")
    try:
        return IPv4Network(address, strict=False)
    except ValueError:
        raise InvalidNetworkInput(
            "Нужна подсеть IPv4 с корректной маской или префиксом 0-32."
        ) from None


def parse_object_groups(value: str) -> dict[str, NetworkGroup]:
    if len(value.encode("utf-8")) > 1_000_000 or len(value.splitlines()) > 10000:
        raise InvalidNetworkInput("Допускается до 10000 строк и 1 МБ текста IP-групп.")
    members: dict[str, list[IPv4Network | tuple[str, int, str]]] = {}
    headers: dict[str, tuple[int, str]] = {}
    current = None
    for line, raw in enumerate(value.splitlines(), 1):
        text = cli_payload(raw)
        if text is None or not text or text.startswith(("!", "#")):
            continue
        if text.lower() in ("exit", "end"):
            current = None
            continue
        try:
            if match := GROUP_HEADER.fullmatch(text):
                current = match[1]
                if current in members:
                    raise InvalidNetworkInput(f"Группа '{current}' объявлена повторно.")
                members[current] = []
                headers[current] = (line, text)
                continue
            if current is None:
                raise InvalidNetworkInput("Перед адресами укажите object-group network <имя>.")
            if text.lower().startswith("description "):
                continue
            if text.lower().startswith("group-object "):
                words = text.split()
                if len(words) != 2:
                    raise InvalidNetworkInput("Нужен group-object <имя вложенной группы>.")
                members[current].append((words[1], line, text))
            else:
                members[current].append(_network(text))
        except InvalidNetworkInput as error:
            raise ObjectGroupSyntaxError(line, text, str(error)) from None

    resolved: dict[str, NetworkGroup] = {}
    total_members = 0
    # Iterative DFS avoids recursion limits and avoids a source x destination rule expansion.
    for root in members:
        if root in resolved:
            continue
        stack = [(root, 0)]
        active = {root}
        while stack:
            name, index = stack[-1]
            if not members[name]:
                line, text = headers[name]
                raise ObjectGroupSyntaxError(
                    line, text, f"Группа '{name}' пуста; добавьте её состав."
                )
            if index == len(members[name]):
                networks = dict.fromkeys(
                    network
                    for member in members[name]
                    for network in (
                        resolved[member[0]].networks if isinstance(member, tuple) else (member,)
                    )
                )
                if len(networks) > 10000:
                    line, text = headers[name]
                    raise ObjectGroupSyntaxError(
                        line, text, "Группа содержит более 10000 подсетей."
                    )
                resolved[name] = NetworkGroup(name, tuple(networks))
                total_members += len(networks)
                if total_members > 100000:
                    line, text = headers[name]
                    raise ObjectGroupSyntaxError(
                        line,
                        text,
                        "Слишком много объектов после раскрытия вложенных групп (100000).",
                    )
                active.remove(name)
                stack.pop()
                continue
            member = members[name][index]
            stack[-1] = (name, index + 1)
            if isinstance(member, tuple):
                child, line, text = member
                if child not in members:
                    raise ObjectGroupSyntaxError(line, text, f"Не задан состав группы '{child}'.")
                if child in active:
                    raise ObjectGroupSyntaxError(
                        line, text, f"Циклическое вложение группы '{child}'."
                    )
                if child not in resolved:
                    active.add(child)
                    stack.append((child, 0))
    return resolved
