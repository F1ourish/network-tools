# Отчёт проверки MAC Address Converter 1.0.0

Дата: 05.10.2026. Статус: **исходники подготовлены; Windows-поставка не завершена**.

Краткий вывод: MAC-модуль, CLI, исходный GUI, тесты, документация и CI созданы.
Локально подтверждены **69 passed, 12 skipped** и проверки Ruff.
Windows `MacAddressConverter.exe` **не создан и не запускался**. Definition of Done
из ТЗ не достигнут; этот архив нельзя выдавать за готовую portable-утилиту.

## Реализовано

- Независимый `mac.py`: normalization, ровно 12 ASCII hex, lowercase representation.
- Cisco, Colon (default), Hyphen, Plain; uppercase/lowercase.
- Tkinter GUI с live conversion, readonly Result, Copy и статусом.
- Очистка stale result и disabled Copy при некорректном MAC.
- Стандартные Ctrl+C/V, Ctrl+A для Input/Result, Ctrl+L для Input.
- CLI из исходников поверх того же API; portable CLI EXE не добавлен.
- Runtime без внешних пакетов, сети, телеметрии, истории и persistent settings.
- Onefile/windowed `.spec`, Windows manifest `asInvoker`, единый `__version__`.
- Закреплённые dev dependencies; GitHub Actions; инструкции build/test/release.

Под «реализовано GUI» подразумевается написанный код, не успешная runtime-проверка.

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
  mac-converter.spec
  pyproject.toml
  requirements-dev.txt
  README.md
  CHANGELOG.md
  LICENSE
  THIRD_PARTY_NOTICES.md
  .gitignore
```

## Фактические проверки

Среда: Ubuntu 24.04.3 x64; CPython 3.12.14; pytest 8.4.2;
Ruff 0.13.3. Tk 9.0 доступен как модуль, рабочего GUI connection нет.

Из корня репозитория выполнялось:

```bash
python -m pytest -q
```

Фактический вывод:

```text
69 passed, 12 skipped in 0.25s
```

GUI checks пропущены из-за отсутствия доступного Tk-дисплея. Отдельные попытки
`--require-gui` корректно дали ошибки setup: подключение к виртуальному
дисплею запрещено/недоступно. Эти ошибки не являются успешной GUI-проверкой
и не показывают функциональный результат работы интерфейса.

Выполнялись:

```bash
python -m ruff check src tests scripts packaging/gui_entry.py
python -m ruff format --check src tests scripts packaging/gui_entry.py
```

Подтверждено: lint и format checks прошли. Все Python-файлы и `.spec`
разобраны AST-парсером. Workflow YAML проверен структурно; выполнение GitHub
Actions не проверялось.

Пакет установлен из исходников без build isolation; metadata сообщает версию
1.0.0. CLI фактически выполнен:

```bash
python -m mac_converter.cli 0011.2233.aabb --format colon
python -m mac_converter.cli aabb.ccdd.eeff --format hyphen --upper
python -m mac_converter.cli --version
```

Фактические результаты по порядку:

```text
00:11:22:33:aa:bb
AA-BB-CC-DD-EE-FF
MAC Address Converter 1.0.0
```

Dependencies дополнительно разрешены для Windows x64 / Python 3.12 с помощью
`uv pip compile`: 13 пакетов, конфликтов не получено. Это проверка совместимости
заявленных зависимостей, а не установка или сборка в Windows.

## Build configuration и artifact

Точная подготовленная команда:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm mac-converter.spec
```

Полная процедура с обязательными тестами и smoke:

```powershell
.\.venv\Scripts\python.exe scripts/build_windows.py
```

Настройки: Windows CPython 3.12.10 x64, PyInstaller 6.22.3, onefile,
`console=False`, UPX disabled, version resource, manifest `asInvoker`.
Ожидаемый artifact: `dist/MacAddressConverter.exe`.
**Фактический artifact отсутствует.** Контрольная сумма Windows EXE отсутствует.

Build script в Linux фактически запущен и отказал с понятным требованием
использовать Windows Python. Linux executable не создавался и не переименовывался в `.exe`.

## Почему EXE не удалось проверить

Попытка использовать Windows Python через Wine заблокирована средой исполнения:

```text
wineserver: socket: Operation not permitted
```

Попытка подключить Tk к виртуальному X-дисплею также не удалась:

```text
couldn't connect to display "127.0.0.1:98"
```

Нет доступа к действующей нативной Windows-машине или подключённому Windows CI.
GitHub workflow пока не запускался, репозиторий в GitHub не создавался.

## Definition of Done

| Требование | Статус |
| --- | --- |
| MAC normalization, validation, четыре output formats, case | Подтверждено unit-тестами |
| GUI, live conversion, Copy, keyboard shortcuts | Код и тесты написаны; runtime не проверен |
| CLI и единая business logic | Подтверждено тестами и запуском CLI |
| pytest | 69 passed; 12 GUI skipped |
| README, docs, CI, build config, LICENSE | Созданы; CI статически проверен |
| Windows PyInstaller build | Не выполнен |
| `MacAddressConverter.exe` | Не создан |
| Фактический EXE smoke test | Не выполнен |
| Без Python / без admin privileges | Требует Windows acceptance test |
| Windows DPI и реальный screenshot | Требует Windows acceptance test |
| Готовый GitHub Release | Не создавался |

## Следующие действия

1. Выполнить `scripts/build_windows.py` на Windows CPython 3.12.10 x64
   либо запустить подготовленный GitHub workflow в разрешённом репозитории.
2. Проверить EXE без Python под стандартным Windows user по `TESTING.md`;
   записать SHA-256, реальные результаты и screenshot.
3. Только после этого создать `v1.0.0` и проверенный release artifact.

Документы `BUILD_AND_RELEASE.md` и `TESTING.md` содержат точные команды,
ожидаемое поведение, rollback и условия завершения проверки.
