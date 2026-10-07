**Network Tools 1.3.1** - новое имя Windows EXE.

### Изменено

- Standalone файл теперь называется `NetworkTools.exe`.
- Portable архив `NetworkTools-1.3.1-windows-x64.zip` содержит `NetworkTools.exe`.
- Заголовок окна - `Network Tools 1.3.1`; имя и описание в свойствах Windows согласованы.
- Сборка, CI, контрольные суммы, publisher и инструкции запуска используют новое имя.
- Нативная проверка готового EXE проверяет также OriginalFilename, InternalName,
  ProductName и FileDescription.

Функции и расчёты версии 1.3.0 сохраняют поведение. Настройка темы совместима:
используется прежний `%APPDATA%\MacAddressConverter\settings.json`.

### Обновление

Распаковать `NetworkTools-1.3.1-windows-x64.zip` в пользовательский каталог
и запустить `NetworkTools.exe`. Python не требуется. Если используется ярлык,
закрепление или скрипт запуска старого EXE, указать в нём путь к новому файлу.
Ранее опубликованные EXE версии 1.3.0 доступны в своём релизе.

### Проверка

Публикация выполняется после полного pytest с обязательными GUI-тестами,
сборки PyInstaller и проверки настоящего EXE на Windows от стандартного пользователя.
Проверяются все шесть вкладок, буфер обмена, темы, помощь, генератор паролей и перезапуск.

Фактические результаты, исходный commit, CI run и SHA-256 EXE - в
[`RELEASE_VERIFICATION.json`](https://github.com/F1ourish/network-tools/releases/download/v1.3.1/RELEASE_VERIFICATION.json).
Контрольные суммы - в
[`SHA256SUMS.txt`](https://github.com/F1ourish/network-tools/releases/download/v1.3.1/SHA256SUMS.txt).

Целевая среда - Windows 10/11 x64; нативный стенд CI - Windows Server.
Клиентские версии Windows и DPI требуют отдельной приёмки. EXE без цифровой подписи.
