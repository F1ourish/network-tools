# Проверка Network Tools 1.4.0

Дата: 07.10.2026. Статус: опубликовано и проверено.

- Release: https://github.com/F1ourish/network-tools/releases/tag/v1.4.0
- Source commit: `bc96f3bdc1ce0c335a438364d3517b93ce8d5a64`.
- Финальная сборка: https://github.com/F1ourish/network-tools/actions/runs/37640205382
- Среда: Windows-2025Server-10.0.26100-SP0; runner image 20260925.250.1; CPython 3.12.10 x64.
- Linux Ruff check / format и 405 non-GUI tests успешны.
- Полный Windows pytest: 496 тестов, 0 failures/errors/skipped.
- Настоящий `NetworkTools.exe`: 48 нативных проверок, все успешны.
- EXE: 20410336 байт.
- EXE SHA-256: `9f4640502b53e6ece4290c152b0cd8b4e6efc8eae85b62e29aa2ec4b1cbdb518`.
- Portable ZIP: 20186654 байт.
- ZIP SHA-256: `1dd8527a94bd147086d46f69409f57be4faf0586eb94672d10daace6d982b1d7`.

## Проверенные изменения

Нумерация физических строк и прокрутка по необходимости; очистка вставки кнопкой
и Ctrl+V; сохранение пустых строк; флажки отсутствия ACL с сохранением текста;
подсказки in/out для выбранной стороны интерфейса; точная строка, sequence и
направление ошибки; синхронизация основного и большого редактора; примеры,
очистка, Escape, Tab/Shift+Tab, Ctrl+L и обе темы.

Нативный EXE дополнительно проверен с очисткой вставки через настоящий Windows
буфер, открытием и закрытием большого редактора, заменой списка с sequence 42,
сохранением правок и включением/снятием флажков обоих направлений. Максимизация
проверена относительно Windows work area, чтобы нижние кнопки не закрывались
панелью задач. Снимки основного редактора, большого окна и ошибки на строке 19
просмотрены отдельно и доступны в [снимках](screenshots/README.md).

Object-group диагностируется явно; разбор состава группы не реализован.
Неизвестная группа останавливает проверку списка. В примере используется
CONFERENCE_NET.

Publisher сверил исходный commit и assets того же CI run. JSON и SHA-256 сверены
с метаданными опубликованных файлов. ZIP и входящий в него EXE проверены по
контрольным суммам; отчёт внутри ZIP совпадает с отдельным report asset.

К релизу приложены
[`RELEASE_VERIFICATION.json`](https://github.com/F1ourish/network-tools/releases/download/v1.4.0/RELEASE_VERIFICATION.json)
и [`SHA256SUMS.txt`](https://github.com/F1ourish/network-tools/releases/download/v1.4.0/SHA256SUMS.txt).

Целевая среда - Windows 10/11 x64. Hosted Windows Server CI не подтверждает
клиентскую приёмку, DPI 125-200% или корпоративные политики. EXE без подписи.
