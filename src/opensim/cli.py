import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from opensim.geometry import MeshElementLimitExceeded, import_and_mesh, make_box
from opensim.results import write_viewer, write_vtk
from opensim.solver import find_solver, parse_dat, run_solver, write_deck
from opensim.regions import support_nodes
from opensim.stress import read_stress, von_mises
from opensim.load_settings import LOAD_AXES, NORMAL_AXES


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def solve(cad: Path, output: Path, size=0.05, scale=1.0, young=210e9,
          poisson=0.0, load=1000.0, ccx=None, order=1, load_axis="x", load_kind="face", load_surface="x-max",
          support_region=None, load_region=None, progress=None, solver_timeout=120, max_elements=None) -> dict:
    executable = find_solver(ccx)
    if not cad.is_file():
        raise FileNotFoundError(cad)
    output.mkdir(parents=True, exist_ok=False)
    if progress:
        progress("meshing")
    mesh = import_and_mesh(cad, size, scale, output / "mesh.msh", order=order, tip_point=load_kind == "point")
    if max_elements is not None and len(mesh.tetrahedra) > max_elements:
        raise MeshElementLimitExceeded(f"Actual mesh has {len(mesh.tetrahedra):,} elements, exceeding the {max_elements:,} element limit; solver was not started")
    if progress:
        progress("preparing")
    solver_length_scale = 1000.0 if support_region or load_region else 1.0
    loading = write_deck(mesh, output / "model.inp", young, poisson, load, load_axis, load_kind, load_surface,
                         support_region, load_region, solver_length_scale)
    if progress:
        progress("solving")
    run_solver(executable, output, timeout=solver_timeout)
    if progress:
        progress("reading")
    displacement, reactions = parse_dat(output / "model.dat", len(mesh.points))
    displacement /= solver_length_scale
    stress = read_stress(output / "model.frd", len(mesh.points)) * solver_length_scale ** 2
    equivalent = von_mises(stress)
    fixed = support_nodes(mesh, support_region)
    fixed_ids = {int(node) + 1 for node in fixed}
    if set(reactions) != fixed_ids:
        raise ValueError("Reaction results do not match the fixed node set")
    reported_reactions = {node: force.copy() for node, force in reactions.items()}
    reactions = {node: np.asarray(force) - loading.forces[node - 1] for node, force in reactions.items()}
    resultant = np.sum(list(reactions.values()), axis=0)
    applied = loading.forces.sum(axis=0)
    relative_imbalance = float(np.linalg.norm(resultant + applied) / abs(load))
    if relative_imbalance > 1e-4:
        raise ValueError("Reaction forces fail global equilibrium tolerance")
    reference = mesh.points[fixed].mean(axis=0)
    loaded = np.array([mesh.tip_node()]) if load_kind == "point" else mesh.end_nodes("max")
    reaction_moment = np.sum([np.cross(mesh.points[node - 1] - reference, force)
                              for node, force in reactions.items()], axis=0)
    applied_moment = np.cross(mesh.points - reference, loading.forces).sum(axis=0)
    moment_scale = abs(load) * np.ptp(mesh.points, axis=0).max()
    moment_imbalance = float(np.linalg.norm(reaction_moment + applied_moment) / moment_scale)
    if moment_imbalance > 1e-4:
        raise ValueError("Reaction forces fail global moment equilibrium tolerance")
    try:
        tip_mean = mesh.tip_average(displacement).tolist()
    except ValueError:
        if not support_region:
            raise
        tip_mean = None
    summary = {"nodes": len(mesh.points), "tetrahedra": len(mesh.tetrahedra), "element_type": mesh.element_type,
               "maximum_displacement_m": float(np.linalg.norm(displacement, axis=1).max()),
               "mean_loaded_ux_m": float(displacement[mesh.end_nodes("max"), 0].mean()),
               "tip_mean_displacement_m": tip_mean,
               "load_point_m": loading.centroid.tolist(),
               "load_point_displacement_m": displacement[loaded].mean(axis=0).tolist(),
               "reaction_moment_Nm": reaction_moment.tolist(), "applied_moment_Nm": applied_moment.tolist(),
               "relative_moment_imbalance": moment_imbalance, "load_axis": load_axis, "load_kind": load_kind,
               "reaction_N": resultant.tolist(), "relative_force_imbalance": relative_imbalance,
               "load_N": load, "young_Pa": young, "poisson": poisson,
               "boundary_condition": f"X minimum clamped; {load_axis.upper()} load at X maximum ({load_kind})"}
    if load_kind == "traction":
        summary.pop("load_point_displacement_m")
        summary["tip_node_mean_ux_m"] = summary.pop("mean_loaded_ux_m")
        markers = []
        for index in np.linspace(0, len(loading.faces) - 1, min(9, len(loading.faces)), dtype=int):
            face = loading.faces[index]
            vector = displacement[face].mean(axis=0) if len(face) == 3 else (-displacement[face[:3]].sum(axis=0) + 4 * displacement[face[3:]].sum(axis=0)) / 9
            markers.append({"point_m": mesh.points[face[:3]].mean(axis=0).tolist(), "displacement_m": vector.tolist(),
                            "direction": loading.face_directions[index].tolist()})
        summary.update({"load_surface": load_surface, "loaded_area_m2": loading.area,
                        "uniform_traction_Pa": load / loading.area, "load_markers": markers,
                        "applied_force_N": applied.tolist(),
                        "reported_support_forces_N": np.sum(list(reported_reactions.values()), axis=0).tolist(),
                        "applied_force_at_support_N": loading.forces[fixed].sum(axis=0).tolist(),
                        "boundary_condition": f"X minimum clamped; uniform {load_axis.upper()} traction on {load_surface}; total force {load} N"})
        patch_average, normal_average = np.zeros(3), 0.0
        for face, direction in zip(loading.faces, loading.face_directions):
            corners = mesh.points[face[:3]]
            area = np.linalg.norm(np.cross(corners[1] - corners[0], corners[2] - corners[0])) / 2
            face_mean = displacement[face[3:] if len(face) == 6 else face].mean(axis=0)
            patch_average += area * face_mean
            normal_average += area * np.dot(face_mean, direction)
        summary["loaded_surface_mean_displacement_m"] = (patch_average / loading.area).tolist()
        if load_axis in NORMAL_AXES:
            summary.update({"normal_pressure_Pa": load / loading.area * (1 if load_axis == "normal-in" else -1),
                            "traction_magnitude_Pa": abs(load) / loading.area,
                            "loaded_surface_mean_normal_displacement_m": normal_average / loading.area,
                            "load_force_meaning": "Integral of local traction magnitudes; net force can be smaller or zero on curved/multiple faces"})
    summary.update({"support_region": support_region or {}, "load_region": load_region or {},
                    "cad_faces": mesh.surface_catalog(),
                    "support_point_m": reference.tolist(), "support_node_count": len(fixed),
                    "maximum_von_mises_Pa": float(equivalent.max()), "stress_measure": "Recovered nodal stress; ideal support edges may be singular"})
    if support_region or load_region:
        summary["boundary_condition"] = "Selected surface region fully fixed; selected load region carries constant global vector traction. No contact/sliding model."
    if load_axis in NORMAL_AXES:
        summary["boundary_condition"] = "Fully fixed support; uniform-magnitude surface-normal traction on initial mesh geometry. No follower loading or contact."
    if progress:
        progress("exporting")
    manifest = {"schema_version": 1, "cad_path": str(cad.resolve()), "cad_sha256": digest(cad),
                "solver_length_unit_m": 1 / solver_length_scale, "solver_force_unit_N": 1,
                "solver_stress_unit_Pa": solver_length_scale ** 2,
                "ccx_path": str(executable), "ccx_sha256": digest(executable),
                "mesh_size_m": size, "cad_scale_to_m": scale, "element_order": order,
                "gmsh": importlib.metadata.version("gmsh"), "numpy": np.__version__,
                "deck_sha256": digest(output / "model.inp"), "summary": summary}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    write_vtk(output / "results.vtk", mesh, displacement, stress=equivalent)
    write_viewer(output / "results.html", mesh, displacement, summary, equivalent)
    np.savez_compressed(output / "fields.npz", points=mesh.points, tetrahedra=mesh.tetrahedra, displacement=displacement,
                        applied_forces_N=loading.forces, stress=stress, von_mises_Pa=equivalent, support_nodes=fixed)
    return summary


