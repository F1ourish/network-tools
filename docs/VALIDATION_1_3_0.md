# Проверка Network Tools 1.3.0

Дата: 07.10.2026. Кандидат: `2a1bfa0e5b67d28cf2f5ae1496d4ad177b9a24a6`.
[GitHub Actions run 37611845777](https://github.com/F1ourish/network-tools/actions/runs/37611845777) завершён успешно.

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

Релиз публикуется только после повторной успешной проверки точного release commit.
Publisher сверяет version/commit/passed и SHA-256 EXE/ZIP/verification report.
Точные данные опубликованной сборки находятся в `RELEASE_VERIFICATION.json`,
контрольные суммы - в `SHA256SUMS.txt`. Имя EXE `MacAddressConverter.exe` сохранено.

Целевая среда Windows 10/11 x64. Клиентские версии Windows, DPI 125-200%,
Defender/SmartScreen и корпоративные политики требуют отдельной приёмки.
EXE без цифровой подписи. ACL не моделирует NAT, маршруты, stateful firewall
и фрагменты; MTU пути не измеряется. Параметры инкапсуляций должны соответствовать VPN.
