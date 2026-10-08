# MTU и ACL в 1.5.0

## MTU

IP MTU не включает Ethernet header, VLAN-теги или FCS. При известном IP MTU
802.1Q/QinQ увеличивают требуемый кадр на 4/8 байт. При фиксированном кадре
эти байты уменьшают доступный IP budget. Кадр включает FCS, без preamble/IFG.
PPPoE 6 + PPP 2 = 8 вычитаются из Ethernet payload; известный IP MTU уже после
PPPoE не уменьшается повторно. Для PPPoE с IP MTU 1500 нужен payload 1508.

| Профиль | Модель сверх внутреннего IP-пакета |
| --- | --- |
| IP-in-IP | Внешний IP 20/40 |
| GRE | Внешний IP 20/40 + GRE 4; checksum/key/sequence по 4 |
| WireGuard | Внешний IP 20/40 + UDP 8 + data header 16 + Poly1305 tag 16 |
| VXLAN | Внешний IP 20/40 + UDP 8 + VXLAN 8 + внутренний Ethernet 14 + VLAN 0/4/8 |
| ESP tunnel | Внешний IP 20/40 + SPI/sequence 8 + IV + trailer 2 + padding + ICV/tag |
| ESP transport | Исходный IP входит в исходную длину; encrypted payload без него, остальные поля ESP |
| OpenVPN UDP AEAD | Внешний IP 20/40 + UDP 8 + DATA_V1 1 / DATA_V2 4 + Packet ID 4 + tag 16; TAP добавляет Ethernet/VLAN |
| L2TP/IPsec | Внешний IP + ESP transport; encrypted UDP 8 + L2TPv2 6 (+Length 2/+Sequence 4) + PPP 1/2/4 + внутренний пакет |

ESP: GCM IV 8, tag 16, alignment 4; CBC IV 16, HMAC-SHA1-96 ICV 12 или
HMAC-SHA256-128 ICV 16, alignment 16. Используется минимальный padding,
без TFC и дополнительных IP options/extensions. NAT-T для ESP data добавляет
UDP 8; 4-байтный Non-ESP marker принадлежит IKE и сюда не включается.
Резерв показывает неиспользованные байты внешнего IP MTU после padding.

WireGuard показывает максимальный пакет при ограничении padding tunnel MTU,
как в Linux. Короткие пакеты могут дополняться до 16, не превышая MTU.
OpenVPN модель ограничена UDP AEAD DATA_V1/V2, без compression/fragmentation.
TCP, другие форматы и дополнительные слои требуют ручного overhead.
L2TP без Offset, выбранный PPP header отражает фактические ACFC/PFC.
Дополнительный overhead считается отдельным внешним расширением, вне ESP padding.

Состав expansion не определяет VPN-конфигурацию автоматически. MSS вычитает
фиксированные IP 20/40 и TCP 20; опции уменьшают payload отдельно. MTU пути не
измеряется. Для IPv6 MTU ниже 1280 выводится предупреждение.

Источники:

