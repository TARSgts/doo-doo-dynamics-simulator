import csv
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path

import gmsh
import numpy as np

from opensim.cli import digest
from opensim.geometry import gmsh_session
from opensim.solver import find_solver, parse_dat, run_solver


@dataclass
class PlateMesh:
    points: np.ndarray
    quadrilaterals: np.ndarray

    def boundary_edges(self):
        edges = {}
        for element in self.quadrilaterals:
            for first, second, middle in ((0, 1, 4), (1, 2, 5), (2, 3, 6), (3, 0, 7)):
                key = tuple(sorted((int(element[first]), int(element[second]))))
                count, _ = edges.get(key, (0, None))
                edges[key] = count + 1, [int(element[first]), int(element[second]), int(element[middle])]
        return [edge for count, edge in edges.values() if count == 1]


def kirsch_hoop(angle_radians, remote_stress=1.0):
    return remote_stress * (1 - 2 * np.cos(2 * np.asarray(angle_radians)))


def mesh_quarter_plate(path: Path, radius=0.005, half_width=0.1, radial=24, angular=16) -> PlateMesh:
    if not np.isfinite(radius) or not np.isfinite(half_width) or not 0 < radius < half_width or radial < 2 or angular < 2:
        raise ValueError("Use a positive hole radius below the plate half-width and at least two mesh divisions")
    with gmsh_session():
        gmsh.model.add("quarter_plate_with_hole")
        center = gmsh.model.geo.addPoint(0, 0, 0)
        inner_first = gmsh.model.geo.addPoint(radius, 0, 0)
        inner_middle = gmsh.model.geo.addPoint(radius / np.sqrt(2), radius / np.sqrt(2), 0)
        inner_last = gmsh.model.geo.addPoint(0, radius, 0)
        outer_first = gmsh.model.geo.addPoint(half_width, 0, 0)
        outer_middle = gmsh.model.geo.addPoint(half_width, half_width, 0)
        outer_last = gmsh.model.geo.addPoint(0, half_width, 0)
        arcs = [gmsh.model.geo.addCircleArc(inner_first, center, inner_middle),
                gmsh.model.geo.addCircleArc(inner_middle, center, inner_last)]
        spokes = [gmsh.model.geo.addLine(inner_first, outer_first),
                  gmsh.model.geo.addLine(inner_middle, outer_middle),
                  gmsh.model.geo.addLine(inner_last, outer_last)]
        outer = [gmsh.model.geo.addLine(outer_first, outer_middle), gmsh.model.geo.addLine(outer_middle, outer_last)]
        loops = [gmsh.model.geo.addCurveLoop([spokes[0], outer[0], -spokes[1], -arcs[0]]),
                 gmsh.model.geo.addCurveLoop([spokes[1], outer[1], -spokes[2], -arcs[1]])]
        surfaces = [gmsh.model.geo.addPlaneSurface([loop]) for loop in loops]
        gmsh.model.geo.synchronize()
        for curve in spokes:
            gmsh.model.mesh.setTransfiniteCurve(curve, radial + 1, "Progression", (half_width / radius) ** (1 / radial))
        for curve in arcs + outer:
            gmsh.model.mesh.setTransfiniteCurve(curve, angular + 1)
        for surface in surfaces:
            gmsh.model.mesh.setTransfiniteSurface(surface)
            gmsh.model.mesh.setRecombine(2, surface)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)
        gmsh.option.setNumber("Mesh.SecondOrderLinear", 0)
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.model.mesh.generate(2)
        types, _, connectivity = gmsh.model.mesh.getElements(2)
        if list(types) != [16]:
            raise ValueError("Expected an eight-node quadrilateral mesh")
        tags, positions, _ = gmsh.model.mesh.getNodes()
        coordinates = {int(tag): point for tag, point in zip(tags, np.asarray(positions).reshape(-1, 3))}
        used = np.unique(connectivity[0])
        indices = {int(tag): index for index, tag in enumerate(used)}
        points = np.array([coordinates[int(tag)] for tag in used])
        quadrilaterals = np.array([[indices[int(tag)] for tag in element] for element in connectivity[0].reshape(-1, 8)])
        corner_points = points[quadrilaterals[:, :4], :2]
        signed_area = np.sum(corner_points[:, :, 0] * np.roll(corner_points[:, :, 1], -1, axis=1)
                             - corner_points[:, :, 1] * np.roll(corner_points[:, :, 0], -1, axis=1), axis=1) / 2
        if np.any(signed_area <= 0):
            raise ValueError("Quarter-plate mesh contains reversed or degenerate elements")
        gmsh.write(str(path.resolve()))
        return PlateMesh(points, quadrilaterals)


