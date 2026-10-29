import time
from pathlib import Path
import numpy as np
import pytest
from opensim.geometry import gmsh_session,import_and_mesh
from opensim.cfd_parameters import CFD_DEFAULTS
from opensim.flow_domain import prepare_flow_mesh
from opensim.su2_flow import find_su2,solve_su2


def sphere(path,radius=.01):
    import gmsh
    with gmsh_session():
        gmsh.model.add('user_sphere');gmsh.model.occ.addSphere(0,0,0,radius);gmsh.model.occ.synchronize();gmsh.write(str(path))


def test_external_domain_keeps_model_as_solid_void_and_source_unchanged(tmp_path):
    import hashlib
    cad=tmp_path/'my-part.step';sphere(cad,10.);before=hashlib.sha256(cad.read_bytes()).hexdigest()
    p=CFD_DEFAULTS|{'cfd_backend':'su2','cfd_case':'cad','cfd_domain_mode':'external','cfd_cad_scale':.001,'cfd_mesh_size_m':.002}
    mesh,domain=prepare_flow_mesh(cad,p,tmp_path/'fluid.msh')
    centers=mesh.points[mesh.tetrahedra].mean(1)
    assert np.linalg.norm(centers,axis=1).min()>.0095
    assert domain['mode']=='external' and domain['body_span_m']==pytest.approx(.02,rel=.01)
    assert hashlib.sha256(cad.read_bytes()).hexdigest()==before


def test_native_su2_runs_user_geometry_with_finite_inertia_and_real_slices(tmp_path):
    try:find_su2()
    except FileNotFoundError:pytest.skip('Native SU2 unavailable')
    cad=tmp_path/'custom-body.step';sphere(cad)
    p=CFD_DEFAULTS|{'cfd_case':'cad','cfd_backend':'su2','cfd_domain_mode':'external','cfd_cad_scale':1.,
        'cfd_mesh_size_m':.004,'cfd_speed_m_s':1.,'cfd_density_kg_m3':1.,'cfd_viscosity_Pa_s':.001}
    summary=solve_su2(cad,tmp_path/'run',p)
    assert summary['Re_reference']>10 # explicitly exercises flow beyond the old Re<=1 gate
    assert summary['final_log_residual']<=-6
    assert summary['relative_mass_imbalance']<.01
    fields=np.load(tmp_path/'run/flow.npz')
    assert np.isfinite(fields['velocity_m_s']).all() and fields['velocity_m_s'].max()>.5
    assert (tmp_path/'run/slice.html').is_file()
    assert (tmp_path/'run/solver.log').is_file()
    # Same Reynolds number, twice the inlet speed: dimensional velocity doubles
    # and gauge pressure quadruples, rather than leaking normalized solver units.
    scaled=solve_su2(cad,tmp_path/'scaled',p|{'cfd_speed_m_s':2.,'cfd_viscosity_Pa_s':.002})
    doubled=np.load(tmp_path/'scaled/flow.npz')
    np.testing.assert_allclose(doubled['velocity_m_s'],2*fields['velocity_m_s'],rtol=1e-5,atol=1e-7)
    np.testing.assert_allclose(doubled['pressure_Pa'],4*fields['pressure_Pa'],rtol=1e-5,atol=1e-7)
    assert scaled['Re_reference']==pytest.approx(summary['Re_reference'])


def test_cfd_is_current_project_study_without_popup(tmp_path,monkeypatch):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication,QDialog
    from opensim.desktop import SimulatorWindow
    from opensim.workspace import Workspace
    app=QApplication.instance() or QApplication([])
    w=Workspace(tmp_path/'workspace');project=w.create_project('My real CAD project')
    cad=tmp_path/'own-solid.step';sphere(cad);w.import_cad(project['id'],str(cad));w.show_project(project['id'])
    window=SimulatorWindow(w)
    try:
        window.show_cfd()
        assert len(w.list_projects())==1 and w.ui_state()['project_id']==project['id']
        assert w.ui_state()['study']=='cfd' and not hasattr(window,'cfd_dialog')
        assert not any(d.isVisible() for d in window.findChildren(QDialog))
        assert not window.fields['cfd_speed_m_s'].isHidden() and window.fields['young_Pa'].isHidden()
        assert window.selectors['cfd_domain_mode'].currentData()=='external'
        window.fields['cfd_speed_m_s'].setValue(1)
        window.fields['cfd_density_kg_m3'].setValue(1)
        window.fields['cfd_viscosity_Pa_s'].setValue(.001)
        window.fields['cfd_mesh_size_m'].setValue(4)
        window.save_parameters()
        assert w.get_project(project['id'])['parameters']['cfd_mesh_size_m']==.004
        assert w.get_project(project['id'])['cad']==str(w.get_project(project['id'])['cad'])
        window.mesh()
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            job=w.list_jobs(project['id'])[0]
            if job['status'] not in {'queued','running'}:break
            app.processEvents();time.sleep(.05)
        assert job['status']=='completed',job['error']
        assert w.current_artifact(project['id'],'geometry').name=='preview-body.html'
        assert w.current_artifact(project['id'],'mesh').name=='preview.html'
    finally:
        window.close();window.view.setPage(None);window.deleteLater();app.processEvents()


def test_flow_geometry_edits_clear_stale_ports_without_changing_structural_regions(tmp_path):
    from opensim.workspace import Workspace
    w=Workspace(tmp_path/'workspace');pid=w.create_project('Ports')['id']
    region={'faces':[1]}
    w.set_parameters(pid,{'support_region':region,'cfd_inlet_region':region,'cfd_outlet_region':{'faces':[2]}})
    w.set_parameters(pid,{'cfd_speed_m_s':20.})
    assert w.get_project(pid)['parameters']['cfd_inlet_region']==region
    w.set_parameters(pid,{'cfd_padding':4.})
    p=w.get_project(pid)['parameters']
    assert p['cfd_inlet_region']==p['cfd_outlet_region']=={}
    assert p['support_region']==region


def test_slice_crop_interpolates_fields_at_exact_boundary():
    from opensim.flow_results import clip_polygon
    values=[(np.array([x,y,0.]),np.array([2*x,0.,0.]),3*x) for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    clipped=clip_polygon(values,0,.25,True)
    assert len(clipped)==4
    for point,velocity,pressure in clipped:
        assert point[0]>=.25
        assert velocity[0]==pytest.approx(2*point[0])
        assert pressure==pytest.approx(3*point[0])
