"""Plots of completed numerical results, with explicit units and CSV provenance."""
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import textwrap

import numpy as np


@dataclass
class PlotSource:
    project_id: str
    project_name: str
    job_id: str
    revision: int
    study: str
    directory: Path
    summary: dict
    arrays: dict


@dataclass
class PlotData:
    title: str
    xlabel: str
    ylabel: str
    kind: str
    x: np.ndarray
    y: np.ndarray
    columns: dict
    note: str
    widths: np.ndarray | None = None
    log_x: bool = False


PLOT_NAMES = {
    "temperature-position": "Temperature vs position",
    "temperature-distribution": "Temperature distribution",
    "heat-flux-position": "Heat flux vs position",
    "heat-flux-distribution": "Heat flux distribution",
    "displacement-position": "Displacement vs position",
    "stress-position": "Von Mises stress vs position",
    "displacement-distribution": "Displacement distribution",
    "stress-distribution": "Von Mises stress distribution",
    "normal-position": "Axial / normal stress vs position",
    "normal-distribution": "Axial / normal stress distribution",
    "shear-position": "Shear stress vs position",
    "shear-distribution": "Shear stress distribution",
    "frequencies": "Natural frequencies",
    "mode-position": "Mode shape vs position",
    "convergence-displacement": "Maximum displacement vs element count",
    "convergence-response": "Loaded-area displacement vs element count",
    "convergence-stress": "Maximum stress vs element count",
}
COMPONENTS = {"magnitude": "Total magnitude", "x": "X component", "y": "Y component", "z": "Z component"}
STRESS_COMPONENTS = {"xx": "Normal X · Sxx", "yy": "Normal Y · Syy", "zz": "Normal Z · Szz",
                     "xy": "Shear XY · Sxy", "yz": "Shear YZ · Syz", "zx": "Shear ZX · Szx"}


def load_plot_source(workspace, project_id, study=None):
    project = workspace.get_project(project_id)
    study = study or workspace.ui_state()["study"]
    from opensim.application.studies import STUDIES
    if study not in STUDIES or study=='cfd':
        raise ValueError("Choose static, modal or convergence study")
    kind=STUDIES[study].job_kind
    job = workspace.latest_result_job(project_id,[kind])
    if job is None:
        raise ValueError(f"Run the {study} study for the current settings before creating plots")
    directory = workspace.job_directory(job["id"]) / kind
    arrays = {}
    if study != "convergence":
        filename = "thermal.npz" if study == "thermal" else "fields.npz" if study == "static" else "modes.npz"
        path = directory / filename
        if not path.is_file():
            raise ValueError("This saved run has no plot data. Solve this study again to generate it")
        keys = ("points", "temperature_K", "heat_flux_W_m2") if study == "thermal" else ("points", "displacement", "von_mises_Pa", "stress") if study == "static" else ("points", "normalized_modes", "frequencies_Hz")
        with np.load(path, allow_pickle=False) as saved:
            arrays = {key: saved[key].copy() for key in keys if key in saved}
        points = arrays.get("points")
        if points is None or points.ndim != 2 or points.shape[1] != 3 or not len(points):
            raise ValueError("Saved plot coordinates are incomplete")
        if any(not np.isfinite(array).all() for array in arrays.values()):
            raise ValueError("Saved plot data contains nonfinite values")
        if study == "static":
            if arrays.get("displacement", np.empty(0)).shape != points.shape:
                raise ValueError("Saved displacement data does not match the nodes")
            if "von_mises_Pa" in arrays and arrays["von_mises_Pa"].shape != (len(points),):
                raise ValueError("Saved stress data does not match the nodes")
            if "stress" in arrays and arrays["stress"].shape != (len(points), 6):
                raise ValueError("Saved stress tensor must have six components per node")
        elif study == 'thermal':
            if arrays.get('temperature_K', np.empty(0)).shape != (len(points),) or arrays.get('heat_flux_W_m2', np.empty(0)).shape != points.shape:
                raise ValueError('Saved thermal fields do not match the nodes')
            if np.any(arrays['temperature_K'] < 0):
                raise ValueError('Saved temperatures are below absolute zero')
        else:
            frequencies = arrays.get("frequencies_Hz", np.empty(0))
            if frequencies.ndim != 1 or not len(frequencies) or np.any(frequencies <= 0):
                raise ValueError("Saved modal frequencies are incomplete")
            if arrays.get("normalized_modes", np.empty(0)).shape != (len(frequencies), len(points), 3):
                raise ValueError("Saved mode shapes do not match the nodes")
    return PlotSource(project_id, project["name"], job["id"], job["revision"], study, directory, job["result"], arrays)


