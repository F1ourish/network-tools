"""Explicit layer budgets and packet-size models for common encapsulations."""

from dataclasses import dataclass

from .network import InvalidNetworkInput

PROFILES = {
    "Без туннеля / ручной": "manual",
    "IP-in-IP": "ipip",
    "GRE": "gre",
    "WireGuard": "wireguard",
    "VXLAN": "vxlan",
    "IPsec ESP": "ipsec",
    "OpenVPN UDP AEAD": "openvpn",
    "L2TP/IPsec": "l2tp",
}
BASES = {"IP MTU уже известен": "ip", "Ethernet payload": "payload", "Ethernet-кадр с FCS": "frame"}
CIPHERS = {
    "AES-GCM-16": (8, 16, 4),
    "AES-CBC + HMAC-SHA1-96": (16, 12, 16),
    "AES-CBC + HMAC-SHA256-128": (16, 16, 16),
}


@dataclass(frozen=True)
class MtuOptions:
    size: int = 1500
    basis: str = "ip"
    profile: str = "manual"
    inner_ip: int = 4
    outer_ip: int = 4
    vlan_tags: int = 0
    pppoe: bool = False
    extra: int = 0
    gre_checksum: bool = False
    gre_key: bool = False
    gre_sequence: bool = False
    inner_tags: int = 0
    esp_mode: str = "tunnel"
    esp_cipher: str = "AES-GCM-16"
    nat_t: bool = False
    openvpn_v2: bool = True
    openvpn_tap: bool = False
    l2tp_length: bool = False
    l2tp_sequence: bool = False
    ppp_header: int = 4

    def validate(self):
        if self.basis not in BASES.values() or self.profile not in PROFILES.values():
            raise InvalidNetworkInput("Выберите исходный размер и профиль инкапсуляции.")
        if self.inner_ip not in (4, 6) or self.outer_ip not in (4, 6):
            raise InvalidNetworkInput("Выберите IPv4 или IPv6.")
        if type(self.size) is not int or not 1 <= self.size <= (
            65593 if self.basis == "frame" else 65535
        ):
            raise InvalidNetworkInput("Исходный размер должен быть 1-65535 (кадр с FCS: до 65593).")
        if type(self.extra) is not int or not 0 <= self.extra <= 65535:
            raise InvalidNetworkInput("Дополнительный overhead должен быть 0-65535.")
        if self.vlan_tags not in (0, 1, 2) or self.inner_tags not in (0, 1, 2):
            raise InvalidNetworkInput("Выберите 0, 1 (802.1Q) или 2 (QinQ) VLAN-тега.")
        if self.esp_mode not in ("tunnel", "transport") or self.esp_cipher not in CIPHERS:
            raise InvalidNetworkInput("Выберите ESP tunnel/transport и поддерживаемый алгоритм.")
        if self.ppp_header not in (1, 2, 4):
            raise InvalidNetworkInput("Размер PPP-заголовка: 1, 2 или 4 байта.")
        if (
            self.profile == "ipsec"
            and self.esp_mode == "transport"
            and self.outer_ip != self.inner_ip
        ):
            raise InvalidNetworkInput(
                "В ESP transport версии внешнего и внутреннего IP должны совпадать."
            )


def components(length: int, options: MtuOptions) -> tuple[tuple[str, int], ...]:
    """Expansion for a maximum inner packet; excludes outer Ethernet/FCS."""
    o = options
    outer = 20 if o.outer_ip == 4 else 40
    inner = 20 if o.inner_ip == 4 else 40
    result = []
    if o.profile in ("ipip", "gre", "wireguard", "vxlan", "openvpn", "l2tp"):
        result.append((f"Внешний IPv{o.outer_ip}", outer))
    if o.profile == "gre":
        result.append(("GRE base", 4))
        for label, enabled in (
            ("GRE checksum/reserved", o.gre_checksum),
            ("GRE key", o.gre_key),
            ("GRE sequence", o.gre_sequence),
        ):
            if enabled:
                result.append((label, 4))
    if o.profile in ("wireguard", "vxlan", "openvpn"):
        result.append(("Внешний UDP", 8))
    if o.profile == "wireguard":
        result.extend((("WireGuard header", 16), ("Poly1305 tag", 16)))
        # Linux WireGuard bounds optional 16-byte padding by the tunnel MTU.
        # At the maximum packet, padding is zero rather than reducing MTU to /16.
    if o.profile == "vxlan":
        result.extend((("VXLAN", 8), ("Внутренний Ethernet без FCS", 14 + 4 * o.inner_tags)))
    if o.profile == "openvpn":
        result.extend(
            (
                (
                    "OpenVPN DATA_V2" if o.openvpn_v2 else "OpenVPN DATA_V1",
                    4 if o.openvpn_v2 else 1,
                ),
                ("Packet ID", 4),
                ("AEAD tag", 16),
            )
        )
        if o.openvpn_tap:
            result.append(("TAP Ethernet без FCS", 14 + 4 * o.inner_tags))
    if o.profile in ("ipsec", "l2tp"):
        iv, tag, alignment = CIPHERS[o.esp_cipher]
        encrypted = length
        if o.profile == "l2tp":
            l2tp = 6 + 2 * o.l2tp_length + 4 * o.l2tp_sequence
            result.extend((("L2TP UDP", 8), ("L2TPv2", l2tp), ("PPP", o.ppp_header)))
            encrypted += 8 + l2tp + o.ppp_header
        elif o.esp_mode == "tunnel":
            result.append((f"Внешний IPv{o.outer_ip}", outer))
        else:
            encrypted = max(0, length - inner)
        if o.nat_t:
            result.append(("NAT-T UDP (без IKE marker)", 8))
        padding = (-(encrypted + 2)) % alignment
        result.extend(
            (
                ("ESP SPI/sequence", 8),
                ("ESP explicit IV", iv),
                ("ESP trailer", 2),
                ("ESP padding", padding),
                ("ESP ICV/tag", tag),
            )
        )
    if o.extra:
        result.append(("Дополнительный overhead", o.extra))
    return tuple(result)


