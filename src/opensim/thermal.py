"""Steady isotropic conduction with CalculiX, SI units throughout."""
import json
from pathlib import Path
import numpy as np

from opensim.geometry import import_and_mesh
from opensim.loads import assemble_load
from opensim.regions import selected_faces
from opensim.solver import deck_number, find_solver, run_solver
from opensim.thermal_parameters import THERMAL_DEFAULTS, validate_thermal_parameters
from opensim.results import write_viewer_data


def boundary_nodes(mesh, region, side):
    nodes = np.unique([node for face in selected_faces(mesh, region) for node in face]) if region else mesh.end_nodes(side)
    if len(nodes) < 3 or np.linalg.matrix_rank(mesh.points[nodes] - mesh.points[nodes[0]]) < 2:
        raise ValueError("Choose a nonzero-area thermal boundary surface")
    return np.asarray(nodes, dtype=int)


def write_thermal_deck(mesh, path, parameters):
    p = THERMAL_DEFAULTS | parameters
    validate_thermal_parameters(p)
    fixed = boundary_nodes(mesh, p["thermal_fixed_region"], "min")
    source = boundary_nodes(mesh, p["thermal_source_region"], "max")
    if np.intersect1d(fixed, source).size:
        raise ValueError("Thermal boundaries share nodes. Select separate surfaces that do not touch")
    power = np.zeros(len(mesh.points))
    if p["thermal_boundary_mode"] == "power" and p["thermal_power_W"] != 0:
        # Reuse only the consistent scalar surface weights; no mechanical force is applied.
        power = assemble_load(mesh, p["thermal_power_W"], "x", "traction", "x-max", p["thermal_source_region"]).forces[:, 0]
    lines = ["*HEADING", "Steady thermal conduction; SI: m, W, K", "*NODE, NSET=NALL"]
    lines += [f"{i+1}, " + ", ".join(deck_number(v) for v in point) for i, point in enumerate(mesh.points)]
    lines += [f"*ELEMENT, TYPE={mesh.element_type}, ELSET=SOLID"]
    lines += [f"{i+1}, " + ", ".join(str(int(n)+1) for n in element) for i, element in enumerate(mesh.tetrahedra)]
    lines += ["*NSET, NSET=FIX"] + [str(int(n)+1) for n in fixed]
    lines += ["*NSET, NSET=SOURCE"] + [str(int(n)+1) for n in source]
    lines += ["*MATERIAL, NAME=THERMAL", "*CONDUCTIVITY", deck_number(p["thermal_conductivity_W_mK"]),
              "*SOLID SECTION, ELSET=SOLID, MATERIAL=THERMAL", "*INITIAL CONDITIONS, TYPE=TEMPERATURE",
              "NALL, " + deck_number(p["thermal_fixed_temperature_K"]), "*STEP",
              "*HEAT TRANSFER, STEADY STATE, SOLVER=SPOOLES", "1., 1.", "*BOUNDARY",
              "FIX, 11, 11, " + deck_number(p["thermal_fixed_temperature_K"])]
    # CalculiX activates temperature DOF 11 on these solids in a HEAT TRANSFER step.
    if p["thermal_boundary_mode"] == "temperature":
        lines += ["SOURCE, 11, 11, " + deck_number(p["thermal_source_temperature_K"])]
    elif np.any(power):
        lines += ["*CFLUX"] + [f"{i+1}, 11, {deck_number(value)}" for i, value in enumerate(power) if value]
    lines += ["*NODE PRINT, NSET=NALL", "NT, RFL", "*NODE FILE", "NT", "*EL FILE", "HFL", "*END STEP"]
    Path(path).write_text("\n".join(lines) + "\n", encoding="ascii")
    return fixed, source, power


def parse_thermal_dat(path, count):
    blocks = {"temperature": {}, "heat": {}}
    current = None
    for line in Path(path).read_text(encoding="ascii", errors="strict").splitlines():
        if "temperatures for set" in line.lower():
            current = blocks["temperature"]
        elif "heat generation for set" in line.lower():
            current = blocks["heat"]
        fields = line.split()
        if current is not None and len(fields) == 2 and fields[0].isdigit():
            node = int(fields[0])
            if node in current:
                raise ValueError("Multiple or duplicate thermal result blocks are unsupported")
            current[node] = float(fields[1].replace("D", "E"))
    arrays = []
    for block in blocks.values():
        if set(block) != set(range(1, count + 1)):
            raise ValueError("Incomplete thermal temperature/heat results")
        values = np.array([block[n] for n in range(1, count + 1)])
        if not np.isfinite(values).all():
            raise ValueError("Nonfinite thermal results")
        arrays.append(values)
    return arrays


def parse_heat_flux(path, count):
    active, complete, values, components = False, False, {}, []
    for line in Path(path).read_text(encoding="ascii", errors="strict").splitlines():
        if line.startswith(" -4"):
            active = line.split()[1] == "FLUX"
        elif active and line.startswith(" -5"):
            components.append(line.split()[1])
        elif active and line.startswith(" -1"):
            node = int(line[3:13])
            if node in values:
                raise ValueError("Duplicate heat flux node")
            values[node] = [float(line[start:start+12].replace("D", "E")) for start in (13, 25, 37)]
        elif active and line.startswith(" -3"):
            complete = True
            break
    if not complete or components[:3] != ['F1','F2','F3'] or set(values) != set(range(1, count+1)):
        raise ValueError("Incomplete nodal heat flux results")
    flux = np.array([values[n] for n in range(1, count+1)])
    if not np.isfinite(flux).all():
        raise ValueError("Nonfinite nodal heat flux results")
    return flux


