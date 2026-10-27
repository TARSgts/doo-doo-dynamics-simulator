import math


def validate_modal_parameters(density, mode_count):
    if isinstance(density, bool) or not math.isfinite(density) or density <= 0:
        raise ValueError("Density must be positive and finite, in kg/m³")
    if isinstance(mode_count, bool) or not isinstance(mode_count, int) or not 1 <= mode_count <= 30:
        raise ValueError("Request an integer number of modes from 1 to 30")
