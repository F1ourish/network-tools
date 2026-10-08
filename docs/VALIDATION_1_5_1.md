# Проверка Network Tools 1.5.1

Дата: 08.10.2026. Статус: опубликовано и проверено.

- Release: https://github.com/F1ourish/network-tools/releases/tag/v1.5.1
- Source commit: `dfddf33fb126a15a66b9fab60e8e7212438ac01a`.
- Финальная сборка: https://github.com/F1ourish/network-tools/actions/runs/37754564894
- Среда: Windows-2025Server-10.0.26100-SP0; runner image 20260925.250.1; CPython 3.12.10 x64.
- Linux Ruff check / format и 434 non-GUI tests успешны.
- Полный Windows pytest: 538 тестов, включая 104 GUI; 0 failures/errors/skipped.
- Настоящий `NetworkTools.exe`: 54 нативные проверки, все успешны.
- EXE: 20422741 байт; SHA-256: `300fdb970781ecea3545e1d7d28ef89cb0d52b4af4396f05adce87524a7a5e7c`.
- Portable ZIP: 20199551 байт; SHA-256: `f0b9849060cdda1e83df0a9281ecd7361d106084c540ffa8a3a476e386a656e4`.

## Проверенные изменения

GUI-тесты проверяют сохранение включённого и выключенного «Показать» при повторной
генерации. При отказе источника случайности прежний пароль очищается, состояние
показа сохраняется, копирование отключается.

Сброс восстанавливает точный DEFAULT_SYMBOLS после ручного изменения, пустого
и ошибочного ввода. Устаревший результат очищается; длина, выбранные группы
и исключение похожих символов сохраняют значения. Выключенная группа спецсимволов
остаётся выключенной. При стандартном наборе кнопка отключена; повторный сброс
не очищает текущий пароль.

Настоящий EXE проверен через клавиатуру и Windows clipboard: генерация с `!@`,
сброс к стандартному списку, очистка устаревшего результата, восстановление после
ввода букв и генерация с исходной политикой. Снимки интерфейса просмотрены;
пароли в них скрыты. Источник снимков: [описание](screenshots/README.md).

Publisher сверил commit и assets того же CI run. SHA-256 и размеры опубликованных
файлов совпадают со скачанными artifacts. EXE и отчёт внутри ZIP совпадают
с отдельными assets. Все контрольные суммы проверены.

[`RELEASE_VERIFICATION.json`](https://github.com/F1ourish/network-tools/releases/download/v1.5.1/RELEASE_VERIFICATION.json)
и [`SHA256SUMS.txt`](https://github.com/F1ourish/network-tools/releases/download/v1.5.1/SHA256SUMS.txt).

Целевая среда - Windows 10/11 x64; нативный стенд - Windows Server CI.
Клиентская приёмка и DPI 125-200% проверяются отдельно. EXE без цифровой подписи.
