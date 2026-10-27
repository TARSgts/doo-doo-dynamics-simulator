"""Mesh convergence study for the static structural solve.

The same model is solved on successively finer meshes. For each tracked quantity the
study reports the change between the last two meshes, a convergence verdict and, when
the last three results change monotonically, a Richardson extrapolation with the grid
convergence index (GCI, Roache's safety factor 1.25 for three meshes).
"""
import csv
import html
import json
import math
from pathlib import Path

from opensim.load_settings import NORMAL_AXES

DEFAULT_LEVELS = 4
DEFAULT_RATIO = 1.4
DEFAULT_TOLERANCE_PERCENT = 2.0
DEFAULT_MAX_ELEMENTS = 300_000
LEVEL_SOLVER_TIMEOUT_S = 1800
TARGETS = ("displacement", "response", "stress")
QUANTITIES = {
    "displacement": ("Maximum displacement |U|", "mm", 1e3),
    "response": ("Loaded-area mean displacement along the force", "mm", 1e3),
    "stress": ("Maximum von Mises stress", "MPa", 1e-6),
}


def validate_convergence_parameters(levels, ratio, tolerance_percent, target, max_elements=DEFAULT_MAX_ELEMENTS):
    if isinstance(levels, bool) or not isinstance(levels, int) or not 3 <= levels <= 6:
        raise ValueError("A convergence study needs 3 to 6 mesh levels")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or not 1.15 <= ratio <= 2.5:
        raise ValueError("Refinement ratio must be between 1.15 and 2.5")
    if isinstance(tolerance_percent, bool) or not isinstance(tolerance_percent, (int, float)) \
            or not math.isfinite(tolerance_percent) or not 0.01 <= tolerance_percent <= 50:
        raise ValueError("Convergence tolerance must be between 0.01% and 50%")
    if target not in TARGETS:
        raise ValueError("Convergence target must be displacement, response or stress")
    if isinstance(max_elements, bool) or not isinstance(max_elements, int) or max_elements < 1000:
        raise ValueError("Element limit must be an integer of at least 1000")


def response_value(summary):
    """Mean displacement of the loaded area along the applied force direction (m), sign kept."""
    axis = summary.get("load_axis", "x")
    if axis in NORMAL_AXES:
        return float(summary["loaded_surface_mean_normal_displacement_m"])
    index = "xyz".index(axis)
    sign = 1.0 if summary.get("load_N", 1) >= 0 else -1.0
    vector = (summary.get("loaded_surface_mean_displacement_m") if summary.get("load_kind") == "traction"
              else summary.get("tip_mean_displacement_m") or summary.get("load_point_displacement_m"))
    if vector is None:
        raise ValueError("No loaded-area displacement in this result")
    return float(vector[index]) * sign


def level_values(summary):
    return {"displacement": float(summary["maximum_displacement_m"]),
            "response": response_value(summary),
            "stress": float(summary["maximum_von_mises_Pa"])}


def observed_order(e_coarse, e_fine, r_coarse, r_fine):
    """Fit C*h**p using each measured refinement ratio, not an averaged ratio."""
    if min(r_coarse, r_fine) <= 1.01 or e_coarse * e_fine <= 0:
        return None
    target = math.log(e_coarse / e_fine)
    def residual(order):
        return (order * math.log(r_fine) + math.log(math.expm1(order * math.log(r_coarse)))
                - math.log(math.expm1(order * math.log(r_fine))) - target)
    low, high = 0.5, 6.0
    if residual(low) > 0 or residual(high) < 0:
        return None
    for _ in range(60):
        middle = (low + high) / 2
        if residual(middle) > 0:
            high = middle
        else:
            low = middle
    return (low + high) / 2


def analyse(levels, tolerance):
    """Verdict, last change, and Richardson estimate for each quantity from completed levels."""
    analysis = {}
    for key in QUANTITIES:
        values = [level["values"][key] for level in levels]
        changes = [abs(values[i] - values[i - 1]) / max(abs(values[i]), 1e-300) for i in range(1, len(values))]
        entry = {"values": values, "changes": changes, "last_change": changes[-1] if changes else None,
                 "extrapolated": None, "observed_order": None, "gci_fine": None}
        refined = len(levels) >= 3 and all(right["tetrahedra"] > left["tetrahedra"] for left, right in zip(levels[-3:], levels[-2:]))
        if len(values) < 3:
            entry["verdict"] = "not enough meshes"
        elif not refined:
            entry["verdict"] = "not enough refinement"
        elif changes[-1] <= tolerance:
            entry["verdict"] = "converged"
        elif len(changes) >= 2 and changes[-1] > changes[-2] * 1.05 and changes[-1] > tolerance:
            entry["verdict"] = "diverging"
        else:
            entry["verdict"] = "converging" if len(changes) >= 2 and changes[-1] < changes[-2] else "not yet converged"
        if len(values) >= 3:
            f1, f2, f3 = values[-3:]  # coarse, medium, fine
            n1, n2, n3 = (level["tetrahedra"] for level in levels[-3:])
            r_coarse, r_fine = (n2 / n1) ** (1 / 3), (n3 / n2) ** (1 / 3)
            e_coarse, e_fine = f2 - f1, f3 - f2
            order = observed_order(e_coarse, e_fine, r_coarse, r_fine)
            if order is not None:
                extrapolated = f3 + e_fine / (r_fine ** order - 1)
                entry.update(observed_order=order, extrapolated=extrapolated,
                             gci_fine=1.25 * abs(e_fine / f3) / (r_fine ** order - 1) if f3 else None)
        analysis[key] = entry
    return analysis


