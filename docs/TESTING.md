# План Windows acceptance test

Версия: 1.0; дата: 05.10.2026; статус: pending.

Краткий вывод: этот checklist относится к **EXE из dist/artifact**, а не к запуску
Python-кода. Пока он не выполнен, Definition of Done из ТЗ не достигнут.

## Зафиксировать среду

- Windows edition/version/build и масштаб экрана.
- Тип учётной записи: стандартный пользователь, без elevation.
- Установлен ли Python: для portable acceptance — отсутствует.
- Путь EXE: пользовательский Downloads; дополнительно папка с пробелами и кириллицей.
- SHA-256 конкретного EXE и источник artifact.

## Проверки

| № | Действие | Ожидаемый результат | Факт |
| --- | --- | --- | --- |
| 1 | Запустить двойным кликом | Компактный GUI, без Python console и UAC elevation | Pending |
| 2 | Проверить пустое окно | Colon, lowercase, Status Ready, Copy disabled | Pending |
| 3 | Ctrl+V: `0011.2233.aabb` | Сразу `00:11:22:33:aa:bb` | Pending |
| 4 | Cisco | `0011.2233.aabb` | Pending |
| 5 | Hyphen | `00-11-22-33-aa-bb` | Pending |
| 6 | Plain | `00112233aabb` | Pending |
| 7 | UPPERCASE в Colon и Cisco | `00:11:22:33:AA:BB`, `0011.2233.AABB` | Pending |
| 8 | Выключить UPPERCASE | Результат возвращается к lowercase | Pending |
| 9 | Copy, вставка в Notepad | Только результат, Status Copied | Pending |
| 10 | Ввести `00:11:22:ZZ:44:55` | Result пустой, Copy disabled, ошибка, GUI работает | Pending |
| 11 | Ввести `123`, EUI-64, `hello` | Понятная ошибка без traceback | Pending |
| 12 | Очистить Input | Result пустой, Ready, Copy disabled | Pending |
| 13 | Снова вставить корректный MAC | GUI восстанавливает корректный результат | Pending |
| 14 | Ctrl+A/C в Result, Ctrl+L в Input | Выделение/копирование и переход работают | Pending |
| 15 | Закрыть и открыть повторно | Окно работает, история не восстанавливается | Pending |
| 16 | Запуск без Python, venv и исходников | EXE работает самостоятельно | Pending |
| 17 | Запуск из пути с кириллицей и пробелами | Все предыдущие операции работают | Pending |
| 18 | Масштаб 100%, 125%, 150% | Текст/поля/Copy/Status видимы, fullscreen не нужен | Pending |
| 19 | Снять screenshot рабочего EXE | Добавить настоящий screenshot в README | Pending |

Не подменять pending результатом предположения. Автоматический harness проверяет
PE/manifest/runtime, запуск, keyboard conversion, форматы, uppercase, Copy,
ошибку и reopen; standard-user/UAC, отсутствие установленного Python,
политики Windows и DPI проверяются отдельно.

## Закрытие проверки

Внести pass/fail и среду в новый validation report. Приложить stdout pytest,
`windows-exe.json`, SHA256SUMS и реальный screenshot. После устранения проблем
повторять соответствующий тест, а не весь checklist без необходимости.
