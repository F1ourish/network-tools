"""Offline SCCP CUCME inventory, relationship lookup and bounded free-number pages."""

from bisect import bisect_right
from dataclasses import dataclass, field
import re
from textwrap import dedent

from .mac import InvalidMacAddress, format_mac
from .network import InvalidNetworkInput

MAX_CONFIG_CHARS = 2 * 1024 * 1024
MAX_CONFIG_LINES = 30000
MAX_TAG = 1000000
MAX_LINKS = 100000
COPY_LIMIT = 10000
SEARCH_KINDS = {
    "Любое поле": "all",
    "ephone ID": "ephone",
    "ephone-dn ID": "dn",
    "Телефон": "number",
    "Имя / label": "name",
}
FREE_KINDS = {"ephone-dn ID": "dn", "ephone ID": "ephone", "Телефонные номера": "number"}
_HEADER = re.compile(r"(ephone-dn|ephone)\s+([0-9]+)(?:\s+(dual-line|octo-line))?", re.I)
_PROMPT = re.compile(r"^\S+(?:\([^)]*\))?[>#]\s*")
_BUTTON = re.compile(r"([0-9]+)([:bcfmoswx])([0-9]+(?:,[0-9]+)*)", re.I)
_PHONE_TOKEN = re.compile(r"(?<![\w])\+?[0-9]+(?![\w])")


class CMESyntaxError(InvalidNetworkInput):
    def __init__(self, line: int, detail: str):
        self.line = line
        super().__init__(f"CUCME, строка {line}: {detail}")


def _tag(value: str, line: int) -> int:
    if not re.fullmatch(r"[0-9]{1,7}", value) or not 1 <= int(value) <= MAX_TAG:
        raise CMESyntaxError(
            line, "ID должен быть целым от 1 до 1000000 (лимит обработки, не ёмкость CME)."
        )
    return int(value)


@dataclass(frozen=True)
class Button:
    position: int
    mode: str
    targets: tuple[int, ...]
    line: int

    @property
    def text(self) -> str:
        return f"{self.position}{self.mode}" + ",".join(map(str, self.targets))


@dataclass
class DirectoryNumber:
    tag: int
    line: int
    mode: str = ""
    number: str = ""
    secondary: str = ""
    description: str = ""
    name: str = ""
    label: str = ""


@dataclass
class Phone:
    tag: int
    line: int
    description: str = ""
    model: str = ""
    mac: str = ""
    buttons: dict[int, Button] = field(default_factory=dict)


@dataclass(frozen=True)
class Link:
    phone: int | None
    dn: int | None
    button: Button | None = None


@dataclass(frozen=True)
class CMEConfig:
    dns: dict[int, DirectoryNumber]
    phones: dict[int, Phone]
    links: tuple[Link, ...]
    warnings: tuple[str, ...]
    referenced_dns: frozenset[int]
    max_dn: int | None
    max_ephones: int | None
    has_sip: bool
    has_templates: bool

    def summary(self) -> str:
        limits = f"max-dn: {self.max_dn if self.max_dn is not None else '?'}; max-ephones (кол-во): {self.max_ephones if self.max_ephones is not None else '?'}"
        return f"ephone-dn: {len(self.dns)}; ephone: {len(self.phones)}; замечаний: {len(self.warnings)}. {limits}."


def _buttons(value: str, line: int) -> tuple[Button, ...]:
    result = []
    for token in value.split():
        match = _BUTTON.fullmatch(token)
        if not match:
            raise CMESyntaxError(line, "неверный button. Примеры: 1:85 2:86; 1o85,86; 2x1.")
        position, mode, targets = match.groups()
        ids = tuple(_tag(item, line) for item in targets.split(","))
        if len(ids) > 25 or (len(ids) > 1 and mode.lower() not in ("o", "c")):
            raise CMESyntaxError(line, "список DN допустим только для o/c, не более 25 ID.")
        result.append(Button(_tag(position, line), mode.lower(), tuple(dict.fromkeys(ids)), line))
    if not result:
        raise CMESyntaxError(line, "после button требуется привязка кнопки.")
    return tuple(result)