def consistent_edge_loads(mesh: PlateMesh, half_width: float, thickness: float, remote_stress: float):
    if any(not np.isfinite(value) or value <= 0 for value in (half_width, thickness, remote_stress)):
        raise ValueError("Plate size, thickness and tensile stress must be positive and finite")
    forces = np.zeros((len(mesh.points), 3))
    for edge in mesh.boundary_edges():
        if not np.allclose(mesh.points[edge, 0], half_width, rtol=0, atol=1e-9):
            continue
        length = np.linalg.norm(mesh.points[edge[1]] - mesh.points[edge[0]])
        forces[edge, 0] += remote_stress * thickness * length * np.array([1 / 6, 1 / 6, 2 / 3])
    if not np.isclose(forces[:, 0].sum(), remote_stress * thickness * half_width, rtol=1e-10):
        raise ValueError("Consistent edge loads do not recover the intended far-field traction")
    return forces


def write_plate_deck(path: Path, mesh: PlateMesh, half_width=0.1, thickness=0.0001, remote_stress=1e6):
    forces = consistent_edge_loads(mesh, half_width, thickness, remote_stress)
    symmetry_x = np.flatnonzero(np.abs(mesh.points[:, 0]) < 1e-9)
    symmetry_y = np.flatnonzero(np.abs(mesh.points[:, 1]) < 1e-9)
    supports = np.union1d(symmetry_x, symmetry_y)
    lines = ["*HEADING", "Quarter-plate Kirsch benchmark, plane stress, consistent edge traction", "*NODE, NSET=NALL"]
    lines += [f"{index + 1}, " + ", ".join(f"{value:.15g}" for value in point) for index, point in enumerate(mesh.points)]
    lines.append("*ELEMENT, TYPE=CPS8R, ELSET=PLATE")
    lines += [f"{index + 1}, " + ", ".join(str(int(node) + 1) for node in element)
              for index, element in enumerate(mesh.quadrilaterals)]
    for name, nodes in (("XSYM", symmetry_x), ("YSYM", symmetry_y), ("SUPPORTS", supports)):
        lines.append(f"*NSET, NSET={name}")
        lines += [str(int(node) + 1) for node in nodes]
    lines += ["*MATERIAL, NAME=STEEL", "*ELASTIC", "210000000000, 0.3",
              "*SOLID SECTION, ELSET=PLATE, MATERIAL=STEEL", f"{thickness:.15g}",
              "*BOUNDARY", "XSYM, 1, 1", "YSYM, 2, 2", "*STEP", "*STATIC, SOLVER=SPOOLES", "*CLOAD"]
    lines += [f"{index + 1}, 1, {force:.15g}" for index, force in enumerate(forces[:, 0]) if force != 0]
    lines += ["*NODE PRINT, NSET=NALL", "U", "*NODE PRINT, NSET=SUPPORTS", "RF",
              "*NODE FILE, OUTPUT=2D", "U", "*EL FILE, OUTPUT=2D", "S", "*END STEP"]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return forces


def read_frd_stress(path: Path, node_count: int) -> np.ndarray:
    active = False
    completed = False
    components, values = [], {}
    for line in path.read_text(encoding="ascii", errors="strict").splitlines():
        if line.startswith(" -4"):
            active = line.split()[1] == "STRESS"
            continue
        if not active:
            continue
        if line.startswith(" -5"):
            components.append(line.split()[1])
        elif line.startswith(" -1"):
            node = int(line[3:13])
            if node in values:
                raise ValueError("Duplicate nodal stress result")
            values[node] = [float(line[start:start + 12].replace("D", "E")) for start in range(13, len(line.rstrip()), 12)]
        elif line.startswith(" -3"):
            completed = True
            break
    expected = ["SXX", "SYY", "SZZ", "SXY", "SYZ", "SZX"]
    if not completed or components[:6] != expected or set(values) != set(range(1, node_count + 1)):
        raise ValueError("Incomplete or unsupported FRD stress block")
    stress = np.array([values[node][:6] for node in range(1, node_count + 1)])
    if stress.shape != (node_count, 6) or not np.isfinite(stress).all():
        raise ValueError("Invalid FRD nodal stress values")
    return stress


def polar_boundary_stress(angle: np.ndarray, stress: np.ndarray):
    sine, cosine = np.sin(angle), np.cos(angle)
    hoop = stress[:, 0] * sine ** 2 + stress[:, 1] * cosine ** 2 - 2 * stress[:, 3] * sine * cosine
    radial = stress[:, 0] * cosine ** 2 + stress[:, 1] * sine ** 2 + 2 * stress[:, 3] * sine * cosine
    return hoop, radial


