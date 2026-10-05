# Windows build и выпуск MAC Address Converter

Версия документа: 1.1; дата: 05.10.2026; контур: Windows workstation / GitHub Actions;
статус: native Windows build и standard-user smoke подтверждены.

Краткий вывод: собрать Windows x64 EXE закреплённым инструментарием, проверить
сам EXE и только затем выпускать portable-поставку. В
[CI](https://github.com/F1ourish/mac-address-converter/actions/runs/37349926876)
прошли 81 тест и 19 проверок готового EXE. Windows 10/11 acceptance и DPI остаются
отдельным этапом; GitHub Release не опубликован.

## Область применения и термины

Целевая среда конечного пользователя — Windows 10/11 x64 без Python и без
административных прав. Среда сборки — CPython 3.12.10 x64 с Tcl/Tk.
Разработчику Python нужен, пользователю готового EXE — нет.

Portable означает запуск файла без установки приложения. Onefile означает
EXE с bundled runtime; при старте PyInstaller распаковывает служебные файлы в TEMP.
Windowed означает отсутствие собственной console window.
Smoke test — короткая проверка запуска и основных операций самого EXE.
`asInvoker` — запуск с текущим токеном пользователя без запроса elevation.

## Pre-check

Где выполнять: PowerShell в корне распакованного репозитория.
Что проверяется: точная версия/разрядность builder и Tcl/Tk.
Зачем: Linux PyInstaller не создаёт Windows binary; отсутствие Tcl/Tk ломает GUI.

```powershell
py -3.12 -c "import sys,struct,tkinter; print(sys.version); print(struct.calcsize('P')*8); print(tkinter.TkVersion)"
```

Ожидаемый результат: Python 3.12.10, 64 bit и доступная версия Tk. Release build
script отклоняет другой patch-level; обновление Python требует изменения
закреплённой версии, конфигурации и нового отчёта проверки.

Использовать обычный PowerShell без elevation. Подготовить интерактивный desktop,
пользовательский каталог с доступом на запись,
свободное место для venv/build/TEMP и доступ к PyPI для установки dev dependencies.
Для обычного запуска готового приложения доступ к сети не требуется.

Для выпуска дополнительно выполнить оставшиеся проверки `TESTING.md`. Если используется
GitHub runner, убедиться, что он позволяет запуск Tk и Win32 keyboard input;
отсутствие desktop не следует подменять пропуском проверок.

## Backup перед заменой проверенной поставки

Где выполнять: каталог с предыдущим пользовательским EXE.
Что проверяется/сохраняется: предыдущий бинарник для rollback.

```powershell
Copy-Item .\MacAddressConverter.exe .\MacAddressConverter.previous.exe
```

Выполнять только при наличии предыдущего EXE. Конфигурации, БД и истории MAC у
приложения нет; резервировать пользовательские данные приложения не требуется.

## Установка инструментов разработки

Где выполнять: корень репозитория в пользовательской директории.
Зачем: изолировать закреплённые build dependencies, без смены ExecutionPolicy.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -e .
```

Ожидаемый результат: все зависимости установлены; версия пакета берётся
из `src/mac_converter/__init__.py`. Ни installer приложения, ни службы не создаются.

## Сборка и автоматическая проверка

Где выполнять: корень репозитория, интерактивный Windows desktop.
Зачем: не допустить успешную поставку при skipped GUI checks или непроверенном EXE.

```powershell
.\.venv\Scripts\python.exe scripts/build_windows.py
```

Скрипт последовательно выполняет:

1. `pytest -q --require-gui`.
2. `python -m PyInstaller --clean --noconfirm mac-converter.spec`.
3. Создание SHA-256 файла для конкретного EXE.
4. Внешний Win32 smoke test копии EXE в отдельной папке с пробелами/Unicode.

Ожидаемые файлы после полного успеха:

```text
dist/MacAddressConverter.exe
dist/SHA256SUMS.txt
smoke-results/windows-exe.json
smoke-results/windows-exe.png
```

Ожидаемый смысл отчёта: `passed: true`, тот же SHA-256, PE x64 GUI subsystem,
manifest `asInvoker`, embedded Python/Tcl/Tk, успешные GUI/clipboard операции и reopen.
В `execution_tokens` оба запуска должны иметь `elevated: false`,
`administrators_enabled: false`, `integrity_rid: 8192`. DLL runtime должны быть
загружены из `_MEI...` каталога onefile, а папка приложения содержать только EXE.
Количество пройденных тестов брать из фактического вывода; примерные числа
не являются подтверждением результата.

Проверка использует клавиатуру и clipboard. Во время неё не работать в других
окнах; прежний текстовый clipboard восстанавливается, остальные форматы не гарантируются.

На обычной Windows-машине smoke использует текущего пользователя и отклоняет
elevated shell. На hosted GitHub runner `scripts/windows_process.py` создаёт
временную стандартную учётную запись, даёт ей доступ только к тестовой папке
и desktop, проверяет токен EXE и после теста удаляет учётную запись, восстанавливает
права desktop и привилегию инспекции у harness. Пароль генерируется в памяти
и не выводится. Эти операции принадлежат CI-стенду и не включены в EXE.

## Ручная проверка конечного пользователя

Скопировать только EXE на Windows без Python, в Downloads стандартного пользователя.
Выполнить `TESTING.md`, включая UAC, DPI, ошибки и повторное открытие.
Обязательно сохранить Windows build/version, account type, SHA-256 и pass/fail.
Сборка на машине разработчика или manifest сами по себе не доказывают этот сценарий.

Для контрольной суммы, где выполнять: папка готового EXE:

```powershell
Get-FileHash .\MacAddressConverter.exe -Algorithm SHA256
```

Ожидаемый результат: Hash совпадает с `SHA256SUMS.txt` именно этой сборки.

## GitHub Actions и выпуск

Workflow успешно выполнен. Он проверяет исходники в Linux,
затем в Windows выполняет полный build script. Artifact публикуется только после
успешного smoke test; автоматического GitHub Release нет.
Действия закреплены SHA-коммитами официальных репозиториев; права token — `contents: read`.

Для будущего выпуска, после оставшейся проверки Windows 10/11, выполнить в локальном git checkout:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Ожидаемый результат: tag-triggered workflow и проверенный Actions artifact.
Далее создать draft Release по этому тегу, прикрепить проверенные EXE/SHA256SUMS,
описать фактически проверенные среды и опубликовать только после проверки draft.
Версия следующего релиза изменяется только в `__init__.py`; тег обязан ей соответствовать.

## Rollback

Закрыть новую версию. Запустить сохранённый `MacAddressConverter.previous.exe`.
Ни migration, ни восстановление конфигурации, ни перезагрузка Windows не нужны.
Не использовать непроверенный старый EXE как заведомо рабочий rollback.

## Влияние и риски

Источник оценки: код проекта, PyInstaller documentation и фактический
Windows CI, зафиксированный в `VALIDATION_2026-10-05.md`.

| Область | Практическое влияние |
| --- | --- |
| Данные | Приложение не сохраняет MAC; незакопированный результат теряется при закрытии |
| Доступность | Закрытие/замена влияет только на запущенное окно утилиты |
| Производительность | Onefile добавляет этап распаковки runtime при старте; время не измерено |
| UX | При ошибке Result очищается; Copy отключается; возможные DPI проблемы ещё требуют проверки |
| Распространение | EXE без code signing может получить предупреждение политики Windows/корпоративного AV; поведение не проверено |

## Troubleshooting

| Симптом | Вероятная причина | Проверка и действие |
| --- | --- | --- |
| `pytest` пропускает GUI | Нет Tk-дисплея | Запустить `--require-gui` на Windows desktop; skipped не считать pass |
| Build script отклоняет платформу | Linux/macOS, 32-bit Python или не 3.12 | Проверить pre-check, использовать Windows CPython 3.12 x64 |
| Smoke timeout / SendInput failed | Нет интерактивного desktop или фокус перехвачен | Повторить на свободном desktop; не отключать проверку для выпуска |
| `Clipboard unavailable` | Clipboard занят или недоступен | Повторить Copy после освобождения clipboard |
| `Expected 12 hexadecimal characters` | Неверная длина после очистки разделителей | Проверить длину и что вставлен один MAC-48 |
| Tag check завершился ошибкой | Тег не совпадает с `__version__` | Исправить новый тег до публикации, не изменять опубликованный release молча |

Официальные источники проверены 05.10.2026:
[PyInstaller usage](https://pyinstaller.org/en/stable/usage.html),
[spec files](https://pyinstaller.org/en/stable/spec-files.html),
[Python 3.12.10](https://www.python.org/downloads/release/python-31210/),
[checkout](https://github.com/actions/checkout),
[setup-python](https://github.com/actions/setup-python),
[upload-artifact](https://github.com/actions/upload-artifact).
