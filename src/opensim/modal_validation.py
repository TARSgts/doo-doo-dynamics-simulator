import csv
import importlib.util
import json
from pathlib import Path

import numpy as np

from opensim.geometry import make_box
from opensim.modal import solve_modal


BENDING_ROOTS = np.array([1.875104068711961, 4.694091132974175, 7.854757438237613])


def beam_frequencies(length=1.0, width=0.02, height=0.02, young=210e9, density=7850.0):
    if any(not np.isfinite(value) or value <= 0 for value in (length, width, height, young, density)):
        raise ValueError("Beam geometry, modulus and density must be positive and finite")
    inertia = width * height ** 3 / 12
    return BENDING_ROOTS ** 2 / (2 * np.pi * length ** 2) * np.sqrt(young * inertia / (density * width * height))


def beam_shape(position, family):
    root = BENDING_ROOTS[family]
    coefficient = (np.cosh(root) + np.cos(root)) / (np.sinh(root) + np.sin(root))
    return np.cosh(root * position) - np.cos(root * position) - coefficient * (np.sinh(root * position) - np.sin(root * position))


def shape_mac(coordinate, numerical, analytical):
    product = np.trapezoid(numerical * analytical, coordinate)
    denominator = np.trapezoid(numerical ** 2, coordinate) * np.trapezoid(analytical ** 2, coordinate)
    if denominator <= 0:
        raise ValueError("Cannot compare a zero mode shape")
    return float(product ** 2 / denominator)