def run_convergence(cad: Path, output: Path, size, scale=1.0, young=210e9, poisson=0.3, load=1000.0, order=1,
                    load_axis="x", load_kind="face", load_surface="x-max", support_region=None, load_region=None,
                    levels=DEFAULT_LEVELS, ratio=DEFAULT_RATIO, tolerance_percent=DEFAULT_TOLERANCE_PERCENT,
                    target="displacement", max_elements=DEFAULT_MAX_ELEMENTS, ccx=None, progress=None):
    """Solve on meshes size, size/ratio, size/ratio², … and stop early once the target quantity converges."""
    from opensim.cli import solve
    from opensim.geometry import MeshElementLimitExceeded
    validate_convergence_parameters(levels, ratio, tolerance_percent, target, max_elements)
    if not math.isfinite(size) or size <= 0:
        raise ValueError("Mesh size must be positive and finite")
    output.mkdir(parents=True, exist_ok=False)
    tolerance = tolerance_percent / 100
    completed, stop_reason = [], f"Ran all {levels} meshes"
    for index in range(levels):
        level_size = size / ratio ** index
        if completed and completed[-1]["tetrahedra"] * ratio ** 3 > max_elements:
            stop_reason = (f"Stopped before mesh {index + 1}: about {int(completed[-1]['tetrahedra'] * ratio ** 3):,} elements "
                           f"would exceed the {max_elements:,} element limit")
            break

        def report(stage, number=index + 1):
            if progress:
                progress(f"convergence-{number}-{levels}-{stage}")

        try:
            summary = solve(cad, output / f"mesh-{index + 1}", size=level_size, scale=scale, young=young, poisson=poisson,
                            load=load, ccx=ccx, order=order, load_axis=load_axis, load_kind=load_kind, load_surface=load_surface,
                            support_region=support_region, load_region=load_region, progress=report,
                            solver_timeout=LEVEL_SOLVER_TIMEOUT_S, max_elements=max_elements)
        except MeshElementLimitExceeded as error:
            stop_reason = str(error)
            break
        completed.append({"level": index + 1, "mesh_size_m": level_size, "nodes": summary["nodes"],
                          "tetrahedra": summary["tetrahedra"], "values": level_values(summary),
                          "relative_force_imbalance": summary["relative_force_imbalance"],
                          "viewer": f"mesh-{index + 1}/results.html"})
        analysis = analyse(completed, tolerance)
        if len(completed) >= 3 and analysis[target]["verdict"] == "converged":
            stop_reason = f"{QUANTITIES[target][0]} changed {analysis[target]['last_change'] * 100:.3g}% on the last refinement, within the {tolerance_percent:g}% target"
            break
    if len(completed) < 2:
        raise ValueError(stop_reason + "; at least two meshes are needed. Increase the mesh size or the element limit")
    analysis = analyse(completed, tolerance)
    result = {"analysis": "convergence", "target": target, "tolerance_percent": tolerance_percent, "refinement_ratio": ratio,
              "requested_levels": levels, "max_elements": max_elements, "element_type": "C3D10" if order == 2 else "C3D4",
              "levels": completed, "quantities": analysis, "stop_reason": stop_reason,
              "verdict": analysis[target]["verdict"], "nodes": completed[-1]["nodes"], "tetrahedra": completed[-1]["tetrahedra"],
              "units": {"displacement": "m", "response": "m", "stress": "Pa"}}
    (output / "convergence.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    with (output / "convergence.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["mesh", "mesh_size_m", "nodes", "tetrahedra", "max_displacement_m", "loaded_mean_displacement_m", "max_von_mises_Pa"])
        for level in completed:
            writer.writerow([level["level"], level["mesh_size_m"], level["nodes"], level["tetrahedra"],
                             level["values"]["displacement"], level["values"]["response"], level["values"]["stress"]])
    write_report(output / "report.html", result)
    return result


