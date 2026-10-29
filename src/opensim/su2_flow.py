"""Native SU2 incompressible finite-volume Navier–Stokes adapter, SI units."""
import csv
import json
import os
from pathlib import Path
import subprocess
import numpy as np
from opensim.cad_flow import port_faces,face_geometry
from opensim.loads import boundary_owners
from opensim import solver as processes


def find_su2():
    selected=os.environ.get('SU2_CFD_EXECUTABLE')
    path=Path(selected) if selected else Path(__file__).resolve().parents[2]/'.tools/su2/v8.5.0/bin/SU2_CFD.exe'
    if not path.is_file():raise FileNotFoundError('SU2 CFD solver is not installed. Run tools/install_su2.py, then reopen the app.')
    return path.resolve()


def boundary_groups(mesh,p):
    axis='xyz'.index(p.get('cfd_flow_axis','x'))
    def select(region,side):
        if region:
            from opensim.regions import selected_faces
            return selected_faces(mesh,region)
        coordinate=mesh.points[:,axis];target=coordinate.min() if side=='min' else coordinate.max()
        tol=np.ptp(mesh.points,axis=0).max()*1e-7
        return [f for f in mesh.boundary_elements() if np.all(abs(mesh.points[f,axis]-target)<tol)]
    inlet=select(p['cfd_inlet_region'],'min');outlet=select(p['cfd_outlet_region'],'max')
    if not inlet or not outlet:raise ValueError('Choose inlet and outlet faces, then save the flow boundaries')
    ins={tuple(sorted(f[:3])) for f in inlet};outs={tuple(sorted(f[:3])) for f in outlet}
    if ins&outs:raise ValueError('Inlet and outlet faces overlap')
    walls=[f for f in mesh.boundary_elements() if tuple(sorted(f[:3])) not in ins|outs]
    return {'inlet':inlet,'outlet':outlet,'wall':walls}


def write_su2_mesh(mesh,path,groups,length=1.):
    lines=['NDIME= 3',f'NELEM= {len(mesh.tetrahedra)}']
    lines += ['10 '+' '.join(map(str,t[:4])) for t in mesh.tetrahedra]
    lines += [f'NPOIN= {len(mesh.points)}']
    lines += [' '.join(f'{x:.16g}' for x in point/length)+f' {i}' for i,point in enumerate(mesh.points)]
    nonempty={key:value for key,value in groups.items() if value}
    lines += [f'NMARK= {len(nonempty)}']
    for name,faces in nonempty.items():
        lines += [f'MARKER_TAG= {name}',f'MARKER_ELEMS= {len(faces)}']
        outward=face_geometry(mesh,faces,boundary_owners(mesh))
        for f,av in zip(faces,outward):
            f=list(f[:3]);point=mesh.points[f]
            if np.cross(point[1]-point[0],point[2]-point[0])@av<0:f[1],f[2]=f[2],f[1]
            lines.append('5 '+' '.join(map(str,f)))
    Path(path).write_text('\n'.join(lines)+'\n',encoding='ascii')


