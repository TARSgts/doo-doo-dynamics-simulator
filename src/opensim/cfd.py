"""Original numerical benchmark solvers; reference formulae do not drive solves.

Cylinder: constant-source boundary panels. Pipe: annular finite volumes.
Flat plate: quarter-panel discrete vortices / three-quarter collocation.
These reduced flow models are not a general CAD Navier–Stokes solver.
"""
import csv
import html
import json
from pathlib import Path

import numpy as np

from opensim.cfd_parameters import CFD_DEFAULTS, CASE_LABELS, CASE_LIMITS, validate_cfd_parameters


def cylinder_velocity(points, data, speed):
    """Evaluate the solved source distribution away from the panel surfaces."""
    points = np.asarray(points)
    vertices = data['vertices_m']
    start, end = vertices[:-1], vertices[1:]
    g, w = np.polynomial.legendre.leggauss(24)
    result = np.tile([speed, 0.], (len(points), 1))
    for j in range(len(start)):
        source = (start[j]+end[j])/2 + g[:, None]*(end[j]-start[j])/2
        delta = points[:, None, :]-source[None, :, :]
        r2 = np.sum(delta*delta, axis=-1)
        result += data['source_strength_m_s'][j]*np.linalg.norm(end[j]-start[j])/(4*np.pi)*np.einsum('iqd,q->id', delta/r2[..., None], w)
    return result


def cylinder_flow(resolution=64, speed=10., radius=.005):
    n = int(resolution)
    theta = np.arange(n+1)*2*np.pi/n
    vertices = radius*np.column_stack((np.cos(theta), np.sin(theta)))
    start, end = vertices[:-1], vertices[1:]
    center = (start+end)/2
    length = np.linalg.norm(end-start, axis=1)
    tangent = (end-start)/length[:, None]
    normal = np.column_stack((tangent[:, 1], -tangent[:, 0]))
    # Integrate the 2D source kernel along each straight panel. The exterior
    # self limit is +1/2 in the normal direction, zero tangentially.
    g, w = np.polynomial.legendre.leggauss(24)
    sources = center[:, None, :] + g[None, :, None]*(end-start)[:, None, :]/2
    delta = center[:, None, None, :] - sources[None, :, :, :]
    r2 = np.sum(delta*delta, axis=-1)
    influence = np.einsum('ijqd,q,j->ijd', delta/r2[..., None], w, length)/(4*np.pi)
    idx = np.arange(n)
    influence[idx, idx] = normal/2
    a = np.einsum('ijd,id->ij', influence, normal)
    strengths = np.linalg.solve(a, -speed*normal[:, 0])
    velocity = np.array([speed, 0.]) + np.einsum('ijd,j->id', influence, strengths)
    vt = np.sum(velocity*tangent, axis=1)
    cp = 1-(vt/speed)**2
    angle = np.arctan2(center[:, 1], center[:, 0]) % (2*np.pi)
    cp_reference = 1-4*np.sin(angle)**2
    force = -np.sum(cp[:, None]*normal*length[:, None], axis=0)/(2*radius)
    return {'theta_deg': np.rad2deg(angle), 'cp': cp, 'cp_reference': cp_reference,
            'velocity_m_s': velocity, 'points_m': center, 'source_strength_m_s': strengths,
            'vertices_m': vertices}, {
                'cp_max_error': float(np.max(abs(cp-cp_reference))),
                'normal_velocity_residual': float(np.max(abs(np.sum(velocity*normal, axis=1)))/speed),
                'relative_net_source': float(abs(strengths@length)/(speed*2*np.pi*radius)),
                'CL': float(force[1]), 'CD_pressure': float(force[0]),
            }


