"""Windows-only smoke helpers: launch and inspect an EXE without admin rights.

This module is used by the build harness and is not bundled into the application.
"""

from contextlib import ExitStack, contextmanager
import ctypes as ct
from ctypes import wintypes as wt
import os
from pathlib import Path
import secrets
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


class UserInfo(ct.Structure):
    _fields_ = [
        ("name", wt.LPWSTR),
        ("password", wt.LPWSTR),
        ("password_age", wt.DWORD),
        ("privilege", wt.DWORD),
        ("home", wt.LPWSTR),
        ("comment", wt.LPWSTR),
        ("flags", wt.DWORD),
        ("script", wt.LPWSTR),
    ]


class TokenPrivileges(ct.Structure):
    _fields_ = [
        ("count", wt.DWORD),
        ("luid_low", wt.DWORD),
        ("luid_high", wt.LONG),
        ("attributes", wt.DWORD),
    ]


kernel32 = ct.WinDLL("kernel32", use_last_error=True)
advapi32 = ct.WinDLL("advapi32", use_last_error=True)
user32 = ct.WinDLL("user32", use_last_error=True)
netapi32 = ct.WinDLL("netapi32", use_last_error=True)
for dll, name, result, arguments in (
    (kernel32, "GetCurrentProcess", wt.HANDLE, []),
    (kernel32, "OpenProcess", wt.HANDLE, [wt.DWORD, wt.BOOL, wt.DWORD]),
    (kernel32, "CloseHandle", wt.BOOL, [wt.HANDLE]),
    (kernel32, "LocalFree", ct.c_void_p, [ct.c_void_p]),
    (kernel32, "WaitForSingleObject", wt.DWORD, [wt.HANDLE, wt.DWORD]),
    (kernel32, "GetExitCodeProcess", wt.BOOL, [wt.HANDLE, ct.POINTER(wt.DWORD)]),
    (kernel32, "TerminateProcess", wt.BOOL, [wt.HANDLE, wt.UINT]),
    (kernel32, "ResumeThread", wt.DWORD, [wt.HANDLE]),
    (
        kernel32,
        "K32EnumProcessModules",
        wt.BOOL,
        [wt.HANDLE, ct.POINTER(wt.HMODULE), wt.DWORD, ct.POINTER(wt.DWORD)],
    ),
    (
        kernel32,
        "K32GetModuleFileNameExW",
        wt.DWORD,
        [wt.HANDLE, wt.HMODULE, wt.LPWSTR, wt.DWORD],
    ),
    (advapi32, "OpenProcessToken", wt.BOOL, [wt.HANDLE, wt.DWORD, ct.POINTER(wt.HANDLE)]),
    (
        advapi32,
        "GetTokenInformation",
        wt.BOOL,
        [wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD, ct.POINTER(wt.DWORD)],
    ),
    (advapi32, "ConvertStringSidToSidW", wt.BOOL, [wt.LPCWSTR, ct.POINTER(ct.c_void_p)]),
    (advapi32, "ConvertSidToStringSidW", wt.BOOL, [ct.c_void_p, ct.POINTER(ct.c_void_p)]),
    (advapi32, "EqualSid", wt.BOOL, [ct.c_void_p, ct.c_void_p]),
    (advapi32, "GetSidSubAuthorityCount", ct.POINTER(ct.c_ubyte), [ct.c_void_p]),
    (advapi32, "GetSidSubAuthority", ct.POINTER(wt.DWORD), [ct.c_void_p, wt.DWORD]),
    (advapi32, "IsTokenRestricted", wt.BOOL, [wt.HANDLE]),
    (
        advapi32,
        "LogonUserW",
        wt.BOOL,
        [
            wt.LPCWSTR,
            wt.LPCWSTR,
            wt.LPCWSTR,
            wt.DWORD,
            wt.DWORD,
            ct.POINTER(wt.HANDLE),
        ],
    ),
    (
        advapi32,
        "CreateProcessWithLogonW",
        wt.BOOL,
        [
            wt.LPCWSTR,
            wt.LPCWSTR,
            wt.LPCWSTR,
            wt.DWORD,
            wt.LPCWSTR,
            wt.LPWSTR,
            wt.DWORD,
            ct.c_void_p,
            wt.LPCWSTR,
            ct.POINTER(StartupInfo),
            ct.POINTER(ProcessInfo),
        ],
    ),
    (
        advapi32,
        "LookupAccountSidW",
        wt.BOOL,
        [
            wt.LPCWSTR,
            ct.c_void_p,
            wt.LPWSTR,
            ct.POINTER(wt.DWORD),
            wt.LPWSTR,
            ct.POINTER(wt.DWORD),
            ct.POINTER(ct.c_int),
        ],
    ),
    (advapi32, "LookupPrivilegeValueW", wt.BOOL, [wt.LPCWSTR, wt.LPCWSTR, ct.c_void_p]),
    (
        advapi32,
        "AdjustTokenPrivileges",
        wt.BOOL,
        [wt.HANDLE, wt.BOOL, ct.c_void_p, wt.DWORD, ct.c_void_p, ct.POINTER(wt.DWORD)],
    ),
    (
        advapi32,
        "ConvertSecurityDescriptorToStringSecurityDescriptorW",
        wt.BOOL,
        [ct.c_void_p, wt.DWORD, wt.DWORD, ct.POINTER(ct.c_void_p), ct.c_void_p],
    ),
    (
        advapi32,
        "ConvertStringSecurityDescriptorToSecurityDescriptorW",
        wt.BOOL,
        [wt.LPCWSTR, wt.DWORD, ct.POINTER(ct.c_void_p), ct.c_void_p],
    ),
    (user32, "OpenWindowStationW", wt.HANDLE, [wt.LPCWSTR, wt.BOOL, wt.DWORD]),
    (user32, "CloseWindowStation", wt.BOOL, [wt.HANDLE]),
    (user32, "OpenDesktopW", wt.HANDLE, [wt.LPCWSTR, wt.DWORD, wt.BOOL, wt.DWORD]),
    (user32, "CloseDesktop", wt.BOOL, [wt.HANDLE]),
    (
        user32,
        "GetUserObjectSecurity",
        wt.BOOL,
        [wt.HANDLE, ct.POINTER(wt.DWORD), ct.c_void_p, wt.DWORD, ct.POINTER(wt.DWORD)],
    ),
    (user32, "SetUserObjectSecurity", wt.BOOL, [wt.HANDLE, ct.POINTER(wt.DWORD), ct.c_void_p]),
    (netapi32, "NetUserAdd", wt.DWORD, [wt.LPCWSTR, wt.DWORD, ct.c_void_p, ct.POINTER(wt.DWORD)]),
    (netapi32, "NetUserDel", wt.DWORD, [wt.LPCWSTR, wt.LPCWSTR]),
    (
        netapi32,
        "NetLocalGroupAddMembers",
        wt.DWORD,
        [wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ct.c_void_p, wt.DWORD],
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
    user_buffer = token_information(token, 1)
    user_sid = SidAndAttributes.from_buffer(user_buffer).sid
    sid_string = ct.c_void_p()
    require(advapi32.ConvertSidToStringSidW(user_sid, ct.byref(sid_string)))
    try:
        user_sid_string = ct.wstring_at(sid_string)
    finally:
        kernel32.LocalFree(sid_string)
    return {
        "elevated": bool(elevation),
        "administrators_enabled": admin_enabled,
        "integrity_rid": integrity,
        "restricted": bool(advapi32.IsTokenRestricted(token)),
        "user_sid": user_sid_string,
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


def process_runtime(pid):
    process = kernel32.OpenProcess(0x410, False, pid)  # QUERY_INFORMATION | VM_READ
    require(process)
    try:
        modules = (wt.HMODULE * 2048)()
        needed = wt.DWORD()
        require(
            kernel32.K32EnumProcessModules(process, modules, ct.sizeof(modules), ct.byref(needed))
        )
        assert needed.value <= ct.sizeof(modules), "DLL inspection buffer is too small"
        required = {"python312.dll", "_tkinter.pyd", "tcl86t.dll", "tk86t.dll"}
        found = {}
        for module in modules[: needed.value // ct.sizeof(wt.HMODULE)]:
            path = ct.create_unicode_buffer(32768)
            require(kernel32.K32GetModuleFileNameExW(process, module, path, len(path)))
            item = Path(path.value)
            if item.name.lower() in required:
                assert item.parent.name.startswith("_MEI"), (
                    f"Runtime was loaded outside the bundle: {item}"
                )
                found[item.name.lower()] = f"{item.parent.name}/{item.name}"
        assert set(found) == required, f"Missing loaded runtime DLLs: {required - set(found)}"
        return found
    finally:
        kernel32.CloseHandle(process)


class LimitedProcess:
    def __init__(self, info):
        self.handle = info.process
        self.pid = info.pid
        self.returncode = None

    def poll(self):
        code = wt.DWORD()
        require(kernel32.GetExitCodeProcess(self.handle, ct.byref(code)))
        self.returncode = None if code.value == 259 else code.value
        return self.returncode

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


@contextmanager
def debug_inspection():
    """Let the CI harness inspect another user's process; restore its own privilege."""
    token = wt.HANDLE()
    require(advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x28, ct.byref(token)))
    previous = TokenPrivileges()
    try:
        enabled = TokenPrivileges(count=1, attributes=2)  # SE_PRIVILEGE_ENABLED
        require(
            advapi32.LookupPrivilegeValueW(
                None, "SeDebugPrivilege", ct.byref(enabled, TokenPrivileges.luid_low.offset)
            )
        )
        size = wt.DWORD()
        ct.set_last_error(0)
        require(
            advapi32.AdjustTokenPrivileges(
                token,
                False,
                ct.byref(enabled),
                ct.sizeof(previous),
                ct.byref(previous),
                ct.byref(size),
            )
        )
        if ct.get_last_error():
            raise ct.WinError(ct.get_last_error())
        try:
            yield
        finally:
            require(advapi32.AdjustTokenPrivileges(token, False, ct.byref(previous), 0, None, None))
    finally:
        kernel32.CloseHandle(token)


@contextmanager
def desktop_access(user_sid):
    """Temporarily grant only the test account access to the existing CI desktop."""
    with ExitStack() as cleanup:
        for open_object, close_object, mask in (
            (
                lambda: user32.OpenWindowStationW("winsta0", False, 0x60000),
                user32.CloseWindowStation,
                "0x000f037f",
            ),
            (
                lambda: user32.OpenDesktopW("default", 0, False, 0x60000),
                user32.CloseDesktop,
                "0x000f01ff",
            ),
        ):
            handle = open_object()
            require(handle)
            cleanup.callback(close_object, handle)
            information = wt.DWORD(4)  # DACL_SECURITY_INFORMATION
            size = wt.DWORD()
            user32.GetUserObjectSecurity(handle, ct.byref(information), None, 0, ct.byref(size))
            if not size.value:
                raise ct.WinError(ct.get_last_error())
            original = ct.create_string_buffer(size.value)
            require(
                user32.GetUserObjectSecurity(
                    handle, ct.byref(information), original, size, ct.byref(size)
                )
            )
            descriptor_string = ct.c_void_p()
            require(
                advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                    original, 1, 4, ct.byref(descriptor_string), None
                )
            )
            try:
                modified = ct.wstring_at(descriptor_string) + f"(A;;{mask};;;{user_sid})"
            finally:
                kernel32.LocalFree(descriptor_string)
            descriptor = ct.c_void_p()
            require(
                advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                    modified, 1, ct.byref(descriptor), None
                )
            )
            try:
                require(user32.SetUserObjectSecurity(handle, ct.byref(information), descriptor))
            finally:
                kernel32.LocalFree(descriptor)
            cleanup.callback(restore_desktop_acl, handle, original)
        yield


def restore_desktop_acl(handle, descriptor):
    information = wt.DWORD(4)
    require(user32.SetUserObjectSecurity(handle, ct.byref(information), descriptor))


def add_to_users(name):
    with sid("S-1-5-32-545") as users:
        group = ct.create_unicode_buffer(256)
        domain = ct.create_unicode_buffer(256)
        group_size, domain_size = wt.DWORD(256), wt.DWORD(256)
        account_type = ct.c_int()
        require(
            advapi32.LookupAccountSidW(
                None,
                users,
                group,
                ct.byref(group_size),
                domain,
                ct.byref(domain_size),
                ct.byref(account_type),
            )
        )
    member = wt.LPWSTR(f"{os.environ['COMPUTERNAME']}\\{name}")
    result = netapi32.NetLocalGroupAddMembers(None, group.value, 3, ct.byref(member), 1)
    if result not in (0, 1378):  # ERROR_MEMBER_IN_ALIAS: already a member
        raise ct.WinError(result)


class StandardAccount:
    def __init__(self, name, password, user_sid):
        self.name = name
        self.password = password
        self.sid = user_sid

    def launch(self, binary: Path, directory: str, environment: dict[str, str]):
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
            advapi32.CreateProcessWithLogonW(
                self.name,
                ".",
                self.password,
                0,
                str(binary),
                command,
                0x404,  # CREATE_UNICODE_ENVIRONMENT | CREATE_SUSPENDED
                block,
                directory,
                ct.byref(startup),
                ct.byref(info),
            )
        )
        process = LimitedProcess(info)
        try:
            security = process_security(info.pid)
            assert_unprivileged(security)
            assert security["user_sid"] == self.sid, "EXE did not run as the test account"
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


