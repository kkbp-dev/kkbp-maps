"""The memory watchdog: its counters on this platform, its rules, and stopping a command."""

import sys

import pytest

from kkbp_maps.jobs import memory
from kkbp_maps.jobs.memory import GB, Limits, Watch, run_watched

SLEEPER = [sys.executable, "-I", "-c", "import time; time.sleep(30)"]
GREEDY = [sys.executable, "-I", "-c", "import time; b = bytearray(300 * 2**20); b[::4096] = b'x' * len(b[::4096]); time.sleep(30)"]


def test_this_platform_reads_its_counters():
    assert memory.total_memory() and memory.available_memory()
    assert 0 < memory.available_memory() <= memory.total_memory()


def test_the_cap_is_a_share_of_this_machine():
    total = memory.total_memory()
    capped = Limits(10_000.0).capped(0.5)
    assert capped.max_rss_gb == pytest.approx(total * 0.5 / GB, abs=0.1)
    assert Limits(0.5).capped().max_rss_gb == 0.5


def test_a_finished_command_reports_its_code():
    code, _, reason = run_watched([sys.executable, "-I", "-c", "raise SystemExit(3)"], Limits(), notice=lambda t: None)
    assert (code, reason) == (3, "")


def test_a_command_past_its_cap_is_stopped():
    code, peak, reason = run_watched(GREEDY, Limits(max_rss_gb=0.1, min_available_gb=0, min_swap_free_gb=0),
                                     notice=lambda t: None)
    assert code != 0 and reason == "stopped: it passed 0.1 GB" and peak > 0.1 * GB


def test_a_command_is_cancelled():
    calls = iter([False, False, True])
    code, _, reason = run_watched(SLEEPER, Limits(), stop=lambda: next(calls, True), notice=lambda t: None)
    assert code != 0 and reason == "cancelled"


def test_an_unreadable_counter_leaves_its_rule_out(monkeypatch):
    monkeypatch.setattr(memory, "available_memory", lambda: None)
    monkeypatch.setattr(memory, "swap_free", lambda: None)
    watch = Watch(0)
    assert "the memory left" in watch.unread
    assert watch.breach(None, Limits(min_available_gb=10**6, min_swap_free_gb=10**6)) == ""
