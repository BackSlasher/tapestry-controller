"""
Predefined screen types for e-ink displays.
"""

from typing import NamedTuple


class AreaDimensions(NamedTuple):
    height: float
    width: float


class FullDimensions(NamedTuple):
    top: float
    bottom: float
    left: float
    right: float


class ScreenType(NamedTuple):
    active_area: AreaDimensions
    bezel: FullDimensions


    def total_dimensions(self) -> AreaDimensions:
        return AreaDimensions(
            height=self.bezel.top + self.active_area.height + self.bezel.bottom,
            width=self.bezel.left + self.active_area.width + self.bezel.right,
        )


# https://www.panelook.com/ED060XC3_E_Ink_6.0_EPD_parameter_21976.html
ED060XC3 = ScreenType(
    active_area=AreaDimensions(
        height=90.58,
        width=122.37,
    ),
    bezel=FullDimensions(
        left=0.2,
        right=1.4,
        top=0.5,
        bottom=0.5,
    ),
)

ED097TC2 = ScreenType(
    active_area=AreaDimensions(
        height=139.425,
        width=202.8,
    ),
    # Approximated
    bezel=FullDimensions(
        top=4.0,
        bottom=12.0,
        left=4.0,
        right=12.0,
    ),
)

# Registry of all available screen types
SCREEN_TYPES = {
    "ED060XC3": ED060XC3,
    "ED097TC2": ED097TC2,
}
