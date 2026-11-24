"""The Builder's look switches: names and choices are checked, defaults hold otherwise."""

import pytest

from kkbp_maps.builder import look


def test_defaults_until_set():
    look.set_switches(None)
    assert look.get("shadow_cull") == "front" and look.number("sun_angle") == 0.5 and look.current() == {}


def test_a_switch_is_set_and_reported():
    look.set_switches(["shadow_cull=none", "sun_angle=0"])
    assert look.get("shadow_cull") == "none" and look.number("sun_angle") == 0.0
    assert look.current() == {"shadow_cull": "none", "sun_angle": "0"}
    look.set_switches(None)


@pytest.mark.parametrize("pair", ["nope=1", "shadow_cull=back", "sun_angle=wide"])
def test_unknown_names_and_values_are_refused(pair):
    with pytest.raises(ValueError):
        look.set_switches([pair])
    look.set_switches(None)
