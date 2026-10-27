import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from opensim.geometry import import_and_mesh, make_box
from opensim.results import write_viewer, write_vtk
from opensim.solver import find_solver, parse_dat, run_solver, write_deck


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def solve(cad: Path, output: Path, size=0.05, scale=1.0, young=210e9,
          poisson=0.0, load=1000.0, ccx=None, order=1, load_axis="x", load_kind="face") -> dict:
    executable = find_solver(ccx)
    if not cad.is_file():
        raise FileNotFoundError(cad)
    output.mkdir(parents=True, exist_ok=False)
    mesh = import_and_mesh(cad, size, scale, output / "mesh.msh", order=order, tip_point=load_kind == "point")
    write_deck(mesh, output / "model.inp", young, poisson, load, load_axis, load_kind)
    run_solver(executable, output)
    displacement, reactions = parse_dat(output / "model.dat", len(mesh.points))
    fixed_ids = {int(node) + 1 for node in mesh.end_nodes("min")}
    if set(reactions) != fixed_ids:
        raise ValueError("Reaction results do not match the fixed node set")
    resultant = np.sum(list(reactions.values()), axis=0)
    applied = np.zeros(3)
    applied["xyz".index(load_axis)] = load
    relative_imbalance = float(np.linalg.norm(resultant + applied) / abs(load))
    if relative_imbalance > 1e-4:
        raise ValueError("Reaction forces fail global equilibrium tolerance")
    reference = (mesh.points.min(axis=0) + mesh.points.max(axis=0)) / 2
    reference[0] = mesh.points[:, 0].min()
    loaded = np.array([mesh.tip_node()]) if load_kind == "point" else mesh.end_nodes("max")
    reaction_moment = np.sum([np.cross(mesh.points[node - 1] - reference, force)
                              for node, force in reactions.items()], axis=0)
    applied_moment = np.cross(mesh.points[loaded].mean(axis=0) - reference, applied)
    moment_scale = abs(load) * np.ptp(mesh.points[:, 0])
    moment_imbalance = float(np.linalg.norm(reaction_moment + applied_moment) / moment_scale)
    if moment_imbalance > 1e-4:
        raise ValueError("Reaction forces fail global moment equilibrium tolerance")
    summary = {"nodes": len(mesh.points), "tetrahedra": len(mesh.tetrahedra), "element_type": mesh.element_type,
               "maximum_displacement_m": float(np.linalg.norm(displacement, axis=1).max()),
               "mean_loaded_ux_m": float(displacement[mesh.end_nodes("max"), 0].mean()),
               "tip_mean_displacement_m": mesh.tip_average(displacement).tolist(),
               "load_point_m": mesh.points[loaded].mean(axis=0).tolist(),
               "load_point_displacement_m": displacement[loaded].mean(axis=0).tolist(),
               "reaction_moment_Nm": reaction_moment.tolist(), "applied_moment_Nm": applied_moment.tolist(),
               "relative_moment_imbalance": moment_imbalance, "load_axis": load_axis, "load_kind": load_kind,
               "reaction_N": resultant.tolist(), "relative_force_imbalance": relative_imbalance,
               "load_N": load, "young_Pa": young, "poisson": poisson,
               "boundary_condition": f"X minimum clamped; {load_axis.upper()} load at X maximum ({load_kind})"}
    manifest = {"schema_version": 1, "cad_path": str(cad.resolve()), "cad_sha256": digest(cad),
                "ccx_path": str(executable), "ccx_sha256": digest(executable),
                "mesh_size_m": size, "cad_scale_to_m": scale, "element_order": order,
                "gmsh": importlib.metadata.version("gmsh"), "numpy": np.__version__,
                "deck_sha256": digest(output / "model.inp"), "summary": summary}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    write_vtk(output / "results.vtk", mesh, displacement)
    write_viewer(output / "results.html", mesh, displacement, summary)
    np.savez_compressed(output / "fields.npz", points=mesh.points, tetrahedra=mesh.tetrahedra, displacement=displacement)
    return summary


def main():
    parser = argparse.ArgumentParser(description="CAD to linear static structural simulation (SI units)")
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example", help="Generate an independently defined STEP bar")
    example.add_argument("path", type=Path)
    run = commands.add_parser("solve", help="Mesh and solve one closed STEP/IGES/BREP solid")
    run.add_argument("cad", type=Path)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--mesh-size", type=float, default=0.05)
    run.add_argument("--cad-scale", type=float, default=1.0, help="Coordinate multiplier to meters; mm: 0.001")
    run.add_argument("--young", type=float, default=210e9)
    run.add_argument("--poisson", type=float, default=0.0)
    run.add_argument("--load", type=float, default=1000.0, help="Total axial force in newtons")
    run.add_argument("--ccx")
    run.add_argument("--order", type=int, choices=[1, 2], default=1)
    run.add_argument("--load-axis", choices=["x", "y", "z"], default="x")
    run.add_argument("--load-kind", choices=["face", "point"], default="face")
    commands.add_parser("doctor", help="Show installed mesher and solver paths")
    validation = commands.add_parser("validate-cantilever", help="Run point-tip beam validation and a mesh study")
    validation.add_argument("--out", type=Path, required=True)
    hole = commands.add_parser("validate-hole", help="Validate thin-plate hole stress concentration against Kirsch")
    hole.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        if arguments.command == "validate-hole":
            from opensim.hole_validation import run_hole_validation
            report = run_hole_validation(arguments.out)
            print(json.dumps(report, indent=2))
            if report["result"] != "PASS":
                parser.exit(1, "Hole stress-concentration validation did not meet acceptance criteria\n")
        elif arguments.command == "validate-cantilever":
            from opensim.validation import run_cantilever_validation
            report = run_cantilever_validation(arguments.out)
            print(json.dumps(report, indent=2))
            if report["result"] != "PASS":
                parser.exit(1, "Cantilever validation did not meet its acceptance criteria\n")
        elif arguments.command == "example":
            make_box(arguments.path)
            print(arguments.path.resolve())
        elif arguments.command == "doctor":
            print(json.dumps({"gmsh": importlib.metadata.version("gmsh"), "ccx": str(find_solver())}, indent=2))
        else:
            summary = solve(arguments.cad, arguments.out, arguments.mesh_size, arguments.cad_scale,
                            arguments.young, arguments.poisson, arguments.load, arguments.ccx,
                            arguments.order, arguments.load_axis, arguments.load_kind)
            print(json.dumps(summary, indent=2))
    except (ValueError, FileNotFoundError, FileExistsError, RuntimeError) as error:
        parser.exit(1, f"open-sim: {error}\n")


if __name__ == "__main__":
    main()
