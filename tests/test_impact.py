import json
import math
import time
from pathlib import Path
import numpy as np
import pytest
from opensim.impact import GRAVITY,plate_modes,midpoint_step,simulate_drop,run_impact
from opensim.impact_parameters import IMPACT_DEFAULTS,validate_impact_parameters


def test_square_plate_frequency_and_finite_patch_modal_averages():
    p=IMPACT_DEFAULTS|{'impact_width_m':.2}
    modes,omega,mass,coupling=plate_modes(p)
    rigidity=p['impact_young_Pa']*p['impact_thickness_m']**3/(12*(1-p['impact_poisson']**2))
    dimensionless=omega[0]*.2**2*math.sqrt(p['impact_density_kg_m3']*p['impact_thickness_m']/rigidity)
    assert dimensionless==pytest.approx(19.739208802178716,rel=1e-12) # exact SSSS square-plate value
    assert np.all(mass==pytest.approx(p['impact_density_kg_m3']*.003*.2*.2/4))
    axis=np.linspace(.1-p['impact_patch_m']/2,.1+p['impact_patch_m']/2,1001)
    # Independent quadrature of the modal shape over the contact patch.
    averages=np.array([np.trapezoid(np.sin(m*np.pi*axis/.2),axis)/p['impact_patch_m'] for m,_ in modes])
    other=np.array([np.trapezoid(np.sin(n*np.pi*axis/.2),axis)/p['impact_patch_m'] for _,n in modes])
    np.testing.assert_allclose(coupling,averages*other,rtol=2e-6)


def test_midpoint_free_oscillator_energy_and_second_order_phase_accuracy():
    errors=[]
    for dt in (.02,.01,.005):
        x=np.array([1.]);v=np.array([0.]);mass=np.array([1.]);stiff=np.array([4.]);zero=np.zeros(1)
        for _ in range(round(1/dt)):x,v,_=midpoint_step(x,v,mass,stiff,zero,zero,0.,zero,dt)
        assert .5*v[0]**2+2*x[0]**2==pytest.approx(2.,abs=1e-11)
        errors.append(abs(x[0]-math.cos(2.)))
    assert 3.8<errors[0]/errors[1]<4.2 and 3.8<errors[1]/errors[2]<4.2


def test_unilateral_spring_rebounds_and_has_no_tensile_contact():
    mass=np.array([.25]);k=1e5;velocity=.2;duration=np.pi*math.sqrt(mass[0]/k)
    dt=duration/2000;x=np.zeros(1);v=np.array([velocity]);forces=[];energies=[]
    for _ in range(2400):
        x,v,_=midpoint_step(x,v,mass,np.zeros(1),np.zeros(1),np.ones(1),k,np.zeros(1),dt)
        forces.append(k*max(x[0],0.));energies.append(.5*mass[0]*v[0]**2+.5*k*max(x[0],0.)**2)
    assert min(forces)>=0 and forces[-1]==0
    assert max(forces)==pytest.approx(velocity*math.sqrt(mass[0]*k),rel=1e-5)
    assert v[0]==pytest.approx(-velocity,rel=1e-5)
    assert max(abs(np.array(energies)-.5*mass[0]*velocity**2))<1e-7


def test_coupled_drop_matches_independent_adaptive_integrator_and_time_refinement():
    from scipy.integrate import solve_ivp
    p=IMPACT_DEFAULTS|{'impact_modes':1,'impact_duration_s':.005,'impact_step_s':20e-6}
    _,omega,modal_mass,coupling=plate_modes(p);mass=np.r_[p['impact_mass_kg'],modal_mass]
    stiffness=np.r_[0.,modal_mass*omega**2];damping=np.r_[0.,2*p['impact_damping_ratio']*modal_mass*omega];c=np.r_[1.,-coupling]
    y0=np.zeros(4);y0[2]=math.sqrt(2*GRAVITY*p['impact_drop_height_m'])
    def rhs(t,y):
        force=p['impact_contact_N_m']*max(c@y[:2],0.)
        return np.r_[y[2:],(np.array([mass[0]*GRAVITY,0])-stiffness*y[:2]-damping*y[2:]-c*force)/mass]
    reference=solve_ivp(rhs,(0,.005),y0,method='DOP853',rtol=1e-10,atol=1e-12,max_step=2e-6,dense_output=True)
    errors=[]
    for step in (20e-6,10e-6,5e-6):
        history,q,_,summary=simulate_drop(p|{'impact_step_s':step})
        exact=reference.sol(history[:,0])
        errors.append(np.max(abs(q[:,0]-exact[1])))
        assert summary['maximum_relative_energy_error']<.001
        assert history[:,3].min()>=0
    assert errors[2]<errors[1]<errors[0]
    assert errors[-1]<2e-7


