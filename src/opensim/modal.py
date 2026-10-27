import importlib.metadata
import json
from pathlib import Path
import re

import numpy as np

from opensim.cli import digest
from opensim.geometry import import_and_mesh
from opensim.modal_parameters import validate_modal_parameters
from opensim.results import write_viewer, write_vtk
from opensim.solver import find_solver, run_solver


def write_modal_deck(mesh, path, young, poisson, density, mode_count):
    validate_modal_parameters(density, mode_count)
    if not np.isfinite(young) or young <= 0 or not np.isfinite(poisson) or not -1 < poisson < 0.5:
        raise ValueError("Use positive finite Young's modulus and Poisson ratio strictly between -1 and 0.5")
    fixed = mesh.end_nodes("min")
    if len(fixed) < 3 or np.linalg.matrix_rank(mesh.points[fixed] - mesh.points[fixed[0]]) < 2:
        raise ValueError("The X-min fixed support needs a planar face with noncollinear nodes")
    lines = ["*HEADING", "Independent undamped unprestressed modal analysis", "*NODE, NSET=NALL"]
    lines.extend(f"{index + 1}, " + ", ".join(f"{value:.15g}" for value in point) for index, point in enumerate(mesh.points))
    lines.append(f"*ELEMENT, TYPE={mesh.element_type}, ELSET=SOLID")
    lines.extend(f"{index + 1}, " + ", ".join(str(int(node) + 1) for node in element)
                 for index, element in enumerate(mesh.tetrahedra))
    lines.append("*NSET, NSET=FIX")
    lines.extend(str(int(node) + 1) for node in fixed)
    lines.extend(["*MATERIAL, NAME=ELASTIC", "*ELASTIC", f"{young:.15g}, {poisson:.15g}",
                  "*DENSITY", f"{density:.15g}", "*SOLID SECTION, ELSET=SOLID, MATERIAL=ELASTIC", "*BOUNDARY", "FIX, 1, 3, 0",
                  "*STEP", "*FREQUENCY, SOLVER=SPOOLES", str(mode_count), "*NODE PRINT, NSET=NALL", "U", "*NODE FILE", "U", "*END STEP"])
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def parse_modal_dat(path: Path, node_count: int, mode_count: int):
    frequencies, eigenvalues, modes = [], [], {}
    table = False
    current = None
    reading = False
    for line in path.read_text(encoding="ascii", errors="strict").splitlines():
        compact = "".join(line.split())
        if compact.startswith("MODENO") and "EIGENVALUE" in compact:
            table = True
            continue
        if "PARTICIPATIONFACTORS" in compact:
            table = False
        match = re.fullmatch(r"EIGENVALUENUMBER(\d+)", compact)
        if match:
            current = int(match[1])
            if current in modes:
                raise ValueError("Duplicate eigenmode block")
            modes[current] = {}
            reading = False
            continue
        if "displacements" in line.lower():
            if current is None:
                raise ValueError("Displacement block without an eigenmode number")
            reading = True
            continue
        fields = line.split()
        if table and len(fields) == 5 and fields[0].isdigit():
            if int(fields[0]) != len(frequencies) + 1:
                raise ValueError("Eigenfrequency numbers must be complete and sequential")
            eigenvalue, angular, frequency, imaginary = [float(value.replace("D", "E")) for value in fields[1:]]
            if (not np.isfinite([eigenvalue, angular, frequency, imaginary]).all() or min(eigenvalue, angular, frequency) <= 0
                    or imaginary != 0 or not np.isclose(angular, 2 * np.pi * frequency, rtol=2e-6)
                    or not np.isclose(eigenvalue, angular ** 2, rtol=2e-6)):
                raise ValueError("Invalid, unstable or inconsistent eigenfrequency")
            eigenvalues.append(eigenvalue)
            frequencies.append(frequency)
        elif reading and len(fields) == 4 and fields[0].isdigit():
            node = int(fields[0])
            if node in modes[current]:
                raise ValueError("Duplicate node in eigenmode")
            modes[current][node] = [float(value.replace("D", "E")) for value in fields[1:]]
    if len(frequencies) != mode_count or set(modes) != set(range(1, mode_count + 1)):
        raise ValueError("Incomplete eigenfrequency or eigenmode results")
    if any(set(nodes) != set(range(1, node_count + 1)) for nodes in modes.values()):
        raise ValueError("Eigenmode nodal results are incomplete")
    shapes = np.array([[modes[mode][node] for node in range(1, node_count + 1)] for mode in range(1, mode_count + 1)])
    if not np.isfinite(shapes).all() or np.any(np.max(np.linalg.norm(shapes, axis=2), axis=1) <= 0):
        raise ValueError("Nonfinite or zero eigenmode shape")
    if np.any(np.diff(frequencies) < 0):
        raise ValueError("Eigenfrequencies are not sorted")
    return np.asarray(frequencies), np.asarray(eigenvalues), shapes


