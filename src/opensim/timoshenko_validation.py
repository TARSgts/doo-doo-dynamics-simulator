import csv
import importlib.util
import json
from pathlib import Path

import numpy as np

from opensim.cli import solve
from opensim.geometry import make_box


def timoshenko_components(coordinate, length=1.0, width=0.02, height=0.02,
                          young=210e9, poisson=0.3, force=-10.0, shear_factor=5 / 6):
    parameters = (length, width, height, young, shear_factor)
    if any(not np.isfinite(value) or value <= 0 for value in parameters):
        raise ValueError("Dimensions, modulus and shear factor must be positive and finite")
    if not np.isfinite(poisson) or not -1 < poisson < 0.5 or not np.isfinite(force):
        raise ValueError("Use a finite force and Poisson ratio strictly between -1 and 0.5")
    position = np.asarray(coordinate, dtype=float)
    if not np.isfinite(position).all() or np.any(position < 0) or np.any(position > length):
        raise ValueError("Coordinates must be finite and within the beam span")
    area = width * height
    inertia = width * height ** 3 / 12
    shear_modulus = young / (2 * (1 + poisson))
    bending = force * position ** 2 * (3 * length - position) / (6 * young * inertia)
    shear = force * position / (shear_factor * shear_modulus * area)
    return bending, shear


