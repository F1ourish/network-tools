# Third-party notices — Network Tools 1.1.0

Код приложения — MIT. Лицензии bundled runtime сохраняются отдельно и не
заменяются лицензией приложения. Оригинальные файлы входят в EXE и ZIP.

| Компонент | Версия / источник notice в Windows build |
| --- | --- |
| CPython | 3.12.10; LICENSE.txt из actual builder runtime |
| Tcl | runtime CPython; packaging/licenses/TCL-LICENSE.txt, официальный tag core-8-6-15 |
| Tk | runtime CPython; tcl/tk8.6/license.terms из actual builder runtime |
| PyInstaller bootloader | 6.22.3; COPYING.txt из закреплённого distribution |
| ttkbootstrap | 2.2.3; distribution .dist-info/licenses/LICENSE (MIT) |
| Bootstrap Icons | ttkbootstrap/assets/icons/LICENSE; полный bundled notice сохранён |
| Pillow | 12.3.0; distribution .dist-info/licenses/LICENSE, включая notices включённых компонентов |

Spec прерывает сборку при отсутствии notice. Smoke проверяет оригинальные
файлы в архиве EXE и ресурсы ttkbootstrap. Скрипт сборки извлекает те же notices
в ZIP, сохраняя их содержание. Не удалять third_party при распространении ZIP.

Официальные источники:
[Python](https://docs.python.org/3/license.html),
[Tcl](https://github.com/tcltk/tcl/blob/core-8-6-15/license.terms),
[Tk](https://github.com/tcltk/tk/blob/core-8-6-branch/license.terms),
[PyInstaller](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/COPYING.txt),
[ttkbootstrap](https://pypi.org/project/ttkbootstrap/2.2.3/),
[Pillow](https://pypi.org/project/pillow/12.3.0/).
Пакет ttkbootstrap также объявляет лицензии ресурсов MIT AND (Apache-2.0 OR
BSD-2-Clause); распространяется полный комплект notices из закреплённого пакета.
