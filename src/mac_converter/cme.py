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
    "Номер ephone": "ephone",
    "Номер ephone-dn": "dn",
    "Телефон": "number",
    "Имя / label": "name",
}
FREE_KINDS = {"Номера ephone-dn": "dn", "Номера ephone": "ephone", "Телефонные номера": "number"}
_HEADER = re.compile(r"(ephone-dn|ephone)\s+([0-9]+)(?:\s+(dual-line|octo-line))?", re.I)
_PROMPT = re.compile(r"^\S+(?:\([^)]*\))?[>#]\s*")
_BUTTON = re.compile(r"([0-9]+)([:bcfmoswx])([0-9]+(?:,[0-9]+)*)", re.I)
_PHONE_TOKEN = re.compile(r"(?<![\w])\+?[0-9]+(?![\w])")
PAIR_RESOURCE = "ephone / ephone-dn"
RESOURCE_KINDS = (PAIR_RESOURCE, "Телефонные номера")


class CMESyntaxError(InvalidNetworkInput):
    def __init__(self, line: int, detail: str):
        self.line = line
        super().__init__(f"CUCME, строка {line}: {detail}")


def _tag(value: str, line: int) -> int:
    if not re.fullmatch(r"[0-9]{1,7}", value) or not 1 <= int(value) <= MAX_TAG:
        raise CMESyntaxError(
            line,
            "номер секции или кнопки должен быть целым от 1 до 1000000 (лимит обработки, не ёмкость CME).",
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
    template: int | None = None
    forwarding: dict[str, "CallForward | None"] = field(default_factory=dict)
    effective_forwarding: tuple["CallForward", ...] = ()
    forwarding_incomplete: bool = False
    forwarding_clear: bool = False


@dataclass(frozen=True)
class CallForward:
    kind: str
    argument: str
    line: int
    template: int | None = None

    def text(self) -> str:
        label = {
            "all": "Все вызовы",
            "busy": "Если занято",
            "noan": "Если нет ответа",
            "night-service": "В ночном режиме",
        }.get(self.kind, "Дополнительная настройка")
        source = f"; шаблон ephone-dn-template {self.template}" if self.template is not None else ""
        return f"{label} ({self.kind}): {self.argument}{source}; строка {self.line}"


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
    limitations: tuple[str, ...] = ()

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
            raise CMESyntaxError(
                line, "список номеров ephone-dn допустим только для o/c, не более 25."
            )
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
    dns, phones, warnings, templates, limitations = {}, {}, [], {}, []
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
            limitations.append(f"{text} (строка {line})")
            current, context = None, ""
            continue
        if text.startswith(("ephone-template ", "ephone-dn-template ")):
            has_templates = True
            limitations.append(f"{text} (строка {line})")
            token = text.split()[-1]
            if text.startswith("ephone-dn-template "):
                tag = _tag(token, line)
                if (
                    isinstance(current, DirectoryNumber)
                    and context == "ephone-dn"
                    and raw[:1].isspace()
                ):
                    current.template = tag
                elif not raw[:1].isspace():
                    if tag in templates:
                        raise CMESyntaxError(line, f"повторный ephone-dn-template {tag}.")
                    current = DirectoryNumber(tag, line)
                    templates[tag], context = current, "ephone-dn-template"
                continue
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
            elif (
                command == "call-forward"
                or text == "no call-forward"
                or text.startswith("no call-forward ")
            ):
                removed = command == "no"
                args = (text[16:] if removed else argument).split(None, 1)
                if not args:
                    if removed:
                        current.forwarding.clear()
                        current.forwarding_clear = True
                    else:
                        raise CMESyntaxError(line, "после call-forward требуется условие и номер.")
                else:
                    kind = args[0].lower()
                    if not removed and len(args) < 2:
                        raise CMESyntaxError(line, f"после call-forward {kind} требуется значение.")
                    current.forwarding[kind] = (
                        None
                        if removed
                        else CallForward(
                            kind,
                            args[1],
                            line,
                            current.tag if context == "ephone-dn-template" else None,
                        )
                    )
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
            missing = []
            if not phone.mac:
                missing.append("MAC-адрес (mac-address)")
            if not phone.model:
                missing.append("модель телефона (type)")
            warnings.append(
                f"ephone {phone.tag} существует в конфигурации (строка {phone.line}).\n"
                f"Описание (description): {phone.description or 'не указано'}.\n"
                f"Не заполнены поля: {', '.join(missing)}.\n"
                f"Номер секции ephone {phone.tag} исключён из списка свободных."
            )
    for dn in sorted(dns.values(), key=lambda item: item.tag):
        inherited = {}
        if dn.template is not None:
            template = templates.get(dn.template)
            if template is None:
                dn.forwarding_incomplete = True
                warnings.append(
                    f"ephone-dn {dn.tag}: указан ephone-dn-template {dn.template}, но его содержимое не предоставлено.\n"
                    "Добавьте секцию шаблона из show running-config, чтобы увидеть его переадресации."
                )
            else:
                if not dn.forwarding_clear:
                    inherited.update(template.forwarding)
        inherited.update(dn.forwarding)
        dn.effective_forwarding = tuple(value for value in inherited.values() if value is not None)
        if dn.tag not in referenced:
            links.append(Link(None, dn.tag))
        if not dn.number:
            warnings.append(
                f"ephone-dn {dn.tag} существует в конфигурации (строка {dn.line}).\n"
                f"Описание (description): {dn.description or 'не указано'}.\n"
                "Телефонный номер (number) не задан.\n"
                f"Номер секции ephone-dn {dn.tag} исключён из списка свободных."
            )
        tokens = _PHONE_TOKEN.findall(dn.description)
        if dn.number and tokens and dn.number not in tokens:
            warnings.append(
                f"ephone-dn {dn.tag} (строка {dn.line}): номер в описании отличается от назначенного.\n"
                f"Телефонный номер (number): {dn.number}.\n"
                f"Описание (description): {dn.description}.\n"
                "number задаёт телефонный номер, description - произвольное описание. "
                "Различие само по себе не означает ошибку конфигурации."
            )
    for tag in sorted(referenced - dns.keys()):
        warnings.append(
            f"ephone-dn {tag}: есть ссылка из button, но сама секция отсутствует во вставленном конфиге.\n"
            f"Номер секции ephone-dn {tag} исключён из списка свободных до проверки полного конфига."
        )
    if has_sip or has_templates:
        warnings.append(
            "Обнаружены SIP-разделы или шаблоны. Это ограничение анализа, а не ошибка Cisco-конфига.\n"
            "Таблица номеров секций ephone/ephone-dn доступна: учитываются явные секции SCCP и ссылки button.\n"
            "Переадресации из предоставленных ephone-dn-template учитываются; прочие поля шаблонов и SIP-номера не разворачиваются.\n"
            "Общий поиск свободных телефонных номеров недоступен, чтобы не предложить неучтённый SIP/шаблонный номер.\n"
            "Где обнаружено: "
            + "; ".join(limitations[:8])
            + (f"; и ещё {len(limitations) - 8}" if len(limitations) > 8 else "")
        )
    if max_dn is not None and any(tag > max_dn for tag in dns.keys() | referenced):
        warnings.append(
            "Номер секции ephone-dn превышает max-dn: проверить полноту и актуальность конфига."
        )
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
        tuple(limitations),
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
            raise InvalidNetworkInput("Для поиска номера секции ввести целое от 1 до 1000000.")
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
    lines = ["", f"Замечания по всей конфигурации: {len(config.warnings)}."]
    for index, warning in enumerate(config.warnings, 1):
        detail = warning.replace("\n", "\n   ")
        lines += ["", f"{index}. {detail}"]
    return lines


def diagnostics_report(config: CMEConfig | None, error: str = "", raw: str = "") -> str:
    lines = ["Замечания по конфигурации CUCME"]
    if error:
        lines += ["", "Не удалось выполнить выбранную операцию", error]
        match = re.search(r"CUCME, строка ([0-9]+):", error)
        if match:
            line = int(match[1])
            source = raw.splitlines()
            if 1 <= line <= len(source):
                lines += [f"Текст строки {line}: {source[line - 1][:240]}"]
            lines += [
                "Исправьте указанную строку или вставьте полный running-config. Строка подсвечена в редакторе."
            ]
        else:
            lines += [
                "Проверьте выбранный режим и границы диапазона. Сам конфиг сохранён в редакторе."
            ]
    if config is not None:
        lines += _notes(config)
        if not config.warnings and not error:
            lines += ["", "Замечаний по разобранным секциям не найдено."]
    elif not error:
        lines += ["", "Вставьте конфигурацию для проверки."]
    return "\n".join(lines)


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
                f"ephone {phone.tag}: существует в конфигурации (строка {phone.line})",
                f"Описание аппарата (description): {phone.description or 'не указано'}",
                f"Модель (type): {phone.model or 'не указана'}; MAC: {phone.mac or 'не указан'}",
            ]
        else:
            lines.append("ephone: привязка в предоставленном конфиге отсутствует.")
        if link.button:
            lines.append(
                f"button {link.button.text} -> ephone-dn {link.dn}"
                + (" (x: ссылка на overlay-кнопку)" if link.button.mode == "x" else "")
            )
        elif phone:
            lines.append("button: привязки к ephone-dn не указаны.")
        if dn:
            lines.append("")
            lines += [
                f"ephone-dn {dn.tag}: существует в конфигурации (строка {dn.line}; {dn.mode or 'single-line'})",
                f"Телефонный номер (number): {dn.number or 'не задан'}",
                f"Дополнительный номер (secondary): {dn.secondary or 'не задан'}",
                f"Описание (description): {dn.description or 'не указано'}",
                f"Имя (name): {dn.name or 'не указано'}; подпись (label): {dn.label or 'не указана'}",
            ]
            lines += ["Переадресации:"]
            if dn.effective_forwarding:
                lines += ["  " + item.text() for item in dn.effective_forwarding]
                lines += [
                    "  Значения timeout указаны в секундах; условия primary/secondary и dialplan-pattern сохранены."
                ]
            elif not dn.forwarding_incomplete:
                lines += ["  Не заданы во вставленном конфиге."]
            if dn.forwarding_incomplete:
                lines += [
                    "  Содержимое шаблона отсутствует - переадресации известны не полностью. Подробнее в «Замечаниях»."
                ]
        elif link.dn is not None:
            lines.append(
                f"ephone-dn {link.dn}: есть ссылка из button, но сама секция отсутствует во вставленном конфиге."
            )
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
            raise InvalidNetworkInput(
                "Диапазон номеров секций должен быть от 1 до 1000000 (лимит обработки)."
            )
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
    if kind == "number" and (config.has_templates or config.has_sip):
        raise InvalidNetworkInput(
            "Поиск свободных телефонных номеров недоступен: конфиг содержит SIP voice register или шаблоны. "
            "Их телефонные номера учитываются не полностью. Это ограничение приложения, а не ошибка конфига. "
            "Выберите «ephone / ephone-dn»: поиск номеров секций SCCP работает. Подробности и строки - в «Замечаниях»."
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
    label = label[0].lower() + label[1:]
    first, last = str(result.first).zfill(result.width), str(result.last).zfill(result.width)
    lines = [
        f"Свободные {label}: {result.total}. Диапазон {first}-{last}.",
        f"Страница {page + 1} / {pages}.",
        "Номера секций ephone/ephone-dn и телефонные номера - разные ресурсы.",
        "Созданные секции, включая пустые или с description FREE, исключены из свободных номеров секций.",
        "Телефоны: учитываются назначенный number, дополнительный secondary и числа из описания description DN.",
        "max-ephones ограничивает количество аппаратов; допустимые номера секций ephone зависят от платформы.",
        "",
        *values,
        "",
        "Перед назначением сверить полный актуальный конфиг и ограничения платформы.",
    ]
    return "\n".join(lines), pages


@dataclass(frozen=True)
class SectionAvailability:
    """Independent SCCP namespaces, aligned by numeric tag rather than button links."""

    config: CMEConfig
    first: int
    last: int

    @property
    def total(self):
        return self.last - self.first + 1

    @property
    def free_phones(self):
        return self.total - sum(self.first <= tag <= self.last for tag in self.config.phones)

    @property
    def free_dns(self):
        high = min(self.last, self.config.max_dn) if self.config.max_dn is not None else self.last
        return max(0, high - self.first + 1) - sum(
            self.first <= tag <= high for tag in self.config.dns.keys() | self.config.referenced_dns
        )

    def row(self, tag):
        phone = self.config.phones.get(tag)
        phone_status = f"✗ {tag} - секция существует" if phone else f"✓ {tag} - секция не создана"
        if tag in self.config.dns:
            dn_status = f"✗ {tag} - секция существует"
        elif tag in self.config.referenced_dns:
            dn_status = f"✗ {tag} - ссылка button"
        elif self.config.max_dn is not None and tag > self.config.max_dn:
            dn_status = f"✗ {tag} - выше max-dn {self.config.max_dn}"
        else:
            dn_status = f"✓ {tag} - секция не создана"
        return str(tag), phone_status, dn_status

    def page(self, page=0, size=100):
        if type(size) is not int or not 1 <= size <= 1000:
            raise InvalidNetworkInput("Размер страницы должен быть от 1 до 1000.")
        pages = max(1, (self.total + size - 1) // size)
        if type(page) is not int or not 0 <= page < pages:
            raise InvalidNetworkInput(f"Номер страницы должен быть от 1 до {pages}.")
        start = self.first + page * size
        return tuple(self.row(tag) for tag in range(start, min(self.last + 1, start + size))), pages

    def all_text(self):
        if self.total > COPY_LIMIT:
            raise InvalidNetworkInput(
                "Таблица целиком копируется до 10000 строк; используйте страницы."
            )
        return "Номер\tephone\tephone-dn\n" + "\n".join(
            "\t".join(self.row(tag)) for tag in range(self.first, self.last + 1)
        )


def section_availability(config: CMEConfig, first: str, last: str) -> SectionAvailability:
    start, end = first.strip(), last.strip()
    if not re.fullmatch(r"[0-9]{1,7}", start) or not re.fullmatch(r"[0-9]{1,7}", end):
        raise InvalidNetworkInput("Номера секций: введите целые границы от 1 до 1000000.")
    low, high = int(start), int(end)
    if not 1 <= low <= high <= MAX_TAG:
        raise InvalidNetworkInput(
            "Номера секций: начало и конец должны быть от 1 до 1000000; начало не больше конца."
        )
    return SectionAvailability(config, low, high)


def availability_report(result: SectionAvailability, page=0) -> tuple[str, int]:
    rows, pages = result.page(page)
    lines = [
        f"Номера секций {result.first}-{result.last}. Страница {page + 1} / {pages}.",
        f"Не созданы секции ephone: {result.free_phones}; ephone-dn: {result.free_dns}.",
        "✓ секция не создана; ✗ секция существует, есть ссылка button или превышен max-dn.",
        "Одинаковые номера в строке - сравнение двух независимых списков, а не привязка аппарата к DN.",
        "",
        "Номер\tephone\tephone-dn",
        *("\t".join(row) for row in rows),
        "",
        "Статусы по вставленному снимку. Пустая секция и description FREE не освобождают номер секции.",
    ]
    if result.config.max_ephones is not None:
        count, limit = len(result.config.phones), result.config.max_ephones
        lines += [
            f"max-ephones: создано {count} из {limit}; остаток ёмкости {max(0, limit - count)}. Это лимит количества аппаратов, не их номеров."
        ]
    return "\n".join(lines), pages
