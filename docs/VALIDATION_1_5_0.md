# Проверка Network Tools 1.5.0

Дата: 08.10.2026. Статус: опубликовано и проверено.

- Release: https://github.com/F1ourish/network-tools/releases/tag/v1.5.0
- Source commit: `8f1a0c3e36558a85b29db4d132c8699ec62d8b7d`.
- Финальная сборка: https://github.com/F1ourish/network-tools/actions/runs/37745215699
- Среда: Windows-2025Server-10.0.26100-SP0; runner image 20260925.250.1; CPython 3.12.10 x64.
- Linux Ruff check / format и 434 non-GUI tests успешны.
- Полный Windows pytest: 530 тестов, 0 failures/errors/skipped.
- Настоящий `NetworkTools.exe`: 52 нативные проверки, все успешны.
- EXE: 20420776 байт; SHA-256: `ed519a23b46ff8cbe09a85809d140997f81efaea2906d9b1cdb373f7ea053a6f`.
- Portable ZIP: 20196684 байт; SHA-256: `cf025fc9947e7d30a381a1a3988e36741324fb8bd96eb8acdcafffd7969b4be6`.

## Проверенные изменения

IOS network object-group: hosts, маски подсети/CIDR, any, вложенные группы,
forward references и дубликаты участников. Сопоставление источника/назначения,
порты, first match, sequence исходного правила и совпавший участник в заключении.
Missing/empty/duplicate/cycle/unsupported состав не даёт частичного разрешения.
Номер ошибки подсвечивается в редакторе IP-групп. Изменение состава сразу очищает
старый вывод и меняет решение; Escape/повторное открытие сохраняют текст.
Ctrl+L и видимость нижних кнопок большого окна проверены отдельно.

Настоящий EXE: полный show access-lists через Windows clipboard, удаление prompts,
команд и counters при сохранении типа/имени; окно групп с несколькими именами и
вложением; обе ACL с source/destination groups; замена состава меняет permit на deny;
цикл очищает заключение, исправленный состав восстанавливает результат без перезапуска.
Максимизация окна проверена относительно Windows work area. Снимки настоящего EXE
просмотрены и доступны в [снимках](screenshots/README.md).

Publisher сверил commit и assets того же CI run. Метаданные опубликованных файлов
совпадают с SHA-256/размерами скачанных artifacts. ZIP содержит NetworkTools.exe,
его digest совпадает с отдельным asset; отчёт внутри ZIP совпадает с отдельным report.

[`RELEASE_VERIFICATION.json`](https://github.com/F1ourish/network-tools/releases/download/v1.5.0/RELEASE_VERIFICATION.json)
и [`SHA256SUMS.txt`](https://github.com/F1ourish/network-tools/releases/download/v1.5.0/SHA256SUMS.txt).

Целевая среда - Windows 10/11 x64; нативный стенд - Windows Server CI.
Клиентская приёмка и DPI 125-200% проверяются отдельно. EXE без цифровой подписи.