def solve_thermal(cad, output, size=.004, scale=1., order=1, parameters=None, ccx=None, progress=None):
    from opensim.cli import digest
    p = THERMAL_DEFAULTS | (parameters or {})
    validate_thermal_parameters(p)
    executable = find_solver(ccx)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    if progress: progress("meshing")
    mesh = import_and_mesh(Path(cad), size, scale, output / "mesh.msh", order=order)
    if progress: progress("preparing")
    fixed, source, power = write_thermal_deck(mesh, output / "model.inp", p)
    if progress: progress("solving")
    run_solver(executable, output)
    if progress: progress("reading")
    temperature, heat = parse_thermal_dat(output / "model.dat", len(mesh.points))
    flux = parse_heat_flux(output / "model.frd", len(mesh.points))
    if temperature.min() < -1e-6:
        raise ValueError("Predicted temperatures fall below absolute zero; review conductivity and heat extraction")
    temperature = np.maximum(temperature, 0.)
    fixed_heat, source_heat = float(heat[fixed].sum()), float(heat[source].sum())
    incoming = float(power.sum()) if p["thermal_boundary_mode"] == "power" else source_heat
    balance = fixed_heat + incoming
    rate = max(abs(fixed_heat), abs(incoming))
    if abs(balance) > max(1e-7, rate * 1e-4):
        raise ValueError("Thermal energy balance failed; inspect the solver output")
    summary = {"analysis": "thermal", "nodes": len(mesh.points), "tetrahedra": len(mesh.tetrahedra),
               "element_type": mesh.element_type, "mesh_repair": mesh.repair_report, "cad_faces": mesh.surface_catalog(),
               "minimum_temperature_K": float(temperature.min()), "maximum_temperature_K": float(temperature.max()),
               "maximum_heat_flux_W_m2": float(np.linalg.norm(flux, axis=1).max()),
               "fixed_boundary_heat_W": fixed_heat, "source_boundary_heat_W": source_heat,
               "applied_heat_W": float(power.sum()), "energy_balance_W": balance,
               "relative_energy_imbalance": abs(balance) / rate if rate > 1e-7 else 0.,
               "thermal_conductivity_W_mK": p["thermal_conductivity_W_mK"], "thermal_boundary_mode": p["thermal_boundary_mode"],
               "thermal_fixed_region": p["thermal_fixed_region"], "thermal_source_region": p["thermal_source_region"],
               "interpretation": "Steady isotropic conduction. Other surfaces insulated. No convection, radiation, transients or thermal expansion."}
    if progress: progress("exporting")
    data = {"points": mesh.points.tolist(), "faces": mesh.boundary_faces(), "face_ids": mesh.boundary_face_ids(),
            "displacement": np.zeros_like(mesh.points).tolist(), "temperature_K": temperature.tolist(),
            "heat_flux_W_m2": flux.tolist(), "summary": summary}
    write_viewer_data(output / "results.html", data)
    np.savez_compressed(output / "thermal.npz", points=mesh.points, tetrahedra=mesh.tetrahedra,
                        temperature_K=temperature, heat_flux_W_m2=flux, nodal_heat_W=heat,
                        applied_heat_W=power, fixed_nodes=fixed, source_nodes=source)
    np.savetxt(output / "temperatures.csv", np.column_stack([np.arange(1,len(temperature)+1), mesh.points,
                temperature, temperature - 273.15, flux]), delimiter=",", comments="",
                header="node_id,x_m,y_m,z_m,temperature_K,temperature_C,heat_flux_x_W_m2,heat_flux_y_W_m2,heat_flux_z_W_m2")
    corners = mesh.tetrahedra.shape[1]
    lines = ["# vtk DataFile Version 3.0", "Steady thermal results; SI", "ASCII", "DATASET UNSTRUCTURED_GRID",
             f"POINTS {len(mesh.points)} double"]
    lines += [" ".join(map(str, point)) for point in mesh.points]
    lines += [f"CELLS {len(mesh.tetrahedra)} {len(mesh.tetrahedra)*(corners+1)}"]
    lines += [str(corners) + " " + " ".join(map(str, row)) for row in mesh.tetrahedra]
    lines += [f"CELL_TYPES {len(mesh.tetrahedra)}"] + ["24" if corners == 10 else "10"] * len(mesh.tetrahedra)
    lines += [f"POINT_DATA {len(mesh.points)}", "SCALARS temperature_K double 1", "LOOKUP_TABLE default"] + list(map(str, temperature))
    lines += ["VECTORS heat_flux_W_m2 double"] + [" ".join(map(str, row)) for row in flux]
    (output / "results.vtk").write_text("\n".join(lines)+"\n", encoding="ascii")
    manifest = {"schema_version": 1, "analysis": "thermal", "units": {"length":"m","temperature":"K","heat_rate":"W","heat_flux":"W/m2"},
                "cad_sha256": digest(Path(cad)), "deck_sha256": digest(output / "model.inp"), "ccx_sha256": digest(executable),
                "parameters": p, "mesh_size_m": size, "cad_scale": scale, "summary": summary}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    return summary
