"""Drive the actual EXE through Windows keyboard/clipboard APIs.

This is a developer test harness, not part of the shipped application.
It needs an interactive Windows desktop. The child receives no Python/Tcl
environment and runs from a new temporary folder containing only the EXE.
"""

import argparse
import ctypes as ct
from ctypes import wintypes as wt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET


def verify_binary(binary: Path) -> list[str]:
    import pefile
    from PyInstaller.archive.readers import CArchiveReader
    from mac_converter import __version__

    checks = []
    with pefile.PE(str(binary)) as pe:
        assert pe.FILE_HEADER.Machine == 0x8664, "Not a Windows x64 executable"
        assert pe.OPTIONAL_HEADER.Subsystem == 2, "Executable would create a console"
        checks.append("PE x64; Windows GUI subsystem (no console)")
        manifests = []
        for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if entry.id == 24:
                for name in entry.directory.entries:
                    for language in name.directory.entries:
                        data = language.data.struct
                        manifests.append(pe.get_data(data.OffsetToData, data.Size))
        levels = [
            node.attrib.get("level")
            for manifest in manifests
            for node in ET.fromstring(manifest).iter()
            if node.tag.endswith("requestedExecutionLevel")
        ]
        assert levels == ["asInvoker"], f"Unexpected execution level: {levels}"
        checks.append("Embedded manifest: asInvoker")
        assert getattr(pe, "VS_FIXEDFILEINFO", None), "Missing Windows version resource"
        fixed = pe.VS_FIXEDFILEINFO[0]
        actual_version = (
            fixed.FileVersionMS >> 16,
            fixed.FileVersionMS & 0xFFFF,
            fixed.FileVersionLS >> 16,
            fixed.FileVersionLS & 0xFFFF,
        )
        assert actual_version == tuple(int(part) for part in __version__.split(".")) + (0,)
        checks.append(f"Windows version resource matches application {__version__}")

    names = {name.lower().replace("\\", "/") for name in CArchiveReader(str(binary)).toc}
    for required in (
        "python312.dll",
        "_tkinter.pyd",
        "_tcl_data/init.tcl",
        "_tk_data/tk.tcl",
        "third_party/application/license",
        "third_party/python/license.txt",
        "third_party/tcl/tcl-license.txt",
        "third_party/tk/license.terms",
        "third_party/pyinstaller/copying.txt",
    ):
        assert required in names, f"Missing embedded runtime component: {required}"
    checks.append("Python/Tcl/Tk runtime and original third-party notices embedded")
    return checks


