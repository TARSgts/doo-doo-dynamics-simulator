import csv
import importlib.util
import json
from pathlib import Path

import numpy as np

from opensim.cli import solve
from opensim.geometry import make_box


BEAM_PARAMETERS = {"mesh_size_m": 0.0067, "cad_scale": 1.0, "young_Pa": 210e9,
                   "poisson": 0.3, "load_N": -10.0, "element_order": 2,
                   "load_axis": "z", "load_kind": "point"}


def euler_bernoulli(coordinate, length=1.0, width=0.02, height=0.02, young=210e9, force=-10.0):
    inertia = width * height ** 3 / 12
    position = np.asarray(coordinate)
    return force * position ** 2 * (3 * length - position) / (6 * young * inertia)


def run_cantilever_validation(output: Path) -> dict:
    if importlib.util.find_spec("matplotlib") is None:
        raise RuntimeError("Install plotting dependencies first: pip install '.[validation]'")
    output.mkdir(parents=True, exist_ok=False)
    cad = output / "cantilever.step"
    make_box(cad, (1.0, 0.02, 0.02))
    expected = float(euler_bernoulli(1.0))
    cases = []
    curves = {}
    for label, size, order in (("linear-baseline", 0.01, 1), ("quadratic-coarse", 0.02, 2),
                                ("quadratic-medium", 0.01, 2), ("quadratic-fine", 0.0067, 2)):
        summary = solve(cad, output / label, size=size, young=210e9, poisson=0.3,
                        load=-10, order=order, load_axis="z", load_kind="point")
        fields = np.load(output / label / "fields.npz")
        points, displacement = fields["points"], fields["displacement"]
        edge = np.flatnonzero((np.abs(points[:, 1]) < 1e-8) & (np.abs(points[:, 2]) < 1e-8))
        edge = edge[np.argsort(points[edge, 0])]
        curve_error = float(np.max(np.abs(displacement[edge, 2] - euler_bernoulli(points[edge, 0]))) / abs(expected))
        tip = summary["tip_mean_displacement_m"][2]
        cases.append({"case": label, "mesh_size_m": size, "element_type": summary["element_type"],
                      "nodes": summary["nodes"], "tetrahedra": summary["tetrahedra"],
                      "tip_mean_z_m": tip, "point_z_m": summary["load_point_displacement_m"][2],
                      "tip_error_fraction": abs(tip / expected - 1), "curve_error_fraction": curve_error,
                      "reaction_z_N": summary["reaction_N"][2], "reaction_moment_y_Nm": summary["reaction_moment_Nm"][1],
                      "force_imbalance": summary["relative_force_imbalance"],
                      "moment_imbalance": summary["relative_moment_imbalance"]})
        curves[label] = {"x_m": points[edge, 0].tolist(), "uz_m": displacement[edge, 2].tolist()}
        with (output / label / "edge-curve.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["x_m", "fem_uz_m", "euler_bernoulli_uz_m"])
            writer.writerows(zip(points[edge, 0], displacement[edge, 2], euler_bernoulli(points[edge, 0])))
    fine, medium = cases[-1], cases[-2]
    change = abs(fine["tip_mean_z_m"] - medium["tip_mean_z_m"]) / abs(fine["tip_mean_z_m"])
    criteria = {"tip_error_below_2_percent": fine["tip_error_fraction"] < 0.02,
                "curve_error_below_2_percent": fine["curve_error_fraction"] < 0.02,
                "last_mesh_change_below_0_5_percent": change < 0.005,
                "force_balance_below_0_001_percent": fine["force_imbalance"] < 1e-5,
                "moment_balance_below_0_001_percent": fine["moment_imbalance"] < 1e-5}
    report = {"result": "PASS" if all(criteria.values()) else "FAIL", "criteria": criteria,
              "geometry_m": {"length": 1.0, "width": 0.02, "height": 0.02},
              "young_Pa": 210e9, "poisson": 0.3, "force_z_N": -10,
              "inertia_y_m4": 0.02 * 0.02 ** 3 / 12,
              "euler_bernoulli_tip_z_m": expected, "expected_reaction_z_N": 10,
              "expected_root_moment_y_Nm": -10,
              "last_mesh_change_fraction": change, "cases": cases,
              "reference_formula": "w(x) = F*x^2*(3*L-x)/(6*E*I), I=b*h^3/12",
              "measurement": "Area-averaged tip section displacement; exact quadratic surface integration on flat faces",
              "limitations": "3D clamped solid versus ideal beam; local point-load stress/displacement singularity is not a convergence target."}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (output / "convergence.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(cases)
    lines = ["# Long cantilever validation", "", f"**{report['result']}** — Euler–Bernoulli displacement comparison.", "",
             "1,000 × 20 × 20 mm beam; E=210 GPa, ν=0.3; full clamp at X=0; a single −10 N Z force at (1, 0.01, 0.01) m.", "",
             f"I = {report['inertia_y_m4']:.10g} m⁴. Analytical tip w = −1.190476190 mm; reaction Z=10 N; root moment Y=−10 N·m.", "",
             "| Element / mesh | Elements | Tip mean Z (mm) | Error vs EB |", "|---|---:|---:|---:|"]
    lines.extend(f"| {case['case']} ({case['mesh_size_m'] * 1000:g} mm) | {case['tetrahedra']:,} | "
                 f"{case['tip_mean_z_m'] * 1000:.6f} | {case['tip_error_fraction'] * 100:.4f}% |" for case in cases)
    lines += ["", f"Last quadratic mesh change: **{change * 100:.4f}%**. Fine-mesh force imbalance: "
              f"{fine['force_imbalance']:.3e}; moment imbalance: {fine['moment_imbalance']:.3e}.", "",
              "Acceptance was specified as <2% tip and normalized curve error, <0.5% last-mesh change and <1e−5 equilibrium residuals.", "",
              "The linear-tetrahedron baseline is retained to expose its bending stiffness error. It is not included in the quadratic acceptance result.", "",
              "A mathematical 3D point load has a local singularity. The area-averaged tip section and a longitudinal edge curve away from the load point are the comparison quantities; no point-stress convergence claim is made. The plotted edge is at Y=Z=0. The solid root is fully clamped and includes Poisson constraint; Euler–Bernoulli theory omits 3D end effects and transverse shear. Estimated shear deflection is 0.000371 mm, or 0.0312% of the EB bending deflection.", "",
              "![Deflection and mesh refinement](validation.png)", "",
              "References: [CalculiX element guidance](https://www.dhondt.de/ccx_2.23.pdf), "
              "[Gmsh node ordering](https://gmsh.info/doc/texinfo/#Node-ordering), "
              "[University of Alberta beam theory](https://engcourses-uofa.ca/books/introduction-to-solid-mechanics/plane-beam-approximations/euler-bernoulli-beam/)."]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    plot_validation(output, report, curves)
    return report


def plot_validation(output: Path, report: dict, curves: dict):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(12, 4.6), layout="constrained")
    position = np.linspace(0, 1, 201)
    axes[0].plot(position, euler_bernoulli(position) * 1000, color="#111827", linewidth=2.5, label="Euler–Bernoulli")
    for label in ("linear-baseline", "quadratic-fine"):
        curve = curves[label]
        axes[0].plot(curve["x_m"], np.asarray(curve["uz_m"]) * 1000, "--", label=label)
    axes[0].set(xlabel="Distance from clamp (m)", ylabel="Z displacement (mm)", title="Deflected shape / lower edge")
    axes[0].legend()
    refined = report["cases"][1:]
    axes[1].plot([case["tetrahedra"] for case in refined], [case["tip_error_fraction"] * 100 for case in refined], "o-", color="#2563eb")
    axes[1].set(xlabel="Quadratic tetrahedra", ylabel="Tip-section error versus EB (%)", title="Quadratic mesh refinement", xscale="log")
    for axis in axes:
        axis.grid(alpha=0.2)
    figure.suptitle("Doo Doo Dynamics Simulator · 1 m cantilever · −10 N tip force")
    figure.savefig(output / "validation.png", dpi=160)
    plt.close(figure)
