"""Original single-solid heat sink and an illustrative steady-conduction setup."""
from pathlib import Path
import gmsh

from opensim.geometry import gmsh_session


# STEP coordinates are millimeters; thermal regions use the app's SI meters.
HEAT_SINK_PARAMETERS = {
    "mesh_size_m": .0025, "cad_scale": .001, "element_order": 2,
    "thermal_conductivity_W_mK": 200., "thermal_boundary_mode": "power", "thermal_power_W": 20.,
    "thermal_fixed_temperature_K": 293.15,
    "thermal_fixed_region": {"box_m": [-1e-7,-1e-7,.024-1e-7,.0600001,.0400001,.0240001]},
    "thermal_source_region": {"box_m": [-1e-7,-1e-7,-1e-7,.0600001,.0400001,1e-7]},
}


def make_heat_sink(path: Path):
    """60×40×4 mm base; six 2×40×20 mm fins, fused into one solid."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gmsh_session():
        gmsh.model.add("sample_heat_sink")
        base = gmsh.model.occ.addBox(0,0,0,60,40,4)
        fins = [(3,gmsh.model.occ.addBox(4+10*i,0,4,2,40,20)) for i in range(6)]
        gmsh.model.occ.fuse([(3,base)],fins)
        gmsh.model.occ.synchronize()
        if len(gmsh.model.getEntities(3)) != 1:
            raise ValueError("Heat-sink sample must be one connected solid")
        gmsh.write(str(path.resolve()))