VERDICT_TEXT = {
    "converged": ("Converged", "The last refinement changed this value less than your tolerance. This is a mesh-stability check, not proof of physical accuracy."),
    "converging": ("Converging", "Changes are shrinking but are still above your tolerance. Add a mesh level or start finer."),
    "not yet converged": ("Not yet converged", "Changes are still large. Add mesh levels or use quadratic elements."),
    "diverging": ("Not converging", "The changes grew on the last refinement. Check mesh quality and the load/support geometry. "
                                    "For peak stress, a singular corner, point load or ideal fixed edge can cause this behavior; "
                                    "inspect stress away from those locations or use displacement as the study target."),
    "not enough meshes": ("Not enough meshes", "At least three successively refined meshes are needed for a convergence verdict."),
    "not enough refinement": ("Not enough refinement", "Element counts did not increase on the last three meshes; unchanged output alone does not establish convergence."),
}


def _format(value, scale):
    return f"{value * scale:.5g}"


def _chart(levels, values, scale, unit, extrapolated, dark=False):
    width, height, left, right, top, bottom = 560, 260, 70, 20, 20, 46
    counts = [level["tetrahedra"] for level in levels]
    scaled = [value * scale for value in values]
    span_values = scaled + ([extrapolated * scale] if extrapolated is not None else [])
    low, high = min(span_values), max(span_values)
    pad = (high - low) * 0.12 or abs(high) * 0.05 or 1
    low, high = low - pad, high + pad
    x_low, x_high = math.log10(min(counts)) - 0.08, math.log10(max(counts)) + 0.08

    def x(count):
        return left + (math.log10(count) - x_low) / (x_high - x_low) * (width - left - right)

    def y(value):
        return top + (high - value) / (high - low) * (height - top - bottom)

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Value against element count" class="chart">',
             f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" class="axis"/>',
             f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" class="axis"/>']
    for tick in range(5):
        value = low + (high - low) * tick / 4
        parts.append(f'<text x="{left - 8}" y="{y(value) + 4:.1f}" text-anchor="end" class="tick">{value:.4g}</text>')
        parts.append(f'<line x1="{left}" y1="{y(value):.1f}" x2="{width - right}" y2="{y(value):.1f}" class="grid"/>')
    for count in counts:
        parts.append(f'<text x="{x(count):.1f}" y="{height - bottom + 18}" text-anchor="middle" class="tick">{count:,}</text>')
    parts.append(f'<text x="{(left + width - right) / 2}" y="{height - 6}" text-anchor="middle" class="tick">elements (log scale)</text>')
    parts.append(f'<text x="14" y="{(top + height - bottom) / 2}" transform="rotate(-90 14 {(top + height - bottom) / 2})" text-anchor="middle" class="tick">{unit}</text>')
    if extrapolated is not None:
        level = y(extrapolated * scale)
        parts.append(f'<line x1="{left}" y1="{level:.1f}" x2="{width - right}" y2="{level:.1f}" class="extrapolated"/>')
        parts.append(f'<text x="{width - right - 4}" y="{level - 6:.1f}" text-anchor="end" class="tick">extrapolated {extrapolated * scale:.4g}</text>')
    points = " ".join(f"{x(count):.1f},{y(value):.1f}" for count, value in zip(counts, scaled))
    parts.append(f'<polyline points="{points}" class="line"/>')
    parts.extend(f'<circle cx="{x(count):.1f}" cy="{y(value):.1f}" r="4.5" class="dot"><title>{count:,} elements: {value:.6g} {unit}</title></circle>'
                 for count, value in zip(counts, scaled))
    parts.append("</svg>")
    return "".join(parts)


def write_report(path: Path, result: dict):
    levels, target = result["levels"], result["target"]
    target_entry = result["quantities"][target]
    title, explanation = VERDICT_TEXT[target_entry["verdict"]]
    rows = []
    for index, level in enumerate(levels):
        cells = [f"{level['level']}", f"{level['mesh_size_m'] * 1000:.4g}", f"{level['nodes']:,}", f"{level['tetrahedra']:,}"]
        for key, (_, _, scale) in QUANTITIES.items():
            change = result["quantities"][key]["changes"][index - 1] if index else None
            cells.append(_format(level["values"][key], scale) + (f' <span class="change">({change * 100:.3g}%)</span>' if change is not None else ""))
        cells.append(f'<a href="{html.escape(level["viewer"])}">open</a>')
        rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    cards = []
    for key, (label, unit, scale) in QUANTITIES.items():
        entry = result["quantities"][key]
        verdict, _ = VERDICT_TEXT[entry["verdict"]]
        estimate = (f"Extrapolated: <b>{entry['extrapolated'] * scale:.5g} {unit}</b> · observed order {entry['observed_order']:.2f}"
                    + (f" · GCI {entry['gci_fine'] * 100:.3g}%" if entry["gci_fine"] is not None else "")
                    if entry["extrapolated"] is not None else "No reliable extrapolation (needs three meshes with steadily shrinking changes)")
        cards.append(f'<section class="card{" target" if key == target else ""}"><h2>{html.escape(label)}'
                     f'{" · study target" if key == target else ""}</h2>'
                     f'<p class="verdict {entry["verdict"].replace(" ", "-")}">{verdict} · last change '
                     f'{entry["last_change"] * 100:.3g}%</p>{_chart(levels, entry["values"], scale, unit, entry["extrapolated"])}'
                     f'<p class="note">{estimate}</p></section>')
    hint = ('<p>Tip: linear C3D4 elements are too stiff in bending and converge slowly. Quadratic C3D10 elements '
            'usually converge with far fewer elements.</p>'
            if result["element_type"] == "C3D4" and target_entry["verdict"] != "converged" else "")
    document = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Mesh convergence study</title>
