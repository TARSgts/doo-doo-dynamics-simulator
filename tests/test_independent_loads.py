import numpy as np
import pytest
from opensim.geometry import make_box,import_and_mesh
from opensim.load_cases import assemble_load_cases,validate_load_cases,preview_markers
from opensim.cli import solve

FORCE={'name':'End force','kind':'force','components_N':[2.,3.,0.],'surface':'x-max','region':{}}
PRESSURE={'name':'Top pressure','kind':'pressure','pressure_Pa':1000.,'surface':'z-max','region':{}}


def test_independent_regions_components_pressure_area_and_previews(tmp_path):
    cad=tmp_path/'bar.step';make_box(cad,(.1,.02,.02));mesh=import_and_mesh(cad,.01,1.,tmp_path/'mesh.msh',order=2)
    load=assemble_load_cases(mesh,[FORCE,PRESSURE])
    np.testing.assert_allclose(load.forces.sum(0),[2,3,-2],atol=1e-10)
    np.testing.assert_allclose(load.parts[0][1].centroid,[.1,.01,.01],atol=1e-10)
    np.testing.assert_allclose(load.parts[1][1].centroid,[.05,.01,.02],atol=1e-10)
    markers=preview_markers(mesh,load)
    assert {m['load_index'] for m in markers}=={0,1}
    np.testing.assert_allclose(markers[0]['direction'],np.array([2,3,0])/np.sqrt(13))
    np.testing.assert_allclose(next(m['direction'] for m in markers if m['load_index']==1),[0,0,-1])
    assert len({m['color'] for m in markers})==2
    assert any('Pa' in m['label'] for m in markers)


def test_multi_load_superposition_and_force_moment_balance(tmp_path):
    from opensim.solver import find_solver
    try:find_solver()
    except FileNotFoundError:pytest.skip('CalculiX unavailable')
    cad=tmp_path/'bar.step';make_box(cad,(.1,.02,.02))
    fields=[]
    for name,cases in [('force',[FORCE]),('pressure',[PRESSURE]),('both',[FORCE,PRESSURE])]:
        result=solve(cad,tmp_path/name,size=.01,order=2,load_cases=cases)
        assert result['relative_force_imbalance']<1e-4
        assert result['relative_moment_imbalance']<1e-4
        fields.append(np.load(tmp_path/name/'fields.npz')['displacement'])
    np.testing.assert_allclose(fields[2],fields[0]+fields[1],rtol=2e-4,atol=1e-12)


@pytest.mark.parametrize('cases',[[{'kind':'force','components_N':[0,0,0]}],[{'kind':'force','components_N':[1,2]}],
    [{'kind':'pressure','pressure_Pa':float('nan')}],[{'kind':'pressure','pressure_Pa':1,'region':{'faces':[-1]}}],
    [{'kind':'force','components_N':[1,0,0],'enabled':False}]])
def test_invalid_load_lists(cases):
    with pytest.raises(ValueError):validate_load_cases(cases)


def test_workspace_worker_uses_all_independent_loads(tmp_path):
    import time
    from opensim.workspace import Workspace
    from opensim.solver import find_solver
    try:find_solver()
    except FileNotFoundError:pytest.skip('CalculiX unavailable')
    cad=tmp_path/'bar.step';make_box(cad,(.1,.02,.02))
    w=Workspace(tmp_path/'workspace');project=w.create_project('Independent worker loads');w.import_cad(project['id'],str(cad))
    w.set_parameters(project['id'],{'mesh_size_m':.01,'element_order':2,'load_N':0,'load_cases':[FORCE,PRESSURE]})
    job=w.start_job(project['id'],'solve');deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        result=w.get_job(job['id'])
        if result['status'] not in {'queued','running'}:break
        time.sleep(.05)
    assert result['status']=='completed',result['error']
    np.testing.assert_allclose(result['result']['applied_force_N'],[2,3,-2],atol=1e-9)
    assert result['result']['load_kind']=='multiple'
    w.import_cad(project['id'],str(cad))
    assert w.get_project(project['id'])['parameters']['load_cases']==[]
