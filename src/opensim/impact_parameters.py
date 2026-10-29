"""Inputs for the low-height elastic plate drop-test demonstrator, in SI."""
import math

IMPACT_DEFAULTS={
 'impact_length_m':.2,'impact_width_m':.15,'impact_thickness_m':.003,
 'impact_young_Pa':210e9,'impact_poisson':.3,'impact_density_kg_m3':7850.,
 'impact_mass_kg':.25,'impact_drop_height_m':.01,'impact_patch_m':.02,
 'impact_contact_N_m':1e6,'impact_damping_ratio':.01,
 'impact_duration_s':.02,'impact_step_s':2e-6,'impact_modes':3,
}
IMPACT_LIMITS='Low-height blunt drop test on a simply supported rectangular elastic plate. Modal thin-plate bending with a compliant contact spring. Independent of imported CAD. No plasticity, fracture, penetration, material failure, or through-thickness stress-wave prediction.'


def validate_impact_parameters(parameters):
    p=IMPACT_DEFAULTS|parameters
    for key in IMPACT_DEFAULTS:
        value=p[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError('Drop-test inputs must be finite numbers')
    bounds={
        'impact_length_m':(.05,1.),'impact_width_m':(.05,1.),'impact_thickness_m':(.001,.02),
        'impact_young_Pa':(1e6,300e9),'impact_poisson':(-.9,.49),'impact_density_kg_m3':(50,20000),
        'impact_mass_kg':(.05,2.),'impact_drop_height_m':(.0001,.05),'impact_patch_m':(.005,.2),
        'impact_contact_N_m':(1e4,1e7),'impact_damping_ratio':(0.,.1),
        'impact_duration_s':(.005,.1),'impact_step_s':(1e-7,2e-5),
    }
    for key,(lo,hi) in bounds.items():
        if not lo<=p[key]<=hi:raise ValueError(f'{key} must be between {lo:g} and {hi:g} SI')
    if p['impact_modes']!=int(p['impact_modes']) or not 1<=p['impact_modes']<=5:
        raise ValueError('Use 1–5 symmetric plate modes per direction')
    short=min(p['impact_length_m'],p['impact_width_m'])
    if p['impact_thickness_m']/short>.05:raise ValueError('Thin-plate model requires thickness / shorter side ≤ 0.05')
    if p['impact_patch_m']>short/3:raise ValueError('The centered drop-weight patch must fit within one third of the shorter plate side')
    return p
