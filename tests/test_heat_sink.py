import time
import numpy as np
import pytest
import gmsh

from opensim.geometry import gmsh_session, import_and_mesh
from opensim.heat_sink import make_heat_sink, HEAT_SINK_PARAMETERS
from opensim.regions import selected_faces
from opensim.workspace import Workspace


def area(mesh,faces):
    p=mesh.points[np.asarray(faces)[:,:3]]
    return np.linalg.norm(np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]),axis=1).sum()/2


def test_heat_sink_geometry_and_thermal_regions(tmp_path):
    cad=tmp_path/'sink.step';make_heat_sink(cad)
    with gmsh_session():
        gmsh.model.occ.importShapes(str(cad));gmsh.model.occ.synchronize()
        volumes=gmsh.model.getEntities(3)
        assert len(volumes)==1
        assert gmsh.model.occ.getMass(*volumes[0])==pytest.approx(60*40*4+6*2*40*20)
    with pytest.raises(FileExistsError):make_heat_sink(cad)
    p=HEAT_SINK_PARAMETERS
    mesh=import_and_mesh(cad,p['mesh_size_m'],p['cad_scale'],tmp_path/'mesh.msh',order=2)
    np.testing.assert_allclose(mesh.points.min(0),[0,0,0],atol=1e-9)
    np.testing.assert_allclose(mesh.points.max(0),[.06,.04,.024],atol=1e-9)
    fixed=selected_faces(mesh,p['thermal_fixed_region'])
    source=selected_faces(mesh,p['thermal_source_region'])
    assert area(mesh,fixed)==pytest.approx(6*.002*.04,rel=1e-7)
    assert area(mesh,source)==pytest.approx(.06*.04,rel=1e-7)
    assert not set(np.asarray(fixed).ravel())&set(np.asarray(source).ravel())


@pytest.mark.integration
def test_heat_sink_example_worker_is_ready_for_thermal_solve(tmp_path):
    from opensim.solver import find_solver
    try:find_solver()
    except FileNotFoundError:pytest.skip('CalculiX unavailable')
    workspace=Workspace(tmp_path)
    original=workspace.create_project('Original project')
    workspace.show_project(original['id'])
    sample=workspace.create_project('Sample heat sink')
    def finish(job):
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            result=workspace.get_job(job['id'])
            if result['status'] not in {'queued','running'}:break
            time.sleep(.05)
        assert result['status']=='completed',result['error']
        return result
    example=finish(workspace.start_job(sample['id'],'example',example='heat_sink'))
    assert example['payload']['study']=='thermal'
    p=workspace.get_project(sample['id'])['parameters']
    assert p['thermal_power_W']==20 and p['cad_scale']==.001
    assert p['thermal_fixed_region']==HEAT_SINK_PARAMETERS['thermal_fixed_region']
    result=finish(workspace.start_job(sample['id'],'thermal'))['result']
    assert result['minimum_temperature_K']==pytest.approx(293.15,abs=1e-4)
    assert 293.15<result['maximum_temperature_K']<323.15
    assert result['applied_heat_W']==pytest.approx(20)
    assert result['fixed_boundary_heat_W']==pytest.approx(-20,rel=2e-6)
    assert result['relative_energy_imbalance']<1e-6
    assert workspace.ui_state()['project_id']==original['id']
    assert workspace.get_project(original['id'])==original
