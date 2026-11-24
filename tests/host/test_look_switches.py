"""The Builder's look switches: names and choices are checked, defaults hold otherwise."""

import pytest

from kkbp_maps.builder import look


def test_defaults_until_set():
    look.set_switches(None)
    assert look.get("reflection") == "on" and look.current() == {}


def test_a_switch_is_set_and_reported():
    look.set_switches(["reflection=off"])
    assert look.get("reflection") == "off" and look.current() == {"reflection": "off"}
    look.set_switches(None)


@pytest.mark.parametrize("pair", ["nope=1", "reflection=sharp"])
def test_unknown_names_and_values_are_refused(pair):
    with pytest.raises(ValueError):
        look.set_switches([pair])
    look.set_switches(None)
