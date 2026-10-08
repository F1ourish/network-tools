"""Strict, offline Cisco IOS IPv4 ACL parsing and first-match evaluation."""

from dataclasses import dataclass
from ipaddress import IPv4Address
import re

from .network import InvalidNetworkInput, ipv4_address
from .acl_objects import NetworkGroup, cli_payload, parse_object_groups

PROTOCOLS = {
    "icmp": 1,
    "igmp": 2,
    "ipinip": 4,
    "tcp": 6,
    "udp": 17,
    "gre": 47,
    "esp": 50,
    "ahp": 51,
    "eigrp": 88,
    "ospf": 89,
    "pim": 103,
}
PORTS = {
    "ftp-data": 20,
    "ftp": 21,
    "ssh": 22,
    "telnet": 23,
    "smtp": 25,
    "domain": 53,
    "bootps": 67,
    "bootpc": 68,
    "tftp": 69,
    "www": 80,
    "http": 80,
    "pop3": 110,
    "ntp": 123,
    "imap": 143,
    "snmp": 161,
    "snmptrap": 162,
    "bgp": 179,
    "https": 443,
    "isakmp": 500,
    "syslog": 514,
    "ldaps": 636,
    "non500-isakmp": 4500,
}
OPERATORS = {"eq", "neq", "lt", "gt", "range"}
COUNTER = re.compile(r"\s+\(\s*[0-9]+\s+match(?:es)?\s*\)\s*$", re.I)


def normalize_acl_paste(value: str) -> str:
    """Clean terminal output; preserve policy, ACL type/name and intentional blank lines."""
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned = []
    for raw in lines:
        text = cli_payload(raw)
        if text is None:
            continue
        if header := re.fullmatch(r"(Standard|Extended) IP access list (\S+)", text, re.I):
            text = f"ip access-list {header[1].lower()} {header[2]}"
        cleaned.append(COUNTER.sub("", text))
    return "\n".join(cleaned)


class AclSyntaxError(InvalidNetworkInput):
    def __init__(self, line, rule, detail, side=None):
        self.line, self.rule, self.detail, self.side = line, rule, str(detail), side
        sequence = re.match(r"([0-9]+)\s", rule)
        label = f" (sequence {sequence[1]})" if sequence else ""
        prefix = ("ACL запроса: ", "ACL ответа: ")[side] if side is not None else ""
        super().__init__(f"{prefix}Строка {line}{label}: {detail}\nПравило: {rule[:300]}")


ICMP_NAMES = {
    "echo",
    "echo-reply",
    "unreachable",
    "time-exceeded",
    "redirect",
    "timestamp-request",
    "timestamp-reply",
    "information-request",
    "information-reply",
    "mask-request",
    "mask-reply",
    "packet-too-big",
}


def port_number(text: str) -> int:
    if text.lower() in PORTS:
        return PORTS[text.lower()]
    if re.fullmatch(r"[0-9]{1,5}", text) and int(text) <= 65535:
        return int(text)
    raise InvalidNetworkInput(f"Порт '{text}': нужен номер 0-65535 или поддерживаемое имя сервиса.")


@dataclass(frozen=True)
class AddressCondition:
    base: int = 0
    wildcard: int = 0xFFFFFFFF

    def matches(self, address: IPv4Address) -> bool:
        return not ((int(address) ^ self.base) & (self.wildcard ^ 0xFFFFFFFF))


@dataclass(frozen=True)
class PortCondition:
    operator: str
    first: int
    last: int = 0

    def matches(self, port: int) -> bool:
        if self.operator == "eq":
            return port == self.first
        if self.operator == "neq":
            return port != self.first
        if self.operator == "lt":
            return port < self.first
        if self.operator == "gt":
            return port > self.first
        return self.first <= port <= self.last


@dataclass(frozen=True)
class Flow:
    source: IPv4Address
    destination: IPv4Address
    protocol: int
    source_port: int | None
    destination_port: int | None
    ack_or_rst: bool = False

    def __post_init__(self):
        if self.protocol not in (6, 17):
            raise InvalidNetworkInput("Проверка потока поддерживает TCP и UDP.")
        for port in (self.source_port, self.destination_port):
            if port is not None and (type(port) is not int or not 0 <= port <= 65535):
                raise InvalidNetworkInput("Порты должны быть от 0 до 65535.")

    def reverse(self):
        return Flow(
            self.destination,
            self.source,
            self.protocol,
            self.destination_port,
            self.source_port,
            self.protocol == 6,
        )

    def text(self):
        return (
            f"{'TCP' if self.protocol == 6 else 'UDP'} "
            f"{self.source}:{self.source_port if self.source_port is not None else '?'} -> "
            f"{self.destination}:{self.destination_port if self.destination_port is not None else '?'}"
            + (f"; ACK/RST={'1' if self.ack_or_rst else '0'}" if self.protocol == 6 else "")
        )


