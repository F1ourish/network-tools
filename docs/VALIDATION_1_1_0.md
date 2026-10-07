# Проверка Network Tools 1.1.0

Дата: 06.10.2026. Кандидат прошёл Windows CI, включая исходный GUI и готовый EXE.
Публикация заново собирает и проверяет точный commit из main. Источник версии,
commit, результатов и SHA-256 опубликованного EXE - RELEASE_VERIFICATION.json
в assets релиза; контрольные суммы всех трёх файлов - SHA256SUMS.txt.

## Проверенный кандидат

- Commit: `242d71e7d469e40dec568eba75b9ebda3204374e`.
- [Успешный workflow run 37442034527](https://github.com/F1ourish/mac-address-converter/actions/runs/37442034527).
- Windows job: `112198021767`; Linux job: `112197853711`.
- После этого кандидата изменены только документы и добавлены скриншоты;
  исходники приложения, тесты и сборочная процедура сохранены.

| Проверка | Фактический результат |
| --- | --- |
| Windows pytest с --require-gui | 223 passed; failures 0, errors 0, skipped 0 |
| Из них GUI | 37 passed |
| Linux pytest без GUI | 186 passed |
| Ruff check и format --check | Passed |
| Готовый Windows EXE | 28 checks, passed true |
| ZIP и EXE | ZIP содержит побайтово тот же EXE, который запускал smoke |
| SHA-256 | Все три строки SHA256SUMS.txt совпадают с файлами кандидата |

## Среда готового EXE

| Параметр | Значение |
| --- | --- |
| ОС | Windows Server 2025, build 26100, runner image 20260925.250.1 |
| Сборщик | CPython 3.12.10 x64, PyInstaller 6.22.3 |
| UI dependencies | ttkbootstrap 2.2.3, Pillow 12.3.0 |
| Desktop | 1024×768; window DPI 96 (100%) |
| Два запуска | elevated false; administrators_enabled false; integrity RID 8192 (medium) |
| Каталог приложения | Новая папка с пробелами и Unicode, содержит только EXE |
| Окружение запуска | Python/Tcl переменные очищены; PATH не содержит Python |
| Runtime DLL | python312.dll, _tkinter.pyd, tcl86t.dll и tk86t.dll загружены из распакованного EXE bundle |

Перед вводом проверены PE x64, Windows GUI subsystem, manifest asInvoker,
version resource 1.1.0 и наличие runtime notices/fonts. Это проверка собственного
runtime EXE на Windows runner, а не проверка Windows-клиента без установленного Python.

## Проверенные действия через готовый EXE

- MAC: четыре формата, lowercase/uppercase, вставка, live calculation,
  копирование только результата, ошибка и восстановление.
- IPv4: значения 192.168.1.0/24 по умолчанию, IP/CIDR, override маски,
  subnet/host range/broadcast/full и binary mask/wildcard, случаи /31, /32 и /0.
- Хосты: первая, вторая и последняя страницы, переход по номеру,
  копирование страницы. Список не разворачивает всю большую подсеть в память.
- MTU/MSS: IPv4 и IPv6, ручной overhead, ошибка MTU и очистка результата.
- Маршруты: longest prefix match, равные кандидаты, default route,
  отсутствие совпадения, невыравненный CIDR и очистка результата.
- ACL: прерывистая wildcard, совпадение/несовпадение, ошибка и очистка.
- Темы: смена сохраняет расчёт; после закрытия и повторного запуска сохраняется
  только night. Адреса сброшены в defaults, exit code обоих запусков 0.
- Клавиатура и clipboard: Ctrl+L/A/C/V, выбор формата, переключение вкладок
  и тем, копирование через кнопки/shortcut; доступ к полям при прокрутке.

Все 28 записей и сведения о токене находятся в smoke-results/windows-exe.json
artifact проверки. JUnit XML и native PNG доступны в том же workflow run.

## Проверка поставки и лицензий

После скачивания artifact кандидата дополнительно проверены контрольные суммы,
совпадение EXE внутри ZIP с отдельным EXE, совпадение JSON внутри ZIP с отдельным
отчётом. В PyInstaller archive и ZIP сохранены восемь оригинальных notices:
приложение, CPython, Tcl, Tk, ttkbootstrap, Bootstrap Icons, Pillow и PyInstaller.
Их содержимое совпадает между EXE bundle и ZIP.

Кандидат и финальный main собираются отдельно. Hash кандидата не выдаётся за
hash опубликованного asset: используйте RELEASE_VERIFICATION.json и SHA256SUMS.txt
из нужного релиза. Независимые сборки не заявлены как побайтово идентичные.

## Скриншоты

Ниже ссылки на снимки настоящего EXE кандидата. PNG не редактировались.
Внешняя рамка окна соответствует теме Windows Server на стенде.

| Снимок | Состояние |
| --- | --- |
| [MAC](screenshots/mac-1.1.0.png) | Дневная тема, Colon |
| [IPv4, день](screenshots/ipv4-day-1.1.0.png) | Расчёт подсети |
| [IPv4, ночь](screenshots/ipv4-night-1.1.0.png) | Ночная тема |
| [Хосты](screenshots/hosts-1.1.0.png) | Последняя страница /24 |
| [MTU/MSS](screenshots/mss-1.1.0.png) | IPv6 и ручной overhead |
| [Маршруты](screenshots/routes-1.1.0.png) | Два равных /24 кандидата |
| [ACL](screenshots/acl-1.1.0.png) | Прерывистая wildcard, несовпадение |
| [После перезапуска](screenshots/ipv4-reopen-1.1.0.png) | Сохранена night, восстановлены defaults |

## Границы подтверждения

Отдельно ещё не проверены клиентские Windows 10/11, масштабы 125-200%,
Defender, SmartScreen и корпоративные политики. EXE без цифровой подписи.
Клиентский acceptance описан в [TESTING.md](TESTING.md).

Историческая проверка 1.0.0 и её снимок сохранены отдельно:
[VALIDATION_2026-10-05.md](VALIDATION_2026-10-05.md).
