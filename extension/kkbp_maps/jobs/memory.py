"""Runs a command and stops it before memory runs short, so a runaway extraction or Blender build
can't freeze the machine. Reads the operating system's own counters: /proc on Linux, psapi and
GlobalMemoryStatusEx on Windows, libproc and sysctl on macOS, all through the standard library.
A counter that can't be read leaves its rule out, with a notice; nothing is guessed.

Imports only the standard library.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

POLL_SECONDS = 0.5
GB = 2**30


@dataclass(frozen=True)
class Limits:
    max_rss_gb: float = 3.0          # the process's own memory (and its swap, where that is counted)
    min_available_gb: float = 1.5    # the machine's memory left for everything else
    min_swap_free_gb: float = 6.0    # Linux only: swap left, where there is swap

    def capped(self, share: float = 0.6) -> "Limits":
        """These limits with the process cap at most `share` of this machine's memory."""
        total = total_memory()
        if total is None:
            return self
        return Limits(min(self.max_rss_gb, round(total * share / GB, 1)), self.min_available_gb, self.min_swap_free_gb)


EXTRACT = Limits(3.0)   # a Golden Map takes under 1 GB
BUILD = Limits(8.0)     # a Blender step on the biggest Golden Map stays under 3 GB


def run_watched(cmd: list[str], limits: Limits, *, stop: Callable[[], bool] = lambda: False,
                notice: Callable[[str], None] = print, **popen) -> tuple[int, int, str]:
    """Runs a command, stopping it if memory runs short or `stop()` turns true.
    Returns (exit code, peak bytes, why it was stopped or "")."""
    proc = subprocess.Popen(cmd, **popen)
    watch = Watch(proc.pid)
    if watch.unread:
        notice(f"(can't read {', '.join(watch.unread)} here: those memory rules are off)")
    peak, reason = 0, ""
    while proc.poll() is None:
        used = watch.process()
        if used is not None:
            peak = max(peak, used)
        reason = "cancelled" if stop() else watch.breach(used, limits)
        if reason:
            proc.kill()
            proc.wait()
            return -9, peak, reason if reason == "cancelled" else f"stopped: {reason}"
        time.sleep(POLL_SECONDS)
    return proc.returncode, peak, ""


class Watch:
    def __init__(self, pid: int):
        self.pid = pid
        self.unread = [name for name, value in (("the process's memory", self.process()),
                                                 ("the memory left", available_memory())) if value is None]

    def process(self) -> int | None:
        return process_memory(self.pid)

    def breach(self, used: int | None, limits: Limits) -> str:
        if used is not None and used > limits.max_rss_gb * GB:
            return f"it passed {limits.max_rss_gb} GB"
        available = available_memory()
        if available is not None and available < limits.min_available_gb * GB:
            return f"less than {limits.min_available_gb} GB of memory was left"
        swap = swap_free()
        if swap is not None and swap < limits.min_swap_free_gb * GB:
            return f"less than {limits.min_swap_free_gb} GB of swap was left"
        return ""


# --- the counters, per platform ---------------------------------------------------------------------

def process_memory(pid: int) -> int | None:
    """The memory a process holds, in bytes: VmRSS + VmSwap on Linux, the private commit on Windows,
    the physical footprint on macOS."""
    try:
        if sys.platform.startswith("linux"):
            total = 0
            for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                if line.startswith(("VmRSS:", "VmSwap:")):
                    total += int(line.split()[1]) * 1024
            return total
        if sys.platform == "win32":
            return _windows_process(pid)
        if sys.platform == "darwin":
            return _mac_process(pid)
    except (OSError, ValueError, AttributeError):
        pass
    return None


def available_memory() -> int | None:
    try:
        if sys.platform.startswith("linux"):
            return _meminfo()["MemAvailable"]
        if sys.platform == "win32":
            return _windows_status().ullAvailPhys
        if sys.platform == "darwin":
            level = _sysctl_int("kern.memorystatus_level")   # the share of memory free, in percent
            total = _sysctl_int("hw.memsize")
            return None if level is None or total is None else total * level // 100
    except (OSError, ValueError, KeyError, AttributeError):
        pass
    return None


def total_memory() -> int | None:
    try:
        if sys.platform.startswith("linux"):
            return _meminfo()["MemTotal"]
        if sys.platform == "win32":
            return _windows_status().ullTotalPhys
        if sys.platform == "darwin":
            return _sysctl_int("hw.memsize")
    except (OSError, ValueError, KeyError, AttributeError):
        pass
    return None


def swap_free() -> int | None:
    """Linux only, where a full swap is what freezes the desktop; None where there is no swap."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        info = _meminfo()
        return info["SwapFree"] if info.get("SwapTotal") else None
    except (OSError, ValueError, KeyError):
        return None


def _meminfo() -> dict[str, int]:
    out = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        name, _, rest = line.partition(":")
        out[name] = int(rest.split()[0]) * 1024
    return out


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class _ProcessMemoryCountersEx(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


def _windows_status() -> _MemoryStatusEx:
    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx failed")
    return status


def _windows_process(pid: int) -> int | None:
    kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        counters = _ProcessMemoryCountersEx()
        counters.cb = ctypes.sizeof(counters)
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        if not psapi.GetProcessMemoryInfo(ctypes.c_void_p(handle), ctypes.byref(counters), counters.cb):
            return None
        return counters.PrivateUsage
    finally:
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle(ctypes.c_void_p(handle))


class _RusageInfoV2(ctypes.Structure):
    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in (
        "ri_user_time", "ri_system_time", "ri_pkg_idle_wkups", "ri_interrupt_wkups", "ri_pageins",
        "ri_wired_size", "ri_resident_size", "ri_phys_footprint", "ri_proc_start_abstime",
        "ri_proc_exit_abstime", "ri_child_user_time", "ri_child_system_time", "ri_child_pkg_idle_wkups",
        "ri_child_interrupt_wkups", "ri_child_pageins", "ri_child_elapsed_abstime", "ri_diskio_bytesread",
        "ri_diskio_byteswritten")]


def _mac_process(pid: int) -> int | None:
    libproc = ctypes.CDLL(ctypes.util.find_library("proc") or "/usr/lib/libproc.dylib")
    info = _RusageInfoV2()
    if libproc.proc_pid_rusage(ctypes.c_int(pid), ctypes.c_int(2), ctypes.byref(info)) != 0:   # RUSAGE_INFO_V2
        return None
    return info.ri_phys_footprint


def _sysctl_int(name: str) -> int | None:
    libc = ctypes.CDLL(ctypes.util.find_library("c"))
    value = ctypes.c_uint64(0)
    size = ctypes.c_size_t(ctypes.sizeof(value))
    if libc.sysctlbyname(name.encode(), ctypes.byref(value), ctypes.byref(size), None, ctypes.c_size_t(0)) != 0:
        return None
    return value.value & ((1 << (8 * size.value)) - 1)
