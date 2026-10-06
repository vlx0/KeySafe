"""Windows DPAPI helpers (CryptProtectData / CryptUnprotectData)."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32

CRYPTPROTECT_UI_FORBIDDEN = 0x1


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wt.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _blob_from_bytes(data: bytes) -> DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))


def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def protect(data: bytes) -> bytes:
    """Encrypt for the current Windows user."""
    inn = _blob_from_bytes(data)
    out = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(inn),
        "KeySafe",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out),
    ):
        raise OSError(f"CryptProtectData failed: {kernel32.GetLastError()}")
    try:
        return _blob_to_bytes(out)
    finally:
        kernel32.LocalFree(out.pbData)


def unprotect(data: bytes) -> bytes:
    """Decrypt data protected for the current Windows user."""
    inn = _blob_from_bytes(data)
    out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(inn),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out),
    ):
        raise OSError(f"CryptUnprotectData failed: {kernel32.GetLastError()}")
    try:
        return _blob_to_bytes(out)
    finally:
        kernel32.LocalFree(out.pbData)