def available_plots(source):
    if source.study == 'thermal':
        return ['temperature-position', 'temperature-distribution', 'heat-flux-position', 'heat-flux-distribution']
    if source.study == "static":
        result = ["displacement-position", "displacement-distribution"]
        if "von_mises_Pa" in source.arrays:
            result += ["stress-position", "stress-distribution"]
        if "stress" in source.arrays:
            result += ["normal-position", "normal-distribution", "shear-position", "shear-distribution"]
        return result
    if source.study == "modal":
        return ["frequencies", "mode-position"]
    return ["convergence-displacement", "convergence-response", "convergence-stress"]


def make_plot_data(source, plot, axis="x", component="magnitude", mode=1, bins=30, stress_component=None):
    if plot not in available_plots(source):
        raise ValueError("This plot is not available for the saved study")
    if axis not in ("x", "y", "z") or component not in COMPONENTS:
        raise ValueError("Choose X/Y/Z position and a valid result component")
    if plot.startswith("convergence-"):
        quantity = plot.removeprefix("convergence-")
        levels = source.summary["levels"]
        if not levels:
            raise ValueError("No completed mesh levels to plot")
        scale, unit = (1e-6, "MPa") if quantity == "stress" else (1000, "mm")
        x = np.asarray([level["tetrahedra"] for level in levels], dtype=float)
        y = np.asarray([level["values"][quantity] for level in levels], dtype=float) * scale
        if np.any(x <= 0) or not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("Convergence data must be finite with positive element counts")
        label = {"displacement": "Maximum displacement", "response": "Loaded-area mean displacement along force", "stress": "Maximum von Mises stress"}[quantity]
        columns = {"mesh_level": [level["level"] for level in levels], "element_count": x,
                   "mesh_size_mm": [level["mesh_size_m"] * 1000 for level in levels], f"{quantity}_{unit}": y}
        note = "Completed mesh refinements; plotted values are the saved solver results."
        if len(y) > 1 and y[-1] != 0:
            note += f" Last refinement change: {abs((y[-1] - y[-2]) / y[-1]) * 100:.3g}%."
        return PlotData(PLOT_NAMES[plot], "Element count (log scale)", f"{label} ({unit})", "line", x, y, columns, note, log_x=True)
    if plot == "frequencies":
        y = source.arrays["frequencies_Hz"]
        x = np.arange(1, len(y) + 1)
        return PlotData("Natural frequencies", "Mode number", "Natural frequency (Hz)", "bar", x, y,
                        {"mode_number": x, "frequency_Hz": y}, "Undamped, unprestressed eigenfrequencies.")
    modal = source.study == "modal"
    if source.study == 'thermal':
        vectors = source.arrays['heat_flux_W_m2']
        unit, scale = 'W/m²', 1
    elif modal:
        count = len(source.arrays["normalized_modes"])
        if type(mode) is not int or not 1 <= mode <= count:
            raise ValueError(f"Choose a mode between 1 and {count}")
        vectors = source.arrays["normalized_modes"][mode - 1]
        unit, scale = "dimensionless", 1
    else:
        vectors = source.arrays["displacement"]
        unit, scale = "mm", 1000
    tensor = plot.startswith(("normal-", "shear-"))
    stress = plot.startswith("stress-")
    if plot.startswith('temperature-'):
        values = source.arrays['temperature_K'] - 273.15
        label, unit = 'Temperature', '°C'
    elif tensor:
        allowed = ("xx", "yy", "zz") if plot.startswith("normal-") else ("xy", "yz", "zx")
        stress_component = stress_component or allowed[0]
        if stress_component not in allowed:
            raise ValueError("Choose a matching normal or shear stress component")
        values = source.arrays["stress"][:, list(STRESS_COMPONENTS).index(stress_component)] * 1e-6
        label, unit = "Recovered " + STRESS_COMPONENTS[stress_component], "MPa"
    elif stress:
        values = source.arrays["von_mises_Pa"] * 1e-6
        label, unit = "Recovered von Mises stress", "MPa"
    else:
        values = (np.linalg.norm(vectors, axis=1) if component == "magnitude" else vectors[:, "xyz".index(component)]) * scale
        label = ("Heat flux" if source.study == 'thermal' else "Normalized mode shape" if modal else "Displacement") + " · " + COMPONENTS[component]
    if plot.endswith("distribution"):
        if type(bins) is not int or not 5 <= bins <= 200:
            raise ValueError("Choose 5–200 histogram bins")
        limits = None
        if np.ptp(values) == 0:
            pad = max(abs(float(values[0])) * 0.05, 1e-9)
            limits = float(values[0]) - pad, float(values[0]) + pad
        counts, edges = np.histogram(values, bins=bins, range=limits)
        return PlotData(label + " distribution", f"{label} ({unit})", "Mesh node count", "histogram", edges[:-1], counts,
                        {f"bin_lower_{unit}": edges[:-1], f"bin_upper_{unit}": edges[1:], "node_count": counts},
                        f"{len(values):,} nodal samples. Counts depend on mesh-node density; no volume weighting." +
                        (" Global axes; normal stress positive in tension, negative in compression. Shear retains its tensor sign." if tensor else ""), widths=np.diff(edges))
    points = source.arrays["points"] * 1000
    x = points[:, "xyz".index(axis)]
    columns = {"node_id": np.arange(1, len(points) + 1), "x_mm": points[:, 0], "y_mm": points[:, 1], "z_mm": points[:, 2], f"value_{unit}": values}
    note = f"{len(values):,} mesh nodes across the whole model; undeformed coordinates."
    if tensor:
        note += " Global axes; normal stress positive in tension, negative in compression. Shear retains its tensor sign."
    if modal:
        note += f" Mode {mode}, {source.arrays['frequencies_Hz'][mode - 1]:.6g} Hz; arbitrary normalized amplitude."
    return PlotData(label + f" vs {axis.upper()} position", f"Undeformed {axis.upper()} position (mm)", f"{label} ({unit})", "scatter", x, values, columns, note)


