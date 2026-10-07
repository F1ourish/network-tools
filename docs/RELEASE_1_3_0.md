**Network Tools 1.3.0** - профили MTU, проверка ACL запросов/ответов и вставка из буфера.

### Добавлено

- MTU/MSS: выбор IP MTU, Ethernet payload или кадра с FCS; dot1q/QinQ и PPPoE без двойного вычитания.
- IP-in-IP, GRE с опциями, WireGuard, VXLAN, IPsec ESP, OpenVPN UDP AEAD и L2TP/IPsec.
  Явные параметры IPv4/IPv6, ESP/NAT-T, DATA_V1/V2, TUN/TAP и L2TP/PPP; состав overhead, padding, MSS и требуемый кадр.
- Две Cisco IOS IPv4 ACL для запроса и ответа; оба IPv4, TCP/UDP и порты.
  Первый permit/deny, sequence number, implicit deny и точная строка решения.
- Неизвестный нужный порт требует уточнения; неподдерживаемый синтаксис даёт ошибку всего списка.
  Отдельная проверка wildcard сохранена в дополнительном блоке.
- Кнопки вставки, Ctrl+V/Shift+Insert и контекстное меню, многострочные маршруты/ACL,
  сочетания клавиш в русской раскладке Windows. Readonly-поля защищены от изменения.
- Обновлены справка и документация. В авторских текстах используется одиночный '-'.

### Скачать

Рекомендуется `NetworkTools-1.3.0-windows-x64.zip`: распаковать и запустить
`MacAddressConverter.exe`. Python не требуется. Приложены отдельный EXE,
`SHA256SUMS.txt` и `RELEASE_VERIFICATION.json` с commit и результатами CI.
Имя EXE пока сохранено; ранее опубликованные файлы не меняются.

### Проверка

Опубликованная сборка прошла **480 тестов без ошибок и пропусков**
(398 без GUI, 82 GUI) и **44 проверки готового EXE** на Windows Server 2025
от стандартного пользователя. Проверены оба направления ACL, первый match/implicit deny,
ошибки и неизвестный порт, все профили MTU, VLAN/PPPoE, вставка, русская раскладка и перезапуск.
[CI опубликованного релиза](https://github.com/F1ourish/network-tools/actions/runs/37612881211);
исходный commit `875c31a6c9d34fc683faac23f64c643b700a1c37`.
EXE и ZIP собраны из этого commit; контрольные суммы и исходный commit подтверждены
в `RELEASE_VERIFICATION.json` и `SHA256SUMS.txt`.
[Подробный отчёт](https://github.com/F1ourish/network-tools/blob/main/docs/VALIDATION_1_3_0.md).

ACL проверяет только введённые списки, без NAT, маршрутизации, stateful firewall
и фрагментов. TCP-ответ моделируется с ACK=1. MTU пути не измеряется; параметры
VPN должны соответствовать конфигурации. Целевая среда Windows 10/11 x64;
клиентские Windows, DPI 125-200% и корпоративные политики требуют отдельной проверки.
EXE без цифровой подписи. История/синхронизация буфера Windows не контролируется.