def beam_study(output: Path, label: str, length: float, poisson: float):
    directory = output / label
    directory.mkdir()
    cad = directory / "beam.step"
    make_box(cad, (length, 0.02, 0.02))
    bending, shear = (float(value) for value in timoshenko_components(length, length=length, poisson=poisson))
    expected = bending + shear
    sizes = (0.02, 0.01, 0.0067) if length == 1.0 else (0.0067, 0.005, 0.0033)
    cases = []
    for name, size in zip(("coarse", "medium", "fine"), sizes):
        summary = solve(cad, directory / name, size=size, young=210e9, poisson=poisson,
                        load=-10, order=2, load_axis="z", load_kind="point")
        tip = summary["tip_mean_displacement_m"][2]
        manifest = json.loads((directory / name / "manifest.json").read_text())
        cases.append({"mesh": name, "mesh_size_m": size, "nodes": summary["nodes"],
                      "elements": summary["tetrahedra"], "tip_mean_z_m": tip,
                      "error_vs_timoshenko_fraction": abs(tip / expected - 1),
                      "error_vs_euler_bernoulli_fraction": abs(tip / bending - 1),
                      "excess_over_bending_m": tip - bending,
                      "excess_over_bending_divided_by_theoretical_shear": (tip - bending) / shear,
                      "reaction_z_N": summary["reaction_N"][2],
                      "root_moment_y_Nm": summary["reaction_moment_Nm"][1],
                      "relative_force_imbalance": summary["relative_force_imbalance"],
                      "relative_moment_imbalance": summary["relative_moment_imbalance"],
                      "solver_sha256": manifest["ccx_sha256"], "deck_sha256": manifest["deck_sha256"]})
    change = abs(cases[-1]["tip_mean_z_m"] - cases[-2]["tip_mean_z_m"]) / abs(cases[-1]["tip_mean_z_m"])
    fields = np.load(directory / "fine" / "fields.npz")
    points, displacement = fields["points"], fields["displacement"]
    edge = np.flatnonzero((np.abs(points[:, 1]) < 1e-8) & (np.abs(points[:, 2]) < 1e-8))
    edge = edge[np.argsort(points[edge, 0])]
    edge_bending, edge_shear = timoshenko_components(points[edge, 0], length=length, poisson=poisson)
    with (directory / "edge-curve.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["x_m", "fem_lower_edge_z_m", "timoshenko_centerline_z_m", "bending_z_m", "shear_z_m"])
        writer.writerows(zip(points[edge, 0], displacement[edge, 2], edge_bending + edge_shear, edge_bending, edge_shear))
    return {"study": label, "geometry_m": [length, 0.02, 0.02], "length_over_height": length / 0.02,
            "poisson": poisson, "young_Pa": 210e9, "shear_modulus_Pa": 210e9 / (2 * (1 + poisson)),
            "shear_factor": 5 / 6, "force_z_N": -10, "bending_tip_z_m": bending,
            "shear_tip_z_m": shear, "timoshenko_tip_z_m": expected,
            "shear_over_bending_fraction": shear / bending, "last_mesh_change_fraction": change, "cases": cases}


def run_timoshenko_validation(output: Path):
    if importlib.util.find_spec("matplotlib") is None:
        raise RuntimeError("Install plotting dependencies first: pip install '.[validation]'")
    output.mkdir(parents=True, exist_ok=False)
    studies = [beam_study(output, "thin-beam", 1.0, 0.3),
               beam_study(output, "shear-control", 0.1, 0.0),
               beam_study(output, "poisson-clamp-diagnostic", 0.1, 0.3)]
    thin, control, diagnostic = studies
    criteria = {
        "thin_tip_error_below_2_percent": thin["cases"][-1]["error_vs_timoshenko_fraction"] < 0.02,
        "thin_last_mesh_change_below_0_5_percent": thin["last_mesh_change_fraction"] < 0.005,
        "shear_control_tip_error_below_0_5_percent": control["cases"][-1]["error_vs_timoshenko_fraction"] < 0.005,
        "shear_control_last_mesh_change_below_0_5_percent": control["last_mesh_change_fraction"] < 0.005,
        "shear_control_excess_deflection_within_10_percent_of_theoretical_shear": abs(
            control["cases"][-1]["excess_over_bending_divided_by_theoretical_shear"] - 1) < 0.1,
        "shear_control_closer_to_timoshenko_than_euler_bernoulli": control["cases"][-1]["error_vs_timoshenko_fraction"]
            < control["cases"][-1]["error_vs_euler_bernoulli_fraction"],
        "all_force_balances_below_1e_5": all(case["relative_force_imbalance"] < 1e-5 for study in studies for case in study["cases"]),
        "all_moment_balances_below_1e_5": all(case["relative_moment_imbalance"] < 1e-5 for study in studies for case in study["cases"]),
    }
    report = {"result": "PASS" if all(criteria.values()) else "FAIL", "criteria": criteria,
              "formula": "w(x)=F*x^2*(3*L-x)/(6*E*I)+F*x/(kappa*G*A); I=b*h^3/12; A=b*h; G=E/(2*(1+nu))",
              "formulation": "Independent 3D C3D10 solid meshes solved by CalculiX, not a beam formula used as the numerical solver",
              "measurement": "Area-averaged tip-section Z displacement using exact quadratic surface integration",
              "boundary_conditions": "Full X=0 face clamp; -10 N Z force at the center node of the X=L face",
              "studies": studies,
              "limitations": "Timoshenko is a 1D approximation with kappa=5/6. A fully clamped 3D solid has local warping and Poisson constraint. The thin case does not isolate its tiny shear term. The shorter nu=0 control reduces Poisson restraint; the nu=0.3 diagnostic is retained without a shear-isolation accuracy claim. Point-load stress and point displacement are not convergence targets."}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    with (output / "convergence.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["study", *thin["cases"][0]])
        writer.writeheader()
        writer.writerows({"study": study["study"], **case} for study in studies for case in study["cases"])
    plot_timoshenko(output, studies)
    write_report(output, report)
    return report


def plot_timoshenko(output: Path, studies: list):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 3, figsize=(16, 4.8), layout="constrained")
    thin, control, diagnostic = studies
    coordinate = np.linspace(0, 1, 201)
    bending, shear = timoshenko_components(coordinate)
    axes[0].plot(coordinate, (bending + shear) * 1000, color="#111827", label="Timoshenko centerline")
    axes[0].plot(coordinate, bending * 1000, "--", label="Euler–Bernoulli")
    data = np.genfromtxt(output / "thin-beam" / "edge-curve.csv", delimiter=",", names=True)
    axes[0].plot(data["x_m"], data["fem_lower_edge_z_m"] * 1000, ":", linewidth=2, label="3D FEM lower edge")
    axes[0].set(xlabel="Distance from clamp (m)", ylabel="Z deflection (mm)", title="Thin beam · L/h=50, ν=0.3")
    for study, marker in ((thin, "o"), (control, "s"), (diagnostic, "^")):
        axes[1].plot([case["elements"] for case in study["cases"]],
                     [case["error_vs_timoshenko_fraction"] * 100 for case in study["cases"]], marker + "-", label=study["study"])
    axes[1].set(xlabel="Quadratic tetrahedra", ylabel="Tip mean error vs Timoshenko (%)", title="Independent 3D mesh studies", xscale="log")
    fractions = [case["excess_over_bending_divided_by_theoretical_shear"] * 100 for case in control["cases"]]
    axes[2].plot([case["elements"] for case in control["cases"]], fractions, "s-", label="3D tip mean minus EB")
    axes[2].axhline(100, color="#111827", linestyle="--", label="Theoretical shear = 100%")
    axes[2].set(xlabel="Quadratic tetrahedra", ylabel="Excess / theoretical shear (%)", title="Shear control · L/h=5, ν=0", xscale="log", ylim=(90, 103))
    for axis in axes:
        axis.grid(alpha=0.2)
        axis.legend(fontsize=8)
    figure.suptitle("Doo Doo Dynamics Simulator · Timoshenko beam verification · −10 N tip force")
    figure.savefig(output / "validation.png", dpi=160)
    plt.close(figure)


def write_report(output: Path, report: dict):
    thin, control, diagnostic = report["studies"]
    lines = ["# Timoshenko beam validation", "", f"**{report['result']}** — independent CalculiX C3D10 solid comparison.", "",
             "Each beam has a 20 × 20 mm rectangular section, E=210 GPa and a −10 N tip-center Z force. The X=0 face is fully clamped. All quantities use SI units. The comparison uses area-averaged tip-section displacement, not the singular loaded-node displacement.", "",
             "Timoshenko: `w(x)=F*x²*(3L−x)/(6EI)+F*x/(κGA)`, with `A=bh`, `I=bh³/12`, `G=E/[2(1+ν)]` and the conventional rectangular-section shear factor `κ=5/6`. The first term is Euler–Bernoulli bending; the second is transverse shear. This formula supplies the reference only; the numerical solutions use independent 3D solid elements.", "",
             "The thin beam is 1,000 mm long (L/h=50), ν=0.3. A separate 100 mm beam (L/h=5), ν=0, isolates shear more clearly by reducing Poisson restraint at the full clamp. A third study retains ν=0.3 on the 100 mm beam to expose the effect of 3D end conditions. The zero-Poisson material is a controlled verification case, not an assumed steel property.", "",
             "| Study | Bending tip (mm) | Shear tip (mm) | Timoshenko tip (mm) | Fine FEM mean (mm) | Error |",
             "|---|---:|---:|---:|---:|---:|"]
    for study in report["studies"]:
        fine = study["cases"][-1]
        lines.append(f"| {study['study']} | {study['bending_tip_z_m'] * 1000:.9f} | {study['shear_tip_z_m'] * 1000:.9f} | "
                     f"{study['timoshenko_tip_z_m'] * 1000:.9f} | {fine['tip_mean_z_m'] * 1000:.9f} | {fine['error_vs_timoshenko_fraction'] * 100:.4f}% |")
    lines += ["", f"The thin-beam shear term is only **{thin['shear_over_bending_fraction'] * 100:.4f}%** of bending. Its total-deflection agreement cannot, by itself, verify that tiny shear contribution. The shear control has a **{control['shear_over_bending_fraction'] * 100:.4f}%** theoretical shear/bending ratio; its computed excess over EB is **{control['cases'][-1]['excess_over_bending_divided_by_theoretical_shear'] * 100:.3f}%** of the theoretical shear term.", "",
              "| Study / mesh | Elements | FEM tip mean (mm) | Error vs Timoshenko |", "|---|---:|---:|---:|"]
    for study in report["studies"]:
        for case in study["cases"]:
            lines.append(f"| {study['study']} / {case['mesh']} | {case['elements']:,} | {case['tip_mean_z_m'] * 1000:.9f} | {case['error_vs_timoshenko_fraction'] * 100:.4f}% |")
    lines += ["", "Last mesh changes: " + "; ".join(f"{study['study']}: **{study['last_mesh_change_fraction'] * 100:.4f}%**" for study in report["studies"]) + ".", "",
              "Acceptance: thin total tip error <2%, shear-control total tip error <0.5%, both last-mesh changes <0.5%, shear-control excess over EB within 10% of the theoretical shear term and closer to Timoshenko than EB, plus force and moment residuals <1e−5 in every solve. The ν=0.3 short-beam diagnostic is included in equilibrium checks; its tip error is reported rather than treated as shear-isolation validation.", "",
              "These tolerances are regression acceptance limits, not certified error bounds. Full 3D clamping restricts Poisson deformation and warping; Timoshenko's 1D clamp does not resolve those local effects. The retained short ν=0.3 results show that this model difference persists with refinement. The plotted lower-edge curve is not a cross-section average or a centerline measurement. Only the tip mean is used for the main accuracy criteria. The mathematical point load makes local stress and loaded-node displacement unsuitable convergence targets.", "",
              "![Beam verification and shear check](validation.png)", "",
              "Reproduce: `open-sim validate-timoshenko --out <new-folder>` after installing the validation extra. Each case retains STEP, mesh, deck, DAT/FRD, logs, displacement viewer, nodal data and solver/input hashes. `convergence.csv` contains all nine solves.", "",
              "References: [TU Delft: Timoshenko beam governing equations and shear locking](https://teachbooks.tudelft.nl/computational-modelling/structural_linear/timoshenko.html), "
              "[NASA/TP-2007-215086: Timoshenko theory and the conventional 5/6 rectangular shear factor](https://ntrs.nasa.gov/api/citations/20070035078/downloads/20070035078.pdf), "
              "[CalculiX solid element documentation](https://www.dhondt.de/ccx_2.23.pdf)."]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
