# Сборка и выпуск Network Tools

Версия документа: 2.0; дата: 06.10.2026; контур: Windows / GitHub Actions.

Выпуск проходит через тесты исходников, запуск готового EXE и проверку hashes.
Публикуется точный source commit, для которого Windows job сформировал assets.
Целевая версия - 1.3.0; статус конкретной проверки - VALIDATION_1_3_0.md.

## Подготовка и сборка

Среда: Windows CPython 3.12.10 x64 с Tcl/Tk, интерактивный desktop.
Локальный PowerShell запускать без elevation. Репозиторий распаковать в новый
каталог; предыдущий рабочий EXE сохранить отдельно для rollback.

```powershell
py -3.12 -c "import sys,struct,tkinter; print(sys.version); print(struct.calcsize('P')*8); print(tkinter.TkVersion)"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -e .
.\.venv\Scripts\python.exe -m ruff check src tests scripts packaging/gui_entry.py
.\.venv\Scripts\python.exe -m ruff format --check src tests scripts packaging/gui_entry.py
.\.venv\Scripts\python.exe scripts/build_windows.py
```

Pre-check должен показать 3.12.10, 64 bit и доступный Tk. Скрипт отклоняет другую
платформу/версию, запускает pytest --require-gui и сохраняет JUnit XML.
PyInstaller создаёт onefile EXE без console, UPX и elevation. Оригинальные
notices runtime и UI assets проверяются перед сборкой и в готовом архиве.

Win32 smoke запускает EXE в новой папке с пробелами/кириллицей, только EXE,
без Python/Tcl переменных и Python в PATH. Проверяет реальный process token
и DLL, MAC, IPv4, MSS, LPM, wildcard, clipboard, clear/recovery, темы и reopen.
В hosted CI временно используется обычная учётная запись; она удаляется после
проверки и не является компонентом поставки.

## Результат успешной сборки

| Файл | Назначение |
| --- | --- |
| dist/MacAddressConverter.exe | Standalone GUI x64 |
| dist/NetworkTools-1.3.0-windows-x64.zip | EXE, инструкция, notices и verification report |
| dist/RELEASE_VERIFICATION.json | Version, source commit, runner, dependencies, pytest summary, actual smoke checks |
| dist/SHA256SUMS.txt | SHA-256 EXE, ZIP и verification JSON |
| smoke-results/pytest.xml | Фактические результаты pytest |
| smoke-results/*.png | Скриншоты реально запущенного EXE |
| smoke-results/windows-exe.json | Подробности EXE проверки и токена |

ZIP и sums создаются только после successful smoke. Failed job не публикует
релиз; failure.json и screenshot сохраняются как диагностический artifact.
Проверка hashes в PowerShell:

```powershell
Get-FileHash .\dist\MacAddressConverter.exe -Algorithm SHA256
Get-FileHash .\dist\NetworkTools-1.3.0-windows-x64.zip -Algorithm SHA256
Get-Content .\dist\SHA256SUMS.txt
```

Hash сравнивается с тем же asset релиза. Изменение EXE после проверки недопустимо.
Процесс воспроизводим по шагам; byte-for-byte reproducibility не заявляется.

## GitHub Actions и публикация

Workflow запускается на ветках, pull requests, тегах v* и вручную.
Linux проверяет Ruff и все non-GUI tests. Windows обязательно выполняет GUI
и готовый EXE smoke. Ветка candidate позволяет проверить изменения до main.

Для нового выпуска обновить __version__, changelog и release notes; сначала
получить successful candidate CI, затем fast-forward main на проверенные
изменения. Commit main с явной меткой `[release]` включает publish-release job.
Обычные push и candidate не публикуют Release. CI сначала заново проверяет
точный main commit и строит assets, затем download-artifact передаёт их publisher.

Каждый успешный Windows job загружает три отдельных artifact:

| Artifact | Содержимое при распаковке |
| --- | --- |
| MacAddressConverter-windows-x64-<ref> | MacAddressConverter.exe в корне |
| MacAddressConverter-portable-<ref> | NetworkTools-1.3.0-windows-x64.zip в корне |
| MacAddressConverter-verification-<ref> | dist/SHA256SUMS.txt, dist/RELEASE_VERIFICATION.json и smoke-results/ |

Publisher скачивает первые два artifact в verified/dist, третий в verified.
Таким образом четыре файла поставки находятся в одном verified/dist;
диагностические PNG и JUnit XML остаются отдельно. Artifact выбираются по имени
и относятся к тому же workflow run, без поиска сборки на другой ветке.

Только publish job получает contents:write. Скрипт проверяет список/checksums
assets, версию, source commit, successful smoke и hash проверенного EXE.
`gh release create` создаёт v<version> для точного github.sha и прикладывает
четыре assets. Existing release/tag не перезаписывается; при занятой версии
устранить причину и выпустить новую версию. Тег при отдельном tag build должен
совпадать с __version__. Текст release notes хранится в docs/RELEASE_1_1_0.md.

После выпуска проверить страницу Release, target commit, имена и hashes assets.
GitHub artifact имеет retention; Release assets являются основной поставкой.

## Rollback и диагностика

Закрыть новую версию и запустить сохранённый проверенный предыдущий EXE.
Настройка темы совместима и не содержит адресов; для её сброса можно переименовать
settings.json. Не заменять опубликованные assets без нового номера версии.

| Симптом | Проверка и действие |
| --- | --- |
| GUI tests skipped | Использовать --require-gui на интерактивном desktop |
| Версия builder отвергнута | Проверить Python 3.12.10 x64 и Tcl/Tk |
| Smoke timeout / SendInput failed | Проверить desktop и фокус, смотреть failure.json/png; не отключать smoke |
| Clipboard unavailable | Освободить clipboard и повторить Copy |
| Тема не сохраняется | Проверить доступ к APPDATA; расчёты продолжают работать |
| Publish hash/commit mismatch | Проверить assets того же workflow run; чужой artifact не публиковать |
| Release уже существует | Использовать новый номер версии, не clobber опубликованные файлы |

Источник ограничений: actual CI и код. Windows client acceptance, разные DPI,
Defender/SmartScreen не покрываются hosted server CI. Onefile стартует с
распаковкой TEMP; EXE без подписи, поведение корпоративных политик не проверено.

Release notes выбираются автоматически: docs/RELEASE_<version с подчёркиваниями>.md.
Пароли smoke-стенда не включаются в отчёты и screenshots.
