"""Low-height elastic drop test: modal plate, unilateral compliant contact.

The rank-one midpoint solve preserves quadratic energy in each contact state.
Contact switching and time/modal truncation errors remain explicitly reported.
"""
from pathlib import Path
import csv
import json
import math
import numpy as np
from opensim.impact_parameters import validate_impact_parameters,IMPACT_LIMITS

GRAVITY=9.80665


def plate_modes(p):
    a,b,h=p['impact_length_m'],p['impact_width_m'],p['impact_thickness_m']
    modes=np.array([(m,n) for m in range(1,2*int(p['impact_modes']),2) for n in range(1,2*int(p['impact_modes']),2)])
    rigidity=p['impact_young_Pa']*h**3/(12*(1-p['impact_poisson']**2))
    omega=np.pi**2*np.sqrt(rigidity/(p['impact_density_kg_m3']*h))*((modes[:,0]/a)**2+(modes[:,1]/b)**2)
    width=p['impact_patch_m']
    coupling=np.sin(modes[:,0]*np.pi/2)*np.sin(modes[:,1]*np.pi/2)*np.sinc(modes[:,0]*width/(2*a))*np.sinc(modes[:,1]*width/(2*b))
    mass=p['impact_density_kg_m3']*h*a*b/4
    return modes,omega,np.full(len(modes),mass),coupling


def midpoint_step(position,velocity,mass,stiffness,damping,contact_vector,contact_stiffness,external,dt):
    """One implicit-midpoint step, using a consistent unilateral active set."""
    inverse=1/(2*mass/dt+damping+dt*stiffness/2)
    rhs=2*mass*velocity/dt+external-stiffness*position
    mid_velocity=inverse*rhs
    gap=float(contact_vector@position)
    if gap+dt/2*float(contact_vector@mid_velocity)>0:
        base=inverse*(rhs-contact_stiffness*contact_vector*gap)
        direction=inverse*contact_vector
        weight=dt*contact_stiffness/2
        mid_velocity=base-direction*(weight*float(contact_vector@base)/(1+weight*float(contact_vector@direction)))
    return position+dt*mid_velocity,2*mid_velocity-velocity,float(dt*np.sum(damping*mid_velocity**2))


def simulate_drop(parameters,progress=None):
    p=validate_impact_parameters(parameters);modes,omega,modal_mass,coupling=plate_modes(p)
    mass=np.r_[p['impact_mass_kg'],modal_mass];stiffness=np.r_[0.,modal_mass*omega**2]
    damping=np.r_[0.,2*p['impact_damping_ratio']*modal_mass*omega]
    contact=np.r_[1.,-coupling];external=np.r_[mass[0]*GRAVITY,np.zeros(len(modes))]
    frequency_bound=math.sqrt(float(omega.max()**2+p['impact_contact_N_m']*np.sum(contact**2/mass)))
    target_step=min(p['impact_step_s'],.1/frequency_bound)
    steps=math.ceil(p['impact_duration_s']/target_step)
    if steps>300000:raise ValueError('Drop-test integration exceeds 300000 steps; shorten duration or reduce mode count')
    dt=p['impact_duration_s']/steps
    position=np.zeros(len(mass));velocity=np.zeros(len(mass));velocity[0]=math.sqrt(2*GRAVITY*p['impact_drop_height_m'])
    initial=float(.5*mass[0]*velocity[0]**2);dissipated=0.;error=0.;peak_force=0.;peak_response=0.;bound=0.;closure=0.
    sample_indices=set(np.linspace(0,steps,min(1001,steps+1),dtype=int));records=[];coordinates=[]
    for step in range(steps+1):
        gap=float(contact@position);force=p['impact_contact_N_m']*max(gap,0.)
        closure=max(closure,max(gap,0.))
        kinetic=float(.5*np.sum(mass*velocity**2));elastic=float(.5*np.sum(stiffness*position**2));contact_energy=.5*p['impact_contact_N_m']*max(gap,0.)**2
        potential=-mass[0]*GRAVITY*position[0]
        balance=(kinetic+elastic+contact_energy+potential+dissipated-initial)/initial
        error=max(error,abs(balance));peak_force=max(peak_force,force)
        peak_response=max(peak_response,abs(float(coupling@position[1:])))
        bound=max(bound,float(np.abs(position[1:]).sum()))
        if step in sample_indices:
            records.append([step*dt,position[0],float(coupling@position[1:]),force,kinetic,elastic,contact_energy,dissipated,potential,balance])
            coordinates.append(position[1:].copy())
        if step==steps:break
        position,velocity,loss=midpoint_step(position,velocity,mass,stiffness,damping,contact,p['impact_contact_N_m'],external,dt)
        dissipated+=loss
        if not np.isfinite(position).all() or not np.isfinite(velocity).all():raise ValueError('Nonfinite drop-test integration')
        if progress and step%max(1,steps//10)==0:progress('impact-solving')
    if error>.01:raise ValueError(f'Drop-test energy error {error:.2%} exceeds 1%; reduce the time step')
    if bound>p['impact_thickness_m']*.25:raise ValueError('Response exceeds the conservative small-deflection limit (25% of thickness). Reduce drop height/mass; this elastic plate model is not valid for that case.')
    if closure>p['impact_thickness_m']*.25:raise ValueError('Contact compression exceeds the compliant-interface model scope (25% of plate thickness). Reduce drop energy or use a physically justified contact stiffness; this model cannot represent that response.')
    summary={'analysis':'impact','method':'Modal Kirchhoff–Love plate / unilateral linear contact / implicit midpoint',
        'maximum_contact_force_N':peak_force,'maximum_patch_deflection_m':peak_response,'deflection_bound_over_thickness':bound/p['impact_thickness_m'],
        'initial_energy_J':initial,'maximum_relative_energy_error':error,'dissipated_energy_J':dissipated,
        'maximum_contact_compression_m':closure,
        'first_frequency_Hz':float(omega.min()/(2*np.pi)),'plate_modes':len(modes),'integration_steps':steps,'actual_time_step_s':dt,
        'duration_s':p['impact_duration_s'],'nodes':0,'tetrahedra':0,'limitations':IMPACT_LIMITS,
        'accuracy_note':'Energy balance checks temporal consistency, not spatial/modal convergence or experimental accuracy. Repeat with more modes and smaller time steps.'}
    return np.array(records),np.array(coordinates),modes,summary


def run_impact(directory,parameters,progress=None):
    p=validate_impact_parameters(parameters);directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    if progress:progress('impact-solving')
    history,q,modes,summary=simulate_drop(p,progress)
    if progress:progress('exporting')
    columns=['time_s','drop_weight_displacement_m','plate_patch_deflection_m','contact_force_N','kinetic_J','plate_elastic_J','contact_elastic_J','dissipated_J','gravity_potential_J','relative_energy_error']
    with (directory/'history.csv').open('w',newline='',encoding='utf-8') as file:
        writer=csv.writer(file);writer.writerow(columns);writer.writerows(history)
    np.savez_compressed(directory/'impact.npz',history=history,modal_coordinates=q,mode_numbers=modes,columns=np.array(columns))
    (directory/'manifest.json').write_text(json.dumps({'parameters':{k:v for k,v in p.items() if k.startswith('impact_')},'summary':summary},indent=2,allow_nan=False),encoding='utf-8')
    from opensim.impact_report import write_impact_report
    write_impact_report(directory,p,history,q,modes,summary)
    return summary
