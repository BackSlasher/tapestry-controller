"""
Predefined screen types for e-ink displays.
"""

from typing import NamedTuple


class ScreenType(NamedTuple):
    name: str
    description: str
    connector: str


# Registry of all available screen types
SCREEN_TYPES = {
    # https://www.panelook.com/ED060XC3_E_Ink_6.0_EPD_parameter_21976.html
    "ED060XC3": ScreenType(
        name="ED060XC3", description='6.0" E-Paper Display', connector="33"
    ),
    "ED097TC2": ScreenType(
        name="ED097TC2", description='9.7" E-Paper Display', connector="34"
    ),
}
