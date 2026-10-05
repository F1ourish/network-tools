# Windows acceptance test

Версия: 1.1; дата: 05.10.2026; статус: **server CI и standard-user EXE smoke прошли**;
clean Windows 10/11 и DPI остаются непроверенными.

[Фактический CI](https://github.com/F1ourish/mac-address-converter/actions/runs/37349926876): 81 pytest-тест, включая 12 тестов исходного Tk GUI,
и 19 проверок готового EXE. В таблице разделены доказательства для EXE и исходного GUI.
Для повторной клиентской проверки использовать тот же EXE с SHA-256 из validation report.

## Зафиксировать среду новой проверки

- Windows edition/version/build, локаль и масштаб экрана.
- Тип учётной записи: стандартный пользователь, без elevation.
- Установлен ли Python: для clean-client acceptance — отсутствует.
- Путь EXE: пользовательский Downloads; дополнительно папка с пробелами и кириллицей.
- SHA-256 конкретного EXE и источник artifact.

## Проверки

| № | Действие | Ожидаемый результат | Факт на 05.10.2026 |
| --- | --- | --- | --- |
| 1 | Запустить EXE | Компактный GUI, без console и elevation | EXE: passed на Server 2025; двойной клик на Windows 10/11 не проверен |
| 2 | Проверить пустое окно | Colon, lowercase, Ready, Copy disabled | Исходный Tk GUI: passed; defaults после reopen EXE: passed |
| 3 | Ctrl+V: `0011.2233.aabb` | Сразу `00:11:22:33:aa:bb` | EXE: passed |
| 4 | Cisco | `0011.2233.aabb` | EXE: passed |
| 5 | Hyphen | `00-11-22-33-aa-bb` | EXE: passed |
| 6 | Plain | `00112233aabb` | EXE: passed |
| 7 | UPPERCASE в Colon и Cisco | `00:11:22:33:AA:BB`, `0011.2233.AABB` | EXE: passed |
| 8 | Выключить UPPERCASE | Возврат lowercase | Исходный Tk GUI: passed |
| 9 | Copy и чтение clipboard | Только результат, Copied | EXE: содержимое passed; статус проверен Tk GUI |
| 10 | `00:11:22:ZZ:44:55` | Пустой Result, Copy disabled, ошибка, GUI работает | EXE: clear/recovery passed; disabled/status проверены Tk GUI |
| 11 | `123`, EUI-64, `hello` | Понятная ошибка без traceback | Validation unit tests: passed; GUI длины `123`: passed |
| 12 | Очистить Input | Пустой Result, Ready, Copy disabled | Исходный Tk GUI: passed |
| 13 | Снова корректный MAC | Корректный результат | EXE: passed |
| 14 | Ctrl+A/C в Result, Ctrl+L в Input | Выделение/копирование/переход | EXE: passed |
| 15 | Закрыть и открыть | Окно работает, default Colon/lowercase | EXE: passed, оба exit code 0 |
| 16 | Без исходников, venv и Python PATH | EXE работает со своим runtime | EXE: passed, DLL из `_MEI...`; физически чистый client pending |
| 17 | Папка с кириллицей и пробелами | Все операции работают | EXE: passed от стандартной учётной записи |
| 18 | Масштаб 100%, 125%, 150% | Поля/Copy/Status видимы без fullscreen | Pending: отдельная DPI-проверка не выполнена |
| 19 | Снять screenshot EXE | Настоящий screenshot в README | Passed, `docs/screenshot.png` |

## Как работает автоматический стенд

Harness проверяет PE/manifest/version, runtime/licenses, токен процесса,
загруженные DLL, keyboard conversion, форматы, uppercase, clipboard, ошибку и reopen.
У обоих GUI процессов: `elevated=false`, `administrators_enabled=false`,
`integrity_rid=8192`. На hosted CI используется временная стандартная учётная
запись; она удаляется после теста. На локальной машине тест запускать из обычного
PowerShell без elevation. Никакая инфраструктура стенда не входит в EXE.

Server CI не доказывает работу всех клиентских Windows, разные DPI или результат
Defender/SmartScreen. Эти пункты не отмечать passed без фактической проверки.

## Закрытие клиентской проверки

Записать pass/fail, среду, SHA-256 и настоящий screenshot в новый validation report.
После исправления повторять соответствующую проверку. Приложить stdout pytest,
`windows-exe.json` и SHA256SUMS, не подменять реальный запуск кодом из Python.