def run_modal_validation(output: Path):
    if importlib.util.find_spec("matplotlib") is None:
        raise RuntimeError("Install plotting dependencies first: pip install '.[validation]'")
    output.mkdir(parents=True, exist_ok=False)
    cad = output / "beam.step"
    make_box(cad, (1.0, 0.02, 0.02))
    reference = np.repeat(beam_frequencies(), 2)
    cases = []
    for label, size, density in (("coarse", 0.02, 7850.0), ("medium", 0.01, 7850.0),
                                 ("fine", 0.0067, 7850.0), ("density-scaling", 0.01, 31400.0)):
        result = solve_modal(cad, output / label, size=size, density=density, mode_count=6, order=2)
        cases.append({"case": label, "mesh_size_m": size, "density_kg_m3": density,
                      "elements": result["tetrahedra"], "nodes": result["nodes"],
                      "frequencies_Hz": result["frequencies_Hz"], "clamp_residual": result["clamp_shape_residual"]})
    fine, medium = cases[2], cases[1]
    frequency_error = np.abs(np.asarray(fine["frequencies_Hz"]) / reference - 1)
    mesh_change = float(np.max(np.abs(np.asarray(fine["frequencies_Hz"]) / medium["frequencies_Hz"] - 1)))
    density_error = float(np.max(np.abs(2 * np.asarray(cases[3]["frequencies_Hz"]) / medium["frequencies_Hz"] - 1)))
    fields = np.load(output / "fine" / "modes.npz")
    points, modes = fields["points"], fields["normalized_modes"]
    edge = np.flatnonzero((np.abs(points[:, 1]) < 1e-8) & (np.abs(points[:, 2]) < 1e-8))
    edge = edge[np.argsort(points[edge, 0])]
    coordinate = points[edge, 0]
    mac_values = []
    curves = []
    for index, mode in enumerate(modes):
        axis = 1 + int(np.argmax(np.sum(mode[edge, 1:] ** 2, axis=0)))
        numerical = mode[edge, axis]
        analytical = beam_shape(coordinate, index // 2)
        mac_values.append(shape_mac(coordinate, numerical, analytical))
        aligned = numerical / np.max(np.abs(numerical)) * np.sign(np.dot(numerical, analytical))
        curves.append(aligned)
    criteria = {"all_six_frequency_errors_below_2_percent": bool(np.all(frequency_error < 0.02)),
                "last_mesh_frequency_changes_below_0_5_percent": mesh_change < 0.005,
                "density_scaling_error_below_0_01_percent": density_error < 1e-4,
                "all_shape_MAC_above_0_995": min(mac_values) > 0.995,
                "all_clamped_shape_components_below_1e_8": all(case["clamp_residual"] < 1e-8 for case in cases)}
    report = {"result": "PASS" if all(criteria.values()) else "FAIL", "criteria": criteria,
              "geometry_m": [1.0, 0.02, 0.02], "young_Pa": 210e9, "poisson": 0.3, "density_kg_m3": 7850.0,
              "analytical_frequencies_Hz": reference.tolist(), "fine_relative_errors": frequency_error.tolist(),
              "last_mesh_change_fraction": mesh_change, "density_scaling_error_fraction": density_error,
              "fine_longitudinal_shape_MAC": mac_values, "cases": cases,
              "reference": "f_n=beta_n²/(2*pi*L²)*sqrt(E*I/(rho*A)); cos(beta)*cosh(beta)=-1",
              "limitations": "Euler–Bernoulli slender-beam approximation versus 3D clamp, shear and rotary inertia. Square section gives paired bending modes whose orientation/sign is arbitrary. MAC compares the dominant transverse component along a corner edge with the corresponding longitudinal beam shape, not a full mass-weighted 3D MAC. No stiffness/mass residual check or forced-response validation is claimed."}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (output / "frequencies.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["mode", "analytical_Hz", "fine_Hz", "relative_error", "edge_shape_MAC"])
        writer.writerows(zip(range(1, 7), reference, fine["frequencies_Hz"], frequency_error, mac_values))
    plot_modal_validation(output, report, coordinate, curves)
    lines = ["# Modal beam validation", "", f"**{report['result']}** — undamped, unprestressed free vibration.", "",
             "1,000 × 20 × 20 mm solid cantilever; E=210 GPa, ν=0.3, density 7,850 kg/m³. The X-min face is fully fixed. There are no applied loads, damping or prestress. CalculiX solves the generalized eigenproblem Kφ=ω²Mφ using C3D10 tetrahedra and consistent mass.", "",
             "Reference: `f_n=β_n²/(2πL²) √(EI/(ρA))`, where `cos(β_n)cosh(β_n)=−1`. The first roots are 1.875104069, 4.694091133 and 7.854757438. A square cross-section produces two nearly equal-frequency bending modes per family; their orientation and sign may rotate or swap between meshes.", "",
             "| Mode | Beam theory (Hz) | Fine FEM (Hz) | Error | Edge-shape MAC |", "|---|---:|---:|---:|---:|"]
    for index in range(6):
        lines.append(f"| {index + 1} | {reference[index]:.6f} | {fine['frequencies_Hz'][index]:.6f} | {frequency_error[index] * 100:.4f}% | {mac_values[index]:.7f} |")
    lines += ["", f"Largest last-mesh frequency change: **{mesh_change * 100:.4f}%**. Quadrupling density on the identical medium mesh halves every frequency; maximum deviation from that scaling: **{density_error * 100:.6f}%**.", "",
              "| Mesh | Quadratic elements | First frequency (Hz) | Sixth frequency (Hz) |", "|---|---:|---:|---:|"]
    lines.extend(f"| {case['case']} | {case['elements']:,} | {case['frequencies_Hz'][0]:.6f} | {case['frequencies_Hz'][-1]:.6f} |" for case in cases)
    lines += ["", "Acceptance: every frequency within 2% of beam theory, every last-mesh frequency change below 0.5%, density scaling error below 0.01%, every edge-shape MAC above 0.995, and fixed-node normalized components below 1e−8. These are benchmark regression limits, not universal error bounds.", "",
              "Displayed modes are each normalized to maximum nodal vector magnitude 1. Their amplitude is dimensionless and arbitrary; they are not static displacement predictions. Animation plays at 1 Hz for inspection regardless of the actual natural frequency. Raw solver eigenvectors are retained separately. Linear tetrahedra are available but quadratic elements are recommended for bending.", "",
              report["limitations"], "", "![Modal verification](validation.png)", "",
              "Reproduce: `open-sim validate-modal --out <new-folder>`. Each solve retains its deck, mesh, DAT/FRD, mode HTML/VTK files, raw and normalized vectors, and solver/input hashes. No additional dependencies were installed.", "",
              "References: [TU Graz cantilever beam frequencies and shapes](https://lampz.tugraz.at/~hadley/memm/mechanics/cbeam.php), "
              "[CalculiX 2.23 manual, frequency analysis and *FREQUENCY](https://www.dhondt.de/ccx_2.23.pdf)."]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def plot_modal_validation(output, report, coordinate, curves):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 3, figsize=(16, 4.8), layout="constrained")
    modes = np.arange(1, 7)
    axes[0].plot(modes, report["analytical_frequencies_Hz"], "o", label="Beam theory")
    axes[0].plot(modes, report["cases"][2]["frequencies_Hz"], "x", markersize=9, label="3D FEM fine")
    axes[0].set(xlabel="Mode number", ylabel="Frequency (Hz)", title="Three paired bending families")
    for index in (0, 2, 4):
        axes[1].plot(coordinate, curves[index], label=f"FEM mode {index + 1}")
        reference = beam_shape(coordinate, index // 2)
        axes[1].plot(coordinate, reference / np.max(np.abs(reference)), "--", color="black", alpha=0.5)
    axes[1].set(xlabel="Distance from fixed end (m)", ylabel="Normalized transverse edge component", title="Shapes vs beam theory (dashed)")
    for case in report["cases"][:3]:
        errors = np.abs(np.asarray(case["frequencies_Hz"]) / report["analytical_frequencies_Hz"] - 1) * 100
        axes[2].plot(modes, errors, "o-", label=case["case"])
    axes[2].set(xlabel="Mode number", ylabel="Frequency error (%)", title="Mesh refinement")
    for axis in axes:
        axis.legend(fontsize=8)
        axis.grid(alpha=0.2)
    figure.suptitle("Doo Doo Dynamics Simulator · modal verification · 1 m square cantilever")
    figure.savefig(output / "validation.png", dpi=160)
    plt.close(figure)