def make_flow(
    source: str,
    destination: str,
    protocol: str,
    source_port: str,
    destination_port: str,
    ack_or_rst=False,
) -> Flow:
    number = {"TCP": 6, "UDP": 17}.get(protocol.upper())
    if number is None:
        raise InvalidNetworkInput("Выберите TCP или UDP.")
    if not destination_port.strip():
        raise InvalidNetworkInput("Укажите порт назначения.")
    return Flow(
        ipv4_address(source),
        ipv4_address(destination),
        number,
        port_number(source_port.strip()) if source_port.strip() else None,
        port_number(destination_port.strip()),
        bool(ack_or_rst),
    )


@dataclass(frozen=True)
class Rule:
    action: str
    protocol: int | None
    source: AddressCondition | NetworkGroup
    destination: AddressCondition | NetworkGroup
    source_port: PortCondition | None
    destination_port: PortCondition | None
    established: bool
    line: int
    sequence: int | None
    original: str

    def match(self, flow: Flow) -> tuple[bool | None, str]:
        if self.protocol is not None and self.protocol != flow.protocol:
            return False, ""
        if not self.source.matches(flow.source) or not self.destination.matches(flow.destination):
            return False, ""
        if self.established and not flow.ack_or_rst:
            return False, ""
        missing = []
        for label, condition, port in (
            ("источника", self.source_port, flow.source_port),
            ("назначения", self.destination_port, flow.destination_port),
        ):
            if condition is None:
                continue
            if port is None:
                missing.append(label)
            elif not condition.matches(port):
                return False, ""
        if missing:
            return None, "Неизвестен порт " + " и ".join(missing) + "."
        details = ["Первое совпадение по порядку правил."]
        for condition, address, label in (
            (self.source, flow.source, "источника"),
            (self.destination, flow.destination, "назначения"),
        ):
            if isinstance(condition, NetworkGroup):
                details.append(condition.match_text(address, label))
        return True, " ".join(details)


@dataclass(frozen=True)
class Acl:
    name: str
    rules: tuple[Rule, ...]


class _Tokens:
    def __init__(self, words, object_groups):
        self.words = words
        self.object_groups = object_groups
        self.position = 0

    def peek(self):
        return self.words[self.position].lower() if self.position < len(self.words) else ""

    def take(self):
        if self.position >= len(self.words):
            raise InvalidNetworkInput("Неполное правило.")
        word = self.words[self.position].lower()
        self.position += 1
        return word

    def address(self, *, standard=False):
        word = self.take()
        if word == "object-group":
            if standard:
                raise InvalidNetworkInput("IP-группы поддерживаются в extended ACL.")
            name = self.words[self.position] if self.position < len(self.words) else "?"
            self.take()
            if name not in self.object_groups:
                raise InvalidNetworkInput(
                    f"Не задан состав object-group '{name}'. "
                    f"Получить состав на Cisco: show object-group {name}. "
                    "Откройте «IP-группы» и вставьте определение группы с её адресами."
                )
            return self.object_groups[name]
        if word == "any":
            return AddressCondition()
        if word == "host":
            return AddressCondition(int(ipv4_address(self.take())), 0)
        address = int(ipv4_address(word))
        if standard and (not self.peek() or self.peek() in ("log", "log-input")):
            return AddressCondition(address, 0)
        return AddressCondition(address, int(ipv4_address(self.take())))

    def port(self):
        if self.peek() not in OPERATORS:
            return None
        operator = self.take()
        first = port_number(self.take())
        last = port_number(self.take()) if operator == "range" else 0
        if operator == "range" and first > last:
            raise InvalidNetworkInput("Начало диапазона портов больше конца.")
        return PortCondition(operator, first, last)


def _kind_for_number(name):
    if not name.isascii() or not name.isdigit():
        return None
    if len(name) > 4:
        raise InvalidNetworkInput("Недопустимый номер IPv4 ACL.")
    number = int(name)
    if 1 <= number <= 99 or 1300 <= number <= 1999:
        return "standard"
    if 100 <= number <= 199 or 2000 <= number <= 2699:
        return "extended"
    raise InvalidNetworkInput("Номер IPv4 ACL должен быть 1-99, 100-199, 1300-1999 или 2000-2699.")


