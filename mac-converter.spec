# Run from the repository root with Windows CPython 3.12 x64.
from pathlib import Path
from runpy import run_path
from importlib.metadata import distribution
import sys

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

root = Path(SPECPATH)
version = run_path(str(root / "src" / "mac_converter" / "__init__.py"))["__version__"]
numeric_version = tuple(int(part) for part in version.split(".")) + (0,)

# Preserve notices from the actual runtime/tool installation being bundled.
notices = [(str(root / "LICENSE"), "third_party/application")]
for component, path in {
    "Python": Path(sys.base_prefix) / "LICENSE.txt",
    "Tcl": root / "packaging" / "licenses" / "TCL-LICENSE.txt",
    "Tk": Path(sys.base_prefix) / "tcl" / "tk8.6" / "license.terms",
}.items():
    if not path.is_file():
        raise SystemExit(f"Missing {component} notice in the build runtime: {path}")
    notices.append((str(path), f"third_party/{component}"))
pyinstaller_distribution = distribution("pyinstaller")
pyinstaller_notice = next(
    (pyinstaller_distribution.locate_file(path)
     for path in pyinstaller_distribution.files or []
     if str(path).endswith("COPYING.txt")), None,
)
if pyinstaller_notice is None or not pyinstaller_notice.is_file():
    raise SystemExit("Missing PyInstaller COPYING.txt in the pinned build installation")
notices.append((str(pyinstaller_notice), "third_party/PyInstaller"))
version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=numeric_version, prodvers=numeric_version, mask=0x3F, flags=0,
        OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable("040904B0", [
                StringStruct("FileDescription", "MAC Address Converter"),
                StringStruct("FileVersion", version),
                StringStruct("ProductName", "MAC Address Converter"),
                StringStruct("ProductVersion", version),
                StringStruct("OriginalFilename", "MacAddressConverter.exe"),
            ])
        ]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

a = Analysis(
    [str(root / "packaging" / "gui_entry.py")],
    pathex=[str(root / "src")],
    binaries=[], datas=notices, hiddenimports=[], hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="MacAddressConverter", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=True,
    manifest=str(root / "packaging" / "windows.manifest"), version=version_info,
    icon="NONE", uac_admin=False,
)
