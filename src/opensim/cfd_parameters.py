"""SI settings for the first, deliberately bounded CFD workbench."""
import math

CFD_DEFAULTS = {
    'cfd_case': 'cylinder', 'cfd_resolution': 64,
    'cfd_speed_m_s': 10., 'cfd_density_kg_m3': 1.225,
    'cfd_viscosity_Pa_s': 1.81e-5, 'cfd_sound_speed_m_s': 343.,
    'cfd_radius_m': .005, 'cfd_length_m': 1., 'cfd_pressure_drop_Pa': .1,
    'cfd_chord_m': .1, 'cfd_alpha_min_deg': -8., 'cfd_alpha_max_deg': 8.,
    'cfd_alpha_step_deg': 2.,
}
CASE_LABELS = {'cylinder': 'Cylinder in a flow', 'pipe': 'Laminar round pipe',
               'flat_plate': 'Flat-plate airfoil · CL vs α'}
CASE_LIMITS = {
    'cylinder': '2D inviscid, incompressible potential flow. Slip surface, zero circulation. No viscous drag, boundary layer, separation or vortex shedding.',
    'pipe': 'Steady, fully developed, incompressible laminar flow in a straight circular pipe. No entrance region, bends, turbulence or heat transfer. Reynolds number must be below 2000.',
    'flat_plate': '2D inviscid thin flat plate with a trailing-edge condition. Small angles only (±10°). No stall, separation, viscous drag or finite-wing effects. Lift is per unit span.',
}


def validate_cfd_parameters(parameters):
    p = CFD_DEFAULTS | parameters
    if p['cfd_case'] not in CASE_LABELS:
        raise ValueError('Choose cylinder, pipe or flat_plate CFD case')
    for key in CFD_DEFAULTS.keys() - {'cfd_case'}:
        v = p[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError('CFD inputs must be finite numbers')
    n = p['cfd_resolution']
    if n != int(n) or not 12 <= n <= 256:
        raise ValueError('CFD resolution must be an integer from 12 to 256')
    for key in ('cfd_speed_m_s', 'cfd_density_kg_m3', 'cfd_viscosity_Pa_s',
                'cfd_sound_speed_m_s', 'cfd_radius_m', 'cfd_length_m', 'cfd_pressure_drop_Pa', 'cfd_chord_m'):
        if p[key] <= 0:
            raise ValueError('CFD speed, fluid properties, dimensions and pressure drop must be positive')
    lo, hi, step = (p[k] for k in ('cfd_alpha_min_deg', 'cfd_alpha_max_deg', 'cfd_alpha_step_deg'))
    if not -10 <= lo <= hi <= 10 or step <= 0 or (hi-lo)/step > 100:
        raise ValueError('Use −10° ≤ start ≤ end ≤ 10°, a positive angle step and at most 101 samples')
    if p['cfd_case'] != 'pipe' and p['cfd_speed_m_s']/p['cfd_sound_speed_m_s'] > .3:
        raise ValueError('This incompressible external-flow model requires Mach ≤ 0.3')
    return p