def parse_acl(value: str, *, object_groups: dict[str, NetworkGroup] | None = None) -> Acl:
    if len(value.encode("utf-8")) > 1_000_000 or len(value.splitlines()) > 10000:
        raise InvalidNetworkInput("Допускается до 10000 строк и 1 МБ текста ACL.")
    rules, sequences = [], set()
    name, kind = "", None
    numbered = set()
    for line, raw in enumerate(value.splitlines(), 1):
        text = raw.strip()
        if not text or text.startswith(("!", "#")) or text.lower() in ("exit", "end"):
            continue
        text = COUNTER.sub("", text)
        words = text.split()
        try:
            config = re.fullmatch(r"ip access-list (standard|extended) (\S+)", text, re.I)
            shown = re.fullmatch(r"(Standard|Extended) IP access list (\S+)", text, re.I)
            header = config or shown
            if header:
                new_kind, new_name = header.group(1).lower(), header.group(2)
                if name and name != new_name or kind and kind != new_kind:
                    raise InvalidNetworkInput("В одно поле вставляйте один список ACL.")
                if rules and not name:
                    raise InvalidNetworkInput("Заголовок ACL должен предшествовать правилам.")
                name, kind = new_name, new_kind
                expected = _kind_for_number(name)
                if expected and expected != kind:
                    raise InvalidNetworkInput("Тип ACL не соответствует его номеру.")
                continue
            if words[0].lower() == "access-list":
                if len(words) < 3:
                    raise InvalidNetworkInput("Неполное правило access-list.")
                new_name = words[1]
                if name and new_name != name:
                    raise InvalidNetworkInput("В одно поле вставляйте один список ACL.")
                name = new_name
                new_kind = _kind_for_number(name)
                if kind and new_kind and new_kind != kind:
                    raise InvalidNetworkInput("Тип ACL не соответствует его номеру.")
                kind = kind or new_kind
                words = words[2:]
            sequence = None
            if words[0].isascii() and words[0].isdigit():
                if len(words[0]) > 10:
                    raise InvalidNetworkInput("Недопустимый sequence number.")
                sequence = int(words.pop(0))
                if not 1 <= sequence <= 2147483647 or sequence in sequences:
                    raise InvalidNetworkInput("Недопустимый или повторяющийся sequence number.")
                sequences.add(sequence)
            if not words:
                raise InvalidNetworkInput("Неполное правило.")
            if words[0].lower() == "remark":
                continue
            tokens = _Tokens(words, object_groups or {})
            action = tokens.take()
            if action not in ("permit", "deny"):
                raise InvalidNetworkInput(
                    "Ожидается permit/deny; неподдерживаемые команды не пропускаются."
                )
            inferred = (
                "extended"
                if tokens.peek() in ("ip", "object-group")
                or tokens.peek() in PROTOCOLS
                or tokens.peek().isdigit()
                else "standard"
            )
            rule_kind = kind or inferred
            if kind is None:
                kind = rule_kind
            protocol = None
            if rule_kind == "extended":
                proto = tokens.take()
                if proto == "object-group":
                    raise InvalidNetworkInput(
                        "Группы сервисов/протоколов не поддерживаются; IP-группы задаются вместо адреса."
                    )
                if proto != "ip":
                    protocol = PROTOCOLS.get(proto)
                    if protocol is None:
                        if not re.fullmatch(r"[0-9]{1,3}", proto) or int(proto) > 255:
                            raise InvalidNetworkInput(f"Неподдерживаемый IP-протокол '{proto}'.")
                        protocol = int(proto)
            source = tokens.address(standard=rule_kind == "standard")
            source_port = tokens.port() if protocol in (6, 17) else None
            destination = tokens.address() if rule_kind == "extended" else AddressCondition()
            destination_port = tokens.port() if protocol in (6, 17) else None
            if protocol == 1 and tokens.peek() not in ("", "log", "log-input"):
                icmp = tokens.take()
                if icmp not in ICMP_NAMES:
                    if not re.fullmatch(r"[0-9]{1,3}", icmp) or int(icmp) > 255:
                        raise InvalidNetworkInput("Неподдерживаемый ICMP type.")
                    if re.fullmatch(r"[0-9]{1,3}", tokens.peek()):
                        if int(tokens.take()) > 255:
                            raise InvalidNetworkInput("ICMP code должен быть 0-255.")
            established = False
            if tokens.peek() == "established":
                if protocol != 6:
                    raise InvalidNetworkInput("established допустим только для TCP.")
                tokens.take()
                established = True
            if tokens.peek() in ("log", "log-input"):
                tokens.take()
            if tokens.peek():
                raise InvalidNetworkInput(
                    f"Неподдерживаемое условие '{tokens.peek()}'; результат не вычисляется."
                )
            numbered.add(sequence is not None)
            if len(numbered) > 1:
                raise InvalidNetworkInput("Не смешивайте правила с sequence number и без него.")
            rules.append(
                Rule(
                    action,
                    protocol,
                    source,
                    destination,
                    source_port,
                    destination_port,
                    established,
                    line,
                    sequence,
                    text,
                )
            )
        except (InvalidNetworkInput, IndexError) as error:
            raise AclSyntaxError(line, text, error) from None
    if not rules:
        raise InvalidNetworkInput("Вставьте ACL с хотя бы одним правилом permit/deny.")
    if True in numbered:
        rules.sort(key=lambda rule: rule.sequence)
    return Acl(name, tuple(rules))