def main():
    parser = argparse.ArgumentParser(description="CAD to linear static structural simulation (SI units)")
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example", help="Generate an independently defined STEP bar")
    example.add_argument("path", type=Path)
    def add_static_arguments(command):
        command.add_argument("cad", type=Path)
        command.add_argument("--out", type=Path, required=True)
        command.add_argument("--mesh-size", type=float, default=0.05)
        command.add_argument("--cad-scale", type=float, default=1.0, help="Coordinate multiplier to meters; mm: 0.001")
        command.add_argument("--young", type=float, default=210e9)
        command.add_argument("--poisson", type=float, default=0.0)
        command.add_argument("--load", type=float, default=1000.0, help="Total axial force in newtons")
        command.add_argument("--ccx")
        command.add_argument("--order", type=int, choices=[1, 2], default=1)
        command.add_argument("--load-axis", choices=LOAD_AXES, default="x", help="X/Y/Z or normal-in/normal-out (requires --load-kind traction)")
        command.add_argument("--load-kind", choices=["face", "point", "traction"], default="face")
        from opensim.load_settings import LOAD_SURFACES
        command.add_argument("--load-surface", choices=LOAD_SURFACES, default="x-max", help="Bounding-plane patch for uniform traction; --load is total signed force in N")
        command.add_argument("--regions", type=Path, help="JSON file containing support_region and/or load_region")

    add_static_arguments(commands.add_parser("solve", help="Mesh and solve one closed STEP/IGES/BREP solid or STL/OBJ/3MF mesh"))
    study = commands.add_parser("convergence", help="Mesh convergence study: repeat the static solve on successively finer meshes")
    add_static_arguments(study)
    study.add_argument("--levels", type=int, default=4, help="Number of meshes, 3–6; starts at --mesh-size and divides it by --ratio each time")
    study.add_argument("--ratio", type=float, default=1.4, help="Mesh size divisor between meshes")
    study.add_argument("--tolerance", type=float, default=2.0, help="Stop when the target changes less than this percent")
    study.add_argument("--target", choices=["displacement", "response", "stress"], default="displacement")
    commands.add_parser("doctor", help="Show installed mesher and solver paths")
    validation = commands.add_parser("validate-cantilever", help="Run point-tip beam validation and a mesh study")
    validation.add_argument("--out", type=Path, required=True)
    hole = commands.add_parser("validate-hole", help="Validate thin-plate hole stress concentration against Kirsch")
    hole.add_argument("--out", type=Path, required=True)
    timoshenko = commands.add_parser("validate-timoshenko", help="Validate thin and shear-sensitive solid beams against Timoshenko theory")
    timoshenko.add_argument("--out", type=Path, required=True)
    modal = commands.add_parser("modal", help="Extract unprestressed natural frequencies and mode shapes, X-min fixed")
    modal.add_argument("cad", type=Path)
    modal.add_argument("--out", type=Path, required=True)
    modal.add_argument("--mesh-size", type=float, default=0.01)
    modal.add_argument("--cad-scale", type=float, default=1.0)
    modal.add_argument("--young", type=float, default=210e9)
    modal.add_argument("--poisson", type=float, default=0.3)
    modal.add_argument("--density", type=float, default=7850.0)
    modal.add_argument("--modes", type=int, default=6)
    modal.add_argument("--order", type=int, choices=[1, 2], default=2)
    modal.add_argument("--ccx")
    modal_validation = commands.add_parser("validate-modal", help="Validate beam eigenfrequencies, shapes and density scaling")
    modal_validation.add_argument("--out", type=Path, required=True)
    distributed = commands.add_parser("validate-distributed", help="Validate uniform surface traction with axial and uniformly loaded beam studies")
    distributed.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        if arguments.command == "validate-distributed":
            from opensim.distributed_validation import run_distributed_validation
            report = run_distributed_validation(arguments.out)
            print(json.dumps(report, indent=2))
            if report["result"] != "PASS":
                parser.exit(1, "Distributed-load validation did not meet acceptance criteria\n")
        elif arguments.command == "modal":
            from opensim.modal import solve_modal
            summary = solve_modal(arguments.cad, arguments.out, arguments.mesh_size, arguments.cad_scale,
                                  arguments.young, arguments.poisson, arguments.density, arguments.modes,
                                  arguments.ccx, arguments.order)
            print(json.dumps(summary, indent=2))
        elif arguments.command == "validate-modal":
            from opensim.modal_validation import run_modal_validation
            report = run_modal_validation(arguments.out)
            print(json.dumps(report, indent=2))
            if report["result"] != "PASS":
                parser.exit(1, "Modal validation did not meet acceptance criteria\n")
        elif arguments.command == "validate-timoshenko":
            from opensim.timoshenko_validation import run_timoshenko_validation
            report = run_timoshenko_validation(arguments.out)
            print(json.dumps(report, indent=2))
            if report["result"] != "PASS":
                parser.exit(1, "Timoshenko beam validation did not meet acceptance criteria\n")
        elif arguments.command == "validate-hole":
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
            region_options = json.loads(arguments.regions.read_text(encoding="utf-8")) if arguments.regions else {}
            if not isinstance(region_options, dict) or set(region_options) - {"support_region", "load_region"}:
                raise ValueError("Region JSON accepts only support_region and load_region")
            if arguments.command == "convergence":
                from opensim.convergence import run_convergence
                report = run_convergence(arguments.cad, arguments.out, arguments.mesh_size, arguments.cad_scale, arguments.young,
                                         arguments.poisson, arguments.load, arguments.order, arguments.load_axis, arguments.load_kind,
                                         arguments.load_surface, levels=arguments.levels, ratio=arguments.ratio,
                                         tolerance_percent=arguments.tolerance, target=arguments.target, ccx=arguments.ccx,
                                         progress=lambda stage: print(stage, flush=True), **region_options)
                print(json.dumps({key: report[key] for key in ("verdict", "stop_reason", "quantities")}, indent=2))
                print(f"Report: {arguments.out / 'report.html'}")
                return
            summary = solve(arguments.cad, arguments.out, arguments.mesh_size, arguments.cad_scale,
                            arguments.young, arguments.poisson, arguments.load, arguments.ccx,
                            arguments.order, arguments.load_axis, arguments.load_kind, arguments.load_surface, **region_options)
            print(json.dumps(summary, indent=2))
    except (ValueError, FileNotFoundError, FileExistsError, RuntimeError) as error:
        parser.exit(1, f"open-sim: {error}\n")


if __name__ == "__main__":
    main()