def _numbers(value: str, line: int) -> tuple[str, str]:
    tokens = value.split()
    if not tokens or not re.fullmatch(r"[A-Za-z0-9+*.#-]{1,32}", tokens[0]):
        raise CMESyntaxError(line, "неверное значение number.")
    primary, secondary, index = tokens[0], "", 1
    if index < len(tokens) and tokens[index].lower() == "secondary":
        if index + 1 == len(tokens) or not re.fullmatch(
            r"[A-Za-z0-9+*.#-]{1,32}", tokens[index + 1]
        ):
            raise CMESyntaxError(line, "после secondary требуется номер.")
        secondary, index = tokens[index + 1], index + 2
    if tokens[index:] and [token.lower() for token in tokens[index:]] not in (
        ["no-reg"],
        ["no-reg", "both"],
        ["no-reg", "primary"],
    ):
        raise CMESyntaxError(
            line, "неподдерживаемые параметры number; поддерживаются secondary и no-reg."
        )
    return primary, secondary


def parse_config(value: str) -> CMEConfig:
    if len(value) > MAX_CONFIG_CHARS:
        raise InvalidNetworkInput("CUCME: допускается не более 2 МБ текста.")
    lines = dedent(value).splitlines()
    if len(lines) > MAX_CONFIG_LINES:
        raise InvalidNetworkInput("CUCME: допускается не более 30000 строк.")
    dns, phones, warnings = {}, {}, []
    current, context, max_dn, max_ephones = None, "", None, None
    has_sip = has_templates = False
    for line, raw in enumerate(lines, 1):
        text = _PROMPT.sub("", raw.strip())
        if "--More--" in text:
            raise CMESyntaxError(
                line, "вставьте полный вывод без маркеров постраничного просмотра --More--."
            )
        if not text or text.startswith("!") or text in ("exit", "end"):
            if text:
                current, context = None, ""
            continue
        header = _HEADER.fullmatch(text)
        if header:
            kind, token, mode = header.groups()
            tag = _tag(token, line)
            collection = dns if kind.lower() == "ephone-dn" else phones
            if tag in collection:
                raise CMESyntaxError(
                    line, f"повторная секция {kind} {tag}; первая в строке {collection[tag].line}."
                )
            if kind.lower() == "ephone" and mode:
                raise CMESyntaxError(line, "dual-line/octo-line относятся к ephone-dn.")
            current = (
                DirectoryNumber(tag, line, mode or "") if collection is dns else Phone(tag, line)
            )
            collection[tag], context = current, kind.lower()
            continue
        if re.match(r"(?:no\s+)?ephone(?:-dn)?(?:\s|$)", text, re.I):
            raise CMESyntaxError(
                line, "неверный заголовок ephone/ephone-dn; требуется снимок show running-config."
            )
        if text == "telephony-service":
            current, context = None, "telephony-service"
            continue
        if text.startswith("voice register "):
            has_sip = True
            current, context = None, ""
            continue
        if text.startswith(("ephone-template ", "ephone-dn-template ")):
            has_templates = True
            if current is None or not raw[:1].isspace():
                current, context = None, ""
            continue
        parts = text.split(None, 1)
        command, argument = parts[0].lower(), parts[1].strip() if len(parts) > 1 else ""
        if context == "telephony-service" and command in ("max-dn", "max-ephones"):
            token = argument.split()[0] if argument else ""
            if not re.fullmatch(r"[0-9]{1,7}", token) or int(token) > MAX_TAG:
                raise CMESyntaxError(line, "неверный max-dn/max-ephones.")
            if command == "max-dn":
                max_dn = int(token)
            else:
                max_ephones = int(token)
        elif isinstance(current, DirectoryNumber):
            if command in ("name", "label", "description"):
                setattr(current, command, argument)
            elif command == "number":
                current.number, current.secondary = _numbers(argument, line)
            elif text == "no number":
                current.number = current.secondary = ""
            elif text in ("no name", "no label", "no description"):
                setattr(current, text[3:], "")
            elif not raw[:1].isspace() and command not in (
                "call-forward",
                "pickup-group",
                "preference",
                "no",
                "conference",
                "huntstop",
                "mwi",
                "intercom",
                "paging",
                "call-waiting",
                "translation-profile",
            ):
                current, context = None, ""
        elif isinstance(current, Phone):
            if command == "description":
                current.description = argument
            elif command == "type":
                current.model = argument
            elif command == "mac-address":
                try:
                    current.mac = format_mac(argument, "cisco", uppercase=True)
                except InvalidMacAddress:
                    raise CMESyntaxError(
                        line, "mac-address должен содержать 12 hex-цифр."
                    ) from None
            elif command == "button":
                for button in _buttons(argument, line):
                    if button.position in current.buttons:
                        raise CMESyntaxError(
                            line, f"кнопка {button.position} уже задана для ephone {current.tag}."
                        )
                    current.buttons[button.position] = button
            elif text == "no button":
                current.buttons.clear()
            elif text.startswith("no button "):
                for button in _buttons(text[10:], line):
                    current.buttons.pop(button.position, None)
            elif text in ("no description", "no mac-address", "no type"):
                setattr(
                    current,
                    {"no description": "description", "no mac-address": "mac", "no type": "model"}[
                        text
                    ],
                    "",
                )
            elif not raw[:1].isspace() and command not in (
                "device-security-mode",
                "max-calls-per-button",
                "auto-line",
                "speed-dial",
                "headset",
                "no",
                "codec",
                "keepalive",
                "restart",
                "reset",
            ):
                current, context = None, ""
        elif not raw[:1].isspace() and command not in ("max-dn", "max-ephones"):
            context = ""
    if not dns and not phones:
        raise InvalidNetworkInput(
            "В конфиге нет секций ephone/ephone-dn. Вставьте show running-config или полный раздел."
        )
    links, referenced = [], set()
    for phone in sorted(phones.values(), key=lambda item: item.tag):
        if not phone.buttons:
            links.append(Link(phone.tag, None))
        for button in sorted(phone.buttons.values(), key=lambda item: item.position):
            target, seen = button, set()
            while target.mode == "x":
                if target.position in seen or target.targets[0] not in phone.buttons:
                    raise CMESyntaxError(
                        button.line,
                        f"button {button.text}: отсутствует исходная overlay-кнопка или обнаружен цикл.",
                    )
                seen.add(target.position)
                target = phone.buttons[target.targets[0]]
            if button.mode == "x" and target.mode != "o":
                raise CMESyntaxError(button.line, "x ссылается на overlay-кнопку o, а не на DN.")
            for dn in target.targets:
                links.append(Link(phone.tag, dn, button))
                referenced.add(dn)
                if len(links) > MAX_LINKS:
                    raise InvalidNetworkInput("CUCME: более 100000 связей button/DN.")
        if not phone.mac or not phone.model:
            warnings.append(f"ephone {phone.tag}: MAC или type не указаны; ID занят.")
    for dn in sorted(dns.values(), key=lambda item: item.tag):
        if dn.tag not in referenced:
            links.append(Link(None, dn.tag))
        if not dn.number:
            warnings.append(f"ephone-dn {dn.tag}: нет number; секция существует, ID занят.")
        tokens = _PHONE_TOKEN.findall(dn.description)
        if dn.number and tokens and dn.number not in tokens:
            warnings.append(
                f"ephone-dn {dn.tag}: number и description различаются; показаны оба поля."
            )
    for tag in sorted(referenced - dns.keys()):
        warnings.append(
            f"ephone-dn {tag} упомянут в button, но секция не предоставлена; ID исключён из свободных."
        )
    if has_sip or has_templates:
        warnings.append(
            "SIP voice register/шаблоны не разворачиваются; показаны прямые SCCP-связи. Соответствующие свободные ресурсы блокируются."
        )
    if max_dn is not None and any(tag > max_dn for tag in dns.keys() | referenced):
        warnings.append("ID DN превышает max-dn: проверить полноту и актуальность конфига.")
    return CMEConfig(
        dns,
        phones,
        tuple(links),
        tuple(warnings),
        frozenset(referenced),
        max_dn,
        max_ephones,
        has_sip,
        has_templates,
    )