@contextmanager
def unprivileged_launcher(directory: Path):
    """Use the current standard user, or a disposable account on hosted GitHub CI."""
    current = wt.HANDLE()
    require(advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x8, ct.byref(current)))
    try:
        security = token_security(current)
    finally:
        kernel32.CloseHandle(current)
    if not security["elevated"] and not security["administrators_enabled"]:
        assert_unprivileged(security)
        yield lambda binary, cwd, env: subprocess.Popen([str(binary)], cwd=cwd, env=env)
        return
    assert (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
    ), "Run local smoke as a standard user; account creation is hosted-CI only"
    name = "macsmoke_" + secrets.token_hex(4)
    password = ct.create_unicode_buffer("Aa9!" + secrets.token_urlsafe(24))
    account = UserInfo(
        name=name,
        password=ct.cast(password, wt.LPWSTR),
        privilege=1,
        comment="Temporary MAC converter EXE test",
        flags=0x10201,
    )
    parameter_error = wt.DWORD()
    result = netapi32.NetUserAdd(None, 1, ct.byref(account), ct.byref(parameter_error))
    if result:
        ct.memset(password, 0, ct.sizeof(password))
        raise ct.WinError(result)
    token = wt.HANDLE()
    try:
        add_to_users(name)
        require(advapi32.LogonUserW(name, ".", password, 2, 0, ct.byref(token)))
        security = token_security(token)
        assert_unprivileged(security)
        user_sid = security["user_sid"]
        icacls = Path(os.environ["SystemRoot"]) / "System32/icacls.exe"
        subprocess.run(
            [str(icacls), str(directory), "/grant", f"*{user_sid}:(OI)(CI)M"],
            check=True,
            capture_output=True,
        )
        with debug_inspection(), desktop_access(user_sid):
            yield StandardAccount(name, password, user_sid).launch
    finally:
        if token:
            kernel32.CloseHandle(token)
        ct.memset(password, 0, ct.sizeof(password))
        result = netapi32.NetUserDel(None, name)
        if result:
            raise ct.WinError(result)
