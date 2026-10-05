# Original license texts

`TCL-LICENSE.txt` — исходный текст из официального репозитория Tcl,
tag `core-8-6-15`:
https://raw.githubusercontent.com/tcltk/tcl/core-8-6-15/license.terms

`PYTHON-LICENSE.txt` — оригинальный `LICENSE.txt` из `exe.msi` официального
Windows installer CPython 3.12.10:
https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe

Тексты сохранены без изменений. Windows installer Python 3.12.10 содержит
Tcl 8.6.15 (проверено по `tcl/tcl8.6/init.tcl`). Tcl notice в его MSI отсутствует,
поэтому для Tcl `.spec` использует сохранённый исходный текст.
Python/Tk notices и PyInstaller COPYING берутся из фактической builder-установки;
это не проверка наличия notices внутри готового EXE — он ещё не собран.