def _number_matches(dn: DirectoryNumber | None, query: str) -> bool:
    return dn is not None and query.casefold() in {
        dn.number.casefold(),
        dn.secondary.casefold(),
        *(token.casefold() for token in _PHONE_TOKEN.findall(dn.description)),
    }


def find_links(config: CMEConfig, query: str, kind: str = "all") -> tuple[Link, ...]:
    text = " ".join(query.split())
    if not text or len(text) > 256:
        raise InvalidNetworkInput("Введите запрос длиной от 1 до 256 символов.")
    if kind not in SEARCH_KINDS.values():
        raise InvalidNetworkInput("Выберите поле поиска CUCME.")
    numeric = int(text) if re.fullmatch(r"[0-9]{1,16}", text) else None
    if kind in ("ephone", "dn"):
        if numeric is None or not 1 <= numeric <= MAX_TAG:
            raise InvalidNetworkInput("Для поиска ID ввести целое от 1 до 1000000.")
    result = []
    for link in config.links:
        phone, dn = config.phones.get(link.phone), config.dns.get(link.dn)
        names = " ".join(
            (phone.description if phone else "", dn.name if dn else "", dn.label if dn else "")
        ).casefold()
        matches_name = all(part in names for part in text.casefold().split())
        matches_number = _number_matches(dn, text)
        if (
            (kind == "ephone" and link.phone == numeric)
            or (kind == "dn" and link.dn == numeric)
            or (kind == "number" and matches_number)
            or (kind == "name" and matches_name)
            or (
                kind == "all"
                and (
                    (numeric is not None and numeric in (link.phone, link.dn))
                    or matches_number
                    or (numeric is None and matches_name)
                )
            )
        ):
            result.append(link)
    return tuple(result)


