"""Conditionally clear the OS clipboard without deleting replacement content."""

import ctypes as ct
from ctypes import wintypes as wt
import sys
import tkinter as tk


class ClipboardUnavailable(RuntimeError):
    """Clipboard is locked or a native clipboard operation failed."""


def clear_if_matches(root: tk.Misc, expected: str) -> bool:
    if sys.platform == "win32":
        return _clear_windows(expected)
    try:
        if root.clipboard_get() == expected:
            root.clipboard_clear()
            return True
    except tk.TclError as error:
        # A non-text/empty selection has no matching secret to clear.
        if "doesn't exist" not in str(error) and "not defined" not in str(error):
            raise ClipboardUnavailable("Clipboard could not be inspected") from error
    return False


def _clear_windows(expected: str) -> bool:
    user32 = ct.WinDLL("user32", use_last_error=True)
    kernel32 = ct.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wt.HWND]
    user32.OpenClipboard.restype = wt.BOOL
    user32.GetClipboardData.argtypes = [wt.UINT]
    user32.GetClipboardData.restype = wt.HANDLE
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wt.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wt.BOOL
    kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
    kernel32.GlobalLock.restype = ct.c_void_p
    kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
    kernel32.GlobalSize.argtypes = [wt.HGLOBAL]
    kernel32.GlobalSize.restype = ct.c_size_t
    if not user32.OpenClipboard(None):
        raise ClipboardUnavailable("Clipboard is busy")
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT.
        if not handle:
            return False
        size = kernel32.GlobalSize(handle)
        # Passwords are bounded ASCII: refuse a differently sized replacement early.
        if size < 2 * (len(expected) + 1):
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise ClipboardUnavailable("Clipboard data could not be read")
        try:
            value = ct.wstring_at(pointer, len(expected) + 1)
        finally:
            kernel32.GlobalUnlock(handle)
        if value != expected + "\0":
            return False
        # Compare and erase while OpenClipboard holds the lock: no read/clear race.
        if not user32.EmptyClipboard():
            raise ClipboardUnavailable("Clipboard could not be cleared")
        return True
    finally:
        user32.CloseClipboard()
