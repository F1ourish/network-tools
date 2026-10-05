"""Windows-only smoke helpers: launch and inspect an EXE without admin rights.

This module is used by the build harness and is not bundled into the application.
"""

from contextlib import contextmanager
import ctypes as ct
from ctypes import wintypes as wt
from pathlib import Path
import subprocess


class SidAndAttributes(ct.Structure):
    _fields_ = [("sid", ct.c_void_p), ("attributes", wt.DWORD)]


class TokenGroups(ct.Structure):
    _fields_ = [("count", wt.DWORD), ("groups", SidAndAttributes * 1)]


class StartupInfo(ct.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("reserved", wt.LPWSTR),
        ("desktop", wt.LPWSTR),
        ("title", wt.LPWSTR),
        ("x", wt.DWORD),
        ("y", wt.DWORD),
        ("width", wt.DWORD),
        ("height", wt.DWORD),
        ("x_chars", wt.DWORD),
        ("y_chars", wt.DWORD),
        ("fill", wt.DWORD),
        ("flags", wt.DWORD),
        ("show", wt.WORD),
        ("reserved_size", wt.WORD),
        ("reserved_data", ct.c_void_p),
        ("stdin", wt.HANDLE),
        ("stdout", wt.HANDLE),
        ("stderr", wt.HANDLE),
    ]


class ProcessInfo(ct.Structure):
    _fields_ = [
        ("process", wt.HANDLE),
        ("thread", wt.HANDLE),
        ("pid", wt.DWORD),
        ("tid", wt.DWORD),
    ]


kernel32 = ct.WinDLL("kernel32", use_last_error=True)
advapi32 = ct.WinDLL("advapi32", use_last_error=True)
for dll, name, result, arguments in (
    (kernel32, "GetCurrentProcess", wt.HANDLE, []),
    (kernel32, "OpenProcess", wt.HANDLE, [wt.DWORD, wt.BOOL, wt.DWORD]),
    (kernel32, "CloseHandle", wt.BOOL, [wt.HANDLE]),
    (kernel32, "LocalFree", ct.c_void_p, [ct.c_void_p]),
    (kernel32, "WaitForSingleObject", wt.DWORD, [wt.HANDLE, wt.DWORD]),
    (kernel32, "GetExitCodeProcess", wt.BOOL, [wt.HANDLE, ct.POINTER(wt.DWORD)]),
    (kernel32, "TerminateProcess", wt.BOOL, [wt.HANDLE, wt.UINT]),
    (kernel32, "ResumeThread", wt.DWORD, [wt.HANDLE]),
    (advapi32, "OpenProcessToken", wt.BOOL, [wt.HANDLE, wt.DWORD, ct.POINTER(wt.HANDLE)]),
    (
        advapi32,
        "GetTokenInformation",
        wt.BOOL,
        [wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD, ct.POINTER(wt.DWORD)],
    ),
    (advapi32, "SetTokenInformation", wt.BOOL, [wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD]),
    (advapi32, "ConvertStringSidToSidW", wt.BOOL, [wt.LPCWSTR, ct.POINTER(ct.c_void_p)]),
    (advapi32, "EqualSid", wt.BOOL, [ct.c_void_p, ct.c_void_p]),
    (advapi32, "GetLengthSid", wt.DWORD, [ct.c_void_p]),
    (advapi32, "GetSidSubAuthorityCount", ct.POINTER(ct.c_ubyte), [ct.c_void_p]),
    (advapi32, "GetSidSubAuthority", ct.POINTER(wt.DWORD), [ct.c_void_p, wt.DWORD]),
    (advapi32, "IsTokenRestricted", wt.BOOL, [wt.HANDLE]),
    (
        advapi32,
        "CreateRestrictedToken",
        wt.BOOL,
        [
            wt.HANDLE,
            wt.DWORD,
            wt.DWORD,
            ct.POINTER(SidAndAttributes),
            wt.DWORD,
            ct.c_void_p,
            wt.DWORD,
            ct.c_void_p,
            ct.POINTER(wt.HANDLE),
        ],
    ),
    (
        advapi32,
        "CreateProcessAsUserW",
        wt.BOOL,
        [
            wt.HANDLE,
            wt.LPCWSTR,
            wt.LPWSTR,
            ct.c_void_p,
            ct.c_void_p,
            wt.BOOL,
            wt.DWORD,
            ct.c_void_p,
            wt.LPCWSTR,
            ct.POINTER(StartupInfo),
            ct.POINTER(ProcessInfo),
        ],
    ),
):
    function = getattr(dll, name)
    function.restype = result
    function.argtypes = arguments


def require(success):
    if not success:
        raise ct.WinError(ct.get_last_error())


@contextmanager
def sid(value):
    pointer = ct.c_void_p()
    require(advapi32.ConvertStringSidToSidW(value, ct.byref(pointer)))
    try:
        yield pointer
    finally:
        kernel32.LocalFree(pointer)


def token_information(token, information_class):
    size = wt.DWORD()
    advapi32.GetTokenInformation(token, information_class, None, 0, ct.byref(size))
    if not size.value:
        raise ct.WinError(ct.get_last_error())
    buffer = ct.create_string_buffer(size.value)
    require(advapi32.GetTokenInformation(token, information_class, buffer, size, ct.byref(size)))
    return buffer