def solve_hole_case(directory: Path, radial=24, angular=16, half_width=0.1):
    directory.mkdir(parents=True, exist_ok=False)
    radius, thickness, remote_stress = 0.005, 0.0001, 1e6
    mesh = mesh_quarter_plate(directory / "mesh.msh", radius, half_width, radial, angular)
    applied = write_plate_deck(directory / "model.inp", mesh, half_width, thickness, remote_stress)
    executable = find_solver()
    run_solver(executable, directory)
    displacement, reactions = parse_dat(directory / "model.dat", len(mesh.points))
    stress = read_frd_stress(directory / "model.frd", len(mesh.points))
    hole_nodes = np.flatnonzero(np.abs(np.linalg.norm(mesh.points[:, :2], axis=1) - radius) < radius * 1e-7)
    angle = np.arctan2(mesh.points[hole_nodes, 1], mesh.points[hole_nodes, 0])
    ordered = np.argsort(angle)
    hole_nodes, angle = hole_nodes[ordered], angle[ordered]
    hoop, radial_stress = polar_boundary_stress(angle, stress[hole_nodes])
    constrained_reactions = np.zeros((len(mesh.points), 3))
    for node, force in reactions.items():
        if abs(mesh.points[node - 1, 0]) < 1e-9:
            constrained_reactions[node - 1, 0] = force[0]
        if abs(mesh.points[node - 1, 1]) < 1e-9:
            constrained_reactions[node - 1, 1] = force[1]
    resultant = constrained_reactions.sum(axis=0)
    imbalance = float(np.linalg.norm(resultant + applied.sum(axis=0)) / np.linalg.norm(applied.sum(axis=0)))
    if imbalance > 1e-4:
        raise ValueError("Quarter-plate reactions fail force equilibrium")
    reaction_moment = np.cross(mesh.points, constrained_reactions).sum(axis=0)
    applied_moment = np.cross(mesh.points, applied).sum(axis=0)
    moment_imbalance = float(np.linalg.norm(reaction_moment + applied_moment) / (np.linalg.norm(applied.sum(axis=0)) * half_width))
    if moment_imbalance > 1e-4:
        raise ValueError("Quarter-plate reactions fail moment equilibrium")
    peak = int(hoop.argmax())
    result = {"element_type": "CPS8R", "nodes": len(mesh.points), "elements": len(mesh.quadrilaterals),
              "radial_divisions": radial, "angular_divisions_per_patch": angular,
              "half_width_m": half_width, "hole_radius_m": radius, "thickness_m": thickness,
              "remote_stress_Pa": remote_stress, "peak_hoop_stress_Pa": float(hoop[peak]),
              "Kt_gross": float(hoop[peak] / remote_stress),
              "Kt_net": float(hoop[peak] / remote_stress * (1 - radius / half_width)),
              "peak_angle_deg": float(np.degrees(angle[peak])),
              "curve_normalized_max_error": float(np.max(np.abs(hoop / remote_stress - kirsch_hoop(angle))) / 3),
              "hole_radial_residual_over_remote": float(np.abs(radial_stress).max() / remote_stress),
              "relative_force_imbalance": imbalance, "reaction_N": resultant.tolist(),
              "relative_moment_imbalance": moment_imbalance,
              "applied_force_N": applied.sum(axis=0).tolist(), "solver_sha256": digest(executable),
              "deck_sha256": digest(directory / "model.inp")}
    (directory / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    np.savez_compressed(directory / "fields.npz", points=mesh.points, quadrilaterals=mesh.quadrilaterals,
                        displacement=displacement, stress=stress, hole_nodes=hole_nodes, angle=angle, hoop=hoop)
    with (directory / "hole-stress.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["angle_deg", "hoop_stress_Pa", "Kirsch_hoop_Pa", "radial_stress_Pa"])
        writer.writerows(zip(np.degrees(angle), hoop, kirsch_hoop(angle, remote_stress), radial_stress))
    return result


def run_hole_validation(output: Path):
    if importlib.util.find_spec("matplotlib") is None:
        raise RuntimeError("Install plotting dependencies first: pip install '.[validation]'")
    output.mkdir(parents=True, exist_ok=False)
    cases = []
    for name, radial, angular, half_width in (("coarse", 24, 16, 0.2), ("medium", 48, 32, 0.2),
                                             ("fine", 96, 64, 0.2), ("larger-domain", 115, 64, 0.4)):
        result = solve_hole_case(output / name, radial, angular, half_width)
        cases.append({"case": name, **result})
    medium, fine, larger = cases[1:]
    mesh_change = abs(fine["Kt_gross"] - medium["Kt_gross"]) / fine["Kt_gross"]
    domain_change = abs(fine["Kt_gross"] - larger["Kt_gross"]) / larger["Kt_gross"]
    criteria = {
        "fine_peak_error_below_1_percent": abs(fine["Kt_gross"] / 3 - 1) < 0.01,
        "larger_domain_peak_error_below_1_percent": abs(larger["Kt_gross"] / 3 - 1) < 0.01,
        "last_mesh_change_below_0_5_percent": mesh_change < 0.005,
        "domain_change_below_0_5_percent": domain_change < 0.005,
        "hoop_curve_error_below_1_percent_of_peak": fine["curve_normalized_max_error"] < 0.01,
        "recovered_radial_stress_below_1_percent_of_remote": fine["hole_radial_residual_over_remote"] < 0.01,
        "peak_at_90_degrees": abs(fine["peak_angle_deg"] - 90) < 0.5,
        "force_balance_below_1e_5": all(case["relative_force_imbalance"] < 1e-5 for case in cases),
        "moment_balance_below_1e_5": all(case["relative_moment_imbalance"] < 1e-5 for case in cases),
    }
    report = {"result": "PASS" if all(criteria.values()) else "FAIL", "criteria": criteria,
              "reference": "Kirsch: sigma_hoop(a,theta)=sigma_infinity*(1-2*cos(2*theta)); Kt_gross=3",
              "theoretical_Kt_gross": 3.0, "remote_stress_Pa": 1e6,
              "full_plate_size_m": [0.4, 0.4, 0.0001], "hole_diameter_m": 0.01,
              "material": {"young_Pa": 210e9, "poisson": 0.3}, "formulation": "Quarter-symmetry, plane-stress CPS8R",
              "stress_measure": "Recovered/averaged nodal hoop stress on the circular boundary, not von Mises or raw Gauss-point maximum",
              "normalization": "Gross remote tensile stress; net-section normalization is reported separately",
              "last_mesh_change_fraction": mesh_change, "domain_change_fraction": domain_change,
              "fine_reference_error_fraction": abs(fine["Kt_gross"] / 3 - 1), "cases": cases,
              "limitations": "Kirsch is an infinite-plate reference. Finite domain and recovered stress discretization errors remain; this is an elastic plane-stress benchmark."}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (output / "convergence.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case", "half_width_m", "elements", "nodes", "peak_hoop_Pa", "Kt_gross", "Kt_net", "error_vs_3_percent"])
        for case in cases:
            writer.writerow([case["case"], case["half_width_m"], case["elements"], case["nodes"],
                             case["peak_hoop_stress_Pa"], case["Kt_gross"], case["Kt_net"], abs(case["Kt_gross"] / 3 - 1) * 100])
    plot_hole_validation(output, report)
    lines = ["# Circular-hole stress-concentration validation", "", f"**{report['result']}** — Kirsch stress concentration comparison.", "",
             "Main plate: 400 × 400 × 0.1 mm with a centered 10 mm through-hole. E=210 GPa, ν=0.3. Remote tensile stress is 1 MPa in X, applied as consistent quadratic-edge traction loads. The full-plate tensile force is 40 N; the quarter-model loaded edge carries 20 N.", "",
             "A quarter model uses Ux=0 on X=0 and Uy=0 on Y=0, with free hole and outer top boundaries. These are symmetry constraints, not a clamped end. Only constrained reaction components are included in force/moment balance.", "",
             "Kirsch predicts σθθ(a,θ)=σ∞[1−2cos(2θ)], with a maximum 3σ∞ at θ=90° and 270°. Thus Kt=σθθ,max/σ∞=3, normalized by gross remote stress. The minimum hoop stress is −σ∞ at θ=0°/180°.", "",
             "| Mesh/domain | Elements | Peak hoop (MPa) | Kt gross | Error vs 3 |", "|---|---:|---:|---:|---:|"]
    lines.extend(f"| {case['case']} | {case['elements']:,} | {case['peak_hoop_stress_Pa'] / 1e6:.6f} | "
                 f"{case['Kt_gross']:.6f} | {abs(case['Kt_gross'] / 3 - 1) * 100:.4f}% |" for case in cases)
    lines += ["", f"Final mesh change: **{mesh_change * 100:.4f}%**. Doubling plate width and length to 800 mm changes Kt by **{domain_change * 100:.4f}%**. The larger-domain radial count is increased to preserve approximately the same first-cell size at the hole.", "",
              f"Main fine peak: **{fine['peak_hoop_stress_Pa'] / 1e6:.6f} MPa**, at **{fine['peak_angle_deg']:.1f}°**. Kt based on net-section nominal stress is {fine['Kt_net']:.6f}; it must not be compared directly with the gross-stress value 3. Net nominal stress is σ∞/(1−d/W).", "",
              "Eight-node quadratic CPS8R elements use curved circle midside nodes and geometric radial grading. Stress is read from CalculiX FRD OUTPUT=2D, preserving the global stress tensor component order. Boundary hoop stress is recovered from Sxx, Syy and Sxy. Nodal recovery/averaging is explicitly part of the measurement; integration-point stresses are not mislabeled as the hole-boundary peak.", "",
              "The hole is smooth and traction-free; unlike a point load, it has a finite elastic stress concentration. Finite-width effects and stress recovery error are distinguished by mesh and domain studies. Acceptance uses <1% reference/curve error, <0.5% mesh/domain change, <1% recovered radial traction relative to σ∞, and <1e−5 force/moment residuals. The angular curve error is normalized by 3σ∞, avoiding division by the zero crossing of hoop stress.", "",
              "![Stress contours and verification](validation.png)", "",
              "Reproduce: `open-sim validate-hole --out <new-output-folder>`. Raw decks, meshes, logs, DAT/FRD, nodal tensors and boundary CSV samples are retained per case. This dedicated plane-stress benchmark does not replace the general 3D-solid analysis path.", "",
              "References: [MIT OpenCourseWare, linear elastic stress concentration, pp. 4–8](https://ocw.mit.edu/courses/2-002-mechanics-and-materials-ii-spring-2004/09e8137971e754b1b7290a33a100bb05_lab_4_s04.pdf), "
              "[CalculiX CPS8R and OUTPUT=2D documentation](https://www.dhondt.de/ccx_2.23.pdf)."]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def plot_hole_validation(output: Path, report: dict):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.tri import Triangulation

    fields = np.load(output / "fine" / "fields.npz")
    points, quads, stress = fields["points"], fields["quadrilaterals"], fields["stress"]
    radius = 0.005
    triangles = np.concatenate([quads[:, indices] for indices in ((0, 4, 7), (4, 1, 5), (5, 2, 6),
                                                                  (6, 3, 7), (4, 5, 6), (4, 6, 7))])
    triangles = triangles[np.max(np.abs(points[triangles, :2]), axis=(1, 2)) < radius * 3.5]
    figure, axes = plt.subplots(1, 3, figsize=(16, 4.6), layout="constrained")
    for sign_x, sign_y in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        connectivity = triangles[:, [0, 2, 1]] if sign_x * sign_y < 0 else triangles
        triangulation = Triangulation(points[:, 0] * sign_x / radius, points[:, 1] * sign_y / radius, connectivity)
        contour = axes[0].tricontourf(triangulation, stress[:, 0] / 1e6, levels=np.linspace(-0.05, 3.05, 25), cmap="turbo", extend="both")
    axes[0].set(xlim=(-3, 3), ylim=(-3, 3), xlabel="X / hole radius", ylabel="Y / hole radius", title="Axial stress Sxx near the hole (MPa)", aspect="equal")
    figure.colorbar(contour, ax=axes[0], shrink=0.8)
    angles = np.linspace(0, np.pi / 2, 200)
    axes[1].plot(np.degrees(angles), kirsch_hoop(angles), color="#111827", linewidth=2, label="Kirsch")
    for case in report["cases"][:3]:
        data = np.load(output / case["case"] / "fields.npz")
        axes[1].plot(np.degrees(data["angle"]), data["hoop"] / 1e6, "--", label=case["case"])
    axes[1].set(xlabel="Angle from loading axis (degrees)", ylabel="Hoop stress / remote stress", title="Hole-boundary stress")
    axes[1].legend()
    cases = report["cases"][:3]
    axes[2].plot([case["elements"] for case in cases], [case["Kt_gross"] for case in cases], "o-", label="400 mm plate")
    axes[2].axhline(3, color="#111827", linestyle="--", label="Kirsch = 3")
    larger = report["cases"][-1]
    axes[2].plot(larger["elements"], larger["Kt_gross"], "s", color="#16a34a", label="800 mm plate")
    axes[2].set(xlabel="Quarter-model quadratic elements", ylabel="Gross stress concentration Kt", title="Mesh and domain checks", xscale="log")
    axes[2].legend()
    for axis in axes[1:]:
        axis.grid(alpha=0.2)
    figure.suptitle("Doo Doo Dynamics Simulator · thin plate with a circular hole · remote tension 1 MPa")
    figure.savefig(output / "validation.png", dpi=160)
    plt.close(figure)
