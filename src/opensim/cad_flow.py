"""3D incompressible creeping flow on an imported fluid volume.

Symmetric-gradient Stokes equations; stable tetrahedral MINI (P1+bubble/P1)
elements, with exact local elimination of the three bubble velocity DOFs.
No-slip walls, prescribed pressure traction at inlet and outlet. SI exports.
"""
import csv
import json
import warnings
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import spsolve, MatrixRankWarning
from opensim.geometry import import_and_mesh
from opensim.loads import boundary_owners
from opensim.regions import selected_faces
from opensim.results import write_viewer_data, write_vtk


def port_faces(mesh,region,side):
    if region:return selected_faces(mesh,region)
    nodes=set(mesh.end_nodes(side))
    return [f for f in mesh.boundary_elements() if all(n in nodes for n in f)]


def face_geometry(mesh,faces,owners):
    triangles=mesh.points[np.array(faces)[:,:3]]
    av=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])/2
    for i,face in enumerate(faces):
        other=owners.get(tuple(sorted(face[:3])))
        if other is None:raise ValueError('Flow boundary must have one adjacent volume element')
        if av[i]@(mesh.points[other]-triangles[i,0])>0:av[i]*=-1
    return av


def stokes_mesh(mesh,viscosity,density,pressure_drop,inlet_region=None,outlet_region=None):
    if not np.isfinite([viscosity,density,pressure_drop]).all() or min(viscosity,density,pressure_drop)<=0:raise ValueError('Fluid viscosity, density and pressure drop must be finite and positive')
    if mesh.element_type!='C3D4':raise ValueError('CAD flow uses linear tetrahedral geometry with MINI velocity bubbles')
    n=len(mesh.points);ne=len(mesh.tetrahedra)
    if n>7000 or ne>35000:raise ValueError('First CAD-flow stage is limited to 7000 nodes / 35000 tetrahedra; increase flow mesh size')
    inlet=port_faces(mesh,inlet_region,'min');outlet=port_faces(mesh,outlet_region,'max')
    if not inlet or not outlet:raise ValueError('Choose nonempty inlet and outlet surfaces; defaults are X-min and X-max')
    ikeys={tuple(sorted(f[:3])) for f in inlet};okeys={tuple(sorted(f[:3])) for f in outlet}
    if ikeys&okeys:raise ValueError('Flow inlet and outlet must be different faces')
    walls=[f for f in mesh.boundary_elements() if tuple(sorted(f[:3])) not in ikeys|okeys]
    if not walls:raise ValueError('Select ports that leave a nonempty no-slip wall surface')
    wall_nodes=np.unique(walls)
    if not set(np.unique(inlet))-set(wall_nodes) or not set(np.unique(outlet))-set(wall_nodes):
        raise ValueError('Mesh ports need interior nodes that are not on no-slip wall edges; refine the mesh')
    length=float(np.ptp(mesh.points,axis=0).max());x=mesh.points/length
    t=mesh.tetrahedra
    shape=np.concatenate((np.ones((ne,4,1)),x[t]),axis=2)
    det=np.linalg.det(shape);vol=np.abs(det)/6
    if np.any(vol<1e-16):raise ValueError('Degenerate tetrahedron in fluid mesh')
    gradients=np.linalg.inv(shape)[:,1:,:].transpose(0,2,1)
    local=np.zeros((ne,16,16))
    for i in range(4):
        for j in range(4):
            dot=np.einsum('ea,ea->e',gradients[:,i],gradients[:,j])
            block=vol[:,None,None]*(dot[:,None,None]*np.eye(3)+gradients[:,j,:,None]*gradients[:,i,None,:])
            local[:,i*3:i*3+3,j*3:j*3+3]=block
        b=-vol[:,None]*gradients[:,i]/4
        local[:,i*3:i*3+3,12:]=b[:,:,None]
        local[:,12:,i*3:i*3+3]=b[:,None,:]
    gram=np.einsum('eia,eib->eab',gradients,gradients)
    # b=256 λ0λ1λ2λ3; integral(b)=32V/105.
    # integral(grad b tensor grad b)=(65536/15120)V Σ grad λi tensor grad λi.
    bubble=(65536/15120)*vol[:,None,None]*(np.trace(gram,axis1=1,axis2=2)[:,None,None]*np.eye(3)+gram)
    coupling=(32/105)*vol[:,None,None]*gradients.transpose(0,2,1)
    recovery=np.linalg.solve(bubble,coupling)
    local[:,12:,12:]=-np.einsum('eai,eaj->eij',coupling,recovery)
    dofs=np.concatenate(((t[:,:,None]*3+np.arange(3)).reshape(ne,12),3*n+t),axis=1)
    row=np.broadcast_to(dofs[:,:,None],local.shape).ravel();col=np.broadcast_to(dofs[:,None,:],local.shape).ravel()
    matrix=coo_matrix((local.ravel(),(row,col)),shape=(4*n,4*n)).tocsr()
    rhs=np.zeros(4*n);owners=boundary_owners(mesh)
    avin=face_geometry(mesh,inlet,owners);avout=face_geometry(mesh,outlet,owners)
    # Dimensionless inlet pressure 1, outlet 0. Physical values are recovered below.
    for face,av in zip(inlet,avin/length**2):
        for node in face:rhs[3*node:3*node+3]-=av/3
    fixed=(wall_nodes[:,None]*3+np.arange(3)).ravel()
    free=np.setdiff1d(np.arange(4*n),fixed)
    reduced=matrix[free][:,free];f=rhs[free]
    scale=1/np.sqrt(np.maximum(abs(reduced.diagonal()),1e-30))
    with warnings.catch_warnings():
        warnings.simplefilter('error',MatrixRankWarning)
        solution=spsolve(diags(scale)@reduced@diags(scale),scale*f)*scale
    if not np.isfinite(solution).all():raise ValueError('Singular fluid problem: check connected volume, ports and walls')
    residual=float(np.max(abs(reduced@solution-f))/max(np.max(abs(f)),1e-30))
    if residual>1e-7:raise ValueError('CAD-flow linear equation residual exceeds tolerance')
    full=np.zeros(4*n);full[free]=solution
    velocity=full[:3*n].reshape(n,3)*(pressure_drop*length/viscosity)
    pressure=full[3*n:]*pressure_drop
    bubble_velocity=-np.einsum('eai,ei->ea',recovery,full[3*n:][t])*(pressure_drop*length/viscosity)
    centroid_velocity=velocity[t].mean(1)+bubble_velocity
    qin=float(np.sum(velocity[np.array(inlet)].mean(1)*avin));qout=float(np.sum(velocity[np.array(outlet)].mean(1)*avout))
    area=float(np.linalg.norm(avin,axis=1).sum())
    edges={}
    for face in inlet:
        for a,b in ((0,1),(1,2),(2,0)):
            edge=tuple(sorted((face[a],face[b])));edges[edge]=edges.get(edge,0)+1
    perimeter=sum(np.linalg.norm(mesh.points[a]-mesh.points[b]) for (a,b),count in edges.items() if count==1)
    if perimeter<=0:raise ValueError('Inlet must be an open surface patch with a boundary')
    diameter=4*area/perimeter;mean=-qin/area
    # Use peak speed and port hydraulic diameter for a conservative Stokes limit.
    peak=float(max(np.linalg.norm(velocity,axis=1).max(),np.linalg.norm(centroid_velocity,axis=1).max()))
    peak_bound=float(np.max(np.linalg.norm(velocity[t],axis=2).max(axis=1)+np.linalg.norm(bubble_velocity,axis=1)))
    re=density*peak_bound*diameter/viscosity
    balance=abs(qin+qout)/max(abs(qin),abs(qout),1e-30)
    if qin>=0 or qout<=0:raise ValueError('CAD-flow ports did not produce positive through-flow')
    if balance>1e-6:raise ValueError('CAD-flow inlet/outlet fluxes fail mass conservation')
    if re>1:raise ValueError(f'Peak-speed Reynolds number {re:.4g} exceeds the creeping-flow limit Re≤1. Reduce pressure drop or use a future Navier–Stokes backend')
    summary={'analysis':'cfdcad','method':'3D Stokes MINI tetrahedra; symmetric strain; sparse direct solve',
             'nodes':n,'tetrahedra':ne,'element_type':'MINI P1+bubble/P1','Re_peak':re,'Re_definition':'Upper bound from nodal speed plus bubble amplitude, using inlet hydraulic diameter','maximum_speed_m_s':peak,
             'mean_inlet_speed_m_s':mean,'inlet_flow_m3_s':qin,'outlet_flow_m3_s':qout,
             'relative_mass_imbalance':balance,'linear_residual':residual,'inlet_area_m2':area,'hydraulic_diameter_m':diameter,
             'minimum_pressure_Pa':float(pressure.min()),'maximum_pressure_Pa':float(pressure.max()),
             'pressure_drop_Pa':pressure_drop,'viscosity_Pa_s':viscosity,'density_kg_m3':density,
             'cad_faces':mesh.surface_catalog(), 'limitations':'Single connected CAD fluid volume. Steady incompressible creeping flow only (peak Re≤1). No inertia, turbulence, heat transfer or external-domain construction. Pressure values are tractions at ports, not fixed nodal pressures.'}
    return velocity,pressure,bubble_velocity,centroid_velocity,summary


