**Network Tools 1.9.1** - наглядное отображение MAC в CUCME.

- MAC связанного ephone показан отдельной строкой **«MAC-адрес аппарата»** в карточках поиска по аппарату, DN, телефону или имени.
- В таблице занятости добавлена колонка **«MAC ephone»**. Она относится к ephone этой строки; привязка к ephone-dn определяется по button.
- Если MAC не указан, это отмечено явно. Для несозданного ephone показано «-». Совпадение номеров ephone/DN не подставляет чужой MAC.
- MAC сохраняется в обычном и развёрнутом результате, отчётах, выбранных строках и полной таблице TSV. Ширина колонки учитывает шрифт и длину адреса.

Распаковать `NetworkTools-1.9.1-windows-x64.zip` и запустить `NetworkTools.exe`.
Python не требуется. Состав конфигурации остаётся в памяти; приложение не подключается к Cisco.

Фактическая проверка сборки: [`RELEASE_VERIFICATION.json`](https://github.com/F1ourish/network-tools/releases/download/v1.9.1/RELEASE_VERIFICATION.json).
Хеши: [`SHA256SUMS.txt`](https://github.com/F1ourish/network-tools/releases/download/v1.9.1/SHA256SUMS.txt).
Целевая среда - Windows 10/11 x64; нативный стенд - Windows Server CI.
