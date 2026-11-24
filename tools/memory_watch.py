"""Runs a command and stops it before memory runs short, so a runaway extraction or Blender build
can't freeze the desktop. Reads /proc, so it watches on Linux only; elsewhere it runs unwatched."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

POLL_SECONDS = 0.5


@dataclass(frozen=True)
class Limits:
    max_rss_gb: float = 3.0
    min_available_gb: float = 1.5
    min_swap_free_gb: float = 6.0


def run_watched(cmd: list[str], limits: Limits, **popen) -> tuple[int, int, str]:
    """Runs a command, stopping it if memory runs short. Returns (exit code, peak bytes, why stopped)."""
    proc = subprocess.Popen(cmd, **popen)
    if not Path("/proc").is_dir():
        print("  (no /proc here: running without the memory watchdog)")
        return proc.wait(), 0, ""
    peak, reason = 0, ""
    while proc.poll() is None:
        used = process_memory(proc.pid)
        peak = max(peak, used)
        info = meminfo()
        if used > limits.max_rss_gb * 2**30:
            reason = f"it passed {limits.max_rss_gb} GB"
        elif info.get("MemAvailable", 1 << 62) < limits.min_available_gb * 2**30:
            reason = f"less than {limits.min_available_gb} GB of memory was left"
        elif info.get("SwapTotal") and info.get("SwapFree", 1 << 62) < limits.min_swap_free_gb * 2**30:
            reason = f"less than {limits.min_swap_free_gb} GB of swap was left"
        if reason:
            proc.kill()
            proc.wait()
            return -9, peak, f"stopped: {reason}"
        time.sleep(POLL_SECONDS)
    return proc.returncode, peak, ""


def process_memory(pid: int) -> int:
    """VmRSS + VmSwap of a process, in bytes."""
    total = 0
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith(("VmRSS:", "VmSwap:")):
                total += int(line.split()[1]) * 1024
    except OSError:
        pass
    return total


def meminfo() -> dict[str, int]:
    out = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        name, _, rest = line.partition(":")
        out[name] = int(rest.split()[0]) * 1024
    return out