def solve_modal(cad: Path, output: Path, size=0.01, scale=1.0, young=210e9,
                poisson=0.3, density=7850.0, mode_count=6, ccx=None, order=2):
    validate_modal_parameters(density, mode_count)
    executable = find_solver(ccx)
    if not cad.is_file():
        raise FileNotFoundError(cad)
    output.mkdir(parents=True, exist_ok=False)
    mesh = import_and_mesh(cad, size, scale, output / "mesh.msh", order=order)
    write_modal_deck(mesh, output / "model.inp", young, poisson, density, mode_count)
    run_solver(executable, output)
    frequencies, eigenvalues, raw_modes = parse_modal_dat(output / "model.dat", len(mesh.points), mode_count)
    maxima = np.max(np.linalg.norm(raw_modes, axis=2), axis=1)
    shapes = raw_modes / maxima[:, None, None]
    for shape in shapes:
        shape *= np.sign(shape.flat[np.abs(shape).argmax()])
    clamp_residual = float(np.abs(shapes[:, mesh.end_nodes("min")]).max())
    if clamp_residual > 1e-8:
        raise ValueError("Mode shapes violate the fixed support")
    summary = {"analysis": "modal", "nodes": len(mesh.points), "tetrahedra": len(mesh.tetrahedra),
               "element_type": mesh.element_type, "mode_count": mode_count, "frequencies_Hz": frequencies.tolist(),
               "eigenvalues_rad2_s2": eigenvalues.tolist(), "young_Pa": young, "poisson": poisson,
               "density_kg_m3": density, "boundary_condition": "X-min face fully fixed; all other boundaries free",
               "clamp_shape_residual": clamp_residual,
               "normalization": "Each displayed eigenvector has maximum nodal vector magnitude 1 (dimensionless)",
               "interpretation": "Undamped, unprestressed free vibration; no static loads. Display amplitude and animation speed are arbitrary."}
    for index, shape in enumerate(shapes, start=1):
        mode_summary = summary | {"mode_number": index, "frequency_Hz": float(frequencies[index - 1])}
        write_viewer(output / f"mode-{index}.html", mesh, shape, mode_summary)
        write_vtk(output / f"mode-{index}.vtk", mesh, shape, quantity="mode_shape_normalized")
    np.savez_compressed(output / "modes.npz", points=mesh.points, tetrahedra=mesh.tetrahedra,
                        frequencies_Hz=frequencies, eigenvalues=eigenvalues, raw_modes=raw_modes,
                        normalized_modes=shapes, raw_maxima=maxima)
    manifest = {"schema_version": 1, "analysis": "modal", "cad_path": str(cad.resolve()), "cad_sha256": digest(cad),
                "ccx_path": str(executable), "ccx_sha256": digest(executable), "deck_sha256": digest(output / "model.inp"),
                "mesh_size_m": size, "cad_scale_to_m": scale, "element_order": order,
                "gmsh": importlib.metadata.version("gmsh"), "numpy": np.__version__, "summary": summary}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    return summary