@pytest.mark.parametrize('settings',[
 {'impact_mass_kg':-1},{'impact_drop_height_m':1.},{'impact_modes':2.5},
 {'impact_thickness_m':.02,'impact_length_m':.1},{'impact_patch_m':.1},
 {'impact_step_s':float('nan')},{'impact_modes':True},
])
def test_invalid_or_out_of_scope_inputs_rejected(settings):
    with pytest.raises(ValueError):validate_impact_parameters(settings)


@pytest.mark.parametrize('settings,message',[
    ({'impact_young_Pa':1e6},'small-deflection limit'),
    ({'impact_contact_N_m':1e4},'Contact compression'),
    ({'impact_step_s':1e-7,'impact_duration_s':.1},'300000 steps'),
])
def test_unsupported_response_or_excessive_work_does_not_publish_results(tmp_path,settings,message):
    directory=tmp_path/'unsupported'
    with pytest.raises(ValueError,match=message):
        run_impact(directory,IMPACT_DEFAULTS|{'impact_modes':1,'impact_duration_s':.005}|settings)
    assert not (directory/'report.html').exists()
    assert not (directory/'manifest.json').exists()


def test_default_drop_report_is_finite_and_exports_real_time_history(tmp_path):
    p=IMPACT_DEFAULTS|{'impact_duration_s':.005}
    summary=run_impact(tmp_path/'drop',p)
    assert summary['maximum_relative_energy_error']<1e-4
    assert 0<summary['deflection_bound_over_thickness']<.25
    assert summary['initial_energy_J']==pytest.approx(.25*GRAVITY*.01)
    saved=np.load(tmp_path/'drop/impact.npz');history=saved['history']
    assert np.isfinite(history).all() and np.all(np.diff(history[:,0])>0)
    assert history[:,3].max()<=summary['maximum_contact_force_N']
    assert history[:,9].max()<1e-4
    document=(tmp_path/'drop/report.html').read_text(encoding='utf-8')
    assert 'impactPlaybackState' in document and '__IMPACT_DATA__' not in document and '__INPUT_ROWS__' not in document
    assert 'No stress, failure or damage' in document
    assert json.loads((tmp_path/'drop/manifest.json').read_text())['parameters']==p


def test_drop_test_has_separate_inputs_and_needs_no_cad(tmp_path):
    from opensim.workspace import Workspace
    w=Workspace(tmp_path);pid=w.create_project('Elastic drop')['id']
    w.set_parameters(pid,{'impact_modes':1,'impact_duration_s':.005})
    before=w.get_project(pid)['parameters'];job=w.start_job(pid,'impact');deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        job=w.get_job(job['id'])
        if job['status'] not in {'queued','running'}:break
        time.sleep(.05)
    assert job['status']=='completed',job.get('error')
    assert w.get_impact_results(pid)['job_id']==job['id']
    w.set_parameters(pid,{'load_N':50.,'cfd_speed_m_s':20.})
    assert w.get_impact_results(pid)['job_id']==job['id']
    assert w.get_project(pid)['parameters']['impact_mass_kg']==before['impact_mass_kg']
    cad=tmp_path/'unused.step';cad.write_text('An imported file is independent of the parametric drop-test plate')
    w.import_cad(pid,str(cad));assert w.get_impact_results(pid)['job_id']==job['id']
    w.set_parameters(pid,{'impact_drop_height_m':.005})
    with pytest.raises(ValueError):w.get_impact_results(pid)
