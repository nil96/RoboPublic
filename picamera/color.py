
import colorzero as c0

from .exc import PiCameraDeprecated


NAMED_COLORS = c0.tables.NAMED_COLORS
Red = c0.Red
Green = c0.Green
Blue = c0.Blue
Hue = c0.Hue
Lightness = c0.Lightness
Saturation = c0.Saturation


class Color(c0.Color):
    def __new__(cls, *args, **kwargs):
        warnings.warn(
            PiCameraDeprecated(
                ''))
        return c0.Color.__new__(cls, *args, **kwargs)
