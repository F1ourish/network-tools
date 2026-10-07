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
        "third_party/ttkbootstrap/license",
        "third_party/pillow/license",
        "third_party/bootstrapicons/license",
    ):
        assert required in names, f"Missing embedded runtime component: {required}"
    assert any(
        name.startswith("ttkbootstrap/assets/") and name.endswith(".ttf") for name in names
    ), "Missing ttkbootstrap icon font"
    checks.append("Python/Tcl/Tk, ttkbootstrap fonts and original third-party notices embedded")
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
    user32.GetDpiForWindow.argtypes = [wt.HWND]
    user32.GetDpiForWindow.restype = wt.UINT
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
    user32.PeekMessageW.argtypes = [ct.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
    user32.TranslateMessage.argtypes = [ct.POINTER(wt.MSG)]
    user32.DispatchMessageW.argtypes = [ct.POINTER(wt.MSG)]
    user32.DispatchMessageW.restype = ct.c_ssize_t
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
            # Our hidden clipboard-owner window must service WM_DESTROYCLIPBOARD
            # while the EXE replaces its contents. Otherwise Tk's idle clipboard
            # update can wait for this thread while this thread waits for Tk.
            message = wt.MSG()
            while user32.PeekMessageW(ct.byref(message), None, 0, 0, 1):
                user32.TranslateMessage(ct.byref(message))
                user32.DispatchMessageW(ct.byref(message))
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
        extended = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}
        events = [
            Input(type=1, data=InputUnion(ki=KeyboardInput(wVk=key, dwFlags=int(key in extended))))
            for key in virtual_keys
        ]
        events += [
            Input(
                type=1, data=InputUnion(ki=KeyboardInput(wVk=key, dwFlags=2 | int(key in extended)))
            )
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

    def copy_tool(*fragments):
        write_clipboard("tool copy sentinel")

        def matching_report():
            # Editors invalidate old reports immediately, then debounce parsing.
            # Retry the user action once the new report becomes available.
            keys(0x11, 0x10, ord("C"))
            value = read_clipboard()
            return value if value and all(fragment in value for fragment in fragments) else None

        return wait_until(matching_report)

    def paste_control(tab_count, value):
        focus_control(tab_count)
        keys(0x11, ord("A"))
        write_clipboard(value)
        keys(0x11, ord("V"))

    def select_choice(tab_count, index):
        focus_control(tab_count)
        keys(0x28)  # Down opens a readonly combobox.
        keys(0x11, 0x24)  # Ctrl+Home selects the first item; Home scrolls horizontally.
        for _ in range(index):
            keys(0x28)
        keys(0x0D)

    def russian_clipboard_check(hwnd):
        user32.LoadKeyboardLayoutW.argtypes = [wt.LPCWSTR, wt.UINT]
        user32.LoadKeyboardLayoutW.restype = wt.HANDLE
        user32.GetKeyboardLayout.argtypes = [wt.DWORD]
        user32.GetKeyboardLayout.restype = wt.HANDLE
        thread = user32.GetWindowThreadProcessId(hwnd, None)
        original = user32.GetKeyboardLayout(thread)
        russian = user32.LoadKeyboardLayoutW("00000419", 0)
        assert russian, "Russian keyboard layout could not be loaded"
        try:
            user32.PostMessageW(hwnd, 0x50, 0, russian)  # WM_INPUTLANGCHANGEREQUEST.
            wait_until(lambda: user32.GetKeyboardLayout(thread) == russian)
            focus_control(0)  # Ctrl+L must work in this layout too.
            keys(0x11, ord("A"))
            write_clipboard("aabb.ccdd.eeff")
            keys(0x11, ord("V"))
            copy_tool("aa:bb:cc:dd:ee:ff")
        finally:
            user32.PostMessageW(hwnd, 0x50, 0, original)
            wait_until(lambda: user32.GetKeyboardLayout(thread) == original)

    def assert_invalid_copy():
        write_clipboard("invalid tool sentinel")
        keys(0x11, 0x10, ord("C"))
        assert read_clipboard() == "invalid tool sentinel", "Invalid tool copied a stale result"

    def find_window(expected_path, title_prefix="MAC Address Converter "):
        matches = []

        @callback_type
        def visit(hwnd, _parameter):
            title = ct.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, len(title))
            if not title.value.startswith(title_prefix) or not user32.IsWindowVisible(hwnd):
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
                    password_test_started = False
                    expect_clipboard_clear_on_close = False
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
                        security["display"] = {
                            "width": user32.GetSystemMetrics(0),
                            "height": user32.GetSystemMetrics(1),
                            "window_dpi": user32.GetDpiForWindow(hwnd),
                        }
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
                            keys(0x11, ord("2"))
                            copy_tool("Подсеть CIDR: 192.168.1.0/24", "Wildcard: 0.0.0.255")
                            save_screenshot(hwnd, Path("smoke-results/ipv4-night-reopen.png"))
                            assert json.loads(
                                (
                                    Path(environment["APPDATA"])
                                    / "MacAddressConverter/settings.json"
                                ).read_text()
                            ) == {"theme": "night"}
                            checks.append(
                                "Reopen: saved night theme; IPv4 defaults restored; entered addresses not persisted"
                            )
                            keys(0x11, ord("6"))
                            assert_invalid_copy()
                            checks.append("Reopen: password is empty, not persisted")
                            continue

                        paste("0011.2233.aabb")
                        assert_result("00:11:22:33:aa:bb")
                        checks.append("Ctrl+L / Ctrl+V / Ctrl+A / Ctrl+C; live Colon conversion")
                        russian_clipboard_check(hwnd)
                        checks.append(
                            "Russian keyboard layout: Ctrl+L/A/V and Ctrl+Shift+C through Win32"
                        )
                        paste("0011.2233.aabb")
                        focus_control(0)
                        keys(0x11, ord("A"))
                        write_clipboard("00112233aabb")
                        keys(0x10, 0x79)  # Shift+F10, native context menu.
                        keys(0x24)  # Home: Cut (selection is present).
                        keys(0x28)
                        keys(0x28)  # Paste.
                        keys(0x0D)
                        copy_tool("00:11:22:33:aa:bb")
                        checks.append(
                            "Context menu paste replaces selection without duplicate insertion"
                        )
                        paste("0011.2233.aabb")
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

                        keys(0x11, ord("2"))
                        copy_tool(
                            "Адрес подсети: 192.168.1.0",
                            "Первый хост: 192.168.1.1",
                            "Последний хост: 192.168.1.254",
                            "Broadcast подсети: 192.168.1.255",
                            "Полная маска: 255.255.255.0",
                            "Wildcard: 0.0.0.255",
                            "Двоичная маска: 11111111.11111111.11111111.00000000",
                        )
                        save_screenshot(hwnd, Path("smoke-results/ipv4-day.png"))
                        checks.append(
                            "IPv4 defaults: subnet, hosts, broadcast, full/binary mask and wildcard"
                        )
                        focus_control(28)
                        keys(0x20)
                        host_hwnd = wait_until(lambda: find_window(isolated.resolve(), "Адреса: "))
                        user32.SetForegroundWindow(host_hwnd)
                        wait_until(lambda: user32.GetForegroundWindow() == host_hwnd)
                        write_clipboard("host page sentinel")
                        keys(0x11, ord("A"))
                        keys(0x11, ord("C"))
                        wait_until(
                            lambda: (text := read_clipboard())
                            and len(text.splitlines()) == 100
                            and text.splitlines()[0] == "192.168.1.1"
                        )
                        keys(0x09)  # First page: disabled Previous is skipped, focus Next.
                        keys(0x20)
                        keys(0x10, 0x09)  # Previous is now enabled.
                        keys(0x10, 0x09)  # Back to the readonly host list.
                        write_clipboard("host second-page sentinel")
                        keys(0x11, ord("A"))
                        keys(0x11, ord("C"))
                        wait_until(
                            lambda: (text := read_clipboard())
                            and text.splitlines()[0] == "192.168.1.101"
                        )
                        for _ in range(3):
                            keys(0x09)  # Previous, Next, page number.
                        keys(0x11, ord("A"))
                        write_clipboard("3")
                        keys(0x11, ord("V"))
                        keys(0x09)
                        keys(0x20)  # Go to page 3.
                        keys(0x09)
                        write_clipboard("host last-page sentinel")
                        keys(0x20)  # Copy current page button.
                        wait_until(
                            lambda: (text := read_clipboard())
                            and len(text.splitlines()) == 54
                            and text.splitlines()[-1] == "192.168.1.254"
                        )
                        save_screenshot(host_hwnd, Path("smoke-results/hosts-day.png"))
                        user32.PostMessageW(host_hwnd, 0x0010, 0, 0)
                        user32.SetForegroundWindow(hwnd)
                        wait_until(lambda: user32.GetForegroundWindow() == hwnd)
                        checks.append(
                            "Host dialog: first/second/last page, jump and page copy through the EXE"
                        )
                        paste("10.20.30.40/16")
                        copy_tool("Подсеть CIDR: 10.20.0.0/16", "Первый хост: 10.20.0.1")
                        paste_control(1, "255.0.255.0")
                        assert_invalid_copy()
                        paste_control(1, "/24")
                        copy_tool("Подсеть CIDR: 10.20.30.0/24")
                        checks.append(
                            "IPv4 CIDR paste, mask override, invalid-mask clear and recovery"
                        )
                        for cidr, expected in (
                            ("192.0.2.0/31", "Хостовых позиций: 2"),
                            ("192.0.2.7/32", "Хостовых позиций: 1"),
                        ):
                            paste(cidr)
                            copy_tool(expected, "Broadcast подсети: Не применяется")
                        paste("0.0.0.0/0")
                        copy_tool("Хостовых позиций: -", "Всего адресов: 4294967296")
                        checks.append("IPv4 /31, /32 and /0 conventions through the EXE")
                        paste("192.168.1.0/24")
                        before_theme = copy_tool("Подсеть CIDR: 192.168.1.0/24")
                        keys(0x11, 0x10, ord("T"))
                        assert copy_tool("Подсеть CIDR: 192.168.1.0/24") == before_theme
                        settings_path = (
                            Path(environment["APPDATA"]) / "MacAddressConverter/settings.json"
                        )
                        wait_until(lambda: settings_path.is_file())
                        assert json.loads(settings_path.read_text()) == {"theme": "night"}
                        save_screenshot(hwnd, Path("smoke-results/ipv4-night.png"))
                        checks.append("Theme toggle preserves calculation; only theme is saved")

                        keys(0x11, ord("3"))
                        paste("1492")
                        copy_tool("TCP MSS: 1452")
                        select_choice(2, 1)
                        copy_tool("TCP MSS: 1432", "Фиксированный IP-заголовок: 40")
                        paste_control(5, "60")
                        copy_tool("TCP MSS: 1372", "Эффективный IP MTU: 1432")
                        paste("40")
                        assert_invalid_copy()
                        checks.append("MSS: IPv4, IPv6, manual overhead and invalid-MTU clear")
                        paste("1500")
                        paste_control(5, "0")
                        select_choice(2, 0)
                        select_choice(6, 1)  # dot1q, known IP MTU unchanged.
                        copy_tool("TCP MSS: 1460", "Ethernet-кадр с FCS: 1522")
                        select_choice(1, 1)  # Ethernet payload.
                        focus_control(7)
                        keys(0x20)  # PPPoE.
                        copy_tool("Эффективный IP MTU: 1492", "TCP MSS: 1452")
                        paste("1492")
                        select_choice(1, 0)
                        copy_tool("Эффективный IP MTU: 1492", "повторно не вычитается")
                        checks.append(
                            "MTU layers: dot1q frame 1522, PPPoE payload and known IP MTU without double subtraction"
                        )
                        focus_control(7)
                        keys(0x20)
                        select_choice(6, 0)
                        paste("1500")
                        for profile, mss in (
                            (1, "1440"),
                            (2, "1436"),
                            (3, "1400"),
                            (4, "1410"),
                            (5, "1406"),
                            (6, "1408"),
                            (7, "1388"),
                        ):
                            select_choice(3, profile)
                            copy_tool(f"TCP MSS: {mss}", "Размер кадра включает FCS")
                        save_screenshot(hwnd, Path("smoke-results/mtu-profiles-night.png"))
                        checks.append(
                            "MTU EXE presets: IP-in-IP, GRE, WireGuard, VXLAN, ESP, OpenVPN UDP AEAD and L2TP/IPsec"
                        )

                        keys(0x11, ord("4"))
                        copy_tool("[LPM] 10.20.30.0/24  access")
                        paste_control(
                            1,
                            "0.0.0.0/0 default\n10.20.0.0/16 core\n10.20.30.0/24 via A\n10.20.30.0/24 via B",
                        )
                        copy_tool(
                            "[LPM] 10.20.30.0/24  via A",
                            "[LPM] 10.20.30.0/24  via B",
                            "Несколько равных",
                        )
                        save_screenshot(hwnd, Path("smoke-results/routes-night.png"))
                        paste("192.0.2.5")
                        copy_tool("[LPM] 0.0.0.0/0  default")
                        paste_control(1, "10.0.0.0/8 core")
                        copy_tool("Совпадений нет")
                        paste_control(1, "10.1.2.3/24")
                        assert_invalid_copy()
                        checks.append(
                            "Routes: LPM, equal-prefix candidates, default, no match and invalid CIDR"
                        )

                        keys(0x11, ord("5"))
                        copy_tool(
                            "запрос и ответ разрешены", "198.51.100.20:443 -> 192.0.2.10:53000"
                        )
                        save_screenshot(hwnd, Path("smoke-results/acl-request-reply-night.png"))
                        paste_control(8, "10 deny ip any any")
                        copy_tool("БЛОКИРУЕТСЯ: sequence 10, строка 1", "ACL блокируют")
                        checks.append(
                            "ACL EXE: request/reply address and port reversal; reply deny identifies exact rule"
                        )
                        paste_control(8, "")
                        paste_control(6, "permit tcp any any eq 80")
                        copy_tool("Неявный deny", "обратный поток не проверен")
                        checks.append("ACL EXE: implicit deny and empty reverse list are explicit")
                        paste_control(6, "20 permit ip any any\n10 deny tcp any any eq 443")
                        copy_tool("БЛОКИРУЕТСЯ: sequence 10, строка 2")
                        paste_control(6, "permit tcp any eq 53000 any eq 443\npermit ip any any")
                        paste_control(3, "")
                        copy_tool("НЕДОСТАТОЧНО ДАННЫХ", "Неизвестен порт источника")
                        checks.append(
                            "ACL EXE: sequence order and unknown source port do not produce false permit"
                        )
                        paste_control(6, "permit ip any any\npermit tcp any any time-range DAY")
                        time.sleep(0.3)  # Allow the 180-ms editor debounce to finish.
                        assert_invalid_copy()
                        paste_control(6, "permit ip any any")
                        copy_tool("запрос разрешён", "обратный поток не проверен")
                        paste("bad")
                        assert_invalid_copy()
                        paste("192.0.2.10")
                        copy_tool("запрос разрешён")
                        checks.append(
                            "ACL EXE: unsupported conditions and invalid flow clear stale output and recover"
                        )
                        # These are disposable test secrets; never print or capture them unmasked.
                        keys(0x11, ord("6"))
                        password_test_started = True
                        assert_invalid_copy()
                        focus_control(7)  # Length, symbols, four groups, exclusions, Generate.
                        keys(0x20)
                        write_clipboard("password copy sentinel")
                        keys(0x11, 0x10, ord("C"))
                        generated = wait_until(
                            lambda: value
                            if (value := read_clipboard()) and value != "password copy sentinel"
                            else None
                        )
                        from mac_converter.passwords import PasswordOptions

                        groups = PasswordOptions().groups()
                        assert len(generated) == 20
                        assert all(set(generated) & set(group) for group in groups)
                        assert set(generated) <= set("".join(groups))
                        save_screenshot(hwnd, Path("smoke-results/passwords-night.png"))
                        checks.append(
                            "Passwords: default length 20, required groups/exclusions, masked output and Copy"
                        )
                        focus_control(7)
                        keys(0x20)
                        write_clipboard("regenerate sentinel")
                        keys(0x11, 0x10, ord("C"))
                        second = wait_until(
                            lambda: value
                            if (value := read_clipboard()) and value != "regenerate sentinel"
                            else None
                        )
                        assert len(second) == 20 and second != generated
                        checks.append("Passwords: Generate again produces a fresh random result")
                        # Wait for real app timer, pumping Windows messages for clipboard ownership.
                        wait_until(lambda: read_clipboard() is None, timeout=40)
                        checks.append(
                            "Passwords: actual 30-second clipboard timer clears its own value"
                        )
                        paste("24")
                        assert_invalid_copy()
                        focus_control(7)
                        keys(0x20)
                        write_clipboard("length sentinel")
                        keys(0x11, 0x10, ord("C"))
                        resized = wait_until(
                            lambda: value
                            if (value := read_clipboard()) and value != "length sentinel"
                            else None
                        )
                        assert len(resized) == 24
                        write_clipboard("replacement clipboard content")
                        checks.append(
                            "Passwords: policy change clears old output; generation respects length 24"
                        )
                        # Clear must preserve the replacement content.
                        focus_control(10)  # Length … Generate, result, Copy, Clear.
                        keys(0x20)
                        assert read_clipboard() == "replacement clipboard content"
                        checks.append(
                            "Passwords: Clear removes output and preserves another clipboard value"
                        )
                        paste("7")
                        assert_invalid_copy()
                        paste("20")
                        checks.append("Passwords: invalid length disables copying and recovers")

                        for tool, help_name in (
                            (4, "Маршруты"),
                            (5, "ACL"),
                            (6, "Пароли"),
                        ):
                            keys(0x11, ord(str(tool)))
                            keys(0x70)  # F1.
                            help_hwnd = wait_until(
                                lambda: find_window(isolated.resolve(), f"Помощь - {help_name}")
                            )
                            user32.SetForegroundWindow(help_hwnd)
                            wait_until(lambda: user32.GetForegroundWindow() == help_hwnd)
                            write_clipboard("help copy sentinel")
                            keys(0x11, ord("A"))
                            keys(0x11, ord("C"))
                            help_text = wait_until(
                                lambda: value
                                if (value := read_clipboard()) and "Как использовать" in value
                                else None
                            )
                            assert "Пример" in help_text and "Что учитывать" in help_text
                            if tool == 4:
                                assert "10.20.30.0/24" in help_text and "[LPM]" in help_text
                            elif tool == 5:
                                assert (
                                    "permit/deny" in help_text
                                    and "ACL ответа" in help_text
                                    and "0.0.255.254" in help_text
                                )
                            save_screenshot(help_hwnd, Path(f"smoke-results/help-tool-{tool}.png"))
                            keys(0x1B)  # Escape.
                            wait_until(lambda: not user32.IsWindowVisible(help_hwnd))
                            user32.SetForegroundWindow(hwnd)
                            wait_until(lambda: user32.GetForegroundWindow() == hwnd)
                        checks.append(
                            "Context help: F1, route/ACL/password examples, readonly copy and Escape"
                        )
                        keys(0x11, ord("6"))
                        paste("20")
                        focus_control(7)
                        keys(0x20)
                        write_clipboard("close copy sentinel")
                        keys(0x11, 0x10, ord("C"))
                        wait_until(
                            lambda: (value := read_clipboard()) and value != "close copy sentinel"
                        )
                        expect_clipboard_clear_on_close = True

                    except BaseException as error:
                        target = Path("smoke-results")
                        target.mkdir(exist_ok=True)
                        windows = describe_windows(isolated.resolve())
                        if password_test_started:
                            for window in windows:
                                window["text"] = ["<redacted: password test>"]
                        diagnostic = {
                            "error": str(error),
                            "process_exit": process.poll(),
                            "windows": windows,
                            "clipboard": "<redacted: password test>"
                            if password_test_started
                            else read_clipboard(),
                            "completed_checks": checks,
                            "execution_tokens": execution_tokens,
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
                            if not failed and expect_clipboard_clear_on_close:
                                assert read_clipboard() is None, (
                                    "Close did not clear its password from clipboard"
                                )
                                checks.append(
                                    "Passwords: window close clears owned clipboard before process exit"
                                )
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