def write_su2_config(path,p,groups):
    velocity=np.zeros(3);velocity['xyz'.index(p.get('cfd_flow_axis','x'))]=1.
    turbulent=p.get('cfd_turbulence','none')=='sa'
    config={
        'SOLVER':'INC_RANS' if turbulent else 'INC_NAVIER_STOKES','KIND_TURB_MODEL':'SA' if turbulent else 'NONE',
        'RESTART_SOL':'NO','INC_NONDIM':'DIMENSIONAL','INC_DENSITY_MODEL':'CONSTANT','INC_ENERGY_EQUATION':'NO',
        'INC_DENSITY_INIT':1.,'INC_VELOCITY_INIT':'('+','.join(map(str,velocity))+')',
        'VISCOSITY_MODEL':'CONSTANT_VISCOSITY','MU_CONSTANT':p['cfd_viscosity_Pa_s']/(p['cfd_density_kg_m3']*p['cfd_speed_m_s']*p.get('_flow_length_m',1.)),
        'INC_INLET_TYPE':'VELOCITY_INLET','MARKER_INLET':'(inlet, 293.15, 1., '+','.join(map(str,velocity))+')',
        'INC_OUTLET_TYPE':'PRESSURE_OUTLET','MARKER_OUTLET':'(outlet,0.0)',
        'MARKER_HEATFLUX':'(wall,0.0)','MARKER_PLOTTING':'(wall)','MARKER_MONITORING':'(wall)',
        'MESH_FILENAME':'mesh.su2','MESH_FORMAT':'SU2','ITER':p.get('cfd_iterations',2000),
        'CFL_NUMBER':5.,'CFL_ADAPT':'NO','NUM_METHOD_GRAD':'WEIGHTED_LEAST_SQUARES',
        'CONV_NUM_METHOD_FLOW':'FDS','MUSCL_FLOW':'YES','SLOPE_LIMITER_FLOW':'VENKATAKRISHNAN',
        'TIME_DISCRE_FLOW':'EULER_IMPLICIT','LINEAR_SOLVER':'FGMRES','LINEAR_SOLVER_PREC':'ILU',
        'LINEAR_SOLVER_ERROR':.01,'LINEAR_SOLVER_ITER':15,'MGLEVEL':0,
        'CONV_FIELD':'(RMS_PRESSURE,RMS_VELOCITY-X,RMS_VELOCITY-Y,RMS_VELOCITY-Z)',
        'CONV_RESIDUAL_MINVAL':p.get('cfd_residual_target',-6),'CONV_STARTITER':100,
        'TABULAR_FORMAT':'CSV','CONV_FILENAME':'history','RESTART_FILENAME':'restart_flow',
        'VOLUME_FILENAME':'flow','SURFACE_FILENAME':'surface_flow',
        'OUTPUT_FILES':'(RESTART_ASCII,PARAVIEW_ASCII)','VOLUME_OUTPUT':'(COORDINATES,SOLUTION,PRIMITIVE)',
        'HISTORY_OUTPUT':'(ITER,RMS_RES)','OUTPUT_WRT_FREQ':p.get('cfd_iterations',2000),
        'SCREEN_OUTPUT':'(INNER_ITER,RMS_PRESSURE,RMS_VELOCITY-X,RMS_VELOCITY-Y,RMS_VELOCITY-Z)',
        'SCREEN_WRT_FREQ_INNER':50,
    }
    if groups.get('farfield'):config['MARKER_FAR']='(farfield)'
    if turbulent:config.update(CONV_NUM_METHOD_TURB='SCALAR_UPWIND',TIME_DISCRE_TURB='EULER_IMPLICIT',MUSCL_TURB='NO')
    Path(path).write_text('\n'.join(f'{k}= {v}' for k,v in config.items())+'\n',encoding='ascii')


