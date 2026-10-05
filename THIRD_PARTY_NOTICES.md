# Third-party notices

Код приложения лицензирован по MIT. Bundled EXE включает отдельный runtime:
CPython, Tcl/Tk и PyInstaller bootloader. Их лицензии не заменяются MIT приложения.

До распространения Windows artifact:

1. Сохранить `LICENSE.txt` из фактически используемой Windows CPython установки.
2. Tcl license сохранён в `packaging/licenses/TCL-LICENSE.txt` из официального
   `tcltk/tcl` tag `core-8-6-15`; Tk `license.terms` берётся из builder runtime.
3. Сохранить уведомления PyInstaller bootloader из закреплённой версии инструмента.
4. Проверить, что оригинальные notices входят в EXE либо приложены к release.

Сейчас Windows build не выполнен, поэтому наличие всех notices внутри
реального Windows artifact ещё не подтверждено. Предусмотрено включение notices
в `.spec`; build должен завершиться ошибкой, если исходные notices не найдены.

Официальные источники:
[CPython license](https://docs.python.org/3/license.html),
[Tcl license](https://github.com/tcltk/tcl/blob/core-8-6-15/license.terms),
[Tk license](https://github.com/tcltk/tk/blob/core-8-6-branch/license.terms),
[PyInstaller COPYING](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/COPYING.txt).
