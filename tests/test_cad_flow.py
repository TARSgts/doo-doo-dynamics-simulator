import json
import numpy as np
import pytest
from opensim.geometry import make_box,gmsh_session,import_and_mesh
from opensim.cad_flow import stokes_mesh,solve_cad_flow
from opensim.cfd_parameters import CFD_DEFAULTS


def test_stokes_square_duct_refines_and_scales(tmp_path):
    cad=tmp_path/'duct.step';make_box(cad,(.1,.01,.01))
    # Fully developed square duct Q=0.0351443*a^4*dp/(mu*L).
    reference=.0351443*.01**4*.0001/(.001*.1)
    values=[]
    for h in (.003,.002,.0012):
        mesh=import_and_mesh(cad,h,1.,tmp_path/'mesh.msh',order=1)
        u,p,b,c,s=stokes_mesh(mesh,.001,1000.,.0001)
        values.append(s['outlet_flow_m3_s'])
        assert s['relative_mass_imbalance']<1e-8
        assert s['linear_residual']<1e-8
        assert s['Re_peak']<1
        assert np.isfinite(u).all() and np.isfinite(p).all()
    errors=abs(np.array(values)/reference-1)
    assert errors[2]<errors[1]<errors[0]
    assert errors[2]<.06
    doubled=stokes_mesh(mesh,.001,1000.,.0002)[-1]
    assert doubled['outlet_flow_m3_s']==pytest.approx(2*values[-1],rel=1e-8)
    with pytest.raises(ValueError,match='Reynolds'):stokes_mesh(mesh,.001,1000.,1.)


def test_general_cad_elbow_selected_ports_and_exports(tmp_path):
    import gmsh
    cad=tmp_path/'elbow.step'
    with gmsh_session():
        gmsh.model.add('fluid_elbow')
        a=gmsh.model.occ.addBox(0,0,0,.04,.008,.008)
        b=gmsh.model.occ.addBox(.032,0,0,.008,.04,.008)
        gmsh.model.occ.fuse([(3,a)],[(3,b)]);gmsh.model.occ.synchronize();gmsh.write(str(cad))
    inlet={'box_m':[-1e-7,-1e-7,-1e-7,1e-7,.05,.01]}
    outlet={'box_m':[-1e-7,.04-1e-7,-1e-7,.05,.04+1e-7,.01]}
    p=CFD_DEFAULTS|{'cfd_case':'cad','cfd_cad_scale':1.,'cfd_mesh_size_m':.0025,
        'cfd_viscosity_Pa_s':.001,'cfd_density_kg_m3':1000.,'cfd_pressure_drop_Pa':.00001,
        'cfd_inlet_region':inlet,'cfd_outlet_region':outlet}
    summary=solve_cad_flow(cad,tmp_path/'flow',p)
    assert summary['relative_mass_imbalance']<1e-8
    assert summary['outlet_flow_m3_s']>0
    assert summary['analysis']=='cfdcad'
    assert (tmp_path/'flow/results.html').is_file()
    text=(tmp_path/'flow/results.vtk').read_text();assert 'pressure_Pa' in text and 'velocity_m_s' in text
    fields=np.load(tmp_path/'flow/flow.npz');assert np.isfinite(fields['centroid_velocity_m_s']).all()
    assert json.loads((tmp_path/'flow/manifest.json').read_text())['parameters']['cfd_outlet_region']==outlet
    mesh=import_and_mesh(cad,.003,1.,tmp_path/'other.msh',order=1)
    with pytest.raises(ValueError,match='different'):stokes_mesh(mesh,.001,1000.,.00001,inlet,inlet)


def test_stokes_rejects_resource_limit_and_coarse_ports(tmp_path):
    from opensim.geometry import Mesh
    oversized=Mesh(np.zeros((7001,3)),np.array([[0,1,2,3]]))
    with pytest.raises(ValueError,match='limited'):stokes_mesh(oversized,.001,1000.,.0001)
    points=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]],dtype=float)
    mesh=Mesh(points,np.array([[0,1,2,6],[0,2,3,6],[0,3,7,6],[0,7,4,6],[0,4,5,6],[0,5,1,6]]))
    with pytest.raises(ValueError,match='interior nodes'):stokes_mesh(mesh,.001,1000.,.0001)