def packet_size(length: int, options: MtuOptions) -> int:
    return length + sum(size for _, size in components(length, options))


@dataclass(frozen=True)
class MtuCalculation:
    options: MtuOptions
    outer_mtu: int
    inner_mtu: int
    mss: int
    packet: int
    frame: int
    breakdown: tuple[tuple[str, int], ...]

    def rows(self):
        return {
            "Исходный IP MTU": str(self.outer_mtu),
            "Инкапсуляция, байт": str(self.packet - self.inner_mtu),
            "Эффективный IP MTU": str(self.inner_mtu),
            "Фиксированный IP-заголовок": "20" if self.options.inner_ip == 4 else "40",
            "Фиксированный TCP-заголовок": "20",
            "TCP MSS": str(self.mss),
            "Ethernet-кадр с FCS": str(self.frame),
            "Резерв внешнего IP MTU": str(self.outer_mtu - self.packet),
        }

    def explanation(self):
        o = self.options
        lines = [f"Исходный размер: {o.size}; {next(k for k, v in BASES.items() if v == o.basis)}."]
        if o.pppoe:
            lines.append(
                "PPPoE 6 + PPP 2 = 8 байт. "
                + (
                    "Введённый IP MTU уже учитывает PPPoE, повторно не вычитается."
                    if o.basis == "ip"
                    else "Вычитается из Ethernet payload."
                )
            )
        lines.append(
            f"VLAN-тегов снаружи: {o.vlan_tags}; Ethernet header + FCS = {18 + 4 * o.vlan_tags} байт."
        )
        lines.extend(f"{label}: {size} байт" for label, size in self.breakdown)
        if not self.breakdown:
            lines.append("Туннельной инкапсуляции нет.")
        if o.profile == "wireguard":
            lines.append(
                "Padding WireGuard ограничен tunnel MTU, как в реализации Linux; показан максимальный IP-пакет."
            )
        if o.profile == "openvpn":
            lines.append(
                "Профиль: UDP, AEAD tag 16, Packet ID 4; без compression и fragmentation. Другие форматы данных и TCP требуют ручного расчёта."
            )
        if o.profile in ("ipsec", "l2tp"):
            lines.append(
                f"ESP: {o.esp_cipher}; {'transport с L2TP' if o.profile == 'l2tp' else o.esp_mode}; минимальный padding, без TFC и IP options/extensions."
            )
        if o.profile == "l2tp":
            lines.append(
                "L2TPv2 без Offset; размер PPP задаётся по фактическим ACFC/PFC. Это параметры профиля, не автоопределение VPN."
            )
        if o.inner_ip == 6 and self.inner_mtu < 1280:
            lines.append(
                "ВНИМАНИЕ: внутренний IPv6 MTU ниже 1280; без адаптации канала такой профиль непригоден для IPv6."
            )
        if o.outer_ip == 6 and o.profile != "manual" and self.outer_mtu < 1280:
            lines.append("ВНИМАНИЕ: внешний IPv6 MTU ниже 1280.")
        lines.append(
            "Размер кадра включает FCS, без preamble/IFG. MSS вычитает фиксированные IP/TCP-заголовки; опции уменьшают TCP-данные отдельно. Path MTU не измеряется."
        )
        return "\n".join(lines)

    def copy_text(self):
        return (
            "\n".join(f"{label}: {value}" for label, value in self.rows().items())
            + "\n\n"
            + self.explanation()
        )


def calculate_mtu(options: MtuOptions) -> MtuCalculation:
    o = options
    o.validate()
    budget = o.size
    if o.basis == "frame":
        budget -= 18 + 4 * o.vlan_tags
    if o.pppoe and o.basis != "ip":
        budget -= 8
    if not 1 <= budget <= 65535:
        raise InvalidNetworkInput("После L2/PPPoE должен остаться внешний IP MTU 1-65535.")
    low, high = 0, budget
    while low < high:
        middle = (low + high + 1) // 2
        if packet_size(middle, o) <= budget:
            low = middle
        else:
            high = middle - 1
    mss = low - (40 if o.inner_ip == 4 else 60)
    if mss <= 0:
        raise InvalidNetworkInput("После инкапсуляции и IP/TCP-заголовков должен остаться MSS > 0.")
    packet = packet_size(low, o)
    frame = packet + (8 if o.pppoe else 0) + 18 + 4 * o.vlan_tags
    return MtuCalculation(o, budget, low, mss, packet, frame, components(low, o))
