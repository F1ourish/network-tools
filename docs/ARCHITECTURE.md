# Архитектура MAC Address Converter

Версия документа: 1.1; дата: 05.10.2026; статус: Windows runtime проверен в CI.

Краткий вывод: приложение использует один независимый MAC-модуль; GUI и CLI
не содержат собственных правил parsing. Runtime — стандартная библиотека Python и Tcl/Tk.

## Поток обработки

Изменение Input, radio button или UPPERCASE вызывает один GUI callback.
Он передаёт строку в `format_mac()`, который вызывает `normalize_mac()`.
Успех обновляет readonly Result и включает Copy. `InvalidMacAddress`
очищает Result и отключает Copy; текст ошибки выводится в Status.

`normalize_mac()` удаляет внешние whitespace и допустимые разделители,
проверяет длину и ASCII hexadecimal, возвращает lowercase из 12 символов.
Нет проверки производителя, unicast/multicast или принадлежности устройства.

## Ответственность модулей

| Компонент | Ответственность |
| --- | --- |
| `mac.py` | Чистые функции нормализации/форматирования и собственное исключение |
| `gui.py` | Tk variables/widgets, отображение ошибок, clipboard, shortcuts |
| `main.py` | Создание Tk root и event loop |
| `cli.py` | argparse, stdout/stderr, exit codes 0/2 |
| `__init__.py` | Единственный источник версии для package metadata и Windows resources |
| `.spec`, `windows.manifest` | Onefile/windowed сборка и `asInvoker` |
| `scripts/smoke_windows.py` | Внешний тест EXE; не включается в product runtime |
| `scripts/windows_process.py` | Запуск без elevation и инспекция токена/DLL для тестового стенда; не входит в EXE |

## Данные и зависимости

В приложении отсутствуют network requests, shell execution, логи MAC,
настройки и история. После Copy результат существует и в системном clipboard.
Скрипты разработки отдельно запускают pytest/PyInstaller; они не входят в EXE.

PyInstaller onefile распаковывает bundled runtime во временную пользовательскую
директорию. Это служебные Python/Tcl/Tk файлы, не история MAC. Внешний установленный
Python не должен использоваться, что проверяется smoke harness в новой папке
с очищенным Python/Tcl environment и PATH из Windows System32. Фактически
подтверждена загрузка `python312.dll`, `_tkinter.pyd`, `tcl86t.dll`, `tk86t.dll`
из onefile-каталога `_MEI...`, а не из builder Python.

## Обработка ошибок

Некорректный MAC — ожидаемая ошибка, GUI остаётся работающим. Невозможность
записи clipboard даёт сообщение с предложением повторить Copy.
Unexpected callback exception очищает результат, отключает Copy и предлагает
перезапуск без traceback и логирования введённых данных.

## Ограничения v1.0

Нет bulk conversion, persistent settings, OUI lookup, installer, updater,
сканирования сети, внешнего backend и portable CLI executable.
Поддержка Windows 10/11 x64 является целевой, а не уже подтверждённой.
Standard-user запуск EXE на Windows Server 2025 подтверждён. Windows 10/11,
машина без установленного Python и разные DPI требуют оставшихся проверок
в `TESTING.md`; их нельзя выводить из успешного server CI.

## Проверенные официальные источники

Проверены 05.10.2026:

- [PyInstaller: onefile и устройство runtime](https://pyinstaller.org/en/stable/operating-mode.html).
- [PyInstaller: windowed, manifest, UAC options](https://pyinstaller.org/en/stable/usage.html).
- [PyInstaller: spec files и EXE](https://pyinstaller.org/en/stable/spec-files.html).

Утверждения о структуре и обработке MAC основаны на коде проекта;
фактические результаты находятся в `VALIDATION_2026-10-05.md`.
