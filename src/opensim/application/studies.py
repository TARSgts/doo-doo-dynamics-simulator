"""One catalogue of study behavior and the inputs that make results current.

Geometry/material settings remain explicitly shared. Study-only inputs never
invalidate another study. Job payloads remain immutable and readable by old tools.
"""
from dataclasses import dataclass
import hashlib
import json
from opensim.application.parameters import DEFAULT_PARAMETERS

MESH=frozenset({'mesh_size_m','cad_scale','element_order'})
ELASTIC=frozenset({'young_Pa','poisson','support_region'})
LOAD=frozenset({'load_N','load_axis','load_kind','load_surface','load_region','load_cases'})
CONVERGENCE=frozenset(k for k in DEFAULT_PARAMETERS if k.startswith('convergence_'))
THERMAL=frozenset(k for k in DEFAULT_PARAMETERS if k.startswith('thermal_'))
CFD=frozenset(k for k in DEFAULT_PARAMETERS if k.startswith('cfd_'))


@dataclass(frozen=True)
class StudyDefinition:
    key: str
    title: str
    job_kind: str
    result_view: str
    inputs: frozenset[str]
    handler: str
    desktop_command: str


STUDIES={definition.key:definition for definition in (
    StudyDefinition('static','Static Structural','solve','results',MESH|ELASTIC|LOAD,'opensim.execution.analyses:static','solve'),
    StudyDefinition('modal','Modal Analysis','modal','modal',MESH|ELASTIC|{'density_kg_m3','mode_count'},'opensim.execution.analyses:modal','modal'),
    StudyDefinition('convergence','Convergence Study','convergence','geometry',MESH|ELASTIC|LOAD|CONVERGENCE,'opensim.execution.analyses:convergence','convergence'),
    StudyDefinition('thermal','Thermal Analysis','thermal','thermal',MESH|THERMAL,'opensim.execution.analyses:thermal','thermal'),
    StudyDefinition('cfd','Fluid Dynamics','cfd','cfd_slice',CFD,'opensim.execution.analyses:cfd','cfd_run'),
)}
STUDY_TYPES=tuple(STUDIES)
JOB_STUDIES={definition.job_kind:definition.key for definition in STUDIES.values()}|{'cfd_mesh':'cfd','cfd_validation':'cfd'}
VIEW_STUDIES={definition.result_view:definition.key for definition in STUDIES.values() if definition.result_view!='geometry'}|{'cfd':'cfd','cfd_report':'cfd'}


def study_for_job(kind,selected='static',example=None):
    return 'thermal' if kind=='example' and example=='heat_sink' else JOB_STUDIES.get(kind,selected)


def input_values(study,parameters,*,kind=None):
    """Effective numerical inputs, excluding display labels and unused controls."""
    if study not in STUDIES:raise ValueError('Unknown study')
    p=DEFAULT_PARAMETERS|parameters
    if kind=='cfd_validation':return {'reference_suite':1}
    keys=set(STUDIES[study].inputs)
    if study in {'static','convergence'} and p['load_cases']:
        keys-=LOAD-{'load_cases'}
    if study=='thermal':
        keys.discard('thermal_source_temperature_K' if p['thermal_boundary_mode']=='power' else 'thermal_power_W')
    if study=='cfd':
        case=p['cfd_case']
        if case=='cad':
            keys={'cfd_case','cfd_backend','cfd_domain_mode','cfd_mesh_size_m','cfd_cad_scale','cfd_density_kg_m3','cfd_viscosity_Pa_s','cfd_inlet_region','cfd_outlet_region'}
            if p['cfd_backend']=='su2':
                keys|={'cfd_speed_m_s','cfd_sound_speed_m_s','cfd_flow_axis','cfd_turbulence','cfd_iterations','cfd_residual_target'}
                if p['cfd_domain_mode']=='external':keys.add('cfd_padding')
            else:keys.add('cfd_pressure_drop_Pa')
        else:
            common={'cfd_case','cfd_resolution','cfd_density_kg_m3','cfd_viscosity_Pa_s'}
            keys=common|{'cylinder':{'cfd_speed_m_s','cfd_sound_speed_m_s','cfd_radius_m'},
                         'pipe':{'cfd_radius_m','cfd_length_m','cfd_pressure_drop_Pa'},
                         'flat_plate':{'cfd_speed_m_s','cfd_sound_speed_m_s','cfd_chord_m','cfd_alpha_min_deg','cfd_alpha_max_deg','cfd_alpha_step_deg'}}[case]
    if kind in {'mesh','cfd_mesh','example'}:
        if study=='thermal':keys=set(MESH)
        if study=='modal':keys=set(MESH)|{'support_region'}
        if study in {'static','convergence'}:keys=set(MESH)|{'support_region'}|set(LOAD)
        if study=='cfd':keys={'cfd_cad_scale','cfd_mesh_size_m','cfd_domain_mode','cfd_flow_axis','cfd_padding','cfd_inlet_region','cfd_outlet_region'}
    return {key:p[key] for key in sorted(keys)}


def input_snapshot(study,cad,parameters,*,kind=None):
    values=input_values(study,parameters,kind=kind)
    # Analytical reference models do not consume an imported solid.
    consumes_cad=kind!='cfd_validation' and not (study=='cfd' and (DEFAULT_PARAMETERS|parameters)['cfd_case']!='cad' and kind!='cfd_mesh')
    return {'study':study,'cad':str(cad) if cad and consumes_cad else None,'inputs':values}


def input_signature(study,cad,parameters,*,kind=None):
    def normalized(value):
        if isinstance(value,dict):return {k:normalized(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)):return [normalized(v) for v in value]
        if isinstance(value,(int,float)) and not isinstance(value,bool):return float(value)
        return value
    content=json.dumps(normalized(input_snapshot(study,cad,parameters,kind=kind)),sort_keys=True,separators=(',',':'),allow_nan=False)
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def job_is_current(job,project):
    """Compare actual saved inputs, including legacy jobs, instead of global revisions."""
    payload=job.get('payload') or {}
    if 'parameters' not in payload:return job['revision']==project['revision']
    kind=job['kind'];study=study_for_job(kind,payload.get('study','static'),payload.get('example'))
    cad=payload.get('cad')
    if kind=='example':
        # Example jobs create the CAD themselves; only that generated file belongs to this snapshot.
        from pathlib import Path
        filename='heat-sink.step' if payload.get('example')=='heat_sink' else 'test-object.step'
        current=project.get('cad')
        if not current or Path(current).parent.name!=job['id'] or Path(current).name!=filename:return False
        cad=current
    return input_snapshot(study,cad,payload['parameters'],kind=kind)==input_snapshot(study,project.get('cad'),project['parameters'],kind=kind)
