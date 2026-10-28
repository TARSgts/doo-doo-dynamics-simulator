import math
from opensim.region_settings import validate_region


THERMAL_DEFAULTS = {
    "thermal_conductivity_W_mK": 1.0,
    "thermal_fixed_temperature_K": 293.15,
    "thermal_source_temperature_K": 373.15,
    "thermal_power_W": 10.0,
    "thermal_boundary_mode": "temperature",
    "thermal_fixed_region": {}, "thermal_source_region": {},
}


def validate_thermal_parameters(parameters):
    p = THERMAL_DEFAULTS | parameters
    for key in ("thermal_conductivity_W_mK", "thermal_fixed_temperature_K", "thermal_source_temperature_K", "thermal_power_W"):
        if isinstance(p[key], bool) or not isinstance(p[key], (float, int)) or not math.isfinite(p[key]):
            raise ValueError("Thermal conductivity, temperatures and heat input must be finite numbers")
    if p["thermal_conductivity_W_mK"] <= 0:
        raise ValueError("Thermal conductivity must be positive, in W/(m·K)")
    if min(p["thermal_fixed_temperature_K"], p["thermal_source_temperature_K"]) < 0:
        raise ValueError("Temperature cannot be below absolute zero (0 K / -273.15 °C)")
    if p["thermal_boundary_mode"] not in {"temperature", "power"}:
        raise ValueError("Choose a second prescribed temperature or total heat input")
    for key in ("thermal_fixed_region", "thermal_source_region"):
        validate_region(p[key])