def pipe_flow(resolution=64, radius=.005, length=1., pressure_drop=.1, viscosity=1.81e-5, density=1.225):
    n = int(resolution)
    edges = np.linspace(0, radius, n+1)
    dr = radius/n
    r = (edges[1:]+edges[:-1])/2
    # Integrate -μ d(r du/dr)/dr = (Δp/L) r over each annulus.
    # Zero center flux is natural; the wall uses a half-cell no-slip distance.
    left = edges[:-1]/dr
    right = edges[1:]/dr
    right[-1] *= 2
    a = np.diag(left+right) - np.diag(right[:-1], 1) - np.diag(left[1:], -1)
    rhs = pressure_drop/(length*viscosity)*(edges[1:]**2-edges[:-1]**2)/2
    u = np.linalg.solve(a, rhs)
    area = np.pi*(edges[1:]**2-edges[:-1]**2)
    q = float(u@area)
    mean = q/(np.pi*radius**2)
    reynolds = density*mean*(2*radius)/viscosity
    if reynolds >= 2000:
        raise ValueError(f'Pipe Reynolds number {reynolds:.1f} is outside the supported laminar range (<2000); reduce pressure drop')
    reference = pressure_drop*(radius**2-r**2)/(4*viscosity*length)
    q_reference = np.pi*radius**4*pressure_drop/(8*viscosity*length)
    tau = viscosity*u[-1]/(dr/2)
    friction = 8*tau/(density*mean**2)
    return {'radius_m': r, 'velocity_m_s': u, 'velocity_reference_m_s': reference,
            'annulus_area_m2': area}, {
                'flow_rate_m3_s': q, 'flow_reference_m3_s': float(q_reference),
                'flow_relative_error': float(abs(q/q_reference-1)),
                'profile_relative_error': float(np.max(abs(u-reference))/(pressure_drop*radius**2/(4*viscosity*length))),
                'mean_velocity_m_s': mean, 'Re': float(reynolds), 'wall_shear_Pa': float(tau),
                'Darcy_f': float(friction), 'Darcy_f_reference': float(64/reynolds),
                'linear_residual': float(np.max(abs(a@u-rhs))/np.max(abs(rhs))),
            }


def flat_plate_flow(resolution=64, speed=10., chord=.1, density=1.225, alpha_min=-8., alpha_max=8., alpha_step=2.):
    n = int(resolution)
    # Cosine spacing resolves the leading-edge singularity. Each vortex sits
    # at 1/4 of its panel and its no-penetration point at 3/4. The wake-free
    # trailing edge selects the lifting solution, rather than prescribing CL.
    edges = chord*(1-np.cos(np.linspace(0, np.pi, n+1)))/2
    width = np.diff(edges)
    xv = edges[:-1]+.25*width
    xc = edges[:-1]+.75*width
    a = 1/(2*np.pi*(xc[:, None]-xv[None, :]))
    alpha = np.arange(alpha_min, alpha_max+alpha_step*1e-9, alpha_step)
    if abs(alpha[-1]-alpha_max) > 1e-8:
        alpha = np.append(alpha, alpha_max)
    rhs = speed*np.sin(np.deg2rad(alpha))[None, :]*np.ones((n, 1))
    circulation = np.linalg.solve(a, rhs)
    cl = 2*circulation.sum(axis=0)/(speed*chord)
    exact = 2*np.pi*np.sin(np.deg2rad(alpha))
    thin = 2*np.pi*np.deg2rad(alpha)
    slope = float(np.polyfit(np.deg2rad(alpha), cl, 1)[0]) if len(alpha) > 1 else None
    return {'alpha_deg': alpha, 'CL': cl, 'CL_reference': exact, 'CL_small_angle': thin,
            'lift_per_span_N_m': .5*density*speed**2*chord*cl,
            'panel_x_over_c': xc/chord, 'circulation_m2_s': circulation,
            'delta_cp': 2*circulation/(width[:, None]*speed)}, {
                'CL_max_abs_error': float(np.max(abs(cl-exact))),
                'lift_slope_per_rad': slope,
                'small_angle_slope_reference': float(2*np.pi),
                'normal_velocity_residual': float(np.max(abs(a@circulation-rhs))/speed),
                'angle_count': len(alpha),
            }