def run_su2(directory,timeout=900):
    directory=Path(directory);exe=find_su2()
    with (directory/'solver.log').open('w',encoding='utf-8') as log:
        with processes._process_lock:
            if processes._cancelled.is_set():raise processes.SolverCancelled('CFD stopped')
            process=subprocess.Popen([str(exe),'-t','2','flow.cfg'],cwd=directory,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            processes._active_processes.add(process)
        try:code=process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill();process.wait();raise RuntimeError('CFD exceeded its time limit; inspect the solver log or reduce the mesh')
        finally:
            with processes._process_lock:processes._active_processes.discard(process)
    if code:raise RuntimeError('SU2 failed; inspect solver.log in the job folder')


def read_su2_fields(directory,count):
    path=Path(directory)/'restart_flow.csv'
    if not path.is_file():path=Path(directory)/'restart_flow.dat'
    with path.open(encoding='utf-8') as file:
        reader=csv.DictReader(file,skipinitialspace=True);rows=list(reader)
    columns={k.strip().strip('"'):k for k in reader.fieldnames}
    indices=np.array([int(row[columns['PointID']]) for row in rows])
    if len(indices)!=count or set(indices)!=set(range(count)):raise ValueError('CFD output node IDs do not match its mesh')
    order=np.argsort(indices)
    pressure=np.array([float(row[columns['Pressure']]) for row in rows])[order]
    velocity=np.column_stack([np.array([float(row[columns['Velocity_'+axis]]) for row in rows])[order] for axis in 'xyz'])
    if not np.isfinite(velocity).all() or not np.isfinite(pressure).all():raise ValueError('Nonfinite CFD results')
    return velocity,pressure


def solve_su2(cad,output,p,progress=None):
    from opensim.flow_domain import prepare_flow_mesh,classify_external
    from opensim.flow_results import write_flow_views
    from opensim.results import write_vtk
    from opensim.cfd_parameters import validate_cfd_parameters
    p=validate_cfd_parameters(p);find_su2()
    if p['cfd_speed_m_s']/p['cfd_sound_speed_m_s']>.3:raise ValueError('This incompressible setup requires Mach≤0.3; reduce speed or use a compressible solver')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    if progress:progress('meshing')
    mesh,domain=prepare_flow_mesh(cad,p,output/'mesh.msh')
    groups=classify_external(mesh,boundary_groups(mesh,p),domain)
    length=float(np.ptp(mesh.points,axis=0).max());speed=p['cfd_speed_m_s'];rho=p['cfd_density_kg_m3']
    write_su2_mesh(mesh,output/'mesh.su2',groups,length)
    write_su2_config(output/'flow.cfg',p|{'_flow_length_m':length},groups)
    if progress:progress('cfd-solving')
    run_su2(output)
    velocity,pressure=read_su2_fields(output,len(mesh.points));velocity*=speed;pressure*=rho*speed**2
    with (output/'history.csv').open() as file:
        reader=csv.DictReader(file,skipinitialspace=True);history=[{k.strip().strip('"'):float(v) for k,v in row.items()} for row in reader]
    if not history:raise ValueError('SU2 did not write its convergence history')
    residual=max(v for k,v in history[-1].items() if k.startswith('rms['))
    owners=boundary_owners(mesh)
    flux={key:float(np.sum(velocity[np.array(faces)].mean(1)*face_geometry(mesh,faces,owners))) for key,faces in groups.items() if faces}
    net=sum(flux.values());scale=max(sum(abs(v) for v in flux.values())/2,1e-30);balance=abs(net)/scale
    # A successful process exit alone is not a converged CFD result.
    if residual>p['cfd_residual_target']+.05:raise ValueError(f'CFD did not converge: final log residual {residual:.2f}, target {p["cfd_residual_target"]:g}. Increase iterations or refine/check the fluid mesh. Partial results and solver.log are retained.')
    if balance>.05:raise ValueError(f'CFD boundary flux imbalance {balance:.1%} exceeds 5%. Refine the fluid mesh and inspect convergence; partial data are retained.')
    summary={'analysis':'cfdcad','method':'SU2 8.5.0 incompressible Navier–Stokes / '+('Spalart–Allmaras RANS' if p['cfd_turbulence']=='sa' else 'laminar'),
        'nodes':len(mesh.points),'tetrahedra':len(mesh.tetrahedra),'element_type':'SU2 finite-volume tetrahedra',
        'maximum_speed_m_s':float(np.linalg.norm(velocity,axis=1).max()),'minimum_pressure_Pa':float(pressure.min()),'maximum_pressure_Pa':float(pressure.max()),
        'inlet_flow_m3_s':flux['inlet'],'outlet_flow_m3_s':flux['outlet'],'relative_mass_imbalance':balance,
        'final_log_residual':residual,'iterations':int(history[-1]['Inner_Iter'])+1,'flow_axis':p['cfd_flow_axis'],'domain':domain,
        'Re_reference':rho*speed*domain.get('body_span_m',np.ptp(mesh.points,axis=0).max())/p['cfd_viscosity_Pa_s'],
        'cad_faces':mesh.surface_catalog(),'limitations':'Steady incompressible flow. Convergence and boundary flux checks are necessary, not a mesh-accuracy guarantee. Near-wall resolution and turbulence modeling affect drag. Unsteady or separated flows may not converge to a steady solution.'}
    if progress:progress('exporting')
    np.savez_compressed(output/'flow.npz',points=mesh.points,tetrahedra=mesh.tetrahedra,velocity_m_s=velocity,pressure_Pa=pressure)
    with (output/'data.csv').open('w',newline='') as file:
        writer=csv.writer(file);writer.writerow(['x_m','y_m','z_m','ux_m_s','uy_m_s','uz_m_s','pressure_Pa']);writer.writerows(np.column_stack((mesh.points,velocity,pressure)))
    write_vtk(output/'results.vtk',mesh,velocity,quantity='velocity_m_s')
    with (output/'results.vtk').open('a') as file:file.write('SCALARS pressure_Pa double 1\nLOOKUP_TABLE default\n'+'\n'.join(map(str,pressure))+'\n')
    write_flow_views(output,mesh,velocity,pressure,summary,groups)
    (output/'manifest.json').write_text(json.dumps({'parameters':p,'summary':summary,'internal_units':{'length_m':length,'speed_m_s':speed,'pressure_Pa':rho*speed**2}},indent=2,allow_nan=False),encoding='utf-8')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig=Figure(figsize=(9,4),layout='constrained');FigureCanvasAgg(fig);ax=fig.add_subplot(111)
    for name in ('rms[P]','rms[U]','rms[V]','rms[W]'):ax.plot([h['Inner_Iter'] for h in history],[h[name] for h in history],label=name)
    ax.axhline(p['cfd_residual_target'],ls='--',color='black');ax.set(xlabel='Iteration',ylabel='Normalized residual (log10)',title='CFD convergence');ax.legend();fig.savefig(output/'plot.png',dpi=130)
    import html
    rows=''.join(f'<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>' for k,v in summary.items() if k not in {'cad_faces','domain','limitations'})
    (output/'report.html').write_text(f'<!doctype html><meta charset="utf-8"><style>body{{background:#101923;color:#dce8f4;font:15px Segoe UI;margin:24px}}a{{color:#6fd2ff}}img{{max-width:100%}}td{{border:1px solid #536476;padding:8px}}</style><h1>CFD convergence and exports</h1><p>{summary["limitations"]}</p><img src="plot.png"><p><a href="data.csv">CSV nodal data (SI)</a> · <a href="results.vtk">VTK volume fields</a> · <a href="history.csv">Convergence history</a> · <a href="solver.log">Solver log</a></p><table>{rows}</table>',encoding='utf-8')
    return summary
