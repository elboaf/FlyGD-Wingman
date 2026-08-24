"""CryptProtectData / CryptUnprotectData over ctypes. Windows only.

Imports cleanly on Linux, which is a hard requirement -- tokens.py imports
this module for its production defaults, so an import-time WinDLL would
take the whole subsystem's Linux test suite down. Structures and constants
live at module scope (ctypes.Structure is portable); every library binding
is built lazily inside a function, the layout preview/win32.py:1-9
establishes.

EVERY function below gets argtypes and restype. That is not decoration, and
preview/win32.py:10-16 records what it costs to omit: undeclared, ctypes
marshals a pointer-sized value as a 32-bit int, so a returned pbData would
be a truncated pointer and string_at would read from an address that is not
the buffer. Design probing hit that class of bug twice in the preview
subsystem, and both times the symptom appeared nowhere near the cause.

Why DPAPI rather than a plain JSON field: uploader.py:286-293 is explicit
that os.chmod on Windows only toggles the read-only attribute and that one
must "not assume the exposure is closed there". The real protection for a
plaintext file is the %LOCALAPPDATA% directory ACL, which gives nothing at
rest -- a stolen laptop, a disk image, a backup, or a %LOCALAPPDATA%
redirected into OneDrive all expose it. CryptProtectData is user-scoped and
closes that gap for about forty lines.
"""
import ctypes
import sys
from functools import lru_cache


class DATA_BLOB(ctypes.Structure):
    """crypt32's in/out buffer descriptor.

    c_uint32 rather than wintypes.DWORD so the definition is portable to
    the Linux import path; the two are the same width on every Windows ABI
    this ships to.
    """
    _fields_ = [("cbData", ctypes.c_uint32),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def available() -> bool:
    """Whether a token can be stored at all.

    Not read by the controller before it tries -- tokens.wrap/unwrap call
    protect()/unprotect() directly, and _require_windows() below is what
    they hit off Windows, raising the same clean OSError available() would
    otherwise have been used to pre-empt. This is exposed for callers
    (tests, and any future caller) that want to check ahead of time rather
    than catch that OSError.
    """
    return sys.platform == "win32"


def _require_windows() -> None:
    # A clean, explanatory error rather than an AttributeError raised from
    # inside ctypes three frames down.
    if not available():
        raise OSError("DPAPI is only available on Windows.")


@lru_cache(maxsize=1)
def _crypt32():
    # Cached: preview/win32.py:142-166 establishes the same shape -- the
    # DLL handle and its argtypes/restype declarations are process-global
    # mutations, so redoing them on every protect()/unprotect() call (once
    # per character on every state load) is wasted work, not just noise.
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    # BOOL CryptProtectData(DATA_BLOB *in, LPCWSTR desc, DATA_BLOB *entropy,
    #                       PVOID reserved, PROMPTSTRUCT *prompt,
    #                       DWORD flags, DATA_BLOB *out)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), ctypes.c_wchar_p,
        ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.POINTER(DATA_BLOB)]
    crypt32.CryptProtectData.restype = ctypes.c_int
    # CryptUnprotectData's second argument is LPWSTR* -- an OUT pointer to a
    # description string, not a string. Declared as c_void_p and passed
    # NULL, so crypt32 allocates nothing for it and there is nothing extra
    # to LocalFree.
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), ctypes.c_void_p,
        ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.POINTER(DATA_BLOB)]
    crypt32.CryptUnprotectData.restype = ctypes.c_int
    return crypt32


@lru_cache(maxsize=1)
def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # HLOCAL LocalFree(HLOCAL) -- both pointer-sized. Undeclared, the
    # argument would be truncated to 32 bits and the free would either fail
    # or release an address that is not the one crypt32 allocated.
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return kernel32


def _call(func, name: str, data: bytes) -> bytes:
    # create_string_buffer with an explicit length gives a buffer of exactly
    # len(data) with no trailing NUL. It is bound to a local so it stays
    # alive for the duration of the call -- built inline it could be
    # collected while crypt32 still held the pointer.
    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data),
                        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not func(ctypes.byref(blob_in), None, None, None, None, 0,
                ctypes.byref(blob_out)):
        # ctypes.WinError looks up get_last_error()'s code through
        # FormatMessage, giving the real Windows error text ("Access is
        # denied.", "The data is invalid.") rather than just its bare
        # numeric code -- the difference between a message a user could
        # act on and one that sends them to a search engine first. Folded
        # into a fresh OSError so `name` (CryptProtectData vs.
        # CryptUnprotectData) is still there to say which call failed.
        error = ctypes.WinError(ctypes.get_last_error())
        raise OSError(error.errno, f"{name} failed: {error.strerror}") from error
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        # crypt32 allocates the output with LocalAlloc. Not freeing it leaks
        # for the process lifetime, once per token read.
        _kernel32().LocalFree(blob_out.pbData)


def protect(data: bytes) -> bytes:
    # The guard runs before _crypt32(), or the failure off Windows would be
    # an AttributeError on ctypes.WinDLL instead of the stated OSError.
    _require_windows()
    return _call(_crypt32().CryptProtectData, "CryptProtectData", data)


def unprotect(blob: bytes) -> bytes:
    _require_windows()
    return _call(_crypt32().CryptUnprotectData, "CryptUnprotectData", blob)