<style>
:root{{--bg:#ffffff;--fg:#27374a;--muted:#5f7186;--line:#d5dee8;--accent:#2f6fd6;--good:#1f8a4c;--warn:#b7791f;--bad:#c2413b}}
@media (prefers-color-scheme: dark){{:root{{--bg:#121b2b;--fg:#d8e4f1;--muted:#93a6bc;--line:#2b3b52;--accent:#6aa6ff;--good:#4fd17a;--warn:#f1b956;--bad:#ff6b6b}}}}
body.dark{{--bg:#121b2b;--fg:#d8e4f1;--muted:#93a6bc;--line:#2b3b52;--accent:#6aa6ff;--good:#4fd17a;--warn:#f1b956;--bad:#ff6b6b}}
body.light{{--bg:#ffffff;--fg:#27374a;--muted:#5f7186;--line:#d5dee8;--accent:#2f6fd6;--good:#1f8a4c;--warn:#b7791f;--bad:#c2413b}}
body{{background:var(--bg);color:var(--fg);font:14px 'Segoe UI',system-ui,sans-serif;margin:24px;line-height:1.5}}
h1{{font-size:22px;margin:0 0 6px}}h2{{font-size:15px;margin:0 0 6px}}p{{margin:6px 0}}
.summary{{border-left:4px solid var(--accent);padding:8px 14px;margin:14px 0}}.muted,.note,.change{{color:var(--muted)}}
.grid-cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:14px}}
.card{{border:1px solid var(--line);border-radius:8px;padding:12px}}.card.target{{border-color:var(--accent)}}
.verdict{{font-weight:600}}.converged{{color:var(--good)}}.converging,.not-yet-converged{{color:var(--warn)}}.diverging{{color:var(--bad)}}
.chart{{width:100%;height:auto}}.axis{{stroke:var(--muted)}}.grid{{stroke:var(--line)}}.tick{{fill:var(--muted);font-size:11px}}
.line{{fill:none;stroke:var(--accent);stroke-width:2}}.dot{{fill:var(--accent)}}.extrapolated{{stroke:var(--good);stroke-dasharray:5 4}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:10px}}td,th{{border:1px solid var(--line);padding:6px 8px;text-align:right}}
th{{text-align:center}}a{{color:var(--accent)}}
</style>
<body>
<script>const theme=new URLSearchParams(location.search).get('theme');if(['light','dark'].includes(theme))document.body.classList.add(theme);</script>
<h1>Mesh convergence study</h1>
<p class="muted">{result['element_type']} elements · refinement ratio {result['refinement_ratio']:g} · tolerance {result['tolerance_percent']:g}% · {len(levels)} of {result['requested_levels']} meshes solved</p>
<div class="summary"><p><b>{html.escape(QUANTITIES[target][0])}: {title}.</b> {html.escape(explanation)}</p>
<p class="muted">{html.escape(result['stop_reason'])}.</p>{hint}</div>
<div class="grid-cards">{''.join(cards)}</div>
<h2 style="margin-top:18px">All meshes</h2>
<table><tr><th>Mesh</th><th>Size (mm)</th><th>Nodes</th><th>Elements</th><th>Max |U| (mm)</th><th>Loaded mean (mm)</th><th>Max von Mises (MPa)</th><th>Result</th></tr>
{''.join(rows)}</table>
<p class="note">Percentages are the change from the previous mesh. The extrapolated value estimates the answer on an
infinitely fine mesh (Richardson extrapolation) under an asymptotic power-law assumption using effective sizes derived from element counts. GCI is an indicative discretization estimate, not a guaranteed error bound.
Peak stress at singular corners, point loads and ideal fixed edges may fail to converge; use displacement or stress away from those spots.</p>
</body></html>"""
    path.write_text(document, encoding="utf-8")
