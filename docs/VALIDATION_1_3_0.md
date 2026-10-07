# Проверка Network Tools 1.3.0

Дата: 07.10.2026. Опубликован [релиз v1.3.0](https://github.com/F1ourish/network-tools/releases/tag/v1.3.0).
Исходный commit: `875c31a6c9d34fc683faac23f64c643b700a1c37`.
[GitHub Actions run 37612881211](https://github.com/F1ourish/network-tools/actions/runs/37612881211)
завершён успешно; EXE и ZIP релиза получены из этого прогона.

| Проверка | Результат |
| --- | --- |
| Ruff check / format | Успешно |
| Linux, расчёты / CLI / settings | 398 passed, 82 GUI deselected |
| Windows, pytest --require-gui | 480 passed; failures 0, errors 0, skipped 0 |
| Windows GUI | 82 теста, включая ширину окна 820x610 и переходы между редакторами ACL |
| Готовый EXE | 44 проверки, successful smoke |
| Сборка | CPython 3.12.10 x64, PyInstaller 6.22.3, закреплённые зависимости |
| Нативный стенд | Windows Server 2025; windows-2025-vs2026, image 20260925.250.1 |
| Права запуска EXE | Стандартный пользователь, medium integrity, без enabled admin SID |

## Подтверждённые сценарии

- Прежние MAC/IPv4/LPM инструменты, справка, темы, генератор паролей и перезапуск.
- Кнопки вставки в GUI, selected paste/copy/cut, readonly-поля, CIDR адрес/префикс вместе,
  многострочные маршруты/ACL; Win32-проверка Ctrl+V и контекстного меню готового EXE.
- Русская раскладка Windows: Ctrl+L/A/V и Ctrl+Shift+C через настоящий SendInput.
- IP MTU / Ethernet payload / кадр с FCS, dot1q/QinQ и PPPoE без двойного вычитания.
- IP-in-IP, GRE с опциями, WireGuard, VXLAN, ESP cipher/padding/NAT-T,
  OpenVPN DATA_V1/V2 TUN/TAP и L2TP/PPP: unit/GUI; все профили по умолчанию также через EXE.
- ACL запроса/ответа с перестановкой IP и портов, ACK=1 у TCP-ответа; отдельно разрешённый
  запрос и блокируемый ответ с точной строкой правила через готовый EXE.
- Sequence order, implicit deny, пустая вторая ACL и неизвестный порт; неподдерживаемые
  условия и неверные параметры очищают результат, копирование прежнего заключения недоступно.
- Реальный 30-секундный таймер пароля, сохранение чужого буфера и очистка при закрытии.

## Поставка

Опубликованы отдельный EXE, portable ZIP,
[`RELEASE_VERIFICATION.json`](https://github.com/F1ourish/network-tools/releases/download/v1.3.0/RELEASE_VERIFICATION.json)
и [`SHA256SUMS.txt`](https://github.com/F1ourish/network-tools/releases/download/v1.3.0/SHA256SUMS.txt).
Publisher сверил version/commit/passed и SHA-256 перед публикацией.
Имя EXE `MacAddressConverter.exe` сохранено.

Дополнительно скачаны артефакты финального CI. EXE извлечён из portable ZIP;
SHA-256 EXE, ZIP, отчёта и файла контрольных сумм совпадают с digest в метаданных GitHub Release.
Отчёт внутри ZIP совпадает с отдельным отчётом; pytest XML подтверждает 480 тестов
без ошибок и пропусков, smoke JSON - успешное выполнение 44 проверок EXE.

| Файл | SHA-256 |
| --- | --- |
| `MacAddressConverter.exe` | `ee3bd385a0a91e07f30c93ce4d2fe2321da818fd616e1d722c17827b165fdcf0` |
| `NetworkTools-1.3.0-windows-x64.zip` | `57f64642df08c6a7f69eb317bce506eda07c0757282ea81be273a15810b0271e` |
| `RELEASE_VERIFICATION.json` | `90a8379d633a083f237190066387972805f9f3b1c02f56b22288f1c49c2ce0f5` |
| `SHA256SUMS.txt` | `2b4afc28299ab9548d73f535e19c01daf4909d028e38c236f665c720357b94e8` |

Снимки интерфейса из этого же прогона сохранены в [docs/screenshots](screenshots/README.md).

Целевая среда Windows 10/11 x64. Клиентские версии Windows, DPI 125-200%,
Defender/SmartScreen и корпоративные политики требуют отдельной приёмки.
EXE без цифровой подписи. ACL не моделирует NAT, маршруты, stateful firewall
и фрагменты; MTU пути не измеряется. Параметры инкапсуляций должны соответствовать VPN.
