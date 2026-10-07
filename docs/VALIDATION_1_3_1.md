# Проверка Network Tools 1.3.1

Дата: 07.10.2026. Статус: подготовлено к проверке; результаты 1.3.1 ещё не подтверждены.

В этой версии изменяется именование standalone EXE, окна, Windows version resources
и связанных файлов сборки. Функции версии 1.3.0 сохраняют поведение.

## Обязательные проверки выпуска

- Ruff check / format и все тесты расчётов на Linux.
- Полный pytest на Windows с `--require-gui`, без пропусков GUI.
- Сборка настоящего `NetworkTools.exe` через PyInstaller.
- Проверка x64/windowed/asInvoker, версии и имён OriginalFilename/InternalName/ProductName/FileDescription.
- Запуск EXE от стандартного пользователя в папке с пробелами и кириллицей.
- Все шесть вкладок, русская раскладка, буфер обмена, темы, помощь и перезапуск.
- ZIP содержит `NetworkTools.exe`; отчёт и SHA256SUMS ссылаются на новый файл.
- Publisher получает файлы того же CI run, проверяет исходный commit и контрольные суммы.

После проверки фактические результаты фиксируются в этом документе.
При публикации прилагаются `RELEASE_VERIFICATION.json` и `SHA256SUMS.txt`.

Настройка темы сохраняется в `%APPDATA%\MacAddressConverter\settings.json`.
Старые ярлыки и скрипты запуска следует направить на `NetworkTools.exe`.

Целевая среда - Windows 10/11 x64; hosted Windows Server CI не подтверждает
клиентскую приёмку, DPI 125-200% или корпоративные политики. EXE без подписи.
