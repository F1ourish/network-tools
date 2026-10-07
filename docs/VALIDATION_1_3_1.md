# Проверка Network Tools 1.3.1

Дата: 07.10.2026. Статус: опубликовано и проверено.

- Release: https://github.com/F1ourish/network-tools/releases/tag/v1.3.1
- Source commit: `0dac4d5d400c3ac492133bc198f6b4a8710a1631`.
- Финальная сборка: https://github.com/F1ourish/network-tools/actions/runs/37627018129
- Windows CPython 3.12.10 x64; Windows Server 2025, runner image 20260925.250.1.
- Полный pytest: 480 тестов, 0 failures/errors/skipped.
- Готовый EXE: 45 нативных проверок, все успешны.
- EXE: `NetworkTools.exe`, 20400257 байт.
- SHA-256: `fb1abb36a58aaf28435a1dccb2b9e16f541d715d92bed78b0edd57075918b337`.
- Portable ZIP: `NetworkTools-1.3.1-windows-x64.zip`, 20176035 байт.
- ZIP SHA-256: `5f568546ae7f2da65ab8666d4cf09471dbb3ebb474d9ec37c201ab05e8a25d26`.

Фактические результаты сверены с опубликованным `RELEASE_VERIFICATION.json`
и метаданными assets релиза. Linux lint/format и non-GUI tests также успешны.

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

К релизу приложены `RELEASE_VERIFICATION.json` и `SHA256SUMS.txt`.

Настройка темы сохраняется в `%APPDATA%\MacAddressConverter\settings.json`.
Старые ярлыки и скрипты запуска следует направить на `NetworkTools.exe`.

Целевая среда - Windows 10/11 x64; hosted Windows Server CI не подтверждает
клиентскую приёмку, DPI 125-200% или корпоративные политики. EXE без подписи.