- [Cisco, MTU и VLAN](https://www.cisco.com/c/en/us/support/docs/switches/catalyst-9500-series-switches/217233-troubleshoot-mtu-on-catalyst-9000-series.html)
- [PPPoE RFC 2516](https://www.rfc-editor.org/rfc/rfc2516.html), [PPPoE MTU RFC 4638](https://www.rfc-editor.org/rfc/rfc4638.html)
- [IP-in-IP RFC 2003](https://www.rfc-editor.org/rfc/rfc2003.html), [GRE RFC 2784](https://www.rfc-editor.org/rfc/rfc2784.html), [GRE extensions RFC 2890](https://www.rfc-editor.org/rfc/rfc2890.html)
- [WireGuard protocol](https://www.wireguard.com/protocol/), [Linux padding](https://git.zx2c4.com/wireguard-linux/tree/drivers/net/wireguard/send.c)
- [VXLAN RFC 7348](https://www.rfc-editor.org/rfc/rfc7348.html)
- [ESP RFC 4303](https://www.rfc-editor.org/rfc/rfc4303.html), [NAT-T RFC 3948](https://www.rfc-editor.org/rfc/rfc3948.html)
- [AES-GCM RFC 4106](https://www.rfc-editor.org/rfc/rfc4106.html), [AES-CBC RFC 3602](https://www.rfc-editor.org/rfc/rfc3602.html), [HMAC RFC 4868](https://www.rfc-editor.org/rfc/rfc4868.html)
- [OpenVPN data headers](https://build.openvpn.net/doxygen/network_protocol.html), [OpenVPN AEAD wire format](https://build.openvpn.net/doxygen/group__data__crypto.html)
- [L2TPv2 RFC 2661](https://www.rfc-editor.org/rfc/rfc2661.html), [L2TP/IPsec RFC 3193](https://www.rfc-editor.org/rfc/rfc3193.html)

## ACL

Каждое поле содержит один список. Поддерживаются standard/extended IPv4 Cisco IOS
ACL в конфигурационном и показанном в справке show-формате, сырые permit/deny,
sequence number, remark, host/any/wildcard, eq/neq/lt/gt/range, имена основных
сервисов, established и log/log-input. Для TCP/UDP проверки принимаются и другие
известные IP-протоколы / числовые 0-255: такие правила пропускаются по протоколу
после полного разбора. Базовые ICMP type/code принимаются для этого же случая.
Это не универсальный парсер любых Cisco-платформ и версий вывода.

Первое совпадение определяет действие. Нет совпадений - неявный deny.
Sequence number задаёт порядок; смешивать нумерованные и ненумерованные строки
нельзя. Номер исходной строки сохраняется. Неизвестный порт, нужный потенциально
совпадающему правилу, останавливает выбор: результат требует уточнения.
Неразрешённые object-group, time-range, fragments и прочие неизвестные условия дают ошибку
всего списка, даже после разрешающего правила. До 10000 строк / 1 МБ на поле.

Первая ACL проверяет запрос. Вторая - ответ со сменой адресов и портов, ACK=1
для TCP. Это не последовательная ingress/egress проверка одного пакета.
Порт источника нужен для правил порта запроса и порта назначения ответа.
Пустая вторая ACL означает, что ответ не проверен. established проверяет ACK/RST,
а не соединение. NAT, маршрутизация, stateful firewall и фрагменты не моделируются.

Флажок отсутствия ACL явно подтверждает, что в направлении фильтр не назначен:
список сохраняется, но не разбирается. Это отличается от пустого непроверенного
ответного списка. in/out относится к движению через выбранный интерфейс Cisco:

| Интерфейс | Запрос | Ответ |
| --- | --- | --- |
| Со стороны источника | `ip access-group <name> in` | `ip access-group <name> out` |
| Со стороны назначения | `ip access-group <name> out` | `ip access-group <name> in` |

Номера слева - физические строки вставленного текста, sequence - номера правил.
Вставка убирает пробелы по краям и Cisco counters, оставляя пустые строки.
### Состав IP-групп

«IP-группы» открывает общий для обеих ACL редактор. Вставить вывод
`show object-group` / `show object-group <name>` либо конфигурацию:

```text
object-group network CLIENTS
 host 192.0.2.10
 group-object OFFICE_NET
object-group network OFFICE_NET
 203.0.113.0 255.255.255.0
object-group network SERVERS
 198.51.100.0/24
```

Разрешённые объекты: `host IPv4`, одиночный IPv4, `IPv4/префикс`,
`IPv4 /префикс`, `IPv4 маска-подсети`, `any`, `group-object <имя>`.
Маска группы является маской подсети: `255.255.255.0`, а не wildcard `0.0.0.255`.
Ненулевые host bits сетевого объекта приводятся к адресу подсети по маске.
Можно добавить заголовок по имени и вставить адреса под ним. Имена учитывают регистр.
Номера строк относятся к полю состава; исправленная группа учитывается сразу.
Escape/закрытие окна сохраняют текст в памяти до завершения приложения.
Группы используются как объединение участников в адресе источника/назначения;
правила ACL не размножаются, first match и sequence number сохраняются.
Заключение показывает исходное правило и совпавшего участника группы.

Отсутствующая/пустая группа, повторное имя и циклическое вложение дают ошибку;
частичный состав не используется для вычисления результата. IPv6, DNS/hostname,
ASA `network-object`, группы сервисов/протоколов и диапазоны IP не поддерживаются.
До 10000 строк / 1 МБ текста, 100000 разрешённых участников во всех группах.

### Очистка вывода Cisco

Кнопка вставки, Ctrl+V, Shift+Insert и контекстное меню убирают приглашения CLI,
команды show, внешние строки кавычек/блоков, пробелы и match counters.
Заголовок `Extended/Standard IP access list NAME` преобразуется в
`ip access-list extended/standard NAME`, чтобы сохранить имя/тип и границы списков.
Пустые строки внутри текста сохраняются; удаление служебных строк меняет физическую
нумерацию, gutter и ошибки относятся к очищенному полю. Sequence Cisco не меняется.
«Очистить вывод» обрабатывает уже вставленный текст и обновляет большой редактор.
Неподдерживаемые/ошибочные правила сохраняются и дают ошибку: фильтр не скрывает условия ACL.


Источники: [ACK/RST](https://www.cisco.com/c/en/us/support/docs/ip/access-lists/26448-ACLsamples.html),
[sequence number](https://www.cisco.com/c/en/us/td/docs/ios-xml/ios/sec_data_acl/configuration/xe-3e/sec-data-acl-xe-3e-book/sec-acl-seq-num.html),
[Cisco IOS access lists](https://www.cisco.com/c/en/us/support/docs/security/ios-firewall/23602-confaccesslists.html),
[Catalyst IOS XE: object-group, show object-group и ip access-group in/out](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst9500/software/release/17-13/configuration_guide/sec/b_1713_sec_9500_cg/object_groups_for_acls.html).
