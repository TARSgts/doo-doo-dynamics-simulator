"""Backward-compatible defaults and validation for shared and study inputs."""
import math
from opensim.impact_parameters import IMPACT_DEFAULTS,validate_impact_parameters
from opensim.load_settings import LOAD_AXES,LOAD_KINDS,LOAD_SURFACES,NORMAL_AXES
from opensim.region_settings import validate_region
from opensim.thermal_parameters import THERMAL_DEFAULTS,validate_thermal_parameters
from opensim.cfd_parameters import CFD_DEFAULTS,validate_cfd_parameters

DEFAULT_PARAMETERS = {"mesh_size_m": 0.004, "cad_scale": 1.0, "young_Pa": 210e9,
                      "poisson": 0.3, "load_N": 1000.0, "element_order": 1,
                      "load_axis": "x", "load_kind": "face", "load_surface": "x-max", "density_kg_m3": 7850.0, "mode_count": 6,
                      "support_region": {}, "load_region": {}, "load_cases": [], "material_name":"Custom",
                      "convergence_levels": 4, "convergence_ratio": 1.4, "convergence_tolerance_percent": 2.0,
                      "convergence_target": "displacement"} | THERMAL_DEFAULTS | CFD_DEFAULTS | IMPACT_DEFAULTS

TEXT_PARAMETERS = {"load_axis", "load_kind", "load_surface", "support_region", "load_region", "convergence_target",
                   "thermal_boundary_mode", "thermal_fixed_region", "thermal_source_region", "cfd_case", "load_cases", "material_name", "cfd_inlet_region", "cfd_outlet_region",'cfd_backend','cfd_domain_mode','cfd_flow_axis','cfd_turbulence'}


def prepare_parameters(current,parameters):
    project = {"parameters": current}
    geometry_keys={'cfd_domain_mode','cfd_flow_axis','cfd_padding','cfd_mesh_size_m','cfd_cad_scale'}
    parameters=dict(parameters)
    if any(key in parameters and parameters[key]!=project['parameters'][key] for key in geometry_keys):
        parameters.setdefault('cfd_inlet_region',{});parameters.setdefault('cfd_outlet_region',{})
    parameters = {key: {} if key in {"support_region", "load_region"} and value is None else value for key, value in parameters.items()}
    if set(parameters) - set(DEFAULT_PARAMETERS):
        raise ValueError("Unsupported analysis parameter")
    merged = project["parameters"] | parameters
    validate_thermal_parameters(merged)
    validate_cfd_parameters(merged)
    validate_impact_parameters(merged)
    from opensim.load_case_parameters import validate_load_cases
    validate_load_cases(merged['load_cases'])
    if not isinstance(merged['material_name'],str) or len(merged['material_name'])>100: raise ValueError('Invalid material name')
    numeric = [value for key, value in merged.items() if key not in TEXT_PARAMETERS]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in numeric):
        raise ValueError("All parameters must be finite numbers")
    if (merged["element_order"] not in {1, 2} or merged["load_axis"] not in LOAD_AXES
            or merged["load_kind"] not in LOAD_KINDS or merged["load_surface"] not in LOAD_SURFACES):
        raise ValueError("Choose element order 1/2, X/Y/Z or surface normal, face/point/traction and a bounding-plane surface")
    if merged["load_axis"] in NORMAL_AXES and merged["load_kind"] != "traction":
        raise ValueError("Perpendicular surface loading requires uniform surface traction")
    if any(merged[key] <= 0 for key in ("mesh_size_m", "cad_scale", "young_Pa")):
        raise ValueError("Mesh size, CAD scale and Young's modulus must be positive")
    from opensim.modal_parameters import validate_modal_parameters
    validate_modal_parameters(merged["density_kg_m3"], merged["mode_count"])
    from opensim.convergence import validate_convergence_parameters
    if isinstance(merged["convergence_levels"], float) and merged["convergence_levels"].is_integer():
        merged["convergence_levels"] = int(merged["convergence_levels"])
        if "convergence_levels" in parameters:
            parameters["convergence_levels"] = merged["convergence_levels"]
    validate_convergence_parameters(merged["convergence_levels"], merged["convergence_ratio"],
                                    merged["convergence_tolerance_percent"], merged["convergence_target"])
    validate_region(merged["support_region"])
    validate_region(merged["load_region"])
    if merged["load_region"] and merged["load_kind"] != "traction":
        raise ValueError("A selected load region requires uniform surface traction")
    if not -1 < merged["poisson"] < 0.5 or (merged["load_N"] == 0 and not merged['load_cases']):
        raise ValueError("Use -1 < Poisson ratio < 0.5 and a nonzero axial load")
    return parameters,merged