def run_ui_checks(binary: Path) -> tuple[list[str], list[dict]]:
    from windows_process import (
        LimitedProcess,
        assert_unprivileged,
        unprivileged_launcher,
        process_runtime,
        process_security,
    )

    user32 = ct.WinDLL("user32", use_last_error=True)
    kernel32 = ct.WinDLL("kernel32", use_last_error=True)

    class MouseInput(ct.Structure):
        _fields_ = [
            ("dx", wt.LONG),
            ("dy", wt.LONG),
            ("mouseData", wt.DWORD),
            ("dwFlags", wt.DWORD),
            ("time", wt.DWORD),
            ("dwExtraInfo", ct.c_size_t),
        ]

    class KeyboardInput(ct.Structure):
        _fields_ = [
            ("wVk", wt.WORD),
            ("wScan", wt.WORD),
            ("dwFlags", wt.DWORD),
            ("time", wt.DWORD),
            ("dwExtraInfo", ct.c_size_t),
        ]

    class HardwareInput(ct.Structure):
        _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]

    class InputUnion(ct.Union):
        _fields_ = [("mi", MouseInput), ("ki", KeyboardInput), ("hi", HardwareInput)]

    class Input(ct.Structure):
        _fields_ = [("type", wt.DWORD), ("data", InputUnion)]

    callback_type = ct.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wt.LPARAM]
    user32.EnumChildWindows.argtypes = [wt.HWND, callback_type, wt.LPARAM]
    user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ct.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ct.POINTER(wt.DWORD)]
    user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ct.c_int]
    user32.IsWindowVisible.argtypes = [wt.HWND]
    user32.SetForegroundWindow.argtypes = [wt.HWND]
    user32.GetForegroundWindow.restype = wt.HWND
    user32.ShowWindow.argtypes = [wt.HWND, ct.c_int]
    user32.GetWindowRect.argtypes = [wt.HWND, ct.POINTER(wt.RECT)]
    user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    user32.SendInput.argtypes = [wt.UINT, ct.POINTER(Input), ct.c_int]
    user32.SendInput.restype = wt.UINT
    user32.OpenClipboard.argtypes = [wt.HWND]
    user32.GetClipboardData.argtypes = [wt.UINT]
    user32.GetClipboardData.restype = wt.HANDLE
    user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
    user32.SetClipboardData.restype = wt.HANDLE
    user32.CreateWindowExW.argtypes = [
        wt.DWORD,
        wt.LPCWSTR,
        wt.LPCWSTR,
        wt.DWORD,
        ct.c_int,
        ct.c_int,
        ct.c_int,
        ct.c_int,
        wt.HWND,
        wt.HMENU,
        wt.HINSTANCE,
        wt.LPVOID,
    ]
    user32.CreateWindowExW.restype = wt.HWND
    user32.DestroyWindow.argtypes = [wt.HWND]
    kernel32.GlobalAlloc.argtypes = [wt.UINT, ct.c_size_t]
    kernel32.GlobalAlloc.restype = wt.HGLOBAL
    kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
    kernel32.GlobalLock.restype = ct.c_void_p
    kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wt.HGLOBAL]
    kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel32.OpenProcess.restype = wt.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wt.HANDLE,
        wt.DWORD,
        wt.LPWSTR,
        ct.POINTER(wt.DWORD),
    ]
    kernel32.CloseHandle.argtypes = [wt.HANDLE]

    owner = user32.CreateWindowExW(
        0, "STATIC", "MAC converter smoke clipboard", 0, 0, 0, 1, 1, None, None, None, None
    )
    if not owner:
        raise ct.WinError(ct.get_last_error())

    def wait_until(predicate, timeout=15.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = predicate()
            if result:
                return result
            time.sleep(0.05)
        raise AssertionError("Timed out waiting for the EXE or its clipboard result")

    def open_clipboard():
        wait_until(lambda: user32.OpenClipboard(owner), timeout=5)

    def read_clipboard():
        open_clipboard()
        try:
            handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
            if not handle:
                return None
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                raise ct.WinError(ct.get_last_error())
            try:
                return ct.wstring_at(pointer)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    def write_clipboard(text):
        encoded = (text + "\0").encode("utf-16-le")
        handle = kernel32.GlobalAlloc(2, len(encoded))  # GMEM_MOVEABLE
        if not handle:
            raise ct.WinError(ct.get_last_error())
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            raise ct.WinError(ct.get_last_error())
        ct.memmove(pointer, encoded, len(encoded))
        kernel32.GlobalUnlock(handle)
        open_clipboard()
        try:
            if not user32.EmptyClipboard() or not user32.SetClipboardData(13, handle):
                kernel32.GlobalFree(handle)
                raise ct.WinError(ct.get_last_error())
        finally:
            user32.CloseClipboard()

    def keys(*virtual_keys):
        events = [Input(type=1, data=InputUnion(ki=KeyboardInput(wVk=key))) for key in virtual_keys]
        events += [
            Input(type=1, data=InputUnion(ki=KeyboardInput(wVk=key, dwFlags=2)))
            for key in reversed(virtual_keys)
        ]
        inputs = (Input * len(events))(*events)
        if user32.SendInput(len(events), inputs, ct.sizeof(Input)) != len(events):
            raise AssertionError("SendInput failed; run on an interactive desktop")
        time.sleep(0.06)

    def focus_control(tab_count):
        keys(0x11, ord("L"))  # Ctrl+L
        for _ in range(tab_count):
            keys(0x09)

    def paste(value):
        focus_control(0)
        write_clipboard(value)
        keys(0x11, ord("V"))

    def assert_result(expected):
        write_clipboard("smoke clipboard sentinel")
        focus_control(6)  # Input, four radios, UPPERCASE, Result.
        keys(0x11, ord("A"))
        keys(0x11, ord("C"))
        wait_until(lambda: read_clipboard() == expected)

    def find_window(expected_path):
        matches = []

        @callback_type
        def visit(hwnd, _parameter):
            title = ct.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, len(title))
            if not title.value.startswith("MAC Address Converter ") or not user32.IsWindowVisible(
                hwnd
            ):
                return True
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ct.byref(pid))
            handle = kernel32.OpenProcess(0x1000, False, pid.value)
            if handle:
                try:
                    path = ct.create_unicode_buffer(32768)
                    size = wt.DWORD(len(path))
                    if kernel32.QueryFullProcessImageNameW(handle, 0, path, ct.byref(size)):
                        if Path(path.value).resolve() == expected_path:
                            matches.append(hwnd)
                finally:
                    kernel32.CloseHandle(handle)
            return True

        user32.EnumWindows(visit, 0)
        return matches[0] if matches else None

    def describe_windows(expected_path):
        windows = []

        @callback_type
        def visit(hwnd, _parameter):
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ct.byref(pid))
            handle = kernel32.OpenProcess(0x1000, False, pid.value)
            if not handle:
                return True
            try:
                path = ct.create_unicode_buffer(32768)
                size = wt.DWORD(len(path))
                if not kernel32.QueryFullProcessImageNameW(handle, 0, path, ct.byref(size)):
                    return True
                if Path(path.value).resolve() != expected_path or not user32.IsWindowVisible(hwnd):
                    return True
                title = ct.create_unicode_buffer(4096)
                user32.GetWindowTextW(hwnd, title, len(title))
                children = []

                @callback_type
                def child(child_hwnd, _child_parameter):
                    text = ct.create_unicode_buffer(8192)
                    user32.GetWindowTextW(child_hwnd, text, len(text))
                    if text.value:
                        children.append(text.value)
                    return True

                user32.EnumChildWindows(hwnd, child, 0)
                windows.append(
                    {"hwnd": hwnd, "pid": pid.value, "title": title.value, "text": children}
                )
            finally:
                kernel32.CloseHandle(handle)
            return True

        user32.EnumWindows(visit, 0)
        return windows

    def save_screenshot(hwnd, destination):
        rectangle = wt.RECT()
        if not user32.GetWindowRect(hwnd, ct.byref(rectangle)):
            raise ct.WinError(ct.get_last_error())
        destination.parent.mkdir(exist_ok=True)
        escaped = str(destination.resolve()).replace("'", "''")
        script = "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                "Add-Type -AssemblyName System.Drawing",
                f"$image = [System.Drawing.Bitmap]::new({rectangle.right - rectangle.left}, {rectangle.bottom - rectangle.top})",
                "$drawing = [System.Drawing.Graphics]::FromImage($image)",
                "try {",
                f"$drawing.CopyFromScreen({rectangle.left}, {rectangle.top}, 0, 0, $image.Size)",
                f"$image.Save('{escaped}', [System.Drawing.Imaging.ImageFormat]::Png)",
                "} finally { $drawing.Dispose(); $image.Dispose() }",
            )
        )
        powershell = (
            Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
            creationflags=0x08000000,
        )
        assert destination.is_file(), "Screenshot was not saved"

    checks = []
    execution_tokens = []
    previous_text = read_clipboard()
    environment = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "TCL_LIBRARY", "TK_LIBRARY", "VIRTUAL_ENV"):
        environment.pop(key, None)
    environment["PATH"] = str(Path(environment.get("SystemRoot", "C:/Windows")) / "System32")
    try:
        with tempfile.TemporaryDirectory(prefix="MAC portable тест ") as temporary:
            application = Path(temporary) / "application"
            application.mkdir()
            isolated = application / binary.name
            for key in ("TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"):
                folder = Path(temporary) / key.lower()
                folder.mkdir()
                environment[key] = str(folder)
            shutil.copy2(binary, isolated)
            with unprivileged_launcher(Path(temporary)) as launch_unprivileged:
                for launch in range(2):
                    process = launch_unprivileged(isolated, str(application), environment)
                    hwnd = None
                    try:

                        def appeared():
                            assert process.poll() is None, (
                                f"EXE exited before showing a window: {process.returncode}"
                            )
                            return find_window(isolated.resolve())

                        hwnd = wait_until(appeared, timeout=60)
                        user32.ShowWindow(hwnd, 9)
                        user32.SetForegroundWindow(hwnd)
                        wait_until(lambda: user32.GetForegroundWindow() == hwnd)
                        pid = wt.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ct.byref(pid))
                        security = process_security(pid.value)
                        assert_unprivileged(security)
                        security["runtime_dlls"] = process_runtime(pid.value)
                        execution_tokens.append(security)
                        checks.append(
                            f"Launch {launch + 1}: GUI in isolated folder with spaces/Unicode"
                        )
                        checks.append(
                            f"Launch {launch + 1}: non-elevated, no enabled admin SID, medium integrity"
                        )
                        checks.append(
                            f"Launch {launch + 1}: Python/Tcl/Tk DLLs loaded from the EXE bundle"
                        )
                        if launch == 1:
                            paste("AABB.CCDD.EEFF")
                            assert_result("aa:bb:cc:dd:ee:ff")
                            checks.append("Reopen: default Colon/lowercase restored")
                            continue

                        paste("0011.2233.aabb")
                        assert_result("00:11:22:33:aa:bb")
                        checks.append("Ctrl+L / Ctrl+V / Ctrl+A / Ctrl+C; live Colon conversion")
                        save_screenshot(hwnd, Path("smoke-results/windows-exe.png"))
                        checks.append("Screenshot of actual EXE saved")
                        for tabs, expected in (
                            (1, "0011.2233.aabb"),
                            (3, "00-11-22-33-aa-bb"),
                            (4, "00112233aabb"),
                            (2, "00:11:22:33:aa:bb"),
                        ):
                            focus_control(tabs)
                            keys(0x20)
                            assert_result(expected)
                        checks.append("Cisco, Hyphen, Plain and Colon selection")
                        focus_control(5)
                        keys(0x20)
                        assert_result("00:11:22:33:AA:BB")
                        focus_control(1)
                        keys(0x20)
                        assert_result("0011.2233.AABB")
                        checks.append("UPPERCASE in Colon and Cisco")

                        write_clipboard("copy button sentinel")
                        focus_control(7)
                        keys(0x20)
                        wait_until(lambda: read_clipboard() == "0011.2233.AABB")
                        checks.append("Copy button: clipboard contains only formatted result")

                        paste("00:11:22:ZZ:44:55")
                        assert_result("smoke clipboard sentinel")
                        assert user32.IsWindowVisible(hwnd), "Invalid input closed the application"
                        paste("aabb.ccdd.eeff")
                        assert_result("AABB.CCDD.EEFF")
                        checks.append("Invalid input clears result; application recovers")
                    except BaseException as error:
                        target = Path("smoke-results")
                        target.mkdir(exist_ok=True)
                        windows = describe_windows(isolated.resolve())
                        diagnostic = {
                            "error": str(error),
                            "process_exit": process.poll(),
                            "windows": windows,
                        }
                        (target / "failure.json").write_text(
                            json.dumps(diagnostic, indent=2), encoding="utf-8"
                        )
                        print(f"EXE smoke failure: {json.dumps(diagnostic)}", flush=True)
                        if windows:
                            try:
                                save_screenshot(windows[0]["hwnd"], target / "failure.png")
                            except Exception as capture_error:
                                print(
                                    f"Failure screenshot unavailable: {capture_error}", flush=True
                                )
                        raise
                    finally:
                        failed = sys.exc_info()[0] is not None
                        if hwnd:
                            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
                        try:
                            if not failed:
                                assert process.returncode == 0, (
                                    f"EXE exited with {process.returncode}"
                                )
                        finally:
                            if isinstance(process, LimitedProcess):
                                process.close()
            checks.append("Close and restart: exit code 0")
            assert list(application.iterdir()) == [isolated], "EXE wrote files beside itself"
            checks.append("Portable application folder still contains only the EXE")
    finally:
        if previous_text is not None:
            write_clipboard(previous_text)
        user32.DestroyWindow(owner)
    return checks, execution_tokens


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Run this harness with Windows Python on an interactive desktop")
    binary = args.binary.resolve()
    checks = verify_binary(binary)
    ui_checks, execution_tokens = run_ui_checks(binary)
    checks.extend(ui_checks)
    report = {
        "binary": binary.name,
        "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "passed": True,
        "environment": {"python": sys.version, "platform": sys.platform},
        "checks": checks,
        "execution_tokens": execution_tokens,
        "limit": "Tested on a Windows runner using a non-elevated medium token; clean Windows client, Defender and SmartScreen behavior are not covered.",
    }
    target = Path("smoke-results")
    target.mkdir(exist_ok=True)
    (target / "windows-exe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"EXE smoke: {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