@dataclass(frozen=True)
class Decision:
    allowed: bool | None
    rule: Rule | None
    reason: str

    def text(self):
        title = {True: "РАЗРЕШЁН", False: "БЛОКИРУЕТСЯ", None: "НЕДОСТАТОЧНО ДАННЫХ"}[self.allowed]
        if self.rule is None:
            return f"{title}: {self.reason}"
        label = f"sequence {self.rule.sequence}, " if self.rule.sequence is not None else ""
        return f"{title}: {label}строка {self.rule.line}\n  {self.rule.original}\n  {self.reason}"


def evaluate_acl(acl: Acl, flow: Flow) -> Decision:
    for rule in acl.rules:
        matches, reason = rule.match(flow)
        if matches is None:
            return Decision(None, rule, reason + " Первое совпадение пока нельзя определить.")
        if matches:
            return Decision(rule.action == "permit", rule, reason)
    return Decision(False, None, "Неявный deny: ни одно правило не совпало.")


def check_conversation(
    forward_value: str,
    reverse_value: str,
    flow: Flow,
    *,
    forward_absent=False,
    reverse_absent=False,
    object_group_value="",
) -> str:
    active_values = ([] if forward_absent else [forward_value]) + (
        [] if reverse_absent else [reverse_value]
    )
    groups = (
        parse_object_groups(object_group_value)
        if any(re.search(r"\bobject-group\b", value, re.I) for value in active_values)
        else {}
    )

    def parse_side(value, side):
        try:
            return parse_acl(value, object_groups=groups)
        except AclSyntaxError as error:
            raise AclSyntaxError(error.line, error.rule, error.detail, side) from None
        except InvalidNetworkInput as error:
            prefix = ("ACL запроса", "ACL ответа")[side]
            raise InvalidNetworkInput(f"{prefix}: {error}") from None

    forward_acl = None if forward_absent else parse_side(forward_value, 0)
    reverse_acl = (
        None if reverse_absent or not reverse_value.strip() else parse_side(reverse_value, 1)
    )
    request = (
        Decision(True, None, "ACL запроса явно не назначена; этот фильтр не ограничивает запрос.")
        if forward_absent
        else evaluate_acl(forward_acl, flow)
    )
    lines = [f"Запрос: {flow.text()}", request.text(), ""]
    if reverse_acl is None and not reverse_absent:
        lines.append("Ответ: ACL не задан, обратный поток не проверен.")
        lines.append(
            "Вывод: ACL запроса не назначена; обратный поток не проверен."
            if forward_absent
            else {
                True: "Вывод: запрос разрешён указанной ACL.",
                False: "Вывод: запрос блокируется указанной ACL.",
                None: "Вывод: для проверки запроса недостаточно данных.",
            }[request.allowed]
        )
    else:
        reply = flow.reverse()
        response = (
            Decision(True, None, "ACL ответа явно не назначена; этот фильтр не ограничивает ответ.")
            if reverse_absent
            else evaluate_acl(reverse_acl, reply)
        )
        lines.extend([f"Ответ: {reply.text()}", response.text(), ""])
        if request.allowed is False or response.allowed is False:
            lines.append("Вывод: указанные ACL блокируют запрос или ответ.")
        elif forward_absent and reverse_absent:
            lines.append("Вывод: ACL в обоих направлениях не назначены.")
        elif request.allowed is True and response.allowed is True:
            lines.append("Вывод: запрос и ответ разрешены указанными ACL.")
        else:
            lines.append("Вывод: для двусторонней проверки недостаточно данных.")
    lines.append(
        "Проверены только эти ACL: без NAT, маршрутизации, stateful firewall и фрагментов. "
        "TCP-ответ моделируется с ACK=1; established не является отслеживанием соединения."
    )
    return "\n".join(lines)
