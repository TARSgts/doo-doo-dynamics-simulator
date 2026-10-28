"""Independent reference checks for the bounded CFD models, not experiments."""
import csv
import html
import json
from pathlib import Path

import numpy as np

from opensim.cfd import cylinder_flow, cylinder_velocity, pipe_flow, flat_plate_flow, run_cfd


def run_cfd_validation(output, progress=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    # Sample away from collocation points: a symmetric regular cylinder can
    # reproduce surface Cp to roundoff even on coarse panels, so that alone
    # would not test spatial convergence of the computed exterior field.
    angle = np.linspace(.13, 2*np.pi+.13, 33)[:-1]
    rr, tt = np.meshgrid([1.25, 2., 4.], angle)
    sample = np.column_stack(((rr*np.cos(tt)).ravel(), (rr*np.sin(tt)).ravel()))
    exact = np.column_stack(((1-np.cos(2*tt)/rr**2).ravel(), (-np.sin(2*tt)/rr**2).ravel()))
    for n in (24, 48, 96):
        if progress: progress('cfd-solving')
        data, s = cylinder_flow(n, speed=1., radius=1.)
        error = float(np.max(np.linalg.norm(cylinder_velocity(sample, data, 1.)-exact, axis=1)))
        rows.append({'case':'cylinder', 'resolution':n, 'error':error, 'metric':'exterior velocity / freestream',
                     'cp_error':s['cp_max_error'], 'residual':s['normal_velocity_residual']})
    for n in (12, 24, 48):
        _, s = pipe_flow(n)
        rows.append({'case':'pipe', 'resolution':n, 'error':s['flow_relative_error'], 'metric':'relative flow-rate error',
                     'cp_error':None, 'residual':s['linear_residual']})
    for n in (12, 24, 48):
        data, s = flat_plate_flow(n, alpha_min=-8, alpha_max=8, alpha_step=1)
        slope_error = abs(s['lift_slope_per_rad']/(2*np.pi)-1)
        rows.append({'case':'flat_plate', 'resolution':n, 'error':s['CL_max_abs_error'], 'metric':'absolute CL vs 2π sin α',
                     'cp_error':None, 'residual':s['normal_velocity_residual'], 'slope_relative_error':slope_error})
    cyl, pipe, plate = rows[:3], rows[3:6], rows[6:]
    checks = {
        'cylinder_field_error_below_1_percent': cyl[-1]['error'] < .01,
        'cylinder_field_refines': cyl[2]['error'] < cyl[1]['error'] < cyl[0]['error'],
        'cylinder_surface_cp': all(r['cp_error'] < 1e-7 for r in cyl),
        'pipe_flow_error_below_0.05_percent': pipe[-1]['error'] < .0005,
        'pipe_second_order_refinement': all(3.8 < pipe[i]['error']/pipe[i+1]['error'] < 4.2 for i in range(2)),
        'plate_lift_error_below_1e_8': all(r['error'] < 1e-8 for r in plate),
        'plate_small_angle_slope_within_0.5_percent': all(r['slope_relative_error'] < .005 for r in plate),
        'all_equation_residuals_below_1e_8': all(r['residual'] < 1e-8 for r in rows),
    }
    for case in ('cylinder', 'pipe', 'flat_plate'):
        run_cfd(output/case, {'cfd_case':case}, progress=progress)
    result = {'analysis':'cfd_validation', 'result':'PASS' if all(checks.values()) else 'FAIL', 'checks':checks, 'rows':rows,
              'scope':'Numerical verification against potential-flow, Hagen–Poiseuille and thin-airfoil references. No experimental validation, turbulence, separation, stall, viscous external drag or CAD flow.'}
    (output/'report.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    with (output/'data.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, ['case','resolution','metric','error','cp_error','residual','slope_relative_error'])
        writer.writeheader(); writer.writerows(rows)
    row_html = ''.join('<tr>'+''.join('<td>'+html.escape(str(r.get(k,'')))+'</td>' for k in ('case','resolution','metric','error','residual'))+'</tr>' for r in rows)
    check_html = ''.join('<li>'+('PASS' if passed else 'FAIL')+' — '+html.escape(name)+'</li>' for name, passed in checks.items())
    (output/'report.html').write_text(f'''<!doctype html><meta charset="utf-8"><title>CFD verification</title>
<style>body{{font:15px Segoe UI;background:#101923;color:#dce8f4;margin:24px}}td,th{{padding:8px;border:1px solid #536476}}table{{border-collapse:collapse;width:100%}}a{{color:#6fd2ff}}img{{max-width:100%}}</style>
<h1>CFD verification: {result['result']}</h1><p>{result['scope']}</p><ul>{check_html}</ul>
<table><tr><th>Case</th><th>Panels/cells</th><th>Error metric</th><th>Error</th><th>Equation residual</th></tr>{row_html}</table>
<p>The pipe uses annular finite volumes and must converge at second order. Cylinder surface symmetry can reproduce Cp exactly at collocation points, so off-body velocities are tested independently. Plate integrated lift can also be exact at low resolution; this does not establish local pressure accuracy or stall prediction.</p>
<p><a href="data.csv">CSV comparisons</a> · <a href="report.json">Full checks and thresholds</a></p>
<h2>Cylinder</h2><a href="cylinder/report.html">Open cylinder report and streamlines</a><img src="cylinder/plot.png">
<h2>Pipe</h2><a href="pipe/report.html">Open pipe report</a><img src="pipe/plot.png">
<h2>Flat plate: CL vs α</h2><a href="flat_plate/report.html">Open angle sweep</a><img src="flat_plate/plot.png">''', encoding='utf-8')
    return result