def token_security(token):
    elevation = wt.DWORD.from_buffer(token_information(token, 20)).value
    integrity_buffer = token_information(token, 25)
    integrity_sid = SidAndAttributes.from_buffer(integrity_buffer).sid
    count = advapi32.GetSidSubAuthorityCount(integrity_sid)[0]
    integrity = advapi32.GetSidSubAuthority(integrity_sid, count - 1)[0]
    groups_buffer = token_information(token, 2)
    group_count = wt.DWORD.from_buffer(groups_buffer).value
    admin_enabled = False
    with sid("S-1-5-32-544") as administrators:
        for index in range(group_count):
            offset = TokenGroups.groups.offset + index * ct.sizeof(SidAndAttributes)
            group = SidAndAttributes.from_buffer(groups_buffer, offset)
            if advapi32.EqualSid(group.sid, administrators) and group.attributes & 0x4:
                admin_enabled = True
    return {
        "elevated": bool(elevation),
        "administrators_enabled": admin_enabled,
        "integrity_rid": integrity,
        "restricted": bool(advapi32.IsTokenRestricted(token)),
    }


def assert_unprivileged(security):
    assert not security["elevated"], f"EXE token is elevated: {security}"
    assert not security["administrators_enabled"], f"EXE has enabled admin SID: {security}"
    assert security["integrity_rid"] == 8192, f"EXE does not have medium integrity: {security}"


def process_security(pid):
    process = kernel32.OpenProcess(0x1000, False, pid)
    require(process)
    token = wt.HANDLE()
    try:
        require(advapi32.OpenProcessToken(process, 0x8, ct.byref(token)))
        return token_security(token)
    finally:
        if token:
            kernel32.CloseHandle(token)
        kernel32.CloseHandle(process)


class LimitedProcess:
    def __init__(self, info):
        self.handle = info.process
        self.pid = info.pid
        self.returncode = None

    def wait(self, timeout=None):
        milliseconds = 0xFFFFFFFF if timeout is None else int(timeout * 1000)
        result = kernel32.WaitForSingleObject(self.handle, milliseconds)
        if result == 258:
            raise subprocess.TimeoutExpired("MacAddressConverter.exe", timeout)
        if result != 0:
            raise ct.WinError(ct.get_last_error())
        code = wt.DWORD()
        require(kernel32.GetExitCodeProcess(self.handle, ct.byref(code)))
        self.returncode = code.value
        return self.returncode

    def kill(self):
        require(kernel32.TerminateProcess(self.handle, 1))

    def close(self):
        kernel32.CloseHandle(self.handle)


def launch_unprivileged(binary: Path, directory: str, environment: dict[str, str]):
    current = wt.HANDLE()
    limited = wt.HANDLE()
    # QUERY | DUPLICATE | ASSIGN_PRIMARY | ADJUST_DEFAULT, for our own process token.
    require(advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x8B, ct.byref(current)))
    try:
        security = token_security(current)
        if not security["elevated"] and not security["administrators_enabled"]:
            assert_unprivileged(security)
            return subprocess.Popen([str(binary)], cwd=directory, env=environment)
        with sid("S-1-5-32-544") as administrators:
            disabled = SidAndAttributes(administrators.value, 0)
            # DISABLE_MAX_PRIVILEGE | LUA_TOKEN; keep policy enforcement enabled.
            require(
                advapi32.CreateRestrictedToken(
                    current, 0x5, 1, ct.byref(disabled), 0, None, 0, None, ct.byref(limited)
                )
            )
        with sid("S-1-16-8192") as medium:
            label = SidAndAttributes(medium.value, 0x20)  # SE_GROUP_INTEGRITY
            require(
                advapi32.SetTokenInformation(
                    limited, 25, ct.byref(label), ct.sizeof(label) + advapi32.GetLengthSid(medium)
                )
            )
        assert_unprivileged(token_security(limited))
        startup = StartupInfo(cb=ct.sizeof(StartupInfo), desktop="winsta0\\default")
        info = ProcessInfo()
        command = ct.create_unicode_buffer(subprocess.list2cmdline([str(binary)]))
        block = ct.create_unicode_buffer(
            "\0".join(
                f"{key}={value}"
                for key, value in sorted(environment.items(), key=lambda item: item[0].upper())
            )
            + "\0\0"
        )
        require(
            advapi32.CreateProcessAsUserW(
                limited,
                str(binary),
                command,
                None,
                None,
                False,
                0x404,  # CREATE_UNICODE_ENVIRONMENT | CREATE_SUSPENDED
                block,
                directory,
                ct.byref(startup),
                ct.byref(info),
            )
        )
        process = LimitedProcess(info)
        try:
            assert_unprivileged(process_security(info.pid))
            if kernel32.ResumeThread(info.thread) == 0xFFFFFFFF:
                raise ct.WinError(ct.get_last_error())
        except BaseException:
            process.kill()
            process.wait(timeout=5)
            process.close()
            raise
        finally:
            kernel32.CloseHandle(info.thread)
        return process
    finally:
        if limited:
            kernel32.CloseHandle(limited)
        kernel32.CloseHandle(current)
