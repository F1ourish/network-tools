# Проверка Network Tools 1.1.0

Версия: 2.0; дата: 06.10.2026; контур: native Windows CI / отдельный client acceptance.

Подтверждённые результаты и hashes фиксируются в VALIDATION_1_1_0.md.
Server CI, source GUI tests и client acceptance имеют разную область покрытия.
GUI skips не считаются подтверждением работы интерфейса.

## Автоматические проверки

- MAC: ASCII/длина/разделители, 4 формата, регистр, CLI, clipboard и callbacks.
- IPv4: все 33 маски и границы адресов, invalid masks/CIDR, host normalization,
  strict network, /31, /32, /0, первая/последняя страница больших сетей.
- MSS: fixed headers IPv4/IPv6, manual overhead и ошибки MTU/чисел.
- LPM: host/default route, равные кандидаты, порядок, комментарии, отсутствие
  совпадения, невыравненный CIDR, лимит списка.
- ACL: non-contiguous wildcard, полная/нулевая маска, random per-octet cross-check.
- Persistence: corrupt/oversized settings, invalid theme, atomic replace failure.
- GUI: defaults, live updates, CIDR paste/typing, clear/recovery, readonly/copy,
  host pages/snapshot, темы с сохранением ввода, reload и shortcuts.
- Готовый EXE: PE x64/windowed/asInvoker/version, bundled notices/fonts/DLL,
  medium non-admin token, изолированный каталог, все инструменты, themes/restart.

```powershell
.\.venv\Scripts\python.exe -m pytest -q --require-gui
.\.venv\Scripts\python.exe scripts/build_windows.py
```

Второй скрипт также запускает первый этап и затем готовый EXE. Не подменять
EXE smoke тестом исходного Python. Результаты и PNG относятся к проверенному hash.

## Отдельная клиентская проверка

Зафиксировать SHA-256, Windows edition/build, локаль, DPI, тип учётной записи,
наличие Python и путь EXE. Использовать опубликованный asset без пересборки.

| Действие | Ожидаемый результат |
| --- | --- |
| Стандартный пользователь, Windows 10/11 x64 без Python | Запуск EXE без console/elevation, нет missing runtime |
| Папка с пробелами/кириллицей | Все вкладки, clipboard и restart работают |
| 100/125/150/200% и уменьшение окна | Поля доступны, длинные результаты копируются, вертикальная прокрутка работает |
| Дневная/ночная темы, фокус и Tab | Читаемые текст/контраст, ввод сохраняется, focus виден |
| IPv4 192.168.1.42/24 + strict | Normal: сеть .0; strict: ошибка host bits; stale copy отсутствует |
| IPv4 /31, /32, /0 и /8 host list | Корректные особые случаи; страницы не тормозят от размера блока |
| MAC 0011.2233.aabb, все форматы/регистр | Значения совпадают с README |
| MTU 1500 IPv4/IPv6 | MSS 1460/1440, overhead отдельно |
| Маршруты /0,/16,/24 с двумя /24 | Все matching routes; два равных LPM кандидата |
| Wildcard 0.0.255.254, test .2/.3 | Совпадение / несовпадение |
| Ошибка и восстановление каждого ввода | Старый результат очищен, copy disabled, затем корректный расчёт |
| Перезапуск | Только тема сохранена; все поля имеют defaults |
| Defender/SmartScreen / корпоративные политики | Зафиксировать actual поведение unsigned EXE |

Не отмечать client/DPI/security-policy пункты passed без фактической проверки.
Для проблем приложить среду, hash, шаги и screenshot с тестовыми адресами.
