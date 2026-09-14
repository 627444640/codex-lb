from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes
from functools import lru_cache

logger = logging.getLogger(__name__)

_memory_warning_threshold_bytes: int = 0
_memory_reject_threshold_bytes: int = 0
_rss_provider_warning_logged = False


# The warning level is derived, not configured: it exists only as an early
# signal that the reject threshold is being approached, so it is fixed at 80%
# of the reject threshold (issue #1340 / PRINCIPLES.md P2). 0 disables both.
_WARNING_FRACTION = 0.8


def configure(reject_threshold_mb: int = 0) -> None:
    global _memory_warning_threshold_bytes, _memory_reject_threshold_bytes
    _memory_reject_threshold_bytes = reject_threshold_mb * 1024 * 1024
    _memory_warning_threshold_bytes = int(_memory_reject_threshold_bytes * _WARNING_FRACTION)


def _get_windows_rss_bytes() -> int | None:
    if sys.platform != "win32":
        return None

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(ProcessMemoryCounters)
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
    except (AttributeError, OSError):
        return None

    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    process = kernel32.GetCurrentProcess()
    ok = psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
    if ok == 0:
        return None
    return int(counters.WorkingSetSize)


class _MachTaskBasicInfo(ctypes.Structure):
    # mach/task_info.h: MACH_TASK_BASIC_INFO is the platform's always-64-bit
    # layout; resident_size is current RSS, resident_size_max is the peak.
    _fields_ = [
        ("virtual_size", ctypes.c_uint64),
        ("resident_size", ctypes.c_uint64),
        ("resident_size_max", ctypes.c_uint64),
        ("user_time", ctypes.c_int * 2),
        ("system_time", ctypes.c_int * 2),
        ("policy", ctypes.c_int),
        ("suspend_count", ctypes.c_int),
    ]


@lru_cache(maxsize=1)
def _macos_task_library() -> ctypes.CDLL | None:
    try:
        library = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        library.mach_task_self.argtypes = []
        library.mach_task_self.restype = ctypes.c_uint
        library.task_info.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
        library.task_info.restype = ctypes.c_int
        return library
    except (AttributeError, OSError):
        return None


def _get_macos_rss_bytes() -> int | None:
    if sys.platform != "darwin":
        return None
    library = _macos_task_library()
    if library is None:
        return None
    info = _MachTaskBasicInfo()
    expected_count = ctypes.sizeof(info) // ctypes.sizeof(ctypes.c_uint)
    count = ctypes.c_uint(expected_count)
    result = library.task_info(library.mach_task_self(), 20, ctypes.byref(info), ctypes.byref(count))
    if result != 0 or count.value < expected_count:
        return None
    return int(info.resident_size)


def _log_rss_provider_unavailable() -> None:
    global _rss_provider_warning_logged
    if _rss_provider_warning_logged:
        return
    _rss_provider_warning_logged = True
    logger.warning("Memory RSS provider unavailable on platform %s; disabling memory-pressure checks", sys.platform)


def get_rss_bytes() -> int:
    try:
        psutil = __import__("psutil")
        return int(psutil.Process().memory_info().rss)
    except ImportError:
        pass

    if sys.platform == "linux":
        try:
            with open("/proc/self/statm", "rb") as f:
                pages = int(f.read().split()[1])
            return pages * os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError, IndexError):
            pass

    rss = _get_windows_rss_bytes()
    if rss is not None:
        return rss

    rss = _get_macos_rss_bytes()
    if rss is not None:
        return rss

    _log_rss_provider_unavailable()
    return 0


def is_memory_pressure() -> bool:
    if _memory_reject_threshold_bytes <= 0:
        return False
    return get_rss_bytes() >= _memory_reject_threshold_bytes


def is_memory_warning() -> bool:
    if _memory_warning_threshold_bytes <= 0:
        return False
    return get_rss_bytes() >= _memory_warning_threshold_bytes


__all__ = ["configure", "get_rss_bytes", "is_memory_pressure", "is_memory_warning"]