def plot_provenance(source, data):
    return {"project_id": source.project_id, "project_name": source.project_name, "job_id": source.job_id,
            "input_revision": source.revision, "study": source.study, "title": data.title,
            "x_label": data.xlabel, "y_label": data.ylabel, "note": data.note}


def write_plot_csv(path, source, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(data.columns)
        writer.writerows(zip(*data.columns.values()))
    metadata = path.with_suffix(".metadata.json")
    metadata.write_text(json.dumps(plot_provenance(source, data), indent=2, allow_nan=False), encoding="utf-8")
    return path, metadata


def make_figure(source, data, dark=False, figure=None):
    from matplotlib.figure import Figure
    background, foreground, grid, accent = ("#121b2b", "#d8e4f1", "#35475f", "#58c9dc") if dark else ("#ffffff", "#27374a", "#d9e2ed", "#2476b5")
    if figure is None:
        figure = Figure(figsize=(8.5, 5.5), dpi=110, facecolor=background)
    else:
        figure.clear()
        figure.set_facecolor(background)
    axes = figure.add_subplot(111, facecolor=background)
    figure.subplots_adjust(left=0.14, right=0.96, bottom=0.25, top=0.83)
    axes.set_title(data.title, color=foreground, fontsize=12, parse_math=False)
    axes.set_xlabel(data.xlabel, color=foreground, parse_math=False)
    axes.set_ylabel(data.ylabel, color=foreground, parse_math=False)
    axes.tick_params(colors=foreground)
    for spine in axes.spines.values():
        spine.set_color(grid)
    axes.xaxis.get_offset_text().set_color(foreground)
    axes.yaxis.get_offset_text().set_color(foreground)
    axes.grid(True, color=grid, alpha=0.55, linewidth=0.6)
    axes.set_axisbelow(True)
    if data.kind == "scatter":
        axes.scatter(data.x, data.y, s=7, alpha=0.55, color=accent, edgecolors="none", rasterized=True)
    elif data.kind == "histogram":
        from matplotlib.ticker import MaxNLocator
        axes.bar(data.x, data.y, width=data.widths, align="edge", color=accent, edgecolor=background, linewidth=0.4)
        axes.yaxis.set_major_locator(MaxNLocator(integer=True))
    elif data.kind == "bar":
        axes.bar(data.x, data.y, color=accent, width=0.65)
        axes.set_xticks(data.x)
    else:
        axes.plot(data.x, data.y, "o-", color=accent, linewidth=1.5, markersize=5)
    if data.log_x:
        axes.set_xscale("log")
    figure.text(0.14, 0.95, source.project_name, color=foreground, fontsize=10, parse_math=False)
    figure.text(0.03, 0.075, "\n".join(textwrap.wrap(data.note, 110)), color=foreground, fontsize=8, parse_math=False)
    figure.text(0.03, 0.025, f"{source.study.title()} · run {source.job_id[:8]} · input revision {source.revision}", color=foreground, fontsize=8)
    return figure


def write_plot_figure(path, source, data, dark=False):
    path = Path(path)
    if path.suffix.lower() not in {".png", ".svg"}:
        raise ValueError("Save figures as PNG or SVG")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure = make_figure(source, data, dark)
    figure.savefig(path, dpi=180, metadata={"Title": data.title, "Description": json.dumps(plot_provenance(source, data)), "Creator": "Doo Doo Dynamics Simulator"})
    return path