def run_cfd(output, parameters=None, progress=None):
    p = validate_cfd_parameters(CFD_DEFAULTS | (parameters or {}))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    case = p['cfd_case']
    if progress: progress('cfd-solving')
    n = int(p['cfd_resolution'])
    if case == 'cylinder':
        data, summary = cylinder_flow(n, p['cfd_speed_m_s'], p['cfd_radius_m'])
        columns = [('theta_deg', 'theta_deg'), ('Cp', 'cp'), ('Cp_reference', 'cp_reference')]
    elif case == 'pipe':
        data, summary = pipe_flow(n, p['cfd_radius_m'], p['cfd_length_m'], p['cfd_pressure_drop_Pa'], p['cfd_viscosity_Pa_s'], p['cfd_density_kg_m3'])
        columns = [('radius_m', 'radius_m'), ('axial_velocity_m_s', 'velocity_m_s'), ('reference_velocity_m_s', 'velocity_reference_m_s')]
    else:
        data, summary = flat_plate_flow(n, p['cfd_speed_m_s'], p['cfd_chord_m'], p['cfd_density_kg_m3'], p['cfd_alpha_min_deg'], p['cfd_alpha_max_deg'], p['cfd_alpha_step_deg'])
        columns = [('alpha_deg', 'alpha_deg'), ('CL', 'CL'), ('CL_reference', 'CL_reference'), ('CL_small_angle', 'CL_small_angle'), ('lift_per_span_N_m', 'lift_per_span_N_m')]
    if not all(np.isfinite(v).all() for v in data.values()):
        raise ValueError('CFD solve produced nonfinite results')
    summary.update(analysis='cfd', case=case, resolution=n, limitations=CASE_LIMITS[case],
                   method={'cylinder': 'constant-source boundary panels', 'pipe': 'annular finite volumes', 'flat_plate': 'discrete vortex panels'}[case])
    if case != 'pipe':
        summary['Mach'] = p['cfd_speed_m_s']/p['cfd_sound_speed_m_s']
        summary['Re_context_only'] = p['cfd_density_kg_m3']*p['cfd_speed_m_s']*(2*p['cfd_radius_m'] if case == 'cylinder' else p['cfd_chord_m'])/p['cfd_viscosity_Pa_s']
    if progress: progress('exporting')
    np.savez_compressed(output/'flow.npz', **data)
    with (output/'data.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([label for label, _ in columns])
        writer.writerows(zip(*(data[key] for _, key in columns)))
    (output/'manifest.json').write_text(json.dumps({'parameters': p, 'summary': summary}, indent=2, allow_nan=False), encoding='utf-8')
    write_cfd_report(output, p, data, summary)
    return summary


def write_cfd_report(output, p, data, summary):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    case = p['cfd_case']
    fig = Figure(figsize=(10, 4.5), layout='constrained', facecolor='#101923')
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.set_facecolor('#172434')
    ax.tick_params(colors='#dce8f4')
    for spine in ax.spines.values(): spine.set_color('#536476')
    if case == 'cylinder':
        ax.plot(data['theta_deg'], data['cp'], 'o', ms=3, color='#6fd2ff', label='Numerical source panels')
        ax.plot(data['theta_deg'], data['cp_reference'], color='#ffc46b', label='Reference: 1 − 4 sin²θ')
        ax.set(xlabel='Surface angle θ (degrees)', ylabel='Pressure coefficient Cp')
    elif case == 'pipe':
        ax.plot(data['radius_m']*1000, data['velocity_m_s'], 'o', ms=3, color='#6fd2ff', label='Numerical finite volumes')
        ax.plot(data['radius_m']*1000, data['velocity_reference_m_s'], color='#ffc46b', label='Hagen–Poiseuille reference')
        ax.set(xlabel='Radius from center (mm)', ylabel='Axial velocity (m/s)')
    else:
        ax.plot(data['alpha_deg'], data['CL'], 'o-', ms=4, color='#6fd2ff', label='Numerical vortex panels')
        ax.plot(data['alpha_deg'], data['CL_reference'], '--', color='#ffc46b', label='Reference: 2π sin α')
        ax.plot(data['alpha_deg'], data['CL_small_angle'], ':', color='#b1a0ff', label='Small-angle: 2πα (α in radians)')
        ax.set(xlabel='Angle of attack α (degrees)', ylabel='Section lift coefficient CL')
        ax.axhline(0, color='#536476', lw=.7)
        ax.axvline(0, color='#536476', lw=.7)
    ax.xaxis.label.set_color('#dce8f4'); ax.yaxis.label.set_color('#dce8f4')
    ax.grid(alpha=.15, color='white')
    ax.legend(facecolor='#223448', edgecolor='#536476', labelcolor='#dce8f4')
    fig.savefig(output/'plot.png', dpi=150)
    field_image = ''
    if case == 'cylinder':
        radius = p['cfd_radius_m']
        x = np.linspace(-3*radius, 3*radius, 120)
        y = np.linspace(-2*radius, 2*radius, 80)
        xx, yy = np.meshgrid(x, y)
        outside = np.hypot(xx, yy) > 1.03*radius
        velocities = np.full((*xx.shape, 2), np.nan)
        velocities[outside] = cylinder_velocity(np.column_stack((xx[outside], yy[outside])), data, p['cfd_speed_m_s'])
        field = Figure(figsize=(10, 5), layout='constrained')
        FigureCanvasAgg(field)
        axis = field.add_subplot(111)
        color = axis.contourf(xx/radius, yy/radius, np.linalg.norm(velocities, axis=-1), 24, cmap='viridis')
        axis.streamplot(x/radius, y/radius, velocities[..., 0], velocities[..., 1], color='white', density=1, linewidth=.5)
        from matplotlib.patches import Circle
        axis.add_patch(Circle((0, 0), 1, color='#223448', zorder=10))
        axis.set(aspect='equal', xlabel='x / radius', ylabel='y / radius', title='Solved potential-flow velocity and streamlines')
        field.colorbar(color, ax=axis, label='Speed (m/s)')
        field.savefig(output/'field.png', dpi=150)
        field_image = '<img src="field.png" alt="Solved cylinder velocity and streamlines">'
    labels = {
        'case':'Case', 'resolution':'Panels / radial cells', 'method':'Numerical method',
        'cp_max_error':'Maximum pressure-coefficient error',
        'normal_velocity_residual':'No-penetration equation residual',
        'relative_net_source':'Relative source-balance residual',
        'CL':'Lift coefficient CL', 'CD_pressure':'Ideal pressure-drag coefficient',
        'flow_rate_m3_s':'Volume flow rate (m³/s)', 'flow_reference_m3_s':'Reference volume flow rate (m³/s)',
        'flow_relative_error':'Flow-rate error (%)', 'profile_relative_error':'Velocity-profile error (%)',
        'mean_velocity_m_s':'Mean velocity (m/s)', 'Re':'Reynolds number',
        'wall_shear_Pa':'Wall shear stress (Pa)', 'Darcy_f':'Darcy friction factor',
        'Darcy_f_reference':'Reference Darcy friction factor', 'linear_residual':'Momentum equation residual',
        'CL_max_abs_error':'Maximum lift-coefficient error', 'lift_slope_per_rad':'Fitted lift slope (per radian)',
        'small_angle_slope_reference':'Small-angle reference slope (per radian)', 'angle_count':'Angles solved',
        'Mach':'Mach number', 'Re_context_only':'Reynolds number (context only; inviscid model)',
    }
    def display(v):
        return f'{v:.7g}' if isinstance(v, float) else str(v)
    rows = ''.join(f'<tr><td>{html.escape(labels.get(k,k))}</td><td>{html.escape(display(v*100 if k in {"flow_relative_error","profile_relative_error"} else v))}</td></tr>' for k, v in summary.items() if k not in {'analysis', 'limitations'})
    input_labels = {'cfd_case':'Case','cfd_resolution':'Panels / radial cells', 'cfd_speed_m_s':'Freestream speed (m/s)',
                    'cfd_density_kg_m3':'Density (kg/m³)', 'cfd_viscosity_Pa_s':'Dynamic viscosity (Pa·s)',
                    'cfd_sound_speed_m_s':'Speed of sound (m/s)', 'cfd_radius_m':'Radius (m)',
                    'cfd_length_m':'Pipe length (m)', 'cfd_pressure_drop_Pa':'Pressure drop (Pa)',
                    'cfd_chord_m':'Chord (m)', 'cfd_alpha_min_deg':'Start α (degrees)',
                    'cfd_alpha_max_deg':'End α (degrees)', 'cfd_alpha_step_deg':'Step α (degrees)'}
    inputs = ''.join(f'<tr><td>{html.escape(input_labels[k])}</td><td>{html.escape(display(v))}</td></tr>' for k, v in p.items() if k in input_labels)
    document = f'''<!doctype html><html><head><meta charset="utf-8"><title>{CASE_LABELS[case]}</title>
<style>body{{background:#101923;color:#dce8f4;font:15px Segoe UI,sans-serif;margin:24px;max-width:1100px}}h1{{font-size:25px}}img{{width:100%;height:auto}}p{{line-height:1.5}}table{{border-collapse:collapse;width:100%;font-size:13px}}td{{padding:7px;border:1px solid #40546a;overflow-wrap:anywhere}}a{{color:#6fd2ff}}.note{{padding:14px;background:#253447;border-left:4px solid #ffc46b}}</style></head><body>
<h1>{CASE_LABELS[case]}</h1><p class="note">{CASE_LIMITS[case]} These are numerical benchmark models, not a general CAD flow solver. Agreement with theory verifies the implementation within these assumptions; it is not experimental validation.</p>
<img src="plot.png" alt="Numerical flow results compared against analytical reference">{field_image}<p><a href="data.csv">Export plotted data (CSV)</a> · <a href="flow.npz">Full numerical arrays</a></p>
<h2>Results</h2><table>{rows}</table><details><summary>Saved inputs (SI units; angles in degrees)</summary><table>{inputs}</table></details></body></html>'''
    (output/'report.html').write_text(document, encoding='utf-8')