def _notes(config: CMEConfig) -> list[str]:
    if not config.warnings:
        return []
    return ["", f"Замечания: {len(config.warnings)} (первые 20)", *config.warnings[:20]]


def lookup_report(
    config: CMEConfig, query: str, kind: str = "all", page: int = 0
) -> tuple[str, int]:
    links = find_links(config, query, kind)
    pages = max(1, (len(links) + 9) // 10)
    if type(page) is not int or not 0 <= page < pages:
        raise InvalidNetworkInput(f"Номер страницы должен быть от 1 до {pages}.")
    lines = [f"Связей найдено: {len(links)}. Страница {page + 1} / {pages}."]
    if not links:
        lines.append(
            "Совпадений нет во вставленном конфиге. Отсутствие во фрагменте не подтверждает свободу ресурса."
        )
    for link in links[page * 10 : (page + 1) * 10]:
        phone, dn = config.phones.get(link.phone), config.dns.get(link.dn)
        lines.append("")
        if phone:
            lines += [
                f"ephone {phone.tag}: ЗАНЯТ - {phone.description or 'без description'}",
                f"type: {phone.model or '-'}; MAC: {phone.mac or '-'}; строка {phone.line}",
            ]
        else:
            lines.append("ephone: привязка в предоставленном конфиге отсутствует.")
        if link.button:
            lines.append(
                f"button {link.button.text} -> ephone-dn {link.dn}"
                + (" (x: ссылка на overlay-кнопку)" if link.button.mode == "x" else "")
            )
        elif phone:
            lines.append("button: не указан; ephone ID остаётся занятым.")
        if dn:
            lines += [
                f"ephone-dn {dn.tag}: ЗАНЯТ; строка {dn.line}; {dn.mode or 'single-line'}",
                f"description DN (телефон): {dn.description or '-'}",
                f"number: {dn.number or '-'}; secondary: {dn.secondary or '-'}",
                f"name: {dn.name or '-'}; label: {dn.label or '-'}",
            ]
        elif link.dn is not None:
            lines.append(
                f"ephone-dn {link.dn}: упомянут в button; секция не предоставлена, ID не свободен."
            )
    lines += _notes(config)
    lines += [
        "",
        "Поиск по предоставленному снимку; регистрация телефона и фактическая занятость линии не проверяются.",
    ]
    return "\n".join(lines), pages


@dataclass(frozen=True)
class FreeNumbers:
    kind: str
    first: int
    last: int
    width: int
    intervals: tuple[tuple[int, int], ...]
    cumulative: tuple[int, ...]

    @property
    def total(self) -> int:
        return self.cumulative[-1] if self.cumulative else 0

    def page(self, page: int = 0, size: int = 100) -> tuple[tuple[str, ...], int]:
        if type(size) is not int or not 1 <= size <= 1000:
            raise InvalidNetworkInput("Размер страницы должен быть от 1 до 1000.")
        pages = max(1, (self.total + size - 1) // size)
        if type(page) is not int or not 0 <= page < pages:
            raise InvalidNetworkInput(f"Номер страницы должен быть от 1 до {pages}.")
        values = []
        for index in range(page * size, min(self.total, (page + 1) * size)):
            segment = bisect_right(self.cumulative, index)
            offset = index - (self.cumulative[segment - 1] if segment else 0)
            values.append(str(self.intervals[segment][0] + offset).zfill(self.width))
        return tuple(values), pages

    def all_numbers(self) -> tuple[str, ...]:
        if self.total > COPY_LIMIT:
            raise InvalidNetworkInput(
                "Весь список копируется до 10000 номеров; используйте страницы."
            )
        return tuple(
            value
            for page in range(max(1, (self.total + 999) // 1000))
            for value in self.page(page, 1000)[0]
        )


def free_numbers(config: CMEConfig, kind: str, first: str, last: str) -> FreeNumbers:
    if kind not in FREE_KINDS.values():
        raise InvalidNetworkInput("Выберите тип свободных номеров.")
    start, end = first.strip(), last.strip()
    if not re.fullmatch(r"[0-9]{1,16}", start) or not re.fullmatch(r"[0-9]{1,16}", end):
        raise InvalidNetworkInput("Границы диапазона: от 1 до 16 цифр.")
    low, high = int(start), int(end)
    if low > high:
        raise InvalidNetworkInput("Начало диапазона должно быть не больше конца.")
    padded = (len(start) > 1 and start.startswith("0")) or (len(end) > 1 and end.startswith("0"))
    if padded and len(start) != len(end):
        raise InvalidNetworkInput(
            "Для номеров с ведущими нулями длина обеих границ должна совпадать."
        )
    width = len(start) if padded else 0
    if kind in ("dn", "ephone"):
        if low < 1 or high > MAX_TAG:
            raise InvalidNetworkInput("Диапазон ID должен быть от 1 до 1000000 (лимит обработки).")
        maximum = config.max_dn if kind == "dn" else None
        if maximum is not None and high > maximum:
            raise InvalidNetworkInput(
                f"Конец диапазона превышает max-{'dn' if kind == 'dn' else 'ephones'} {maximum} из telephony-service."
            )
        occupied = (
            config.dns.keys() | config.referenced_dns if kind == "dn" else config.phones.keys()
        )
    else:
        if any("." in number for dn in config.dns.values() for number in (dn.number, dn.secondary)):
            raise InvalidNetworkInput(
                "В number есть шаблоны с точкой. Свободные телефонные номера без раскрытия шаблонов не определяются."
            )
        numbers = {
            token
            for dn in config.dns.values()
            for token in (dn.number, dn.secondary, *_PHONE_TOKEN.findall(dn.description))
        }
        numbers = {token.removeprefix("+") for token in numbers}
        occupied = {
            int(token)
            for token in numbers
            if re.fullmatch(r"[0-9]{1,16}", token) and str(int(token)).zfill(width) == token
        }
    if (kind == "dn" and config.has_templates) or (
        kind == "number" and (config.has_templates or config.has_sip)
    ):
        raise InvalidNetworkInput(
            "Найдены SIP voice register/ephone-template: неполная модель не позволяет определить свободные DN/номера. Поиск прямых SCCP-связей доступен."
        )
    intervals, cumulative, total, current = [], [], 0, low
    for number in [*sorted(value for value in occupied if low <= value <= high), high + 1]:
        if current < number:
            intervals.append((current, number - 1))
            total += number - current
            cumulative.append(total)
        current = number + 1
    return FreeNumbers(kind, low, high, width, tuple(intervals), tuple(cumulative))


def free_report(config: CMEConfig, result: FreeNumbers, page: int = 0) -> tuple[str, int]:
    values, pages = result.page(page)
    label = next(label for label, kind in FREE_KINDS.items() if kind == result.kind)
    if result.kind == "number":
        label = label.lower()
    first, last = str(result.first).zfill(result.width), str(result.last).zfill(result.width)
    lines = [
        f"Свободные {label}: {result.total}. Диапазон {first}-{last}.",
        f"Страница {page + 1} / {pages}.",
        "Нет секции/резерва во вставленном конфиге; отсутствующий button не освобождает созданный DN.",
        "Телефоны: учитываются number, secondary и цифровые значения description DN.",
        "max-ephones ограничивает количество аппаратов; границы ephone ID проверяются по платформе.",
        "",
        *values,
        *_notes(config),
        "",
        "Перед назначением сверить полный актуальный конфиг и ограничения платформы.",
    ]
    return "\n".join(lines), pages
