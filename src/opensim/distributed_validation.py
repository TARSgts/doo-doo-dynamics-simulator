import csv
import importlib.util
import json
from pathlib import Path

import numpy as np

from opensim.cli import solve
from opensim.geometry import make_box


def uniform_beam_deflection(coordinate, length=1.0, width=0.02, height=0.02, young=210e9, load_per_length=-10.0):
    if any(not np.isfinite(value) or value <= 0 for value in (length, width, height, young)):
        raise ValueError("Beam dimensions and modulus must be positive and finite")
    position = np.asarray(coordinate)
    inertia = width * height ** 3 / 12
    return load_per_length * position ** 2 * (6 * length ** 2 - 4 * length * position + position ** 2) / (24 * young * inertia)


def run_distributed_validation(output: Path):
    if importlib.util.find_spec("matplotlib") is None:
        raise RuntimeError("Install plotting dependencies first: pip install '.[validation]'")
    output.mkdir(parents=True, exist_ok=False)
    beam, bar = output / "beam.step", output / "bar.step"
    make_box(beam, (1, 0.02, 0.02))
    make_box(bar, (1, 0.1, 0.1))
    expected = float(uniform_beam_deflection(1))
    cases = []
    for label, size in (("coarse", 0.02), ("medium", 0.01), ("fine", 0.0067)):
        summary = solve(beam, output / label, size=size, young=210e9, poisson=0.3, load=-10,
                        order=2, load_axis="z", load_kind="traction", load_surface="z-max")
        tip = summary["tip_mean_displacement_m"][2]
        cases.append({"case": label, "mesh_size_m": size, "elements": summary["tetrahedra"], "nodes": summary["nodes"],
                      "tip_z_m": tip, "error_fraction": abs(tip / expected - 1),
                      "reaction_z_N": summary["reaction_N"][2], "reaction_moment_y_Nm": summary["reaction_moment_Nm"][1],
                      "force_imbalance": summary["relative_force_imbalance"], "moment_imbalance": summary["relative_moment_imbalance"],
                      "loaded_area_m2": summary["loaded_area_m2"], "traction_Pa": summary["uniform_traction_Pa"],
                      "applied_at_support_z_N": summary["applied_force_at_support_N"][2],
                      "reported_support_force_z_N": summary["reported_support_forces_N"][2]})
    axial = []
    for label, size in (("axial-coarse", 0.05), ("axial-fine", 0.035)):
        summary = solve(bar, output / label, size=size, young=210e9, poisson=0, load=1000,
                        order=2, load_axis="x", load_kind="traction", load_surface="x-max")
        axial_expected = 1000 / (210e9 * 0.1 ** 2)
        axial.append({"case": label, "tip_x_m": summary["tip_mean_displacement_m"][0], "expected_x_m": axial_expected,
                      "error_fraction": abs(summary["tip_mean_displacement_m"][0] / axial_expected - 1),
                      "force_imbalance": summary["relative_force_imbalance"], "moment_imbalance": summary["relative_moment_imbalance"]})
    fine, medium = cases[-1], cases[-2]
    change = abs(fine["tip_z_m"] - medium["tip_z_m"]) / abs(fine["tip_z_m"])
    fields = np.load(output / "fine" / "fields.npz")
    points, displacement = fields["points"], fields["displacement"]
    edge = np.flatnonzero((np.abs(points[:, 1]) < 1e-8) & (np.abs(points[:, 2]) < 1e-8))
    edge = edge[np.argsort(points[edge, 0])]
    analytical = uniform_beam_deflection(points[edge, 0])
    curve_error = float(np.max(np.abs(displacement[edge, 2] - analytical)) / abs(expected))
    criteria = {"beam_tip_error_below_2_percent": fine["error_fraction"] < 0.02,
                "beam_edge_curve_error_below_2_percent": curve_error < 0.02,
                "last_mesh_change_below_0_5_percent": change < 0.005,
                "axial_errors_below_0_001_percent": all(case["error_fraction"] < 1e-5 for case in axial),
                "all_force_balances_below_1e_5": all(case["force_imbalance"] < 1e-5 for case in cases + axial),
                "all_moment_balances_below_1e_5": all(case["moment_imbalance"] < 1e-5 for case in cases + axial)}
    report = {"result": "PASS" if all(criteria.values()) else "FAIL", "criteria": criteria,
              "beam_geometry_m": [1, 0.02, 0.02], "young_Pa": 210e9, "poisson": 0.3,
              "total_force_z_N": -10, "uniform_line_load_N_per_m": -10, "surface": "z-max",
              "expected_tip_z_m": expected, "expected_reaction_z_N": 10, "expected_root_moment_y_Nm": -5,
              "last_mesh_change_fraction": change, "edge_curve_error_fraction": curve_error,
              "beam_cases": cases, "axial_cases": axial,
              "load_integration": "Uniform vector traction F/A: P1 triangle nodal forces A*t/3; P2 straight triangle corner forces zero, midside forces A*t/3. Shared-node contributions are accumulated.",
              "reaction_recovery": "CalculiX RF at a support includes CLOAD there; true reaction is RF minus applied nodal force. Moments use every applied nodal force at its actual coordinate.",
              "limitations": "Single constant traction vector on one axis-aligned bounding-plane boundary patch. Not arbitrary face picking, pressure, follower loading or spatially varying loading. Beam theory neglects shear and 3D end effects; global displacement and equilibrium are validated, not local root peak stress."}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (output / "convergence.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(cases)
    with (output / "edge-curve.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["x_m", "fem_lower_edge_z_m", "analytical_z_m"])
        writer.writerows(zip(points[edge, 0], displacement[edge, 2], analytical))
    plot_distributed(output, report, points[edge, 0], displacement[edge, 2])
    lines = ["# Distributed-load validation", "", f"**{report['result']}** — uniform surface traction, equivalent nodal loading and real solver studies.", "",
             "The load input is the signed **total force in N**, not Pa or N/m. The selected surface area is measured from the boundary mesh; constant traction is F/A in the selected global X/Y/Z direction. Planar bounding surfaces X/Y/Z min/max are available. The legacy equal-node end load is retained separately and is not called uniform traction.", "",
             "Beam: 1,000 × 20 × 20 mm, E=210 GPa, ν=0.3, X-min fully fixed. A total −10 N Z force is distributed on Z-max: area 0.02 m², traction −500 Pa, equivalent line load q=−10 N/m. Euler–Bernoulli predicts `w(x)=q*x²*(6L²−4Lx+x²)/(24EI)` and `w(L)=qL⁴/(8EI)`; I=bh³/12. Expected root reaction is +10 N Z and −5 N·m Y.", "",
             "| Quadratic mesh | Elements | Tip mean Z (mm) | Error vs theory |", "|---|---:|---:|---:|"]
    lines.extend(f"| {case['case']} | {case['elements']:,} | {case['tip_z_m'] * 1000:.9f} | {case['error_fraction'] * 100:.4f}% |" for case in cases)
    lines += ["", f"Analytical tip: **{expected * 1000:.9f} mm**. Last mesh change: **{change * 100:.4f}%**. Fine edge-curve error normalized by analytical tip deflection: **{curve_error * 100:.4f}%**.", "",
              "The axial traction patch check uses a 1 × 0.1 × 0.1 m bar, E=210 GPa, ν=0, F=1,000 N at X-max. Uniform stress gives `u=FL/(EA)`. Two quadratic mesh densities are checked against a 0.001% error limit.", "",
              "| Axial mesh | FEM tip X (m) | Relative error (%) |", "|---|---:|---:|"]
    lines.extend(f"| {case['case']} | {case['tip_x_m']:.10g} | {case['error_fraction'] * 100:.7f}% |" for case in axial)
    lines += ["", report["load_integration"], "", report["reaction_recovery"], "",
              f"On the fine beam mesh, applied force at the constrained edge is {fine['applied_at_support_z_N']:.9g} N. Reported support RF sums to {fine['reported_support_force_z_N']:.9g} N; the recovered physical support reaction is {fine['reaction_z_N']:.9g} N. Omitting this correction would fail equilibrium.", "",
              "Acceptance: beam tip and normalized edge curve <2%, last-mesh change <0.5%, axial errors <0.001%, every force/moment residual <1e−5. Unit tests also check all six surface choices in all three vector directions, reversal/scaling, exact quadratic virtual work and malformed surface rejection.", "",
              report["limitations"], "", "![Distributed-load verification](validation.png)", "",
              "Reproduce: `open-sim validate-distributed --out <new-folder>`. Raw meshes, decks, logs, DAT/FRD, viewers and nodal forces are retained per case.", "",
              "References: [TU Graz cantilever under uniform load](https://lampz.tugraz.at/~hadley/memm/mechanics/cbeam.php), "
              "[LUSAS consistent equivalent nodal force theory](https://www.lusas.com/user_area/theory/equivalent_force_distribution.html), "
              "[CalculiX RF definition](https://www.dhondt.de/ccx_2.23.pdf)."]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def plot_distributed(output, report, coordinate, displacement):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.6), layout="constrained")
    position = np.linspace(0, 1, 201)
    axes[0].plot(position, uniform_beam_deflection(position) * 1000, label="Uniform-load beam theory", color="black")
    axes[0].plot(coordinate, displacement * 1000, "--", label="3D FEM fine / lower edge")
    axes[0].set(xlabel="Distance from clamp (m)", ylabel="Z deflection (mm)", title="Uniform load over full span")
    cases = report["beam_cases"]
    axes[1].plot([case["elements"] for case in cases], [case["error_fraction"] * 100 for case in cases], "o-", label="Tip-section mean")
    axes[1].set(xlabel="Quadratic tetrahedra", ylabel="Error vs beam theory (%)", title="Mesh refinement", xscale="log")
    for axis in axes:
        axis.legend()
        axis.grid(alpha=0.2)
    figure.suptitle("Doo Doo Dynamics Simulator · distributed traction · total −10 N")
    figure.savefig(output / "validation.png", dpi=160)
    plt.close(figure)