def solve_cad_flow(cad,output,parameters,progress=None):
    from opensim.cfd_parameters import CFD_DEFAULTS,validate_cfd_parameters
    parameters=validate_cfd_parameters(CFD_DEFAULTS|parameters)
    if parameters['cfd_backend']!='stokes' or parameters['cfd_domain_mode']!='fluid':raise ValueError('The creeping-flow solver requires an existing fluid volume. Use SU2 for external enclosures or Navier–Stokes flow.')
    if cad is None or not Path(cad).is_file():raise ValueError('Import a single closed CAD fluid volume first')
    p=parameters;output=Path(output);output.mkdir(parents=True,exist_ok=False)
    if progress:progress('meshing')
    mesh=import_and_mesh(Path(cad),p['cfd_mesh_size_m'],p['cfd_cad_scale'],output/'mesh.msh',order=1)
    if progress:progress('cfd-solving')
    u,pressure,bubble,cell_u,summary=stokes_mesh(mesh,p['cfd_viscosity_Pa_s'],p['cfd_density_kg_m3'],p['cfd_pressure_drop_Pa'],p['cfd_inlet_region'],p['cfd_outlet_region'])
    if progress:progress('exporting')
    np.savez_compressed(output/'flow.npz',points=mesh.points,tetrahedra=mesh.tetrahedra,velocity_m_s=u,pressure_Pa=pressure,bubble_velocity_m_s=bubble,centroid_velocity_m_s=cell_u)
    with (output/'data.csv').open('w',newline='',encoding='utf-8') as file:
        writer=csv.writer(file);writer.writerow(['x_m','y_m','z_m','ux_m_s','uy_m_s','uz_m_s','pressure_Pa']);writer.writerows(np.column_stack((mesh.points,u,pressure)))
    write_vtk(output/'results.vtk',mesh,u,quantity='velocity_m_s')
    with (output/'results.vtk').open('a') as file:file.write('SCALARS pressure_Pa double 1\nLOOKUP_TABLE default\n'+'\n'.join(map(str,pressure))+'\n')
    from opensim.flow_preview import flow_preview_data
    write_viewer_data(output/'results.html',{'points':mesh.points.tolist(),'faces':mesh.boundary_faces(),'face_ids':mesh.boundary_face_ids(),
        'displacement':np.zeros_like(u).tolist(),'velocity_m_s':u.tolist(),'pressure_Pa':pressure.tolist(),'summary':summary,'flow_preview':flow_preview_data(mesh,p)})
    (output/'manifest.json').write_text(json.dumps({'parameters':p,'summary':summary},indent=2,allow_nan=False),encoding='utf-8')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig=Figure(figsize=(9,5),layout='constrained');FigureCanvasAgg(fig);ax=fig.add_subplot(111,projection='3d')
    idx=np.linspace(0,len(cell_u)-1,min(5000,len(cell_u)),dtype=int);centers=mesh.points[mesh.tetrahedra].mean(1)[idx]
    color=ax.scatter(*centers.T,c=np.linalg.norm(cell_u[idx],axis=1),s=4,cmap='viridis');ax.set(xlabel='X (m)',ylabel='Y (m)',zlabel='Z (m)',title='Interior cell-centroid speed (includes MINI bubbles)');fig.colorbar(color,ax=ax,label='Speed (m/s)');fig.savefig(output/'plot.png',dpi=130)
    import html
    labels={'nodes':'Mesh nodes','tetrahedra':'Fluid tetrahedra','Re_peak':'Conservative peak Reynolds number',
        'maximum_speed_m_s':'Maximum sampled speed (m/s)','mean_inlet_speed_m_s':'Mean inlet speed (m/s)',
        'inlet_flow_m3_s':'Inlet volume flux (m³/s, outward sign)','outlet_flow_m3_s':'Outlet flow rate (m³/s)',
        'relative_mass_imbalance':'Relative flow-balance error','linear_residual':'Normalized equation residual',
        'inlet_area_m2':'Inlet area (m²)','hydraulic_diameter_m':'Inlet hydraulic diameter (m)',
        'minimum_pressure_Pa':'Minimum nodal pressure (Pa)','maximum_pressure_Pa':'Maximum nodal pressure (Pa)',
        'pressure_drop_Pa':'Applied pressure drop (Pa)','viscosity_Pa_s':'Dynamic viscosity (Pa·s)','density_kg_m3':'Fluid density (kg/m³)'}
    rows=''.join(f'<tr><td>{html.escape(label)}</td><td>{summary[k]:.7g}</td></tr>' for k,label in labels.items())
    faces=''.join(f'<tr><td>{f["id"]}</td><td>{f["area_m2"]:.6g}</td><td>{f["centroid_m"]}</td></tr>' for f in summary['cad_faces'])
    (output/'report.html').write_text(f'<!doctype html><meta charset="utf-8"><style>body{{background:#101923;color:#dce8f4;font:15px Segoe UI;margin:24px}}a{{color:#6fd2ff}}td{{padding:7px;border:1px solid #536476}}img{{max-width:100%}}</style><h1>CAD fluid-volume flow</h1><p>{summary["limitations"]}</p><p><a href="results.html">Rotate surface velocity / pressure results</a> · <a href="data.csv">Export nodal data</a> · <a href="results.vtk">VTK volume fields</a></p><img src="plot.png"><table>{rows}</table><h2>CAD face IDs / area (m²) / centroid (m)</h2><table>{faces}</table>',encoding='utf-8')
    return summary
