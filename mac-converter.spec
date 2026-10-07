# Run from the repository root with Windows CPython 3.12 x64.
from pathlib import Path
from runpy import run_path
from importlib.metadata import distribution
import sys
from PyInstaller.utils.hooks import collect_data_files

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
for component, package in (("ttkbootstrap", "ttkbootstrap"), ("Pillow", "pillow")):
    installed = distribution(package)
    license_path = next(
        (installed.locate_file(path) for path in installed.files or []
         if str(path).endswith(".dist-info/licenses/LICENSE")), None,
    )
    if license_path is None or not license_path.is_file():
        raise SystemExit(f"Missing {component} license in the pinned installation")
    notices.append((str(license_path), f"third_party/{component}"))
icon_license = distribution("ttkbootstrap").locate_file("ttkbootstrap/assets/icons/LICENSE")
if not icon_license.is_file():
    raise SystemExit("Missing bundled Bootstrap Icons license")
notices.append((str(icon_license), "third_party/BootstrapIcons"))
version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=numeric_version, prodvers=numeric_version, mask=0x3F, flags=0,
        OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable("040904B0", [
                StringStruct("FileDescription", "Network Tools"),
                StringStruct("FileVersion", version),
                StringStruct("ProductName", "Network Tools"),
                StringStruct("ProductVersion", version),
                StringStruct("InternalName", "NetworkTools"),
                StringStruct("OriginalFilename", "NetworkTools.exe"),
            ])
        ]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

a = Analysis(
    [str(root / "packaging" / "gui_entry.py")],
    pathex=[str(root / "src")],
    binaries=[], datas=notices + collect_data_files("ttkbootstrap"), hiddenimports=[], hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="NetworkTools", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=True,
    manifest=str(root / "packaging" / "windows.manifest"), version=version_info,
    icon="NONE", uac_admin=False,
)
