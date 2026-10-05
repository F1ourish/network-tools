# Отчёт проверки MAC Address Converter 1.0.0

Дата: 05.10.2026. Статус: **Windows x64 EXE собран, фактически запущен и проверен**.

В [GitHub Actions](https://github.com/F1ourish/mac-address-converter/actions/runs/37349926876) успешно прошли **81 pytest-тест и 19 проверок
готового EXE**. Приложение запускалось дважды от настоящей стандартной учётной
записи Windows, без elevation. Проверены live conversion, четыре формата,
UPPERCASE, clipboard, ошибка ввода и повторный запуск. Готовый binary предоставлен.
Windows 10/11, полностью чистая машина без Python и разные DPI отдельно не проверены.

## Реализовано

- Независимый `mac.py`: normalization, ровно 12 ASCII hex, lowercase representation.
- Cisco, Colon (default), Hyphen, Plain; uppercase/lowercase.
- Tkinter GUI с live conversion, readonly Result, Copy и статусом.
- Очистка результата и disabled Copy при некорректном MAC.
- Стандартные Ctrl+C/V/A; Ctrl+L для Input.
- CLI из исходников поверх того же API; отдельный portable CLI EXE не поставляется.
- Runtime без внешних пакетов, сети, телеметрии, истории и persistent settings.
- Onefile/windowed EXE, manifest `asInvoker`, единый `__version__`, MIT.
- Закреплённые dev dependencies, CI и инструкции build/test/release.

## Структура проекта

```text
mac-address-converter/
  src/mac_converter/
    __init__.py
    __main__.py
    main.py
    gui.py
    mac.py
    cli.py
  tests/
    conftest.py
    test_mac.py
    test_cli.py
    test_gui.py
    test_release.py
  scripts/
    build_windows.py
    smoke_windows.py
    windows_process.py
    check_release_tag.py
  packaging/
    gui_entry.py
    windows.manifest
    licenses/
  .github/workflows/build.yml
  docs/
    ARCHITECTURE.md
    BUILD_AND_RELEASE.md
    TESTING.md
    VALIDATION_2026-10-05.md
    screenshot.png
  mac-converter.spec
  pyproject.toml
  requirements-dev.txt
  README.md
  CHANGELOG.md
  LICENSE
  THIRD_PARTY_NOTICES.md
  .gitignore
```

Исходники: [F1ourish/mac-address-converter](https://github.com/F1ourish/mac-address-converter).
Проверенный commit: `f3fb8e3efb8d2c3290fc8b1d76eb648db460ef42`.
Обновление документации после него не меняет код проверенного приложения.

## Фактические тесты и среда

| Проверка | Полученный результат |
| --- | --- |
| Windows `pytest -q --require-gui` | `81 passed in 2.90s`, GUI не пропущен |
| Linux CI: логика, CLI, release-tag tests | 69 passed |
| Локальные логика/CLI/release tests | `69 passed in 0.05s` |
| Ruff lint и format | Passed в Linux CI и локально |
| PyInstaller | Build completed successfully |
| Фактический Windows EXE | `EXE smoke: 19 checks passed` |

Windows: Microsoft Windows Server 2025, build 10.0.26100.
Runner image: `windows-2025-vs2026`, версия `20260925.250.1`.
Builder: CPython 3.12.10 x64, PyInstaller 6.22.3, pytest 8.4.2, Ruff 0.13.3.
Локальная среда проверок логики: Ubuntu x64, CPython 3.12.14.

## Build configuration и artifact

Фактически использована команда:

```powershell
python -m PyInstaller --clean --noconfirm mac-converter.spec
```

Полная процедура, запущенная в Windows CI:

```powershell
python scripts/build_windows.py
```

Настройки: onefile, `console=False`, без UPX, version resource 1.0.0.0,
manifest `asInvoker`, bundled Python/Tcl/Tk и лицензии.

- Файл: `dist/MacAddressConverter.exe`.
- Размер: **11,338,545 байт**.
- SHA-256 EXE: `b3361751cb446e50a352ebfe9de91a30ed9f2b47f4dae088c65531b12287993a`.
- [Проверенный artifact](https://github.com/F1ourish/mac-address-converter/actions/runs/37349926876/artifacts/11362132391), ID `11362132391`.
- Artifact CI ZIP SHA-256: `b8014e8d624da079de95dc668513303c283eacd8f138c871933e511c780b7f27`.
- Создан 05.10.2026, срок хранения CI artifact — до 04.11.2026.

Artifact содержит EXE, SHA256SUMS, `windows-exe.json` и настоящий PNG рабочего EXE.
Скачанный ZIP проверен по digest GitHub и CRC; SHA-256 EXE совпал с SHA256SUMS
и JSON-отчётом. Независимо проверены PE x64, GUI subsystem и 999 entries
PyInstaller archive, включая Python/Tcl/Tk и все обязательные license notices.
Тексты MIT и Tcl notice совпали с исходниками после нормализации Windows CRLF.
Внутренний CI ZIP и пользовательский portable ZIP имеют разные упаковку и digest;
EXE в них один и тот же.

Процедура сборки повторяема по шагам и закреплённым версиям;
побайтовая идентичность независимых сборок не заявляется.

## Фактический запуск EXE

Временная папка приложения содержала только EXE; путь включал пробелы и кириллицу.
`PATH` ограничен Windows System32, переменные Python/Tcl/venv убраны.
TEMP и пользовательские каталоги изолированы. Приложение работало без исходников,
venv, IDE или доступа к установленному builder interpreter.

У обоих процессов GUI Windows token подтвердил:

```json
{
  "elevated": false,
  "administrators_enabled": false,
  "integrity_rid": 8192,
  "restricted": false
}
```

Это запуск от обычной учётной записи, а не обход проверки elevation.
Загруженные `python312.dll`, `_tkinter.pyd`, `tcl86t.dll`, `tk86t.dll` находились
в `_MEI...` папке распакованного onefile runtime. Зависимость от внешнего Python
не обнаружена в этом сценарии. Сам CI builder имеет установленный Python;
тест на физически чистой Windows-машине отдельно не проводился.

| Проверка реального EXE | Факт |
| --- | --- |
| PE x64 / GUI subsystem / version / manifest | Passed |
| Запуск без elevation, обычная учётная запись | Passed, оба запуска |
| Встроенный runtime и notices | Passed, наличие в archive и загрузка DLL |
| Ctrl+L/V/A/C и live Colon conversion | Passed |
| Cisco, Colon, Hyphen, Plain | Passed |
| UPPERCASE в Colon и Cisco | Passed |
| Copy | Clipboard содержит только форматированный результат |
| Некорректный MAC | Result очищен, GUI работает и принимает следующий MAC |
| Закрытие и повторное открытие | Exit code 0, Colon/lowercase восстановлены |
| Portable folder | После проверки по-прежнему только EXE |
| Скриншот | Снят с фактически запущенного EXE и добавлен в README |

Статусы Ready/Copied, disabled Copy, readonly Result, сбой clipboard и обработка
неожиданной ошибки дополнительно подтверждены 12 тестами исходного Tk GUI.
Скрипты инспекции/создания временной CI-учётной записи не входят в приложение.

## Ограничения и оставшаяся проверка

- Windows 10/11 x64 — целевая среда; непосредственно проверен Windows Server 2025.
- Не проведён тест на чистой Windows 10/11 без установленного Python.
- Не проверены масштабы 100%, 125%, 150%, локали и клиентские Windows themes.
- Поведение Defender, SmartScreen и корпоративных политик не проверено; code signing нет.
- GitHub Release и tag `v1.0.0` пока не опубликованы.
- Bulk/OUI lookup, installer, updater, история и portable CLI вне v1.0.

## Следующие действия

1. Выполнить оставшиеся проверки на Windows 10/11 без Python и при разных DPI
   по [TESTING.md](https://github.com/F1ourish/mac-address-converter/blob/main/docs/TESTING.md).
2. После проверки подготовить тег `v1.0.0` и draft Release с проверенным EXE и SHA-256
   по [runbook](https://github.com/F1ourish/mac-address-converter/blob/main/docs/BUILD_AND_RELEASE.md).
